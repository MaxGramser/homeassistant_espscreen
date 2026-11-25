// Feedback from a build (docs/BUILDS.md): its steps, every update of a screen in one card and one build, a version that
// does not run well one tap from the one before, and a failure that says its kind with its own way out.
import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import { stepsOf } from "../src/model/build-steps";
import type { Installed, Plugin } from "../src/model/plugins";
import type { LineBuild, Screen } from "../src/types";
import { usePluginsStore } from "../src/stores/plugins";
import { useInventoryStore } from "../src/stores/inventory";
import { useScreenStore } from "../src/stores/screen";
import ScreenPluginsTab from "../src/components/ScreenPluginsTab.vue";
import PluginOnScreen from "../src/components/plugins/PluginOnScreen.vue";
import BuildRoom from "../src/components/BuildRoom.vue";

const plugin = (id: string, version: string, more: Partial<Plugin> = {}): Plugin => ({
  id, name: { en: id === "bus" ? "Public transport" : "Rain" }, summary: { en: "" }, icon: "F00E7", maintainer: "Someone",
  tessera: false, version, repo: "https://github.com/someone/rain", license: "MIT", type: "functions", boards: "any", requires: {}, flash_kb: 1,
  permissions: { home_assistant: [], network: [] }, readme: { en: "" }, languages: ["en"], attributes: [], source: "index",
  permission_hash: "same", ...more,
});
const hall = { id: "text.hall", name: "Hall", node: "hall", online: true, board: "guition", firmware: "0.63.0", pictures: true, layout: {},
  update: { profile: "hall.yaml", available: true, target: "0.64.0", host: "10.0.0.2" } } as unknown as Screen;
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
    const payload = path.includes("api/plugins") ? { plugins: plugins.index, installed: plugins.installed, secrets: {}, folders: { path: "", errors: {} } }
      : path.includes("api/inventory") ? { screens: [hall], entities: [] } : { written: true, built: true, queued: 0 };
    return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
  }));
  useInventoryStore().inventory.screens = [hall];
  useInventoryStore().inventory.builds = {};
  useScreenStore().selected = hall.id;
  plugins.loaded = true;
  plugins.index = [plugin("rain", "0.6.0")];
  plugins.installed = { [hall.id]: [installed("rain", "0.5.0")] };
});
afterEach(() => vi.unstubAllGlobals());

describe("the steps of a build", () => {
  const build = (more: Partial<LineBuild>) => ({ id: 1, by: "plugins", file: "hall.yaml", action: "install", state: "running", asked: 0, started: 1, finished: null, ...more } as LineBuild);
  it("are at the step the add-on names, and the step a failed build stopped at failed", () => {
    expect(stepsOf(build({ state: "queued" })).map((s) => s.state)).toEqual(["now", "todo", "todo", "todo"]);
    expect(stepsOf(build({ stage: "compile" })).map((s) => s.state)).toEqual(["done", "now", "todo", "todo"]);
    expect(stepsOf(build({ stage: "upload" })).map((s) => s.state)).toEqual(["done", "done", "now", "todo"]);
    expect(stepsOf(build({ phase: "verify", stage: "upload" })).map((s) => s.state)).toEqual(["done", "done", "done", "now"]);
    expect(stepsOf(build({ state: "failed", stage: "upload" })).map((s) => s.state)).toEqual(["done", "done", "failed", "skipped"]);
    expect(stepsOf(build({ state: "success", verified: true })).map((s) => s.state)).toEqual(["done", "done", "done", "done"]);
    expect(stepsOf(build({ state: "success", verified: false })).at(-1)!.state).toBe("failed");
    expect(stepsOf(build({ state: "success", verified: null })).at(-1)!.state).toBe("skipped");
    // Built ahead in a round: built, and its install waits for the screens before it (docs/BUILDS.md, "Building ahead").
    expect(stepsOf(build({ phase: "ready" })).map((s) => s.state)).toEqual(["done", "done", "waits", "todo"]);
    // Back at the end of the line after a download that did not come: the step it stopped at waits, nothing failed.
    expect(stepsOf(build({ state: "retry", stage: "compile" })).map((s) => s.state)).toEqual(["done", "waits", "skipped", "skipped"]);
    // Left out because its round stopped before its turn: nothing of its own failed.
    expect(stepsOf(build({ state: "skipped", stage: "compile" })).map((s) => s.state)).toEqual(["done", "skipped", "skipped", "skipped"]);
  });
});

