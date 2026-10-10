// The session (stores/session.ts): opening a screen and going home, asking first about unsaved edits; removing a screen,
// the open one closing without a question; a new preview screen opened; what follows from a new inventory, in its order;
// and its start, which starts everything once and stops it again.
import { describe, expect, it, beforeEach } from "vitest";
import { i18n } from "../../src/i18n";
import { openSaverStep, state } from "../../src/store";
import { customPreview } from "../../src/model/preview";
import { useBuildsStore } from "../../src/stores/builds";
import { useScreenStore } from "../../src/stores/screen";
import { useSessionStore } from "../../src/stores/session";
import { useSettingsStore } from "../../src/stores/settings";
import { useUiStore } from "../../src/stores/ui";
import type { Inventory, Screen } from "../../src/types";
import { answerDialogs } from "../helpers/dialogs";
import { failure, fakeApi } from "../helpers/fake-api";
import { screenFixture } from "../helpers/fixtures";
import { useInventoryStore } from "../../src/stores/inventory";
import { addTile } from "../../src/editor/tiles";
import { useDocumentStore } from "../../src/stores/document";

let doc: ReturnType<typeof useDocumentStore>;
beforeEach(() => { doc = useDocumentStore(); });

const t = (key: string, named: Record<string, unknown> = {}) => i18n.global.t(key, named);
const screen = (id: string, tiles: { entity: string; name: string; slot: number }[] = []) =>
  screenFixture({ id, name: id, online: true, firmware: "0.53.0", layout: { title: id, tiles } } as unknown as Screen);
const inventory = (...screens: Screen[]) => ({ connected: true, screens, entities: [] }) as unknown as Inventory;
// What opening a screen asks the add-on for: the states and capabilities of its tiles, its top bar's previews.
const api = (extra = {}) => fakeApi({ states: { states: {} }, capabilities: { capabilities: {} }, "POST header-preview": { items: [] }, ...extra });

describe("opening a screen", () => {
  it("opens one with its draft, the editor's sheets and drawers closed, and the layout in view", () => {
    api();
    useInventoryStore().inventory = inventory(screen("hall", [{ entity: "light.a", name: "", slot: 0 }]), screen("desk"));
    const ui = useUiStore(), session = useSessionStore();
    ui.$patch({ menuOpen: true, addSheet: true, pagesSheet: true });
    ui.tab = "settings";
    ui.go("#settings");
    session.select("hall");
    expect(useScreenStore().selected).toBe("hall");
    expect(doc.layout?.tiles.map((tile) => tile.entity)).toEqual(["light.a"]);
    expect([ui.tab, doc.dirty, ui.menuOpen, ui.addSheet, ui.pagesSheet, ui.route]).toEqual(["layout", false, false, false, false, ""]);
    // None: the overview, with no draft left.
    session.select(null);
    expect([useScreenStore().selected, doc.document, doc.dirty]).toEqual([null, null, false]);
  });

  it("asks before leaving unsaved edits, stays on no, and on yes leaves the settings changes of the screen it leaves", async () => {
    api({ "PUT screens/:id/settings": ({ body }) => ({ owner: "screen", values: body.settings, keys: [], unavailable: [] }) });
    useInventoryStore().inventory = inventory(screen("hall"), screen("desk"));
    const session = useSessionStore(), settings = useSettingsStore();
    session.select("hall");
    addTile("light.b");
    expect(doc.dirty).toBe(true);
    let yes = false;
    const asked = answerDialogs(() => yes);
    await session.select("desk");
    expect(asked.map((q) => q.message)).toEqual([t("editor.screen_view.confirm.switch")]);
    expect([useScreenStore().selected, doc.dirty]).toEqual(["hall", true]);
    settings.setSetting("brightness", 40, 1000);
    yes = true;
    await session.select("desk");
    expect([useScreenStore().selected, doc.dirty, doc.layout?.tiles.length]).toEqual(["desk", false, 0]);
    // The brightness changed on the hall screen went out to it, and is not shown on this one.
    expect(settings.settingEdits).toEqual({});
  });

  it("brings the open screen with unsaved edits back to its layout, without a question", async () => {
    api();
    useInventoryStore().inventory = inventory(screen("hall"));
    const session = useSessionStore(), ui = useUiStore();
    session.select("hall");
    addTile("light.b");
    ui.tab = "settings";
    openSaverStep("clock");
    const asked = answerDialogs(false);
    await session.select("hall");
    expect([asked.length, ui.tab, state.inspector, doc.dirty, doc.layout?.tiles.length]).toEqual([0, "layout", null, true, 1]);
  });

  it("goes home from the logo: the overview, after asking about unsaved edits", async () => {
    api();
    useInventoryStore().inventory = inventory(screen("hall"));
    const session = useSessionStore(), ui = useUiStore();
    ui.go("#settings");
    await session.goHome();
    expect(ui.route).toBe("");
    session.select("hall");
    addTile("light.b");
    let yes = false;
    const asked = answerDialogs(() => yes);
    await session.goHome();
    expect([asked.length, useScreenStore().selected]).toEqual([1, "hall"]);
    yes = true;
    await session.goHome();
    expect([useScreenStore().selected, doc.dirty, ui.route]).toEqual([null, false, ""]);
  });

  it("opens a new preview screen at once", () => {
    api();
    useInventoryStore().inventory = inventory(screen("hall"));
    const preview = useSessionStore().createVirtualScreen("Desk preview", customPreview);
    expect(useScreenStore().selected).toBe(preview.id);
    expect(doc.document?.title).toBe("Desk preview");
  });
});

