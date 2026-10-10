// Updates and the firmware job (stores/builds.ts): one screen, every screen and the automatic updates, each with the
// inventory read again or the add-on's refusal said, and the firmware job asked for once by whoever follows it.
import { describe, expect, it } from "vitest";
import { i18n } from "../../src/i18n";
import { state } from "../../src/store";
import { useBuildsStore } from "../../src/stores/builds";
import { useUiStore } from "../../src/stores/ui";
import type { Screen } from "../../src/types";
import { failure, fakeApi } from "../helpers/fake-api";
import { useInventoryStore } from "../../src/stores/inventory";

const screen = (id: string) => ({ id: `text.${id}`, name: id, online: true, layout: {}, update: { profile: `${id}.yaml`, host: "10.0.0.1" } }) as unknown as Screen;
const hall = screen("hall"), desk = screen("desk");
const t = (key: string) => i18n.global.t(key);

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