describe("every update of a screen in one card", () => {
  it("names the firmware and each plugin, and does it all in one build", async () => {
    const view = mount(ScreenPluginsTab);
    await nextTick();
    const card = view.get("#screen-plugin-updates");
    expect(card.text()).toContain("2 updates for Hall");
    expect(card.findAll("[data-update]").map((row) => row.attributes("data-update"))).toEqual(["firmware", "rain"]);
    expect(card.text()).toContain("0.63.0 → 0.64.0");
    await view.get("#screen-plugin-update-all").trigger("click");
    await vi.waitFor(() => expect(calls.length).toBe(1));
    expect(calls[0].path).toContain("screens/text.hall/update-everything");
    expect(calls[0].body.add.map((a: any) => a.id)).toEqual(["rain"]);
  });

  it("waits for a screen that is away", async () => {
    useInventoryStore().inventory.screens = [{ ...hall, online: false }];
    const view = mount(ScreenPluginsTab);
    await nextTick();
    expect(view.get("#screen-plugin-updates").text()).toContain("Hall is offline");
    expect((view.get("#screen-plugin-update-all").element as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("a version that does not run well", () => {
  it("goes back to the one before with one tap, first when the screen came back without it", async () => {
    plugins.index = [plugin("rain", "0.6.0")];
    plugins.installed = { [hall.id]: [installed("rain", "0.6.0", { before: "0.5.0", verified: false })] };
    const view = mount(PluginOnScreen, { props: { plugin: plugins.index[0], screen: hall } });
    await nextTick();
    expect(view.get("#plugin-not-running").text()).toContain("Hall came back without Rain");
    const back = view.get("#plugin-back");
    expect(back.text()).toContain("Back to 0.5.0");
    expect(back.classes()).toContain("primary");
    await back.trigger("click");
    await vi.waitFor(() => expect(calls.length).toBe(1));
    expect(calls[0].path).toContain("screens/text.hall/plugins/rain/back");
  });
});

describe("a failure that says its kind", () => {
  it("waits for a screen that was away, and sends memory that ran short to a build server", async () => {
    plugins.installed = { [hall.id]: [installed("rain", "0.5.0", { failed_update: { version: "0.6.0", reason: "did not answer", kind: "offline", log: "k" } })] };
    let view = mount(ScreenPluginsTab);
    await nextTick();
    let box = view.get("#screen-plugin-failures .sp-failure");
    expect(box.classes()).toContain("waiting");
    expect(box.text()).toContain("installs by itself once the screen is back");
    expect(box.find("a[data-action=issue]").exists()).toBe(false);
    plugins.installed = { [hall.id]: [installed("rain", "0.5.0", { failed_update: { version: "0.6.0", reason: "Killed", kind: "memory", log: "k" } })] };
    view = mount(ScreenPluginsTab);
    await nextTick();
    box = view.get("#screen-plugin-failures .sp-failure");
    expect(box.text()).toContain("ran short of memory");
    expect(box.find("button[data-action=server]").exists()).toBe(true);
  });
});

describe("before a build", () => {
  it("warns when this Home Assistant is short of memory and has no build server", async () => {
    useInventoryStore().inventory.build_room = { free_mb: 900, need_mb: 1500, server: false, tight: true };
    const view = mount(BuildRoom);
    expect(view.get("#build-room").text()).toContain("0.9 GB free");
    useInventoryStore().inventory.build_room = { free_mb: 900, need_mb: 1500, server: true, tight: false };
    await nextTick();
    expect(view.find("#build-room").exists()).toBe(false);
  });
});
