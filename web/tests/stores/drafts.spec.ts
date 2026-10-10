// Work survives a reload (stores/drafts.ts, model/kept-draft.ts): the open screen's unsaved draft is kept in this
// browser as it changes, offered when the screen is opened again ("Unsaved changes from 10:42"), restored as one step of
// undo or discarded, taken through the conflict when the screen was saved since, gone once saved or left behind on
// purpose, never kept for a preview screen, and never taken away from another tab; old and surplus drafts go.
import { flushPromises, mount } from "@vue/test-utils";
import LayoutView from "../../src/components/LayoutView.vue";
import { describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import { setTileName } from "../../src/editor/tiles";
import { customPreview } from "../../src/model/preview";
import { KEPT_MS, KEPT_SCREENS, keptKey, keptToForget, keptWhen, readKept, writeKept, type KeptDraft } from "../../src/model/kept-draft";
import { clone } from "../../src/model/pages";
import { useDocumentStore } from "../../src/stores/document";
import { useDraftsStore } from "../../src/stores/drafts";
import { useInventoryStore } from "../../src/stores/inventory";
import { useSessionStore } from "../../src/stores/session";
import type { Inventory, PageDocument, Screen } from "../../src/types";
import { answerDialogs } from "../helpers/dialogs";
import { fakeApi, failure, type ApiRequest } from "../helpers/fake-api";
import { screenFixture } from "../helpers/fixtures";
import { disposePinia, freshPinia } from "../helpers/pinia";

const TEN_42 = new Date(2026, 9, 10, 10, 42).getTime();
const screen = (id: string) => screenFixture({ id, name: id, online: true, firmware: "0.53.0",
  layout: { title: id, tiles: [{ entity: "light.a", name: "Lamp", slot: 0 }] } } as unknown as Screen);

// The add-on with its saved documents: a save checked against its revision, as the add-on does.
function addon(...screens: Screen[]) {
  const kept = new Map(screens.map((item) => [item.id, clone(item)]));
  let revisions = 0;
  const inventory = () => ({ connected: true, screens: [...kept.values()].map(clone), entities: [] }) as unknown as Inventory;
  const api = fakeApi({
    inventory, states: { states: {} }, capabilities: { capabilities: {} }, "POST header-preview": { items: [] },
    "PUT screens/:id": ({ params, body }: ApiRequest) => {
      const record = kept.get(params.id)!.page_document as PageDocument;
      if (body.revision !== record.revision) return failure(409, "Changed elsewhere");
      const next = { ...record, revision: `r${++revisions}`, layout: body.layout };
      kept.get(params.id)!.page_document = next;
      return { saved: true, document: next };
    },
  });
  /** Another browser saves the screen: a newer revision. */
  const elsewhere = (id: string) => { (kept.get(id)!.page_document as PageDocument).revision = `r${++revisions}`; };
  return { api, inventory, elsewhere };
}
// The page as it starts: its stores, the add-on's inventory and what runs while it is open.
function boot(inventory: () => Inventory) {
  useInventoryStore().inventory = inventory();
  useDraftsStore().start();
  return { doc: useDocumentStore(), drafts: useDraftsStore(), session: useSessionStore() };
}
// The page closed and opened again: other stores, the same browser storage.
function reload(inventory: () => Inventory) {
  disposePinia();
  freshPinia();
  return boot(inventory);
}
const stored = (id: string) => readKept(localStorage.getItem(keptKey(id)));
const lamp = () => useDocumentStore().layout!.tiles[0];

describe("a draft kept in this browser", () => {
  it("is kept as it changes, offered after a reload, and restored as one step of undo", async () => {
    vi.useFakeTimers({ now: TEN_42, toFake: ["Date"] });
    const { inventory } = addon(screen("hall"));
    let { doc, drafts, session } = boot(inventory);
    session.select("hall");
    setTileName(lamp(), "Reading lamp");
    await nextTick();
    expect(stored("hall")).toMatchObject({ v: 1, tab: drafts.tab, revision: doc.documentRevision, at: TEN_42, upright: null, grid: { columns: 2, rows: 3 } });
    expect(stored("hall")!.layout).toEqual(doc.document);

    vi.setSystemTime(TEN_42 + 3600000);
    ({ doc, drafts, session } = reload(inventory));
    session.select("hall");
    expect([doc.dirty, lamp().name]).toEqual([false, "Lamp"]);
    expect(drafts.offerText).toBe("Unsaved changes from 10:42 AM");
    drafts.restore();
    expect([drafts.offer, doc.dirty, lamp().name, doc.conflict, doc.undoWhat]).toEqual([null, true, "Reading lamp", false, "unsaved changes restored"]);
    // Undo takes the restored draft back to what was saved.
    doc.undo();
    expect([doc.dirty, lamp().name]).toEqual([false, "Lamp"]);
  });

  it("goes when it is discarded, and when what it kept is saved", async () => {
    const { inventory } = addon(screen("hall"));
    let { doc, drafts, session } = boot(inventory);
    session.select("hall");
    setTileName(lamp(), "Reading lamp");
    await nextTick();
    ({ doc, drafts, session } = reload(inventory));
    session.select("hall");
    // Opening again without an answer keeps it.
    await nextTick();
    expect(stored("hall")).not.toBeNull();
    drafts.discard();
    expect([drafts.offer, stored("hall"), doc.dirty]).toEqual([null, null, false]);

    setTileName(lamp(), "Desk lamp");
    await nextTick();
    expect(stored("hall")?.layout).toEqual(doc.document);
    await doc.save();
    await flushPromises();
    expect([doc.dirty, stored("hall")]).toEqual([false, null]);
  });

  it("goes through the conflict when the screen was saved since it started", async () => {
    const { inventory, elsewhere, api } = addon(screen("hall"));
    let { doc, drafts, session } = boot(inventory);
    session.select("hall");
    const started = doc.documentRevision;
    setTileName(lamp(), "Reading lamp");
    await nextTick();
    elsewhere("hall");
    ({ doc, drafts, session } = reload(inventory));
    session.select("hall");
    expect(doc.documentRevision).not.toBe(started);
    drafts.restore();
    expect([lamp().name, doc.conflict, doc.documentRevision]).toEqual(["Reading lamp", true, started]);
    // A save is refused by the add-on until Keep mine says to write over the newer one.
    await doc.save();
    expect(api.count("PUT screens/:id")).toBe(1);
    expect(doc.conflict).toBe(true);
    await doc.resolveLayoutConflict("keep");
    expect([doc.conflict, doc.dirty, api.count("PUT screens/:id")]).toEqual([false, false, 2]);
  });

  it("is forgotten when the person leaves it behind on purpose, and offers nothing that says what was saved", async () => {
    const { inventory } = addon(screen("hall"), screen("desk"));
    const { drafts, session } = boot(inventory);
    session.select("hall");
    setTileName(lamp(), "Reading lamp");
    await nextTick();
    answerDialogs(true);
    await session.select("desk");
    expect(stored("hall")).toBeNull();
    // A kept draft the same as the saved layout goes quietly.
    const saved = useInventoryStore().inventory.screens.find((item) => item.id === "hall")!.page_document as PageDocument;
    const same: KeptDraft = { v: 1, tab: "other", revision: null, at: Date.now(), layout: clone(saved.layout), grid: { columns: 2, rows: 3 }, upright: null };
    localStorage.setItem(keptKey("hall"), writeKept(same));
    await session.select("hall");
    expect([drafts.offer, stored("hall")]).toEqual([null, null]);
  });

  it("is never kept for a preview screen, and never taken away from another tab", async () => {
    const { inventory } = addon(screen("hall"));
    const { doc, drafts, session } = boot(inventory);
    const preview = session.createVirtualScreen("Desk preview", customPreview);
    doc.editDocument((draft) => { draft.title = "Preview 2"; });
    await nextTick();
    expect(stored(preview.id)).toBeNull();

    answerDialogs(true);
    await session.select("hall");
    const theirs: KeptDraft = { v: 1, tab: "another-tab", revision: doc.documentRevision, at: Date.now(),
      layout: { ...clone(doc.document!), title: "Theirs" }, grid: { columns: 2, rows: 3 }, upright: null };
    drafts.discard();
    localStorage.setItem(keptKey("hall"), writeKept(theirs));
    // This tab edits and undoes back to what was saved: the other tab's draft stays where it is.
    setTileName(lamp(), "Mine");
    await nextTick();
    localStorage.setItem(keptKey("hall"), writeKept(theirs));
    doc.undo();
    await nextTick();
    expect(stored("hall")?.tab).toBe("another-tab");
  });
});

describe("the bar that offers it", () => {
  it("says when the changes are from, and restores or discards them from its keys", async () => {
    vi.useFakeTimers({ now: TEN_42, toFake: ["Date"] });
    const { inventory } = addon(screen("hall"));
    let { session } = boot(inventory);
    session.select("hall");
    setTileName(lamp(), "Reading lamp");
    await nextTick();
    ({ session } = reload(inventory));
    session.select("hall");
    const view = mount(LayoutView, { attachTo: document.body });
    await nextTick();
    expect(view.find("#kept-draft .notice-text").text()).toBe("Unsaved changes from 10:42 AMKept in this browser, not on the screen yet.");
    await view.find("#kept-restore").trigger("click");
    expect([view.find("#kept-draft").exists(), lamp().name]).toEqual([false, "Reading lamp"]);
    useDocumentStore().undo();
    ({ session } = reload(inventory));
    session.select("hall");
    const again = mount(LayoutView, { attachTo: document.body });
    await nextTick();
    await again.find("#kept-discard").trigger("click");
    expect([again.find("#kept-draft").exists(), lamp().name, stored("hall")]).toEqual([false, "Lamp", null]);
  });
});

describe("what is kept and how it is said", () => {
  it("forgets drafts after two weeks, and past eight screens the oldest", () => {
    const now = TEN_42;
    const kept = [{ key: "old", at: now - KEPT_MS - 1 }, { key: "broken", at: null },
      ...Array.from({ length: KEPT_SCREENS }, (_, i) => ({ key: `s${i}`, at: now - i * 1000 }))];
    expect(keptToForget(kept, now)).toEqual(["old", "broken"]);
    expect(keptToForget(kept, now, 1)).toEqual(["old", "broken", `s${KEPT_SCREENS - 1}`]);
  });
  it("reads only what it wrote", () => {
    expect([readKept(null), readKept("{"), readKept('{"v":2}'), readKept(JSON.stringify({ v: 1, tab: "t", at: 1, revision: 3, layout: {}, grid: {} }))]).toEqual([null, null, null, null]);
  });
  it("says the time today, and the day before it otherwise, on the editor's clock", () => {
    expect(keptWhen(TEN_42, TEN_42 + 60000, false, "en")).toBe("10:42 AM");
    expect(keptWhen(TEN_42, TEN_42 + 60000, true, "en")).toBe("10:42");
    expect(keptWhen(TEN_42, TEN_42 + 86400000, true, "en")).toBe("Sa 10 Oct, 10:42");
  });
});
