// Updates and the firmware job (stores/builds.ts): one screen, every screen and the automatic updates, each with the
// inventory read again or the add-on's refusal said, and the firmware job asked for once by whoever follows it.
import { describe, expect, it } from "vitest";
import { i18n } from "../../src/i18n";
import { useBuildsStore } from "../../src/stores/builds";
import { useUiStore } from "../../src/stores/ui";
import { flushPromises } from "@vue/test-utils";
import type { Screen } from "../../src/types";
import { failure, fakeApi } from "../helpers/fake-api";
import { useInventoryStore } from "../../src/stores/inventory";

const screen = (id: string) => ({ id: `text.${id}`, name: id, online: true, layout: {}, update: { profile: `${id}.yaml`, host: "10.0.0.1" } }) as unknown as Screen;
const hall = screen("hall"), desk = screen("desk");
const t = (key: string, named: Record<string, unknown> = {}) => i18n.global.t(key, named);

describe("updates", () => {
  it("builds one screen: asked for at once, until the add-on names its build; a refusal forgets it and says why", async () => {
    useInventoryStore().inventory = { screens: [hall, desk], entities: [], builds: {} } as any;
    const api = fakeApi({ "POST screens/:id/update": {}, "GET inventory": { screens: [hall, desk], entities: [], builds: {} } });
    const update = api.defer("POST screens/:id/update");
    const builds = useBuildsStore();
    const asking = builds.startUpdate(hall, "hall.local", true);
    expect([builds.updating, builds.isBuilding(hall), builds.anyBuilding]).toEqual([[hall.id], true, true]);
    expect(builds.buildingScreens.map((s) => s.name)).toEqual(["hall"]);
    update.resolve();
    await asking;
    expect(api.asked("POST screens/:id/update")[0].body).toEqual({ host: "hall.local", reinstall: true });
    expect(api.count("GET inventory")).toBe(1);
    // The add-on's inventory does not name the build yet: the page keeps it as asked for.
    expect(builds.updating).toEqual([hall.id]);
    useInventoryStore().inventory.builds = { [hall.id]: { by: "update", state: "running", file: "hall.yaml" } };
    builds.prune();
    expect([builds.updating, builds.isBuilding(hall)]).toEqual([[], true]);

    api.on("POST screens/:id/update", failure(409, "Another build is running"));
    await builds.startUpdate(desk);
    expect(builds.updating).toEqual([]);
    expect(useUiStore().notice?.message).toBe("Another build is running");
  });

  it("updates every screen that waits: the inventory read again, or the refusal said", async () => {
    useInventoryStore().inventory = { screens: [hall], entities: [], updates: { pending: 2, auto: false } } as any;
    const api = fakeApi({ "POST updates/run": {}, "GET inventory": { screens: [hall], entities: [], updates: { pending: 2, busy: true } } });
    const builds = useBuildsStore();
    await builds.runUpdateAll();
    expect(api.calls.map((r) => `${r.method} ${r.path}`)).toEqual(["POST updates/run", "GET inventory"]);
    expect(useInventoryStore().inventory.updates?.busy).toBe(true);
    api.on("POST updates/run", failure(503, "The add-on is busy"));
    await builds.runUpdateAll();
    expect(api.count("GET inventory")).toBe(1);
    expect(useUiStore().notice?.message).toBe("The add-on is busy");
  });

  it("turns automatic updates on and off as the add-on takes it, and keeps them as they were when it refuses", async () => {
    useInventoryStore().inventory = { screens: [], entities: [], updates: { pending: 0, auto: false } } as any;
    const api = fakeApi({ "PUT updates": {} });
    const builds = useBuildsStore();
    await builds.setAutoUpdate(true);
    expect(api.asked("PUT updates")[0].body).toEqual({ auto: true });
    expect(useInventoryStore().inventory.updates?.auto).toBe(true);
    expect(useUiStore().notice?.message).toBe(t("editor.settings.updates.auto_on"));
    api.on("PUT updates", failure(500, "Could not save"));
    await builds.setAutoUpdate(false);
    expect(useInventoryStore().inventory.updates?.auto).toBe(true);
    expect(useUiStore().notice?.message).toBe("Could not save");
  });
});

describe("the firmware job", () => {
  it("is asked for once whoever asks while it is on its way, kept for the build log, and kept when the add-on cannot be reached", async () => {
    const api = fakeApi({ "GET firmware": { job: { file: "hall.yaml", state: "running" }, logs: ["INFO Compiling"] } });
    const builds = useBuildsStore();
    const held = api.defer("GET firmware");
    const first = builds.fetchFirmware(), second = builds.fetchFirmware();
    held.resolve();
    expect(await first).toBe(await second);
    expect(api.count("firmware")).toBe(1);
    expect(builds.firmwareJob).toEqual({ job: { file: "hall.yaml", state: "running" }, logs: ["INFO Compiling"] });
    expect(builds.answer.logs).toEqual(["INFO Compiling"]);
    // A young enough answer is taken as it is; an older one is asked again.
    await builds.fetchFirmware(60000);
    expect(api.count("firmware")).toBe(1);
    await builds.loadFirmwareJob();
    expect(api.count("firmware")).toBe(2);
    api.on("GET firmware", failure(502, "Bad gateway"));
    await builds.loadFirmwareJob();
    expect(builds.firmwareJob?.logs).toEqual(["INFO Compiling"]);
    await expect(builds.fetchFirmware()).rejects.toThrow("Bad gateway");
  });
});

