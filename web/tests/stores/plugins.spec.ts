// Plugins (stores/plugins.ts): the add-on's plan of a change asked once per request, the tray installed with one build per
// screen, a plugin taken off with what goes with it or switched to another of its id, a plugin's state on one screen and
// over all of them, the tile types and bar items of its index, and what its start follows.
import { flushPromises } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import { i18n } from "../../src/i18n";
import type { Installed, Plugin } from "../../src/model/plugins";
import { state } from "../../src/store";
import { usePluginsStore } from "../../src/stores/plugins";
import { useUiStore } from "../../src/stores/ui";
import type { Screen } from "../../src/types";
import { failure, fakeApi, type ApiRequest } from "../helpers/fake-api";

const plugin = (id: string, more: Partial<Plugin> = {}): Plugin => ({
  id, name: { en: id[0].toUpperCase() + id.slice(1) }, summary: { en: "" }, icon: "F00E7", maintainer: "someone", tessera: true,
  version: "1.0.0", repo: "", license: "MIT", type: "functions", boards: "any", requires: {}, flash_kb: 10,
  permissions: { home_assistant: [], network: [] }, readme: { en: "" }, languages: ["en"], attributes: [], source: "index", ...more,
});
const screen = (id: string, more: Partial<Screen> = {}) =>
  ({ id, name: id[0].toUpperCase() + id.slice(1), node: id, online: true, board: "guition", firmware: "0.52.0", pictures: true, layout: {},
     update: { profile: `${id}.yaml` }, ...more }) as unknown as Screen;
const installed = (id: string, more: Partial<Installed> = {}): Installed => ({ id, version: "1.0.0", source: "index", state: "active", ...more });
const hall = screen("hall"), desk = screen("desk");
const t = (key: string, named: Record<string, unknown> = {}, n?: number) => (n === undefined ? i18n.global.t(key, named) : i18n.global.t(key, named, n));

// The add-on as the store asks it: its plugins, a change's plan (what comes along with `along`), and the change itself.
function addOn(index: Plugin[], have: Record<string, Installed[]> = {}, along: Record<string, string[]> = {}) {
  return fakeApi({
    "GET plugins": () => ({ plugins: index, installed: have, secrets: {}, folders: { path: "", errors: {} } }),
    "POST screens/:id/plugins/plan": (request: ApiRequest) => ({ error: null, add: [
      ...request.body.add.map((step: any) => ({ id: step.id, source: "index", auto: false, for: [], flash_kb: 10, permission_hash: "" })),
      ...(along[request.params.id] || []).map((id) => ({ id, source: "index", auto: true, for: [request.body.add[0].id], flash_kb: 5, permission_hash: "" }))] }),
    "POST screens/:id/plugins": {},
  });
}
async function loaded(index: Plugin[], have: Record<string, Installed[]> = {}, along: Record<string, string[]> = {}) {
  state.inventory = { screens: [hall, desk], entities: [], builds: {} } as any;
  const api = addOn(index, have, along);
  const plugins = usePluginsStore();
  await plugins.reloadPlugins();
  return { api, plugins };
}

describe("a change's plan", () => {
  it("is asked once per screen, plugins and chosen providers, shared while it is on its way, and asked again once the plugins load again", async () => {
    const { api, plugins } = await loaded([plugin("bus"), plugin("voice"), plugin("speaker")]);
    const held = api.defer("POST screens/:id/plugins/plan");
    expect(plugins.planOn(hall, ["voice", "bus"])).toBeNull();
    expect(plugins.planOn(hall, ["bus", "voice"])).toBeNull();
    expect(api.count("POST screens/:id/plugins/plan")).toBe(1);
    held.resolve();
    await flushPromises();
    expect(plugins.planOn(hall, ["voice", "bus"])?.add?.map((step) => step.id)).toEqual(["voice", "bus"]);
    expect(api.count("POST screens/:id/plugins/plan")).toBe(1);
    // Nothing to add or take off asks nothing.
    expect(plugins.planOn(hall, [])).toEqual({ error: null, add: [], remove: [], choose: [], orphans: [] });
    // Another screen, a removal, or another provider chosen is another request.
    plugins.planOn(desk, ["voice", "bus"]);
    plugins.planOn(hall, [], ["bus"]);
    plugins.chooseProvider(hall, "speaker", "speaker");
    plugins.planOn(hall, ["voice", "bus"]);
    await flushPromises();
    expect(api.asked("POST screens/:id/plugins/plan").map((r) => [r.params.id, r.body.add.map((a: any) => a.id), r.body.remove, r.body.providers]))
      .toEqual([["hall", ["voice", "bus"], [], {}], ["desk", ["voice", "bus"], [], {}], ["hall", [], ["bus"], {}], ["hall", ["voice", "bus"], [], { speaker: "speaker" }]]);
    await plugins.reloadPlugins();
    plugins.planOn(hall, ["voice", "bus"]);
    expect(api.count("POST screens/:id/plugins/plan")).toBe(5);
  });

  it("keeps the add-on's refusal as the plan, with its words", async () => {
    const { api, plugins } = await loaded([plugin("bus")]);
    api.on("POST screens/:id/plugins/plan", failure(409, "Needs a speaker"));
    plugins.planOn(hall, ["bus"]);
    await flushPromises();
    expect(plugins.planOn(hall, ["bus"])).toEqual({ error: "Needs a speaker" });
  });
});

