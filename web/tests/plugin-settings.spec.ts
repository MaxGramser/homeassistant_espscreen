// Board and plugin settings follow Home Assistant's pushed values, including changes made on the physical panel.
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import PluginSettings from "../src/components/PluginSettings.vue";
import { usePluginsStore } from "../src/stores/plugins";
import { useUiStore } from "../src/stores/ui";
import type { Screen } from "../src/types";
import { useFakeClock } from "./helpers/clock";
import { failure, fakeApi } from "./helpers/fake-api";
import { lastStream, setHidden } from "./helpers/browser";
import { useScreenStore } from "../src/stores/screen";
import { useInventoryStore } from "../src/stores/inventory";

const hall = { id: "hall", name: "Hall", node: "hall", online: true, board: "guition", firmware: "0.52.0", layout: {}, update: { profile: "hall.yaml" } } as unknown as Screen;
let status = "Listening", enabled = true;
beforeEach(() => { status = "Listening"; enabled = true; });
const rows = () => [
  { key: "test", entity: "button.hall_voice_test", kind: "button", label: { en: "Test" }, available: true, status },
  { key: "microphone", entity: "switch.hall_microphone", kind: "switch", label: { en: "Microphone" }, available: true, value: enabled },
  { key: "volume", entity: "number.hall_voice_volume", kind: "number", label: { en: "Volume" }, available: true, value: 5, min: 0, max: 10, step: 1 },
];
const groups = () => [{ plugin: "voice", name: { en: "Voice" }, rows: rows() }];

async function open(extras = false) {
  useInventoryStore().inventory = { screens: [hall], entities: [] } as any;
  useScreenStore().selected = hall.id;
  usePluginsStore().installed = { hall: [{ id: "voice", version: "1.0.0", source: "index" }] };
  const route = `screens/:id/${extras ? "extras" : "plugins/settings"}`;
  const snapshot = () => extras ? rows() : groups();
  const api = fakeApi({ [`GET ${route}`]: snapshot, [`POST ${route}`]: {} });
  const view = mount(PluginSettings, { props: extras ? { extras: true } : { plugin: "voice" } });
  await flushPromises();
  const stream = lastStream()!;
  stream.open();
  stream.send(snapshot());
  await flushPromises();
  return { api, view, stream, route, snapshot };
}

describe("settings pushed by Home Assistant", () => {
  it.each([false, true])("follows panel changes without navigation or polling (Extras: %s)", async (extras) => {
    const clock = useFakeClock();
    const { api, view, stream, snapshot } = await open(extras);
    expect(view.get('[role="switch"]').attributes("aria-checked")).toBe("true");
    enabled = false;
    stream.send(snapshot());
    await flushPromises();
    expect(view.get('[role="switch"]').attributes("aria-checked")).toBe("false");
    await clock.tick(60000);
    expect(api.calls).toHaveLength(0);
    expect(clock.timers()).toBe(0);
  });

  it("follows a test button's status from events without a polling ladder", async () => {
    const clock = useFakeClock();
    const { api, view, stream, route } = await open();
    await view.get(".setting-action button").trigger("click");
    await flushPromises();
    expect(api.asked(`POST ${route}`)[0].body).toEqual({ entity: "button.hall_voice_test", value: true });
    status = "Heard";
    stream.send(groups());
    await flushPromises();
    expect(view.get(".s-status").text()).toBe("Heard");
    await clock.tick(60000);
    expect(api.count(`GET ${route}`)).toBe(0);
    expect(clock.timers()).toBe(0);
  });

  it("closes in a hidden tab, resubscribes when shown, and ignores a closed view's events", async () => {
    const { view, stream } = await open(true);
    setHidden(true);
    await flushPromises();
    expect(stream.readyState).toBe(stream.CLOSED);
    setHidden(false);
    await flushPromises();
    const resumed = lastStream()!;
    expect(resumed).not.toBe(stream);
    enabled = false;
    resumed.send(rows());
    await flushPromises();
    enabled = true;
    stream.send(rows());
    await flushPromises();
    expect(view.get('[role="switch"]').attributes("aria-checked")).toBe("false");
    view.unmount();
    expect(resumed.readyState).toBe(resumed.CLOSED);
  });

  it("disables stale controls on disconnect and accepts the reconnect snapshot", async () => {
    const { view, stream } = await open(true);
    stream.fail();
    await flushPromises();
    expect((view.get('[role="switch"]').element as HTMLButtonElement).disabled).toBe(true);
    enabled = false;
    stream.open();
    stream.send(rows());
    await flushPromises();
    expect((view.get('[role="switch"]').element as HTMLButtonElement).disabled).toBe(false);
    expect(view.get('[role="switch"]').attributes("aria-checked")).toBe("false");
  });

  it("replaces optimistic values with reported results, and reads once when an action is refused", async () => {
    const { api, view, stream, route } = await open(true);
    await view.get('[role="switch"]').trigger("click");
    expect(api.asked(`POST ${route}`)[0].body).toEqual({ entity: "switch.hall_microphone", value: false });
    expect(view.get('[role="switch"]').attributes("aria-checked")).toBe("false");
    enabled = false;
    stream.send(rows());
    await flushPromises();
    api.on(`POST ${route}`, failure(400, "Home Assistant refused it"));
    await view.get('[role="switch"]').trigger("click");
    await flushPromises();
    expect(useUiStore().notice?.message).toBe("Home Assistant refused it");
    expect(view.get('[role="switch"]').attributes("aria-checked")).toBe("false");
    expect(api.count(`GET ${route}`)).toBe(1);
  });

  it("keeps late events from the previous panel out of the new panel", async () => {
    const { view, stream } = await open(true);
    useInventoryStore().inventory.screens.push({ ...hall, id: "kitchen", name: "Kitchen" });
    useScreenStore().selected = "kitchen";
    await flushPromises();
    const current = lastStream()!;
    expect(current.url).toContain("screens/kitchen/extras/events");
    expect(stream.readyState).toBe(stream.CLOSED);
    enabled = false;
    current.send(rows());
    await flushPromises();
    enabled = true;
    stream.send(rows());
    await flushPromises();
    expect(view.get('[role="switch"]').attributes("aria-checked")).toBe("false");
  });
});
