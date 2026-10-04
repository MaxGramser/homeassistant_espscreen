import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { getJson, send } from "../src/api";
import VoiceSettings from "../src/components/VoiceSettings.vue";

vi.mock("../src/api", () => ({ getJson: vi.fn(), send: vi.fn() }));
vi.mock("../src/components/VoiceDeviceSettings.vue", () => ({ default: { template: '<div />' } }));
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getJson).mockResolvedValue({ enabled: true, configured: false, saved_key: false, source: "" });
});
afterEach(() => vi.restoreAllMocks());

it("saves the reply speaker and volume independently of Spotify and provider credentials", async () => {
  const status = { enabled: true, configured: true, provider: 'openai', reply_speaker: '', reply_volume: 30,
    reply_speakers: [{ id: 'media_player.reply', name: 'Reply speaker', available: true }] };
  vi.mocked(getJson).mockResolvedValue(status);
  const wrapper = mount(VoiceSettings); await flushPromises();
  try {
    expect(wrapper.get('#voice-output summary').text()).toContain('Screen / this browser');
    await wrapper.get('#voice-reply-speaker').setValue('media_player.reply');
    await wrapper.get('#voice-reply-volume').setValue('23');
    vi.mocked(send).mockResolvedValue({ ...status, reply_speaker: 'media_player.reply', reply_volume: 23 });
    await wrapper.get('#voice-output-form').trigger('submit'); await flushPromises();
    expect(send).toHaveBeenCalledExactlyOnceWith('voice-preview/config', 'PUT', { reply_speaker: 'media_player.reply', reply_volume: 23 });
    expect(wrapper.get('#voice-output summary').text()).toContain('Reply speaker');
    expect(wrapper.get('#voice-output-form button').attributes('disabled')).toBeDefined();
  } finally { wrapper.unmount(); }
});

it("keeps Spotify search credentials private and independent of the voice provider", async () => {
  const status = { enabled: true, provider: 'claude', configured: true, saved_key: true, source: 'editor', spotify: { configured: false, market: '' } };
  vi.mocked(getJson).mockResolvedValue(status);
  const storage = vi.spyOn(Storage.prototype, 'setItem');
  const wrapper = mount(VoiceSettings); await flushPromises();
  try {
    const secret = 'spotify-test-secret-not-real';
    expect(wrapper.get('#voice-spotify-secret').attributes('type')).toBe('password');
    expect(wrapper.get('#voice-spotify-secret').attributes('placeholder')).toBe('Enter Client Secret');
    await wrapper.get('#voice-spotify-id').setValue('spotify-test-client-not-real');
    await wrapper.get('#voice-spotify-secret').setValue(secret);
    await wrapper.get('#voice-spotify-market').setValue('nl');
    vi.mocked(send).mockResolvedValue({ ...status, spotify: { configured: true, market: 'NL' } });
    await wrapper.get('#voice-spotify-form').trigger('submit'); await flushPromises();
    expect(send).toHaveBeenCalledWith('voice-preview/spotify', 'PUT', {
      client_id: 'spotify-test-client-not-real', client_secret: secret, market: 'NL',
    });
    expect(wrapper.get<HTMLInputElement>('#voice-spotify-id').element.value).toBe('');
    expect(wrapper.get<HTMLInputElement>('#voice-spotify-secret').element.value).toBe('');
    expect(wrapper.get('#voice-spotify-id').attributes('placeholder')).toBe('Enter replacement Client ID');
    expect(wrapper.get('#voice-spotify-secret').attributes('placeholder')).toBe('Enter replacement Client Secret');
    expect(wrapper.get('#voice-spotify summary').text()).toContain('Saved · NL');
    expect(wrapper.get<HTMLInputElement>('#voice-spotify-market').element.value).toBe('NL');
    expect(storage).not.toHaveBeenCalled();
    expect(wrapper.html()).not.toContain(secret);
    expect(wrapper.text()).toContain('Claude API key');
    await wrapper.get('#voice-spotify-form button[type="button"]').trigger('click'); await flushPromises();
    expect(send).toHaveBeenLastCalledWith('voice-preview/spotify', 'DELETE', undefined);
  } finally { wrapper.unmount(); }
});