describe("the tray", () => {
  it("installs what was set aside with one request per screen, with what comes along, and empties as each screen goes", async () => {
    const { api, plugins } = await loaded([plugin("bus"), plugin("waste"), plugin("clock"), plugin("base")], {}, { hall: ["base"] });
    plugins.setAside(hall, plugins.index[0]);
    plugins.setAside(desk, plugins.index[2]);
    plugins.setAside(hall, plugins.index[1]);
    plugins.setAside(hall, plugins.index[1]);
    expect(plugins.trayGroups.map((g) => [g.screen.id, g.plugins.map((p) => p.id)])).toEqual([["hall", ["bus", "waste"]], ["desk", ["clock"]]]);
    plugins.tray.open = false;
    plugins.toggleSetAside(desk, plugins.index[2]);
    plugins.toggleSetAside(desk, plugins.index[2]);
    expect(plugins.tray.open).toBe(true);
    // The tray asks each group's plan as it shows them; a group is ready once its plan is there.
    expect(plugins.trayGroups.map((group) => plugins.trayReady(group))).toEqual([false, false]);
    await flushPromises();
    expect(plugins.trayGroups.map((group) => plugins.trayReady(group))).toEqual([true, true]);
    expect(plugins.trayAlong(plugins.trayGroups[0]).map((row) => row.plugin.id)).toEqual(["base"]);
    expect(plugins.setAsideKb(hall, [plugins.index[0], plugins.index[1]])).toBe(25);
    const installing = plugins.installTray();
    expect(plugins.tray.sending).toBe(true);
    await installing;
    const changes = api.asked("POST screens/:id/plugins");
    expect(changes.map((r) => [r.params.id, r.body.add.map((a: any) => [a.id, Boolean(a.auto)])])).toEqual([
      ["hall", [["bus", false], ["waste", false], ["base", true]]], ["desk", [["clock", false]]]]);
    expect([plugins.tray.items, plugins.tray.sending]).toEqual([[], false]);
    expect(api.count("GET plugins")).toBe(2);
  });

  it("keeps a screen's plugins in the tray when the add-on refuses them, and says why", async () => {
    const { api, plugins } = await loaded([plugin("bus"), plugin("clock")]);
    plugins.setAside(hall, plugins.index[0]);
    plugins.setAside(desk, plugins.index[1]);
    await flushPromises();
    api.on("POST screens/:id/plugins", failure(400, "No room on this screen"));
    await plugins.installTray();
    expect(api.count("POST screens/:id/plugins")).toBe(1);
    expect(plugins.tray.items.map((item) => item.plugin)).toEqual(["bus", "clock"]);
    expect(useUiStore().notice?.message).toBe("No room on this screen");
    expect(plugins.buildingOn(hall, "bus")).toBe(false);
  });
});

describe("taking a plugin off, and switching to another of its id", () => {
  it("takes what goes with it off each screen that has it, and names all of them", async () => {
    const { api, plugins } = await loaded([plugin("voice"), plugin("wake")],
      { hall: [installed("voice"), installed("wake")], desk: [installed("voice")] });
    await plugins.removePlugin([hall, desk], plugins.index[0], ["wake", "gone"]);
    expect(api.asked("POST screens/:id/plugins").map((r) => [r.params.id, r.body.remove])).toEqual([["hall", ["voice", "wake"]], ["desk", ["voice"]]]);
    expect(useUiStore().notice?.message).toBe(t("editor.plugins.removed", { name: "Voice, Wake", screens: "Hall, Desk" }));
    api.on("POST screens/:id/plugins", failure(500, "Could not write"));
    await plugins.removePlugin([hall, desk], plugins.index[0]);
    expect(api.count("POST screens/:id/plugins")).toBe(3);
    expect(useUiStore().notice?.message).toBe("Could not write");
  });

  it("switches a screen to this plugin, building it meanwhile", async () => {
    const fork = plugin("bus", { origin: "github.com/someone/fork" });
    const { api, plugins } = await loaded([fork], { hall: [installed("bus", { origin: "github.com/a/b" })] });
    expect(plugins.otherOrigin(hall, fork)).toBe(true);
    const held = api.defer("POST screens/:id/plugins");
    const switching = plugins.switchPlugin(hall, fork);
    await nextTick();
    expect(plugins.buildingOn(hall, "bus")).toBe(true);
    held.resolve();
    await switching;
    expect(api.asked("POST screens/:id/plugins")[0].body.add[0]).toMatchObject({ id: "bus", switch: true });
    expect(plugins.buildingOn(hall, "bus")).toBe(false);
    expect(api.count("GET plugins")).toBe(2);
  });
});