describe("removing a screen", () => {
  it("closes the open screen without asking, forgets its build and reads the inventory again", async () => {
    const add = api({ "DELETE screens/:id": { name: "Hall screen", kept: [] }, "GET inventory": { connected: true, screens: [], entities: [] } });
    const hall = screen("hall");
    useInventoryStore().inventory = inventory(hall, screen("desk"));
    const session = useSessionStore(), builds = useBuildsStore();
    session.select("hall");
    addTile("light.b");
    builds.updating = ["hall"];
    const asked = answerDialogs(false);
    const deleting = add.defer("DELETE screens/:id");
    const removing = session.removeScreen(hall);
    expect(useScreenStore().removing).toBe("hall");
    // Once at a time: another removal waits for this one.
    expect(await session.removeScreen(useInventoryStore().inventory.screens[1])).toBe(false);
    deleting.resolve();
    expect(await removing).toBe(true);
    expect(asked).toEqual([]);
    expect([useScreenStore().selected, doc.document, doc.dirty, builds.updating, useScreenStore().removing]).toEqual([null, null, false, [], null]);
    expect(useUiStore().notice?.message).toBe(t("editor.sidebar.remove.done", { name: "Hall screen" }));
    expect(add.calls.filter((r) => r.path.startsWith("inventory")).map((r) => r.path)).toEqual(["inventory"]);
    expect(add.asked("GET inventory")[0].query.get("light")).toBe("1");
  });

  it("keeps a screen the add-on refused to remove, open as it was", async () => {
    api({ "DELETE screens/:id": failure(409, "The screen is building") });
    const hall = screen("hall");
    useInventoryStore().inventory = inventory(hall);
    const session = useSessionStore();
    session.select("hall");
    expect(await session.removeScreen(hall)).toBe(false);
    expect([useScreenStore().selected, useInventoryStore().inventory.screens.length, useUiStore().notice?.message]).toEqual(["hall", 1, "The screen is building"]);
  });
});

describe("a new inventory", () => {
  it("prunes the builds, settles the settings and reads the open draft again, in that order", async () => {
    const hall = screen("hall");
    useInventoryStore().inventory = inventory(hall);
    api();
    const session = useSessionStore(), builds = useBuildsStore(), settings = useSettingsStore();
    session.select("hall");
    const heard: string[] = [];
    builds.$onAction(({ name }) => { heard.push(name); });
    settings.$onAction(({ name }) => { heard.push(name); });
    const newer = { ...structuredClone(hall), page_document: { ...structuredClone(hall.page_document!), revision: "newer" } };
    api({ "GET inventory": inventory(newer) });
    addTile("light.b");
    await useInventoryStore().refresh(false);
    expect(heard).toEqual(["prune", "settleSettings"]);
    // This page has unsaved edits and the add-on a newer draft: a conflict, said and not overwritten.
    expect([doc.conflict, doc.layout?.tiles.length]).toEqual([true, 1]);
    // No screen open: the builds alone.
    answerDialogs(true);
    await session.select(null);
    heard.length = 0;
    await useInventoryStore().refresh(false);
    expect(heard).toEqual(["prune"]);
  });
});
