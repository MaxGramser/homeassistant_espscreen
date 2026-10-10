// The open screen (stores/screen.ts): what its firmware takes, and what can be done to a screen from here, each with the
// add-on's answer shown or its refusal said: the screensaver (the latest change wins, and only it is taken back), a new
// name (a preview screen's kept in this browser), a screen New screen wrote that never got its firmware, and letting a
// screen perform actions; and the status lines of the sidebar and the overview.
import { describe, expect, it } from "vitest";
import { i18n } from "../../src/i18n";
import { state } from "../../src/store";
import { useBuildsStore } from "../../src/stores/builds";
import { useScreenStore } from "../../src/stores/screen";
import { useUiStore } from "../../src/stores/ui";
import type { Screen, ScreensaverChoice } from "../../src/types";
import { failure, fakeApi } from "../helpers/fake-api";

const t = (key: string, named: Record<string, unknown> = {}) => i18n.global.t(key, named);
const saver = (patch: Partial<ScreensaverChoice> = {}) => ({ show: true, media: "", camera: "", order: ["media", "camera", "clock"], off: [],
  weather: "auto", more: [], items: [], ready: true, pictures: true, ...patch }) as ScreensaverChoice;
const screen = (id: string, patch: Partial<Screen> = {}) => ({ id, name: id, online: true, firmware: "0.53.0", layout: { title: id, tiles: [] },
  screensaver: saver(), ...patch }) as unknown as Screen;

function open(...screens: Screen[]) {
  state.inventory = { screens, entities: [], header: { max_items: 6, builtin: [] }, pending: [] } as any;
  useScreenStore().selected = screens[0]?.id ?? null;
  return useScreenStore();
}

describe("the open screen's facts", () => {
  it("are its own where it says them, else what its firmware takes", () => {
    const scr = open(screen("hall", { firmware: "0.2.64", bar_limit: 4 } as Partial<Screen>), screen("desk", { firmware: "0.17.0", full_page: false }));
    expect(scr.currentScreen?.id).toBe("hall");
    expect([scr.supports(0, 2, 62), scr.supports(0, 2, 65), scr.fullPage, scr.pageTilesRepeat, scr.noTitle]).toEqual([true, false, true, false, false]);
    expect(scr.topbarMax).toBe(4);
    scr.selected = "desk";
    expect([scr.fullPage, scr.pageTilesRepeat, scr.entityTilesRepeat, scr.noTitle, scr.topbarMax]).toEqual([false, true, true, true, 6]);
    // A clock with keys is on a screen once; any other entity as often as one likes.
    expect([scr.repeatable("screen.nightstand"), scr.repeatable("light.a"), scr.repeatable("screen.page_2")]).toEqual([false, true, true]);
    scr.selected = null;
    expect([scr.currentScreen, scr.topbarMax]).toEqual([undefined, 6]);
  });
});

describe("the screensaver", () => {
  it("shows a change at once, and of two on their way the latest wins: an older answer is not shown", async () => {
    const hall = open(screen("hall")).currentScreen!;
    const api = fakeApi({ "PUT screens/:id/screensaver": ({ body }) => ({ screensaver: { ...body.screensaver, ready: true } }) });
    const first = api.defer("PUT screens/:id/screensaver"), second = api.defer("PUT screens/:id/screensaver");
    const scr = useScreenStore();
    const one = scr.setScreensaver(hall, { camera: "camera.door" });
    const two = scr.setScreensaver(hall, { weather: "" });
    expect([hall.screensaver!.camera, hall.screensaver!.weather]).toEqual(["camera.door", ""]);
    second.resolve();
    await two;
    expect(hall.screensaver!.weather).toBe("");
    // The first answer comes last: what it says is older than what is shown.
    first.resolve({ screensaver: saver({ camera: "camera.door", weather: "auto" }) });
    await one;
    expect([hall.screensaver!.camera, hall.screensaver!.weather]).toEqual(["camera.door", ""]);
    // What goes to the add-on is the whole choice, its bar items without the editor's ids.
    expect(api.asked("PUT screens/:id/screensaver")[1].body.screensaver).toMatchObject({ camera: "camera.door", weather: "", items: [] });
  });

  it("takes back only the latest change that failed, to what was shown before it, and says why", async () => {
    const hall = open(screen("hall")).currentScreen!;
    const api = fakeApi({ "PUT screens/:id/screensaver": failure(503, "The screen is away") });
    const first = api.defer("PUT screens/:id/screensaver");
    const scr = useScreenStore();
    const one = scr.setScreensaver(hall, { camera: "camera.door" });
    await scr.setScreensaver(hall, { media: "media_player.kitchen" });
    // The latest failed: back to what it was before it, the camera still chosen.
    expect([hall.screensaver!.camera, hall.screensaver!.media]).toEqual(["camera.door", ""]);
    expect(useUiStore().notice?.message).toBe("The screen is away");
    // The older one fails too, later: the latest already took the screensaver back, so this one changes nothing.
    first.resolve();
    await one;
    expect([hall.screensaver!.camera, hall.screensaver!.media]).toEqual(["camera.door", ""]);
  });

  it("keeps a preview screen's change in the page, without asking the add-on", async () => {
    const preview = open(screen("virtual.desk", { virtual: true })).currentScreen!;
    const api = fakeApi();
    await useScreenStore().setScreensaver(preview, { off: ["clock"] });
    expect(preview.screensaver!.off).toEqual(["clock"]);
    expect(api.calls).toEqual([]);
  });
});