it("clears Spotify credentials after a failed save", async () => {
  const wrapper = mount(VoiceSettings); await flushPromises();
  try {
    await wrapper.get('#voice-spotify-id').setValue('spotify-test-client-not-real');
    await wrapper.get('#voice-spotify-secret').setValue('spotify-test-secret-not-real');
    await wrapper.get('#voice-spotify-market').setValue('NL');
    vi.mocked(send).mockRejectedValue(new Error('Stop active voice sessions.'));
    await wrapper.get('#voice-spotify-form').trigger('submit'); await flushPromises();
    expect(wrapper.get<HTMLInputElement>('#voice-spotify-secret').element.value).toBe('');
    expect(wrapper.get('[role="alert"]').text()).toContain('Stop active voice sessions.');
  } finally { wrapper.unmount(); }
});

it("saves the shared inactivity timeout independently of provider credentials", async () => {
  const status = { enabled: true, provider: 'claude', configured: true, saved_key: true, source: 'editor', idle_seconds: 5 };
  vi.mocked(getJson).mockResolvedValue(status);
  const wrapper = mount(VoiceSettings); await flushPromises();
  try {
    expect(wrapper.get('#voice-idle-form button').attributes('disabled')).toBeDefined();
    expect(wrapper.get('#voice-idle-seconds').attributes('min')).toBe('1');
    await wrapper.get('#voice-idle-seconds').setValue('1');
    vi.mocked(send).mockResolvedValue({ ...status, idle_seconds: 1 });
    await wrapper.get('#voice-idle-form').trigger('submit'); await flushPromises();
    expect(send).toHaveBeenCalledWith('voice-preview/config', 'PUT', { idle_seconds: 1 });
    expect(wrapper.get('#voice-idle-form button').attributes('disabled')).toBeDefined();
    expect(wrapper.get<HTMLInputElement>('#voice-api-key').element.value).toBe('');
  } finally { wrapper.unmount(); }
});

it("saves a password once, clears the field and never stores it in browser layouts", async () => {
  const storage = vi.spyOn(Storage.prototype, "setItem");
  const wrapper = mount(VoiceSettings); await flushPromises();
  try {
    const input = wrapper.get<HTMLInputElement>("#voice-api-key");
    expect(input.attributes("type")).toBe("password");
    expect(input.element.value).toBe("");
    const key = "sk-test-not-a-real-key-for-local-tests";
    await input.setValue(key);
    vi.mocked(send).mockResolvedValue({ enabled: true, configured: true, saved_key: true, source: "editor" });
    await wrapper.get("form").trigger("submit"); await flushPromises();
    expect(send).toHaveBeenCalledWith("voice-preview/config", "PUT", { api_key: key });
    expect(input.element.value).toBe("");
    expect(wrapper.text()).toContain("API key configured");
    expect(wrapper.html()).not.toContain(key);
    expect(storage).not.toHaveBeenCalled();
  } finally { wrapper.unmount(); }
});

it("does not fetch a saved secret, and removes only the editor-managed key", async () => {
  vi.mocked(getJson).mockResolvedValue({ enabled: true, configured: true, saved_key: true, source: "editor" });
  const wrapper = mount(VoiceSettings); await flushPromises();
  try {
    expect(wrapper.get<HTMLInputElement>("#voice-api-key").element.value).toBe("");
    vi.mocked(send).mockResolvedValue({ enabled: true, configured: false, saved_key: false, source: "" });
    const remove = wrapper.findAll("button").find(button => button.text() === "Remove saved key")!;
    await remove.trigger("click"); await flushPromises();
    expect(send).toHaveBeenCalledWith("voice-preview/config", "DELETE", undefined);
    expect(wrapper.text()).toContain("No API key configured");
  } finally { wrapper.unmount(); }
});

