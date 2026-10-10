// Update all on this screen (docs/PLUGINS.md): every plugin of a screen with an update goes to the add-on in one request,
// so the screen builds once; one that asks for other rights waits for the person's yes; and what was filled in when a
// plugin was added goes along again, so an update never loses it.
import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import type { Installed, Plugin } from "../src/model/plugins";
import { usePluginsStore } from "../src/stores/plugins";
import { state } from "../src/store";
import ScreenPluginsTab from "../src/components/ScreenPluginsTab.vue";
import type { Screen } from "../src/types";
import { useScreenStore } from "../src/stores/screen";
import { useInventoryStore } from "../src/stores/inventory";

const plugin = (id: string, version: string, more: Partial<Plugin> = {}): Plugin => ({
  id, name: { en: id === "bus" ? "Public transport" : "Waste collection" }, summary: { en: "" }, icon: "F00E7", maintainer: "x",
  tessera: true, version, repo: "", license: "MIT", kind: "behaviour", boards: "any", requires: {}, flash_kb: 1,
  permissions: { home_assistant: [], network: [] }, readme: { en: "" }, languages: ["en"], attributes: [], source: "index",
  permission_hash: "same", ...more,
});
const hall = { id: "text.hall_tile_settings", name: "Hall", node: "hall", online: true, board: "guition", firmware: "0.52.0",
  pictures: true, layout: {}, update: { profile: "hall.yaml" } } as unknown as Screen;
const installed = (id: string, version: string, more: Partial<Installed> = {}): Installed =>
  ({ id, version, source: "index", consent: "same", state: "active", ...more });

let calls: { path: string; body: any }[] = [];
let plugins: ReturnType<typeof usePluginsStore>;
beforeEach(() => {
  calls = [];
  plugins = usePluginsStore();
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const path = String(url);
    if (init?.method === "POST") calls.push({ path, body: JSON.parse(String(init.body)) });
    const payload = path.includes("api/plugins") ? { plugins: plugins.index, installed: plugins.installed, secrets: {}, building: {}, folders: { path: "", errors: {} } }
      : { written: true, built: true, queued: 0 };
    return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
  }));
  useInventoryStore().inventory.screens = [hall];
  useScreenStore().selected = hall.id;
  plugins.loaded = true;
  useInventoryStore().inventory.builds = {};
  plugins.index = [
    plugin("bus", "1.2.0"),
    plugin("waste", "1.0.2", { inputs: [{ id: "calendar", kind: "entity", scope: "screen", label: { en: "Calendar" }, domains: ["calendar"] }] }),
  ];
  plugins.installed = { [hall.id]: [installed("bus", "1.1.0"), installed("waste", "1.0.1", { values: { calendar: "calendar.bins" } })] };
});
afterEach(() => vi.unstubAllGlobals());

describe("update all on this screen", () => {
  it("finds every plugin of the screen with an update, and no test", () => {
    expect(plugins.updatesOn(hall).map((p) => p.id)).toEqual(["bus", "waste"]);
    plugins.installed[hall.id][0] = installed("bus", "main", { source: "branch" });
    expect(plugins.hasUpdate(hall, plugins.index[0])).toBe(false);
    expect(plugins.updatesOn(hall).map((p) => p.id)).toEqual(["waste"]);
  });

  it("sends every update in one request, with what was filled in when the plugin was added", async () => {
    const view = mount(ScreenPluginsTab);
    await nextTick();
    const button = view.get("#screen-plugin-update-all");
    expect(view.get("#screen-plugin-updates").text()).toContain("Public transport, Waste collection");
    await button.trigger("click");
    await vi.waitFor(() => expect(calls.length).toBe(1));
    expect(calls[0].path).toContain("screens/text.hall_tile_settings/plugins");
    expect(calls[0].body.add.map((a: any) => a.id)).toEqual(["bus", "waste"]);
    expect(calls[0].body.add[1].values).toEqual({ calendar: "calendar.bins" });
  });

  it("waits for one yes when an update asks for other rights", async () => {
    plugins.index[1] = { ...plugins.index[1], permission_hash: "more" };
    const view = mount(ScreenPluginsTab);
    await nextTick();
    expect(view.get("#screen-plugin-consent").text()).toContain("Waste collection");
    expect((view.get("#screen-plugin-update-all").element as HTMLButtonElement).disabled).toBe(true);
    await view.get("#screen-plugin-consent input").setValue(true);
    expect((view.get("#screen-plugin-update-all").element as HTMLButtonElement).disabled).toBe(false);
    await view.get("#screen-plugin-update-all").trigger("click");
    await vi.waitFor(() => expect(calls.length).toBe(1));
    expect(calls[0].body.add.find((a: any) => a.id === "waste").consent).toBe(true);
  });
});