describe("a plugin's state", () => {
  it("on one screen: building, queued, failed, an update, a test, installed, or why it does not fit", async () => {
    const { plugins } = await loaded([plugin("bus", { version: "1.1.0" }), plugin("clock"), plugin("big", { requires: { psram: true } })],
      { hall: [installed("bus"), installed("clock", { state: "failed" }), installed("lab", { source: "folder" })] });
    const status = (id: string, on = hall) => plugins.statusOn(plugins.index.find((p) => p.id === id) || plugins.testsOn(on).find((p) => p.id === id)!, on).kind;
    expect([status("bus"), status("clock"), status("lab")]).toEqual(["update", "failed", "test"]);
    expect(status("big", screen("cyd", { pictures: false }))).toBe("misfit");
    state.inventory.builds = { hall: { by: "plugins", state: "queued", plugins: ["bus"], file: "hall.yaml" } };
    expect(plugins.statusOn(plugins.index[0], hall)).toEqual({ kind: "building", label: t("editor.plugins.state.queued") });
    state.inventory.builds = {};
    plugins.installed.hall[0].version = "1.1.0";
    expect(status("bus")).toBe("installed");
    expect(status("bus", desk)).toBe("");
  });

  it("over every screen: building, a test by its screen, updates and screens counted, or fitting none", async () => {
    const { plugins } = await loaded([plugin("bus", { version: "1.1.0" }), plugin("big", { requires: { psram: true } }), plugin("new")],
      { hall: [installed("bus"), installed("lab", { source: "branch" })], desk: [installed("bus", { version: "1.1.0" })] });
    expect(plugins.statusOverall(plugins.index[0])).toEqual({ kind: "update", label: t("editor.plugins.state.updates", { n: 1 }, 1) });
    plugins.installed.hall[0].version = "1.1.0";
    expect(plugins.statusOverall(plugins.index[0])).toEqual({ kind: "installed", label: t("editor.plugins.state.on_screens", { n: 2 }, 2) });
    const lab = plugins.allTests()[0];
    expect(plugins.statusOverall(lab)).toEqual({ kind: "test", label: t("editor.plugins.state.test_on", { name: "Hall" }) });
    expect(plugins.statusOverall(plugins.index[2]).kind).toBe("");
    state.inventory.screens = [screen("cyd", { pictures: false })];
    expect(plugins.statusOverall(plugins.index[1])).toEqual({ kind: "misfit", label: t("editor.plugins.state.fits_none") });
    state.inventory.builds = { cyd: { by: "plugins", state: "running", plugins: ["new"], file: "cyd.yaml" } };
    expect(plugins.statusOverall(plugins.index[2]).kind).toBe("building");
  });
});

describe("what the index brings", () => {
  it("knows its tile types and bar items, gone again with the plugin", async () => {
    const weather = plugin("weather", { tiles: [{ id: "radar", name: { en: "Radar" }, min: "single", max: "full", memory: 900 }],
      bar_items: [{ id: "rain", label: { en: "Rain" }, icon: "F0597", example: { en: "2 mm" } }] });
    const { api, plugins } = await loaded([weather]);
    expect(plugins.pluginTileOf("plugin:weather.radar")?.tile.memory).toBe(900);
    expect(plugins.barItemOf("plugin:weather.rain")).toEqual({ label: "Rain", icon: "F0597", example: "2 mm", plugin: "Weather" });
    api.on("GET plugins", { plugins: [], installed: {}, secrets: {}, folders: { path: "", errors: {} } });
    await plugins.reloadPlugins();
    expect([plugins.pluginTileOf("plugin:weather.radar"), plugins.barItemOf("plugin:weather.rain")]).toEqual([undefined, null]);
  });
});

describe("what its start follows", () => {
  it("loads the plugins where they are on, and again when a plugin build starts or ends, until it is stopped", async () => {
    state.inventory = { screens: [hall], entities: [], builds: {} } as any;
    const api = addOn([plugin("bus")]);
    const plugins = usePluginsStore();
    const stop = plugins.start();
    await flushPromises();
    expect([api.count("GET plugins"), plugins.loaded, plugins.index.length]).toEqual([1, true, 1]);
    state.inventory.builds = { hall: { by: "update", state: "running", file: "hall.yaml" } };
    await nextTick();
    expect(api.count("GET plugins")).toBe(1);
    state.inventory.builds = { hall: { by: "plugins", state: "running", plugins: ["bus"], file: "hall.yaml" } };
    await vi.waitFor(() => expect(api.count("GET plugins")).toBe(2));
    stop();
    state.inventory.builds = {};
    await flushPromises();
    expect(api.count("GET plugins")).toBe(2);
  });
});