describe("what can be done to a screen", () => {
  it("renames a screen with the name the add-on answers, and says why it could not", async () => {
    const scr = open(screen("hall"));
    const api = fakeApi({ "PUT screens/:id/name": ({ body }) => ({ name: body.name || "Hall (Home Assistant)" }) });
    expect(await scr.renameScreen(scr.currentScreen!, "Living room")).toBe(true);
    expect(scr.currentScreen!.name).toBe("Living room");
    expect(await scr.renameScreen(scr.currentScreen!, "")).toBe(true);
    expect(scr.currentScreen!.name).toBe("Hall (Home Assistant)");
    api.on("PUT screens/:id/name", failure(400, "That name is taken"));
    expect(await scr.renameScreen(scr.currentScreen!, "Kitchen")).toBe(false);
    expect([scr.currentScreen!.name, useUiStore().notice?.message]).toEqual(["Hall (Home Assistant)", "That name is taken"]);
  });

  it("renames a preview screen in this browser, an empty name keeping the one it had", async () => {
    const scr = open(screen("virtual.desk", { virtual: true, name: "Desk" }));
    const api = fakeApi();
    expect(await scr.renameScreen(scr.currentScreen!, "  Study ")).toBe(true);
    expect(scr.currentScreen!.name).toBe("Study");
    expect(JSON.parse(localStorage.getItem("esp-screens.virtual-screens")!)[0].name).toBe("Study");
    expect(await scr.renameScreen(scr.currentScreen!, "   ")).toBe(true);
    expect(scr.currentScreen!.name).toBe("Study");
    expect(api.calls).toEqual([]);
  });

  it("forgets a screen New screen wrote, one at a time, and keeps it when the add-on refuses", async () => {
    const scr = open(screen("hall"));
    state.inventory.pending = [{ file: "desk.yaml", friendly: "Desk" }, { file: "attic.yaml", friendly: "Attic" }] as any;
    const api = fakeApi({ "DELETE firmware/profiles/:file": {} });
    const asked = api.defer("DELETE firmware/profiles/:file");
    const forgetting = scr.forgetPending("desk.yaml", "Desk");
    expect(scr.removing).toBe("pending:desk.yaml");
    // A second click while the first is on its way does nothing.
    expect(await scr.forgetPending("attic.yaml", "Attic")).toBe(false);
    asked.resolve();
    expect(await forgetting).toBe(true);
    expect(api.asked("DELETE firmware/profiles/:file").map((r) => r.params.file)).toEqual(["desk.yaml"]);
    expect([state.inventory.pending!.map((p) => p.file), scr.removing]).toEqual([["attic.yaml"], null]);
    expect(useUiStore().notice?.message).toBe(t("editor.sidebar.remove.done", { name: "Desk" }));
    api.on("DELETE firmware/profiles/:file", failure(409, "A paired screen builds from it"));
    expect(await scr.forgetPending("attic.yaml", "Attic")).toBe(false);
    expect([state.inventory.pending!.length, scr.removing, useUiStore().notice?.message]).toEqual([1, null, "A paired screen builds from it"]);
  });

  it("lets a screen perform actions once at a time, and says the add-on's refusal", async () => {
    const scr = open(screen("hall", { actions_blocked: true, name: "Hall" }));
    const api = fakeApi({ "POST screens/:id/allow-actions": { name: "Hall screen" } });
    const asked = api.defer("POST screens/:id/allow-actions");
    const hall = scr.currentScreen!;
    const allowing = scr.allowActions(hall);
    expect(scr.allowing).toBe("hall");
    await scr.allowActions(hall);
    asked.resolve();
    await allowing;
    expect(api.count("POST screens/:id/allow-actions")).toBe(1);
    expect([hall.actions_blocked, scr.allowing]).toEqual([false, null]);
    expect(useUiStore().notice?.message).toBe(t("editor.pages.actions_allowed", { name: "Hall screen" }));
    hall.actions_blocked = true;
    api.on("POST screens/:id/allow-actions", failure(502, "Home Assistant did not answer"));
    await scr.allowActions(hall);
    expect([hall.actions_blocked, scr.allowing, useUiStore().notice?.message]).toEqual([true, null, "Home Assistant did not answer"]);
  });
});

describe("a screen's status", () => {
  it("says what its build does, from the builds store", () => {
    const scr = open(screen("hall"), screen("desk", { online: false }));
    const [hall, desk] = state.inventory.screens;
    expect([scr.screenLight(hall), scr.screenSubline(hall), scr.needsAttention(hall)]).toEqual(["ok", null, false]);
    expect([scr.screenLight(desk), scr.needsAttention(desk)]).toEqual(["down", true]);
    useBuildsStore().updating = ["hall"];
    expect(scr.updateState(hall)?.kind).toBe("running");
  });
});
