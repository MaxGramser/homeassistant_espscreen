// The drawer beside the mockup (stores/inspector.ts): a tile's drawer closes the moment its tile goes, however it goes, and
// stays open while the tile only changes; every drawer closes when the draft is replaced as a whole, a cell marked on
// another screen forgotten with it; the screensaver's drawers close when the layout comes back; and one place at a time
// is marked for the next tile from the library.
import { describe, expect, it } from "vitest";
import { nextTick } from "vue";
import { removePage } from "../../src/editor/pages";
import { addTile, removeTile, setTileName } from "../../src/editor/tiles";
import { useDocumentStore } from "../../src/stores/document";
import { useInspectorStore } from "../../src/stores/inspector";
import { useInventoryStore } from "../../src/stores/inventory";
import { useUiStore } from "../../src/stores/ui";
import type { Inventory, PageDocument, Screen, Tile } from "../../src/types";
import { answerDialogs } from "../helpers/dialogs";
import { fakeApi } from "../helpers/fake-api";
import { openScreen, screenFixture } from "../helpers/fixtures";

const screen = (id: string, tiles: Tile[] = [], pages = 1) =>
  screenFixture({ id, name: id, online: true, firmware: "0.53.0", layout: { title: id, tiles, pages } } as unknown as Screen);
function open(...screens: Screen[]) {
  fakeApi({ states: { states: {} }, capabilities: { capabilities: {} }, "POST header-preview": { items: [] } });
  useInventoryStore().inventory = { connected: true, screens, entities: [] } as unknown as Inventory;
  openScreen(screens[0].id);
  return { doc: useDocumentStore(), insp: useInspectorStore() };
}
const tileOf = (entity: string) => useDocumentStore().layout!.tiles.find((tile) => tile.entity === entity)!;

describe("a tile's drawer", () => {
  it("closes when its tile is taken off, its page goes, or undo takes it back, and stays open while it changes", () => {
    const { doc, insp } = open(screen("hall", [{ entity: "light.a", name: "Lamp", slot: 0 }, { entity: "light.b", name: "", slot: 6 }], 2));
    insp.openTile(tileOf("light.a"));
    insp.optionPreview = { tileId: tileOf("light.a").id!, key: "icon", value: "lamp" };
    setTileName(tileOf("light.a"), "Reading lamp");
    expect([insp.inspector, doc.currentTile?.name]).toEqual([{ kind: "tile" }, "Reading lamp"]);
    removeTile(tileOf("light.a"));
    expect([insp.inspector, doc.selectedTileId, insp.optionPreview]).toEqual([null, null, null]);
    // Its page removed.
    insp.openTile(tileOf("light.b"));
    removePage(1);
    expect([insp.inspector, doc.selectedTileId]).toEqual([null, null]);
    // A tile just added, opened, and taken back by undo.
    addTile("light.c");
    expect(doc.currentTile?.entity).toBe("light.c");
    doc.undo();
    expect([insp.inspector, doc.currentTile]).toEqual([null, undefined]);
  });
  it("closes when a key of a bedside clock goes, and not when the clock changes", () => {
    const { insp } = open(screen("bedroom", [{ entity: "screen.nightstand", name: "", slot: 0, options: { size: "full" } },
      { entity: "light.bedside", name: "Lamp", slot: -1, in: "screen.nightstand", key: 0 }]));
    insp.openTile(tileOf("light.bedside"));
    setTileName(tileOf("screen.nightstand"), "Night");
    expect(insp.inspector).toEqual({ kind: "tile" });
    removeTile(tileOf("light.bedside"));
    expect(insp.inspector).toBeNull();
  });
});

describe("every drawer", () => {
  it("closes when another screen opens, forgetting a cell marked on this one", async () => {
    const { doc, insp } = open(screen("hall", [], 2), screen("desk"));
    insp.openPage(doc.document!.pages[1].id);
    insp.insert = { kind: "cell", slot: 3 };
    await openScreen("desk");
    expect([insp.inspector, insp.insert, insp.insertAt]).toEqual([null, null, -1]);
  });
  it("closes when the draft is replaced by a copy, keeping the cell marked", () => {
    const { doc, insp } = open(screen("hall", [{ entity: "light.a", name: "", slot: 0 }]), screen("desk", [{ entity: "light.b", name: "", slot: 0 }]));
    insp.openBar(0);
    insp.insert = { kind: "cell", slot: 2 };
    answerDialogs(true);
    doc.copyLayoutFrom("desk");
    expect(doc.layout!.tiles.map((tile) => tile.entity)).toEqual(["light.b"]);
    expect([insp.inspector, insp.insertAt]).toEqual([null, 2]);
    expect((useInventoryStore().inventory.screens[1].page_document as PageDocument).layout.title).toBe("desk");
  });
  it("of the screensaver closes when the layout comes back, and a tile's stays", async () => {
    const { insp } = open(screen("hall", [{ entity: "light.a", name: "", slot: 0 }]));
    const ui = useUiStore();
    ui.tab = "settings";
    await nextTick();
    insp.openSaverStep("clock");
    ui.tab = "layout";
    await nextTick();
    expect(insp.inspector).toBeNull();
    insp.openTile(tileOf("light.a"));
    ui.tab = "settings";
    await nextTick();
    ui.tab = "layout";
    await nextTick();
    expect(insp.inspector).toEqual({ kind: "tile" });
  });
});

describe("the place for the next tile", () => {
  it("is one at a time: a key place marked forgets a cell, and a tile added there forgets it", async () => {
    const { doc, insp } = open(screen("bedroom", [{ entity: "screen.nightstand", name: "", slot: 0 }]));
    insp.insert = { kind: "cell", slot: 4 };
    insp.insert = { kind: "key", holder: tileOf("screen.nightstand").id!, key: 0 };
    expect([insp.insertAt, insp.insertKey]).toEqual([-1, { holder: tileOf("screen.nightstand").id, key: 0 }]);
    await addTile("light.bedside");
    expect(tileOf("light.bedside")).toMatchObject({ in: "screen.nightstand", key: 0 });
    expect([insp.insert, doc.currentTile?.entity]).toEqual([null, "light.bedside"]);
    insp.insert = { kind: "cell", slot: 4 };
    await addTile("light.desk");
    expect([tileOf("light.desk").slot, insp.insert]).toEqual([4, null]);
  });
});
