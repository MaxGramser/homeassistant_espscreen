// Update all on this screen (docs/PLUGINS.md): every plugin of a screen with an update goes to the add-on in one request,
// so the screen builds once; one that asks for other rights waits for the person's yes; and what was filled in when a
// plugin was added goes along again, so an update never loses it.
import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import type { Installed, Plugin } from "../src/model/plugins";
import { usePluginsStore } from "../src/stores/plugins";
import ScreenPluginsTab from "../src/components/ScreenPluginsTab.vue";
import type { Screen } from "../src/types";
import { useScreenStore } from "../src/stores/screen";
import { useInventoryStore } from "../src/stores/inventory";

const plugin = (id: string, version: string, more: Partial<Plugin> = {}): Plugin => ({
  id, name: { en: id === "bus" ? "Public transport" : "Waste collection" }, summary: { en: "" }, icon: "F00E7", maintainer: "x",
  tessera: true, version, repo: "", license: "MIT", type: "functions", boards: "any", requires: {}, flash_kb: 1,
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
    const card = view.get("#screen-plugin-updates");
    expect(card.text()).toContain("2 updates for Hall");
    expect(card.findAll("[data-update]").map((row) => row.attributes("data-update"))).toEqual(["bus", "waste"]);
    expect(card.text()).toContain("1.1.0 → 1.2.0");
    await button.trigger("click");
    await vi.waitFor(() => expect(calls.length).toBe(1));
    // One request: the add-on builds the plugins with the firmware's update when there is one (update-everything).
    expect(calls[0].path).toContain("screens/text.hall_tile_settings/update-everything");
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

describe("a plugin that did not build", () => {
  it("is said first in the screen's Plugins tab, with its kept log to download and the way to try again", async () => {
    plugins.installed[hall.id][0] = installed("bus", "1.1.0", { failed_update: { version: "1.2.0", reason: "interrupted", log: "20261123-071500-hall" } });
    expect(plugins.failuresOn(hall).map((f) => [f.plugin.id, f.kind, f.version])).toEqual([["bus", "update", "1.2.0"]]);
    expect(plugins.statusOn(plugins.index[0], hall).label).toBe("Update 1.2.0 failed");
    const view = mount(ScreenPluginsTab);
    await nextTick();
    const box = view.get("#screen-plugin-failures");
    expect(box.text()).toContain("Public transport 1.2.0 did not build on Hall");
    expect(box.text()).toContain("still runs version 1.1.0");
    expect(box.get("a[data-action=log]").attributes("href")).toBe("api/firmware/logs/20261123-071500-hall");
    // A build the app restarted during is no fault of the plugin: nothing to report to its maker.
    expect(box.find("a[data-action=issue]").exists()).toBe(false);
    await box.get("button[data-action=retry]").trigger("click");
    await vi.waitFor(() => expect(calls.length).toBe(1));
    expect(calls[0].body.add.map((a: any) => a.id)).toEqual(["bus"]);
  });

  it("names a new plugin that stayed out, and says when no log was kept", async () => {
    plugins.installed[hall.id][1] = installed("waste", "1.0.2", { state: "failed", reason: "compile failed" });
    const view = mount(ScreenPluginsTab);
    await nextTick();
    const box = view.get("#screen-plugin-failures");
    expect(box.text()).toContain("Waste collection did not build on Hall");
    expect(box.text()).toContain("compile failed");
    expect(box.find("a[data-action=log]").exists()).toBe(false);
    expect(box.text()).toContain("No log was kept");
  });

  it("offers a filled-in issue at the maker's repository for a build that stopped on the plugin", async () => {
    plugins.index[0] = { ...plugins.index[0], repo: "https://github.com/someone/tessera-bus/tree/abc/plugin", maintainer: "Someone" };
    plugins.installed[hall.id][0] = installed("bus", "1.1.0", { failed_update: { version: "1.2.0", reason: "hall.yaml: bus.h:3:1: error: oops in Hall\nmore", log: "k" } });
    const view = mount(ScreenPluginsTab);
    await nextTick();
    const link = view.get("#screen-plugin-failures a[data-action=issue]");
    expect(link.text()).toContain("Report to Someone");
    const url = new URL(link.attributes("href")!);
    expect(url.origin + url.pathname).toBe("https://github.com/someone/tessera-bus/issues/new");
    expect(url.searchParams.get("title")).toBe("Public transport 1.2.0 did not build on guition");
    const body = url.searchParams.get("body")!;
    expect(body).toContain("bus 1.2.0 (update from 1.1.0)");
    expect(body).toContain("bus.h:3:1: error: oops");
    expect(body).toContain("0.52.0");
    expect(body).not.toContain("Hall");
    expect(body).not.toContain("hall.yaml");
    expect(body).toContain("<screen>: bus.h:3:1: error: oops in <screen>");
  });
});
