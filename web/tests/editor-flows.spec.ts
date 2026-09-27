import { screenFixture } from "./page-fixtures";
// Editor flows that quietly broke with the page documents of app 0.3.1, found in the audit of app 0.4.1.
import { flushPromises, mount } from "@vue/test-utils";
import { defineComponent, h, nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DevicePage from "../src/components/DevicePage.vue";
import TileCard from "../src/components/TileCard.vue";
import PageInspector from "../src/components/PageInspector.vue";
import { addPage, beginFieldEdit, endFieldEdit, goHome, liveEntries, placeTile, retargetPageTile, select, setTileOption, state } from "../src/store";

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ states: {}, capabilities: {} }))));
  vi.stubGlobal("confirm", vi.fn(() => true));
  state.dirty = false; state.selected = null; state.toast = null;
  state.inventory = { screens: [screenFixture({ id: "test", name: "Test", firmware: "0.4.0", online: true,
    layout: { title: "Home", tiles: [{ entity: "light.a", name: "A", slot: 0 }, { entity: "light.b", name: "B", slot: 1 }] } } as any)],
    entities: [], icons: { groups: [], weather: {}, sun: {}, defaults: {}, fallback: "F0335", builtin: {}, controls: {} } } as any;
  select("test");
});

describe("the editor", () => {
  it("keeps moving a tile with the arrow keys: the focus follows the tile, not the cell", async () => {
    const host = mount(defineComponent({ setup: () => () => h("div", { class: "pages" }, [h(DevicePage, { page: 0, entries: liveEntries(), pages: 1, moving: null })]) }), { attachTo: document.body });
    const a = () => state.layout!.tiles.find((t) => t.name === "A")!;
    const card = () => host.element.querySelector<HTMLElement>(`[data-tile-id="${a().id}"]`)!;
    for (const expected of [2, 4]) {
      card().focus();
      card().dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
      await flushPromises(); await nextTick();
      expect(a().slot).toBe(expected);
      expect(document.activeElement).toBe(card());
    }
    host.unmount();
  });

  it("leaves nothing unsaved after going home from the logo past a confirmed discard", () => {
    setTileOption(state.layout!.tiles[0], "icon", "lightbulb");
    expect(state.dirty).toBe(true);
    goHome();
    expect(state.selected).toBeNull();
    expect(state.dirty).toBe(false);
  });

  it("calls a change that changes nothing no change, whatever order the add-on wrote the fields in", () => {
    // A tile as the add-on writes it after a migration: placement before appearance.
    select(null);
    const layout = state.inventory.screens[0].page_document!.layout as any;
    const tile = layout.pages[0].tiles[0];
    tile.appearance.icon = "lightbulb";
    layout.pages[0].tiles[0] = { id: tile.id, content: tile.content, placement: tile.placement, interaction: tile.interaction, appearance: tile.appearance };
    select("test");
    // Picking the icon the tile already has.
    setTileOption(state.layout!.tiles[0], "icon", "lightbulb");
    expect(state.undoCount).toBe(0);
    expect(state.dirty).toBe(false);
  });

  it("draws the second line the tile panel chose on the mockup: nothing, own words or a value", () => {
    state.liveStates["light.a"] = { state: "on", word: "On", a: { brightness: 128 } };
    const card = (sub?: string) => mount(TileCard, { props: { tile: { ...state.layout!.tiles[0], options: sub ? { sub } : {} }, slot: 0 } }).find(".st");
    expect(card().text()).toBe("On");
    expect(card("none").exists()).toBe(false);
    expect(card("text:Sofa left").text()).toBe("Sofa left");
    expect(card("attr:brightness").text()).toBe("128");
    // A value Home Assistant does not report leaves the line to the screen, as on the glass.
    expect(card("attr:effect").text()).toBe("On");
  });

  it("never pushes a wide tile onto a new page to make room for a single one (app 0.4.2)", () => {
    // Page 1 is full: A B / W W / C E.
    state.inventory.screens[0] = screenFixture({ ...state.inventory.screens[0], layout: { title: "Home", tiles: [
      { entity: "light.a", name: "A", slot: 0 }, { entity: "light.b", name: "B", slot: 1 },
      { entity: "light.w", name: "W", slot: 2, options: { size: "wide" } },
      { entity: "light.c", name: "C", slot: 4 }, { entity: "light.e", name: "E", slot: 5 }] } } as any);
    select(null); select("test");
    const pagesBefore = state.document!.pages.length;
    // E onto W: W does not fit in the one cell E leaves, and page 1 has no other room, so nothing moves.
    expect(placeTile(state.layout!.tiles.find((t) => t.name === "E")!, 2)).toBe(false);
    expect(state.document!.pages.length).toBe(pagesBefore);
    expect(state.layout!.tiles.find((t) => t.name === "W")!.slot).toBe(2);
    // A tile in the way that fits in the cell left behind still swaps.
    expect(placeTile(state.layout!.tiles.find((t) => t.name === "E")!, 4)).toBe(true);
    expect(state.layout!.tiles.find((t) => t.name === "C")!.slot).toBe(5);
  });

  it("makes typing words of your own one step of undo (app 0.4.2)", () => {
    const tile = state.layout!.tiles[0];
    beginFieldEdit(`sub:${tile.id}`);
    for (const words of ["S", "So", "Sof", "Sofa"]) setTileOption(state.layout!.tiles[0], "sub", `text:${words}`, `sub:${tile.id}`);
    endFieldEdit();
    expect(state.layout!.tiles[0].options?.sub).toBe("text:Sofa");
    expect(state.undoCount).toBe(1);
  });

  it("saves a page title without the spaces at its ends, and keeps them while typing (app 0.4.2)", async () => {
    addPage();
    const id = state.document!.pages[1].id;
    const view = mount(PageInspector, { props: { id } });
    const input = view.find("#owned-page-title");
    await input.trigger("focus");
    await input.setValue("Study ");
    expect((input.element as HTMLInputElement).value).toBe("Study ");
    expect(state.document!.pages[1].topbar.title).toEqual({ source: "text", text: "Study" });
  });

  it("keeps a link that follows Home one when it is sent to the home page (app 0.4.2)", () => {
    state.inventory.screens[0] = screenFixture({ ...state.inventory.screens[0], layout: { title: "Home", pages: 2, tiles: [{ entity: "screen.page_1", name: "", slot: 6 }] } } as any);
    const record = state.inventory.screens[0].page_document as any;
    record.layout.pages[1].tiles[0].content.target = { kind: "home" };
    select(null); select("test");
    const link = state.layout!.tiles[0];
    retargetPageTile(link, 1);
    expect(state.document!.pages[1].tiles[0].content).toEqual({ kind: "navigation", target: { kind: "home" } });
    retargetPageTile(state.layout!.tiles[0], 2);
    expect((state.document!.pages[1].tiles[0].content as any).target.kind).toBe("page");
  });
});