describe("a build that ends while the page is open", () => {
  const living = (result?: { state: string; time: number }) =>
    ({ id: "text.living", name: "Living room", online: true, layout: {}, update: { profile: "living.yaml", host: "10.0.0.2", ...(result ? { result: { message: "", ...result } } : {}) } }) as unknown as Screen;
  const arrive = (screen: Screen, builds: Record<string, any> = {}, line: any[] = []) => {
    useInventoryStore().inventory = { screens: [screen], entities: [], builds, line } as any;
    useBuildsStore().prune();
  };

  it("says a watched update is ready, on whatever is open, and says nothing of one that ended before the page was opened", async () => {
    // Opened after a build that went well: nothing to say.
    arrive(living({ state: "success", time: 10 }));
    expect(useUiStore().notice).toBeNull();
    // An update the page sees on its way, then its new result.
    arrive(living({ state: "success", time: 10 }), { "text.living": { by: "update", state: "running", file: "living.yaml", phase: "install" } });
    expect(useBuildsStore().watched["text.living"]).toMatchObject({ by: "update", result: 10 });
    arrive(living({ state: "success", time: 20 }));
    await Promise.resolve();
    expect(useUiStore().notice).toEqual({ message: t("editor.build.ready", { name: "Living room" }), action: undefined });
    expect(useBuildsStore().watched).toEqual({});
  });

  it("says a failed one with the way to its log, and watches an update from the moment it is asked for", async () => {
    const screen = living({ state: "success", time: 10 });
    useInventoryStore().inventory = { screens: [screen], entities: [], builds: {} } as any;
    fakeApi({ "POST screens/:id/update": {}, "GET inventory": { screens: [screen], entities: [], builds: {} } });
    await useBuildsStore().startUpdate(screen);
    expect(useBuildsStore().watched["text.living"]).toBeDefined();
    // Asked for, it stays on its way until the add-on names it, and ends when the add-on no longer does.
    arrive(living({ state: "success", time: 10 }));
    expect(useUiStore().notice).toBeNull();
    arrive(living({ state: "success", time: 10 }), { "text.living": { by: "update", state: "running", file: "living.yaml" } });
    arrive(living({ state: "failed", time: 30 }));
    await Promise.resolve();
    const notice = useUiStore().notice!;
    expect(notice.message).toBe(t("editor.build.update_failed", { name: "Living room" }));
    expect(notice.action!.label).toBe(t("editor.build.show_log"));
    notice.action!.run();
    await flushPromises();
    expect(useUiStore().route).toBe("#firmware");
  });

  it("reads a plugin build's outcome from the build line by its id, in the same answer that no longer names it", async () => {
    // The next build of the line started at once (another screen's): the outcome is this build's own, and nothing is asked.
    const api = fakeApi({});
    arrive(living(), { "text.living": { id: 7, by: "plugins", state: "queued", place: 1, file: "living.yaml" } });
    arrive(living(), { "text.living": { id: 7, by: "plugins", state: "running", file: "living.yaml" } });
    arrive(living(), {}, [{ id: 8, by: "update", file: "desk.yaml", action: "install", state: "running", asked: 7, started: 8, finished: null },
                          { id: 7, by: "plugins", file: "living.yaml", action: "install", state: "failed", asked: 1, started: 2, finished: 6 }]);
    expect(useUiStore().notice?.message).toBe(t("editor.build.build_failed", { name: "Living room" }));
    expect(api.calls.length).toBe(0);
  });

  it("follows a plugin build that became the screen's update, and reads that update's result", async () => {
    arrive(living({ state: "success", time: 10 }), { "text.living": { id: 3, by: "plugins", state: "queued", place: 1, file: "living.yaml", plugins: ["bus"] } });
    arrive(living({ state: "success", time: 10 }), { "text.living": { id: 3, by: "update", state: "running", file: "living.yaml", plugins: ["bus"] } });
    expect(useBuildsStore().watched["text.living"]).toMatchObject({ by: "update", id: 3 });
    arrive(living({ state: "success", time: 50 }));
    await Promise.resolve();
    expect(useUiStore().notice?.message).toBe(t("editor.build.ready", { name: "Living room" }));
  });

  it("forgets a build whose screen went or whose request was refused", async () => {
    arrive(living(), { "text.living": { by: "update", state: "queued", file: "living.yaml" } });
    useBuildsStore().forget("text.living");
    arrive(living({ state: "success", time: 40 }));
    await Promise.resolve();
    expect(useUiStore().notice).toBeNull();
    // A queued screen a round left without a result of its own says nothing either.
    arrive(living(), { "text.living": { by: "update", state: "queued", file: "living.yaml" } });
    arrive(living());
    await Promise.resolve();
    expect(useUiStore().notice).toBeNull();
  });
});