it("clears the typed key on failure and shows the save error", async () => {
  const wrapper = mount(VoiceSettings); await flushPromises();
  try {
    await wrapper.get("input").setValue("sk-test-not-a-real-key-for-local-tests");
    vi.mocked(send).mockRejectedValue(new Error("Stop active voice sessions before changing the API key."));
    await wrapper.get("form").trigger("submit"); await flushPromises();
    expect(wrapper.get<HTMLInputElement>("input").element.value).toBe("");
    expect(wrapper.get('[role="alert"]').text()).toContain("Stop active voice sessions");
  } finally { wrapper.unmount(); }
});

it("loads and saves a voice independently of the API key", async () => {
  const status = { enabled: true, configured: true, saved_key: true, source: "editor", voice: "marin", voices: ["marin", "cedar"] };
  vi.mocked(getJson).mockResolvedValue(status);
  const wrapper = mount(VoiceSettings); await flushPromises();
  try {
    expect(wrapper.get<HTMLSelectElement>("#voice-choice").element.value).toBe("marin");
    expect(wrapper.get("#voice-choice-form button").attributes("disabled")).toBeDefined();
    await wrapper.get("#voice-choice").setValue("cedar");
    vi.mocked(send).mockResolvedValue({ ...status, voice: "cedar" });
    await wrapper.get("#voice-choice-form").trigger("submit"); await flushPromises();
    expect(send).toHaveBeenCalledWith("voice-preview/config", "PUT", { voice: "cedar" });
    expect(wrapper.get<HTMLInputElement>("#voice-api-key").element.value).toBe("");
    expect(wrapper.text()).toContain("New sessions will use this voice");
  } finally { wrapper.unmount(); }
});

it("shows one settings card with independent Claude credentials and verified HA speech choices", async () => {
  const claude = { enabled: true, provider: "claude", configured: false, key_configured: false, saved_key: false, source: "",
    pipeline: "", voices: [], pipelines: [
      { id: "partial", name: "Incomplete", language: "nl", ready: false, stt_ready: true, tts_ready: false },
      { id: "local", name: "Local", language: "nl", ready: true, stt_ready: true, tts_ready: true },
    ] };
  const wrapper = mount(VoiceSettings); await flushPromises();
  try {
    vi.mocked(send).mockResolvedValue(claude);
    await wrapper.get("#voice-provider").setValue("claude"); await flushPromises();
    expect(send).toHaveBeenCalledWith("voice-preview/config", "PUT", { provider: "claude" });
    expect(wrapper.findAll("#voice-settings")).toHaveLength(1);
    expect(wrapper.text()).toContain("Claude API key");
    expect(wrapper.find("#voice-choice-form").exists()).toBe(false);
    expect(wrapper.get('#voice-pipeline option[value="partial"]').attributes("disabled")).toBeDefined();
    expect(wrapper.get('#voice-pipeline option[value="partial"]').text()).toContain("TTS");
    expect(wrapper.get('#voice-credentials').attributes('open')).toBeDefined();
    expect(wrapper.get('#voice-speech').attributes('open')).toBeDefined();
    await wrapper.get("#voice-api-key").setValue("claude-test-key-not-real");
    await wrapper.get("form").trigger("submit"); await flushPromises();
    expect(send).toHaveBeenCalledWith("voice-preview/config/claude", "PUT", { api_key: "claude-test-key-not-real" });
    expect(wrapper.get<HTMLInputElement>("#voice-api-key").element.value).toBe("");
    await wrapper.get("#voice-pipeline").setValue("local");
    await wrapper.get("#voice-pipeline-form").trigger("submit"); await flushPromises();
    expect(send).toHaveBeenCalledWith("voice-preview/config", "PUT", { pipeline: "local" });
  } finally { wrapper.unmount(); }
});
