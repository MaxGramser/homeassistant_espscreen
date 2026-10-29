// Plugins are at one's own risk: a screen's Plugins tab says so before anything is picked, the tray says it again beside
// Install, and names the screen once it would run four plugins or more after the build.
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Installed, Plugin } from "../src/model/plugins";
import { usePluginsStore } from "../src/stores/plugins";
import ScreenPluginsTab from "../src/components/ScreenPluginsTab.vue";
import type { Screen } from "../src/types";
import { useScreenStore } from "../src/stores/screen";
import { useInventoryStore } from "../src/stores/inventory";

const plugin = (id: string): Plugin => ({
  id, name: { en: id[0].toUpperCase() + id.slice(1) }, summary: { en: "" }, icon: "F00E7", maintainer: "x", tessera: true,
  version: "1.0.0", repo: "", license: "MIT", type: "functions", boards: "any", requires: {}, flash_kb: 1,
  permissions: { home_assistant: [], network: [] }, readme: { en: "" }, languages: ["en"], attributes: [], source: "index",
});
const hall = { id: "text.hall_tile_settings", name: "Hall", node: "hall", online: true, board: "guition", firmware: "0.52.0",
  pictures: true, layout: {}, update: { profile: "hall.yaml" } } as unknown as Screen;
const installed = (id: string): Installed => ({ id, version: "1.0.0", source: "index", state: "active" });

let plugins: ReturnType<typeof usePluginsStore>;
beforeEach(() => {
  plugins = usePluginsStore();
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const path = String(url);
    const body = init?.body ? JSON.parse(String(init.body)) : {};
    const payload = path.includes("plugins/plan")
      ? { error: null, add: (body.add || []).map((step: any) => ({ id: step.id, source: "index", auto: false, for: [], flash_kb: 1, permission_hash: "" })) }
      : { plugins: plugins.index, installed: plugins.installed, secrets: {}, building: {}, folders: { path: "", errors: {} } };
    return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
  }));
  useInventoryStore().inventory.screens = [hall];
  useInventoryStore().inventory.builds = {};
  useScreenStore().selected = hall.id;
  plugins.loaded = true;
  plugins.index = ["voice", "proxy", "camera", "bus", "waste"].map(plugin);
  plugins.installed = { [hall.id]: [installed("voice"), installed("proxy")] };
  plugins.tray.items = [];
});
afterEach(() => vi.unstubAllGlobals());

describe("plugins at one's own risk", () => {
  it("is said on a screen's Plugins tab, and beside Install once something is set aside", async () => {
    const view = mount(ScreenPluginsTab);
    await flushPromises();
    expect(view.get("#screen-plugin-risk").text()).toContain("Plugins are at your own risk");
    expect(view.find("#plugin-tray-risk").exists()).toBe(false);
    plugins.setAside(hall, plugins.index[2]);
    await flushPromises();
    expect(view.get("#plugin-tray-risk").text()).toContain("At your own risk");
    // Three plugins after the build: no count yet.
    expect(view.find(".pt-many").exists()).toBe(false);
  });

  it("names the screen once it would run four plugins or more", async () => {
    const view = mount(ScreenPluginsTab);
    await flushPromises();
    plugins.setAside(hall, plugins.index[2]);
    plugins.setAside(hall, plugins.index[3]);
    await flushPromises();
    expect(view.get(".pt-many").text()).toBe("Hall runs 4 plugins after this build. That many can make a screen unstable: if it acts up, take some off.");
  });
});
