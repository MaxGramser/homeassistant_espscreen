// Undo says what it does (stores/document.ts with model/change-label.ts): the toolbar's buttons name the step they take
// back or do again, an undo or a redo says what it did with the way back at hand, the words travel from undo to redo and
// back, and a toast's own Undo leaves the toast that follows it.
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import LayoutView from "../src/components/LayoutView.vue";
import Toast from "../src/components/Toast.vue";
import { moveTileToPage, removeTile, setTileName } from "../src/editor/tiles";
import { useDocumentStore } from "../src/stores/document";
import { useInventoryStore } from "../src/stores/inventory";
import { useUiStore } from "../src/stores/ui";
import type { Inventory, Screen } from "../src/types";
import { fakeApi } from "./helpers/fake-api";
import { openScreen, screenFixture } from "./helpers/fixtures";

function hall() {
  fakeApi({ states: { states: {} }, capabilities: { capabilities: {} }, "POST header-preview": { items: [] } });
  const screen = screenFixture({ id: "hall", name: "Hall", firmware: "0.53.0", online: true, in_sync: true,
    layout: { title: "Hall", pages: 2, tiles: [{ entity: "light.a", name: "Lamp", slot: 0 }, { entity: "switch.b", name: "Fan", slot: 1 }] } } as unknown as Screen);
  useInventoryStore().inventory = { csrf: "t", connected: true, entities: [], screens: [screen] } as unknown as Inventory;
  openScreen("hall");
  return useDocumentStore();
}

describe("undo that says what it does", () => {
  it("names the step each way, and says what an undo or a redo did with the way back", () => {
    const doc = hall(), ui = useUiStore();
    expect([doc.undoWhat, doc.redoWhat]).toEqual(["", ""]);
    moveTileToPage(doc.layout!.tiles[0], 1);
    setTileName(doc.layout!.tiles.find((tile) => tile.entity === "switch.b")!, "Ceiling fan");
    expect(doc.undoWhat).toBe("Fan renamed");
    doc.undo();
    expect([doc.undoWhat, doc.redoWhat]).toEqual(["Lamp moved to page 2", "Fan renamed"]);
    expect(ui.notice?.message).toBe("Undone: Fan renamed");
    expect(ui.notice?.action?.label).toBe("Redo");
    ui.notice!.action!.run();
    expect(ui.notice?.message).toBe("Redone: Fan renamed");
    expect(ui.notice?.action?.label).toBe("Undo");
    // A new edit retires the toast of the step before it.
    setTileName(doc.layout!.tiles.find((tile) => tile.entity === "switch.b")!, "Fan");
    expect(ui.notice).toBeNull();
  });

  it("puts the words on the toolbar's buttons, and the toast's own Undo leaves the toast that follows", async () => {
    const doc = hall();
    const view = mount(LayoutView, { attachTo: document.body });
    const toast = mount(Toast, { attachTo: document.body });
    expect(view.find("#undo").attributes("title")).toBe("Undo · ⌘Z");
    removeTile(doc.layout!.tiles[1]);
    await flushPromises();
    expect(view.find("#undo").attributes("title")).toBe("Undo: Fan removed · ⌘Z");
    expect(view.find("#undo").attributes("aria-label")).toBe("Undo: Fan removed");
    expect(toast.text()).toContain("Fan removed");
    await toast.find("button").trigger("click");
    expect(doc.layout!.tiles).toHaveLength(2);
    expect(toast.text()).toContain("Undone: Fan removed");
    expect(view.find("#redo").attributes("title")).toBe("Redo: Fan removed · ⇧⌘Z");
  });
});
