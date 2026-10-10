// The draft of the open screen (stores/document.ts): undo kept to its last hundred steps and to what the editor shows
// (the map's steps only in the map), unsaved worked out from what was saved (so undoing back to it is saved again),
// saving with the add-on's answers held back (an edit made meanwhile stays unsaved), the map's own save while another
// screen opens, a newer save arriving with the inventory (read again, or a conflict said over unsaved edits, and resolved
// either way), and a layout exported and imported again.
import { describe, expect, it, vi } from "vitest";
import { i18n } from "../../src/i18n";
import { DraftHistory } from "../../src/model/draft-history";
import { clone } from "../../src/model/pages";
import { addPage, setScreenTitle } from "../../src/editor/pages";
import { setTileName } from "../../src/editor/tiles";
import { useDocumentStore } from "../../src/stores/document";
import { useInventoryStore } from "../../src/stores/inventory";
import { useScreenStore } from "../../src/stores/screen";
import { useUiStore } from "../../src/stores/ui";
import type { Inventory, PageDocument, PageWorkspace, Screen } from "../../src/types";
import { clipboardText } from "../helpers/browser";
import { answerDialogs } from "../helpers/dialogs";
import { fakeApi, failure, type ApiRequest } from "../helpers/fake-api";
import { openScreen, screenFixture } from "../helpers/fixtures";

const t = (key: string, named: Record<string, unknown> = {}) => i18n.global.t(key, named);
const screen = (id: string, tiles: { entity: string; name: string; slot: number }[] = [], pages = 1) =>
  screenFixture({ id, name: id, online: true, firmware: "0.53.0", layout: { title: id, tiles, pages } } as unknown as Screen);
const saved = (id: string) => useInventoryStore().inventory.screens.find((item) => item.id === id)!.page_document as PageDocument;

// The add-on as the draft meets it: the inventory with every screen's saved document, a save checked against the
// revision it started from (a newer one refused, as the add-on does), and the map saved on its own.
function addon(...screens: Screen[]) {
  const kept = new Map(screens.map((item) => [item.id, clone(item)]));
  let revisions = 0;
  const inventory = (): Inventory => ({ connected: true, screens: [...kept.values()].map(clone), entities: [] }) as unknown as Inventory;
  const api = fakeApi({
    inventory, states: { states: {} }, capabilities: { capabilities: {} }, "POST header-preview": { items: [] },
    "PUT screens/:id": ({ params, body }: ApiRequest) => {
      const record = kept.get(params.id)!.page_document as PageDocument;
      if (body.revision !== record.revision) return failure(409, "Changed elsewhere");
      const next: PageDocument = { ...record, revision: `r${++revisions}`, layout: body.layout, ...(body.workspace ? { workspace: { ...body.workspace, revision: `w${revisions}` } } : {}) };
      kept.get(params.id)!.page_document = next;
      return { saved: true, document: next };
    },
    "PUT screens/:id/workspace": ({ params, body }: ApiRequest) => {
      const record = kept.get(params.id)!.page_document as PageDocument;
      record.workspace = { ...body.workspace, revision: `w${++revisions}` };
      return record.workspace as PageWorkspace;
    },
  });
  useInventoryStore().inventory = inventory();
  /** Another tab saves this screen: a newer revision, with `change` made to its layout. */
  const elsewhere = (id: string, change: (record: PageDocument) => void) => {
    const record = clone(kept.get(id)!.page_document as PageDocument);
    change(record);
    record.revision = `r${++revisions}`;
    kept.get(id)!.page_document = record;
    return record;
  };
  /** What the add-on holds of a screen now. */
  const record = (id: string) => kept.get(id)!.page_document as PageDocument;
  return { api, inventory, elsewhere, record };
}

