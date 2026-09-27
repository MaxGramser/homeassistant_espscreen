import { screenFixture } from "./page-fixtures";
// Editor flows that quietly broke with the page documents of app 0.3.1, found in the audit of app 0.4.1.
import { flushPromises, mount } from "@vue/test-utils";
import { defineComponent, h, nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DevicePage from "../src/components/DevicePage.vue";
import { goHome, liveEntries, select, setTileOption, state } from "../src/store";

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
});
