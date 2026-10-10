// A tile's name is easy to find (inspector/NameField.vue, inspector/TitleButton.vue): the drawer starts with a Name field,
// Home Assistant's name in grey and a key back to it once another is typed; the drawer's title, the tile's menu and a
// double click on the name on the mockup all bring the focus there, its text selected. A page's title the same way, from
// its menu and its title over the mockup.
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { nextTick } from "vue";
import PageInspector from "../src/components/PageInspector.vue";
import TileCard from "../src/components/TileCard.vue";
import TileInspector from "../src/components/TileInspector.vue";
import { useDocumentStore } from "../src/stores/document";
import { useInspectorStore } from "../src/stores/inspector";
import { useInventoryStore } from "../src/stores/inventory";
import type { Inventory, Tile } from "../src/types";
import { appendTiles, current, loadLayout } from "./helpers/fixtures";

function lamp(name = "") {
  useInventoryStore().inventory = { csrf: "t", connected: true, screens: [], entities: [{ id: "light.a", name: "Kitchen light", domain: "light" }] } as unknown as Inventory;
  loadLayout({ title: "Hall", tiles: [] });
  const tile: Tile = { entity: "light.a", name, slot: 0 };
  appendTiles(tile);
  return current(tile)!;
}
const field = (view: { find: (s: string) => any }) => view.find("#tile-name").element as HTMLInputElement;

describe("a tile's name", () => {
  it("is the drawer's first field, Home Assistant's name in grey, and goes back to it with one key", async () => {
    const tile = lamp();
    const view = mount(TileInspector, { props: { tile }, attachTo: document.body });
    expect(view.find(".dr-body > .name-sec label").text()).toBe("Name on the screen");
    expect([field(view).value, field(view).placeholder, view.find("#tile-name-reset").exists()]).toEqual(["", "Kitchen light", false]);
    await view.find("#tile-name").trigger("focus");
    field(view).value = "Spots";
    await view.find("#tile-name").trigger("input");
    expect(current(tile)!.name).toBe("Spots");
    await view.setProps({ tile: current(tile)! });
    expect(view.find("#tile-name-reset").attributes("aria-label")).toBe("Back to Kitchen light");
    // The key takes the focus from the field first, as a click does in a browser: going back is a step of its own.
    await view.find("#tile-name").trigger("blur");
    await view.find("#tile-name-reset").trigger("click");
    await view.setProps({ tile: current(tile)! });
    expect([current(tile)!.name, view.find("#tile-name-reset").exists()]).toEqual(["", false]);
    expect(useDocumentStore().undoWhat).toBe("Spots renamed");
  });

  it("is reached from the drawer's title, which says it can be renamed", async () => {
    const tile = lamp("Spots");
    const view = mount(TileInspector, { props: { tile }, attachTo: document.body });
    const title = view.find(".dr-head .dr-title-btn");
    expect([title.find("b").text(), title.attributes("aria-label")]).toEqual(["Spots", "Rename: Spots"]);
    await title.trigger("click");
    await flushPromises();
    expect(document.activeElement).toBe(field(view));
    expect([field(view).selectionStart, field(view).selectionEnd]).toEqual([0, 5]);
    // Asked once: a drawer opened again later leaves the focus where it is.
    expect(useInspectorStore().naming).toBeNull();
  });

  it("is reached with a double click on the name on the mockup", async () => {
    const tile = lamp("Spots");
    const card = mount(TileCard, { props: { tile, slot: 0 }, attachTo: document.body });
    await card.find(".nm").trigger("dblclick");
    const insp = useInspectorStore();
    expect([insp.inspector, useDocumentStore().selectedTileId, insp.naming?.kind, insp.naming?.id]).toEqual([{ kind: "tile" }, tile.id, "tile", tile.id]);
    // Elsewhere on the card a double click is two clicks.
    insp.naming = null;
    await card.find(".tile").trigger("dblclick");
    expect(insp.naming).toBeNull();
  });
});

describe("a page's title", () => {
  it("is ready to be typed when the page is renamed", async () => {
    loadLayout({ title: "Hall", tiles: [], pages: 2 });
    const id = useDocumentStore().document!.pages[1].id;
    useInspectorStore().renamePage(id);
    const view = mount(PageInspector, { props: { id }, attachTo: document.body });
    await nextTick(); await nextTick();
    expect(document.activeElement?.id).toBe("owned-page-title");
    expect(useInspectorStore().inspector).toEqual({ kind: "page", id });
    view.unmount();
  });
});