describe("undo", () => {
  it("keeps the last hundred steps, and the map's steps for the map alone", () => {
    const history = new DraftHistory<number>();
    for (let step = 0; step < 101; step++) history.remember(step);
    expect(history.counts(false)).toEqual({ undo: 100, redo: 0 });
    let last = -1, entry;
    while ((entry = history.step("undo", -1, false))) last = entry.value;
    // The first step went to make room: undoing everything ends on the second.
    expect(last).toBe(1);
    expect(history.counts(false)).toEqual({ undo: 0, redo: 100 });

    const map = new DraftHistory<string>();
    map.remember("title"); map.remember("map", "workspace"); map.remember("tile");
    expect([map.counts(false), map.counts(true)]).toEqual([{ undo: 2, redo: 0 }, { undo: 3, redo: 0 }]);
    // In the row the map's step is passed over and stays where it is, to be undone in the map.
    expect(map.step("undo", "now", false)?.value).toBe("tile");
    expect(map.step("undo", "now", false)?.value).toBe("title");
    expect(map.step("undo", "now", false)).toBeUndefined();
    expect(map.counts(true)).toEqual({ undo: 1, redo: 2 });
    expect(map.step("undo", "now", true)).toEqual({ value: "map", scope: "workspace" });
    // A new step leaves nothing to redo.
    map.remember("again");
    expect(map.counts(true)).toEqual({ undo: 1, redo: 0 });
  });
  it("counts the draft's steps as the editor shows them, and is saved again when undone back to what was saved", () => {
    addon(screen("hall", [], 2));
    openScreen("hall");
    const doc = useDocumentStore();
    for (let step = 1; step <= 101; step++) setScreenTitle(`Hall ${step}`);
    expect([doc.undoCount, doc.redoCount, doc.dirty]).toEqual([100, 0, true]);
    doc.undo();
    expect([doc.undoCount, doc.redoCount, doc.document!.title]).toEqual([99, 1, "Hall 100"]);
    // The map's move is a step of the map: counted there, passed over in the row.
    doc.setEditorMode("advanced");
    doc.moveWorkspacePage(doc.document!.pages[1].id, 7, 7);
    expect(doc.undoCount).toBe(100);
    doc.setEditorMode("simple");
    expect(doc.undoCount).toBe(99);
    // Unsaved is what differs from the saved draft: back at it, nothing is.
    for (let step = 0; step < 99; step++) doc.undo();
    // The first step went to make room for the hundred and first: the saved title is one edit away.
    expect([doc.undoCount, doc.document!.title, doc.dirty]).toEqual([0, "Hall 1", true]);
    setScreenTitle("hall");
    expect(doc.dirty).toBe(false);
  });
});

