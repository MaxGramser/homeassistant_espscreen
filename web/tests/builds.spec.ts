// Builds (docs/PLUGINS.md, "A plugin on a screen"): the add-on says per screen what is being built for it, whoever asked
// (Manager.builds), and the store is the editor's one source for it. The screen list, the progress and the build log all
// read it, so a plugin build shows the same way as a firmware update.
import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import BuildLog from "../src/components/BuildLog.vue";
import { state } from "../src/store";
import type { Screen } from "../src/types";
import { useBuildsStore } from "../src/stores/builds";
import { useScreenStore } from "../src/stores/screen";

const screen = (id: string, more: Partial<Screen> = {}) =>
  ({ id: `text.${id}`, name: id, node: id, online: true, board: "guition", firmware: "0.52.0", pictures: true, layout: {},
     update: { profile: `${id}.yaml`, host: "10.0.0.1", state: "idle" }, ...more }) as unknown as Screen;
const hall = screen("hall"), desk = screen("desk");

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ job: useBuildsStore().firmwareJob?.job, logs: useBuildsStore().firmwareJob?.logs || [] }),
    { status: 200, headers: { "Content-Type": "application/json" } })));
  state.inventory.screens = [hall, desk];
  state.inventory.builds = {};
});
afterEach(() => vi.unstubAllGlobals());

describe("builds", () => {
  it("knows nothing builds until the add-on says so", () => {
    expect(useBuildsStore().buildOf(hall)).toBeNull();
    expect(useBuildsStore().anyBuilding).toBe(false);
    expect(useScreenStore().updateState(hall)?.kind).not.toBe("running");
  });

  it("shows a plugin build the way an update shows: running, with its ESPHome stage as progress", () => {
    state.inventory.builds = { [hall.id]: { by: "plugins", state: "running", plugins: ["bus"], file: "hall.yaml", stage: "compile" },
                               [desk.id]: { by: "plugins", state: "queued", plugins: ["waste"], file: "desk.yaml" } };
    expect(useBuildsStore().anyBuilding).toBe(true);
    expect(useScreenStore().updateState(hall)).toEqual({ kind: "running", text: "Building with its plugins" });
    expect(useScreenStore().updateState(desk)?.kind).toBe("queued");
    expect(useBuildsStore().buildProgress(hall)).toEqual({ percent: 40, text: expect.any(String) });
    expect(useBuildsStore().buildProgress(desk)).toBeNull();
    expect(useBuildsStore().buildingScreens.map((s) => s.name)).toEqual(["hall", "desk"]);
  });

  it("reads an update's phase from the same record", () => {
    state.inventory.builds = { [hall.id]: { by: "update", state: "running", phase: "verify", file: "hall.yaml" } };
    expect(useBuildsStore().buildProgress(hall)?.percent).toBe(78);
  });

  it("a build log shows the progress, and the lines of this screen's build when opened", async () => {
    state.inventory.builds = { [hall.id]: { by: "plugins", state: "running", plugins: ["bus"], file: "hall.yaml", stage: "upload" } };
    useBuildsStore().firmwareJob = { job: { file: "hall.yaml", state: "running", stage: "upload" }, logs: ["Compiling", "Uploading"] };
    const view = mount(BuildLog, { props: { screen: hall, name: true } });
    await nextTick();
    expect(view.text()).toContain("hall · 66 %");
    expect(view.find("pre").text()).toContain("Uploading");
  });

  it("keeps the log of a build that failed, and says so, until the next build", async () => {
    useBuildsStore().firmwareJob = { job: { file: "hall.yaml", state: "failed" }, logs: ["error: plugin ov_departures"] };
    const view = mount(BuildLog, { props: { screen: hall } });
    await nextTick();
    expect(view.text()).toContain("The last build of hall failed");
    expect(view.find("pre").text()).toContain("error: plugin ov_departures");
    const other = mount(BuildLog, { props: { screen: desk } });
    await nextTick();
    expect(other.find(".build-log").exists()).toBe(false);
  });
});
