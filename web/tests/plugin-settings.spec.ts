// A plugin's live settings (PluginSettings): a button's status changes on the screen after the press, so its rows are read
// again 1, 2.5, 5, 9 and 15 seconds after it, a new press starting the ladder over, and nothing more once the details close.
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import PluginSettings from "../src/components/PluginSettings.vue";
import { state } from "../src/store";
import { usePluginsStore } from "../src/stores/plugins";
import { useUiStore } from "../src/stores/ui";
import type { Screen } from "../src/types";
import { useFakeClock } from "./helpers/clock";
import { failure, fakeApi } from "./helpers/fake-api";
import { useScreenStore } from "../src/stores/screen";
import { useInventoryStore } from "../src/stores/inventory";

const hall = { id: "hall", name: "Hall", node: "hall", online: true, board: "guition", firmware: "0.52.0", layout: {}, update: { profile: "hall.yaml" } } as unknown as Screen;
let status = "Listening";
beforeEach(() => { status = "Listening"; });
const groups = () => [{ plugin: "voice", name: { en: "Voice" }, rows: [
  { key: "test", entity: "button.hall_voice_test", kind: "button", label: { en: "Test" }, available: true, status },
  { key: "volume", entity: "number.hall_voice_volume", kind: "number", label: { en: "Volume" }, available: true, value: 5, min: 0, max: 10, step: 1 },
] }];

async function open() {
  useInventoryStore().inventory = { screens: [hall], entities: [] } as any;
  useScreenStore().selected = hall.id;
  usePluginsStore().installed = { hall: [{ id: "voice", version: "1.0.0", source: "index" }] };
  const api = fakeApi({ "GET screens/:id/plugins/settings": () => groups(), "POST screens/:id/plugins/settings": {} });
  const view = mount(PluginSettings, { props: { plugin: "voice" } });
  await flushPromises();
  return { api, view, reads: () => api.count("GET screens/:id/plugins/settings") };
}

describe("a plugin's button", () => {
  it("is read again 1, 2.5, 5, 9 and 15 seconds after it is pressed, and its status follows", async () => {
    const clock = useFakeClock();
    const { api, view, reads } = await open();
    expect(view.get(".s-status").text()).toBe("Listening");
    expect(reads()).toBe(1);
    await view.get(".setting-action button").trigger("click");
    await clock.settle();
    expect(api.asked("POST screens/:id/plugins/settings")[0].body).toEqual({ entity: "button.hall_voice_test", value: true });
    status = "Heard";
    const seen: number[] = [];
    let at = 0;
    for (const next of [1000, 2500, 5000, 9000, 15000, 30000]) {
      await clock.tick(next - at);
      at = next;
      seen.push(reads());
    }
    expect(seen).toEqual([2, 3, 4, 5, 6, 6]);
    expect(view.get(".s-status").text()).toBe("Heard");
  });

  it("starts the ladder over with a new press, and stops it when the details close", async () => {
    const clock = useFakeClock();
    const { view, reads } = await open();
    await view.get(".setting-action button").trigger("click");
    await clock.tick(2500);
    expect(reads()).toBe(3);
    await view.get(".setting-action button").trigger("click");
    // The ladder starts again from the second press: 1 second after it, then 2.5.
    await clock.tick(999);
    expect(reads()).toBe(3);
    await clock.tick(1);
    expect(reads()).toBe(4);
    await clock.tick(1500);
    expect(reads()).toBe(5);
    view.unmount();
    await clock.tick(60000);
    expect(reads()).toBe(5);
  });

  it("reads the rows again at once when a change is refused, and asks no ladder for anything but a button", async () => {
    const clock = useFakeClock();
    const { api, view, reads } = await open();
    api.on("POST screens/:id/plugins/settings", failure(400, "Home Assistant refused it"));
    await view.findAll(".setting-number button")[1].trigger("click");
    await clock.settle();
    expect(useUiStore().notice?.message).toBe("Home Assistant refused it");
    expect(reads()).toBe(2);
    await clock.tick(60000);
    expect(reads()).toBe(2);
  });
});