describe("saving", () => {
  it("keeps an edit made while the save is on its way unsaved, and says so", async () => {
    const { api } = addon(screen("hall", [{ entity: "light.a", name: "Lamp", slot: 0 }]));
    openScreen("hall");
    const doc = useDocumentStore(), ui = useUiStore(), started = doc.documentRevision;
    setScreenTitle("Hall");
    const answer = api.defer("PUT screens/:id");
    const saving = doc.save();
    expect(doc.busy).toBe(true);
    // A second save waits for the first.
    await doc.save();
    expect(api.count("PUT screens/:id")).toBe(1);
    setTileName(doc.layout!.tiles[0], "Reading lamp");
    answer.resolve();
    await saving;
    expect(api.asked("PUT screens/:id")[0].body).toMatchObject({ revision: started, layout: { title: "Hall" } });
    expect([doc.busy, doc.documentRevision, doc.dirty, doc.saved, doc.conflict]).toEqual([false, "r1", true, 0, false]);
    expect(ui.notice?.message).toBe(t("editor.screen_view.saved.newer_edit"));
    // The next save sends the rest, from the revision the first one made.
    await doc.save();
    expect(api.asked("PUT screens/:id")[1].body).toMatchObject({ revision: "r1" });
    expect([doc.dirty, doc.documentRevision, ui.notice?.message]).toEqual([false, "r2", t("editor.screen_view.saved.current")]);
    expect(doc.saved).toBeGreaterThan(0);
  });
  it("says a conflict when another tab saved first, and keeps this draft or reads the saved one as chosen", async () => {
    const { api, elsewhere } = addon(screen("hall"));
    openScreen("hall");
    const doc = useDocumentStore();
    setScreenTitle("Mine");
    elsewhere("hall", (record) => { record.layout.title = "Theirs"; });
    // Refused for its revision: the draft stays, the conflict is said.
    await doc.save();
    expect([doc.conflict, doc.dirty, doc.document!.title]).toEqual([true, true, "Mine"]);
    // Keep mine: sent over the revision seen now, and saved.
    await doc.resolveLayoutConflict("keep");
    expect(api.asked("PUT screens/:id").at(-1)!.body).toMatchObject({ revision: "r1", layout: { title: "Mine" } });
    expect([doc.conflict, doc.dirty, saved("hall").layout.title]).toEqual([false, false, "Mine"]);
    // Again, and this time the saved one is read.
    setScreenTitle("Mine again");
    elsewhere("hall", (record) => { record.layout.title = "Theirs again"; });
    await doc.save();
    expect(doc.conflict).toBe(true);
    await doc.resolveLayoutConflict("reload");
    expect([doc.conflict, doc.dirty, doc.undoCount, doc.document!.title]).toEqual([false, false, 0, "Theirs again"]);
  });
  it("changes nothing for a conflict while the add-on cannot be reached", async () => {
    const { api, elsewhere } = addon(screen("hall"));
    openScreen("hall");
    const doc = useDocumentStore();
    setScreenTitle("Mine");
    elsewhere("hall", () => {});
    await doc.save();
    api.on("inventory", failure(502, "Bad gateway"));
    await doc.resolveLayoutConflict("reload");
    expect([doc.conflict, doc.document!.title]).toEqual([true, "Mine"]);
  });
  it("saves the map of the screen that was open, and the next one's after it, when another opens on the way", async () => {
    const { api, record } = addon(screen("hall", [], 2), screen("desk", [], 2));
    vi.useFakeTimers();
    openScreen("hall");
    const doc = useDocumentStore();
    doc.setEditorMode("advanced");
    await vi.advanceTimersByTimeAsync(400);
    const hall = api.defer("PUT screens/:id/workspace");
    doc.moveWorkspacePage(doc.document!.pages[1].id, 5, 5);
    await vi.advanceTimersByTimeAsync(400);
    expect(api.asked("PUT screens/:id/workspace").at(-1)!.params.id).toBe("hall");
    openScreen("desk");
    doc.setEditorMode("advanced");
    doc.moveWorkspacePage(doc.document!.pages[1].id, 9, 9);
    const desk = doc.documentRevision;
    // The desk's save waits for the hall's answer, which changes nothing of the desk's map.
    await vi.advanceTimersByTimeAsync(400);
    hall.resolve();
    await vi.advanceTimersByTimeAsync(0);
    expect(doc.workspaceDirty).toBe(true);
    await vi.advanceTimersByTimeAsync(400);
    const last = api.asked("PUT screens/:id/workspace").at(-1)!;
    expect([last.params.id, last.body.revision, last.body.workspace.positions[doc.document!.pages[1].id]]).toEqual(["desk", desk, { x: 9, y: 9 }]);
    expect([doc.workspaceDirty, doc.workspace.revision]).toEqual([false, record("desk").workspace!.revision]);
    expect(record("hall").workspace!.positions[record("hall").layout.pages[1].id]).toEqual({ x: 5, y: 5 });
  });
});

