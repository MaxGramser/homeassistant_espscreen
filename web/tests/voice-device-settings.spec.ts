import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { getJson, send } from "../src/api";
import VoiceDeviceSettings from "../src/components/VoiceDeviceSettings.vue";

vi.mock("../src/api", () => ({ getJson: vi.fn(), send: vi.fn() }));
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getJson).mockResolvedValue({ url: 'ws://panel-manager.local:8098', screens: [
    { id: 'text_sensor.panel', name: 'Panel', paired: false }, { id: 'text_sensor.second', name: 'Second', paired: false },
  ] });
});
afterEach(() => vi.restoreAllMocks());

it('pairs the selected physical panel and keeps the one-time token out of the page and storage', async () => {
  const wrapper = mount(VoiceDeviceSettings); await flushPromises();
  const storage = vi.spyOn(Storage.prototype, 'setItem');
  try {
    const token = 'test-device-pair-token-not-a-provider-key';
    vi.mocked(send).mockResolvedValue({ url: 'ws://panel-manager.local:8098/voice-devices/a', token });
    await wrapper.get('form').trigger('submit'); await flushPromises();
    expect(send).toHaveBeenCalledExactlyOnceWith('voice-devices/text_sensor.panel/pair', 'POST', { url: 'ws://panel-manager.local:8098' });
    expect(wrapper.get('[role="status"]').text()).toContain('Override YAML');
    expect(wrapper.html()).not.toContain(token);
    expect(storage).not.toHaveBeenCalled();
    await wrapper.get('#voice-device').setValue('text_sensor.second');
    expect(wrapper.find('[role="status"]').exists()).toBe(false);
  } finally { wrapper.unmount(); }
});

it('revokes a pairing without building or changing the provider settings', async () => {
  vi.mocked(getJson).mockResolvedValue({ url: 'ws://panel-manager.local:8098', screens: [
    { id: 'text_sensor.panel', name: 'Panel', paired: true },
  ] });
  const wrapper = mount(VoiceDeviceSettings); await flushPromises();
  try {
    vi.mocked(send).mockResolvedValue({ removed: true });
    await wrapper.get('form button[type="button"]').trigger('click'); await flushPromises();
    expect(send).toHaveBeenCalledExactlyOnceWith('voice-devices/text_sensor.panel', 'DELETE', undefined);
    expect(wrapper.get('form button').text()).toBe('Pair panel');
    expect(wrapper.find('[role="status"]').exists()).toBe(false);
  } finally { wrapper.unmount(); }
});