describe("a newer save arriving with the inventory", () => {
  it("is read into the draft, keeping the page and the tile chosen", () => {
    const { elsewhere } = addon(screen("hall", [{ entity: "light.a", name: "Lamp", slot: 0 }], 2));
    openScreen("hall");
    const doc = useDocumentStore();
    const page = doc.document!.pages[1].id, tile = doc.layout!.tiles[0].id!;
    doc.selectedPageId = page; doc.selectedTileId = tile;
    const record = elsewhere("hall", (next) => { next.layout.title = "Hallway"; });
    useInventoryStore().applyLive({ screens: [{ ...useScreenStore().currentScreen!, page_document: record }] });
    expect([doc.document!.title, doc.documentRevision, doc.selectedPageId, doc.selectedTileId, doc.dirty]).toEqual(["Hallway", record.revision, page, tile, false]);
  });
  it("is a conflict over unsaved edits, and the draft stays", () => {
    const { elsewhere } = addon(screen("hall"));
    openScreen("hall");
    const doc = useDocumentStore();
    addPage();
    const record = elsewhere("hall", (next) => { next.layout.title = "Hallway"; });
    useInventoryStore().applyLive({ screens: [{ ...useScreenStore().currentScreen!, page_document: record }] });
    expect([doc.conflict, doc.document!.pages.length, doc.document!.title]).toEqual([true, 2, "hall"]);
  });
});

describe("a layout exported and imported again", () => {
  it("brings the pages, titles, tiles and map of one screen to another, with ids of its own, as one step of undo", async () => {
    const { api } = addon(screen("hall", [{ entity: "light.a", name: "Lamp", slot: 0 }, { entity: "screen.page_2", name: "More", slot: 1 }], 2), screen("desk"));
    api.on("POST screens/:id/import", ({ body }: ApiRequest) => ({ format: "pages-v2", revision: "imported", layout: body.document.layout,
      sourceGrid: body.sourceGrid, workspace: { revision: "w", positions: body.document.editor.positions } }));
    // The download the export starts, and the copy it makes (a secure page's clipboard).
    vi.stubGlobal("URL", Object.assign(class extends URL {}, { createObjectURL: vi.fn(() => "blob:layout"), revokeObjectURL: vi.fn() }));
    vi.stubGlobal("isSecureContext", true);
    const downloads: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) { downloads.push(this.download); });
    openScreen("hall");
    const doc = useDocumentStore();
    setScreenTitle("Hall");
    doc.moveWorkspacePage(doc.document!.pages[1].id, 4, 2);
    const hall = clone(doc.document!), positions = doc.workspacePositions();
    doc.exportLayout();
    await vi.waitFor(() => expect(clipboardText()).not.toBe(""));
    const text = clipboardText();
    expect(downloads).toEqual(["hall.layout.json"]);
    expect(text).toBe(doc.layoutJson());
    expect(JSON.parse(text)).toMatchObject({ esp_screens_layout: 2, sourceGrid: { columns: 2, rows: 3 } });

    // Leaving the edited screen asks first.
    answerDialogs(true);
    await openScreen("desk");
    const desk = clone(doc.document!);
    await doc.importLayout(text);
    // The same pages, titles and tiles, the Go to page tile leading to the same page, the same places on the map: other ids.
    const ids = (layout: typeof hall) => layout.pages.map((page) => page.id);
    const shape = (layout: typeof hall) => ({ title: layout.title, home: ids(layout).indexOf(layout.homePageId), pages: layout.pages.map((page) => ({
      title: page.topbar.title, tiles: page.tiles.map(({ content, placement, appearance }) => ({ placement, appearance,
        content: content.kind === "navigation" && content.target.kind === "page" ? ids(layout).indexOf(content.target.pageId) : content })) })) });
    expect(shape(doc.document!)).toEqual(shape(hall));
    expect(ids(doc.document!).some((id) => ids(hall).includes(id))).toBe(false);
    expect(ids(doc.document!).map((id) => doc.workspace.positions[id])).toEqual(ids(hall).map((id) => positions[id]));
    expect([doc.dirty, doc.undoCount, useUiStore().notice?.message]).toEqual([true, 1, t("editor.layout.imported")]);
    doc.undo();
    expect([doc.document, doc.dirty]).toEqual([desk, false]);
  });
});
