// The bedside clock (app 0.4.12): its keys are tiles without a cell. The document keeps them under their clock; the
// editor's tile list has them as tiles that name their clock (`in`) and their place (`key`), so they are edited, opened
// and counted like every tile.
import { describe, expect, it } from "vitest";
import type { PageGrid } from "../src/types";
import { arrangeTiles, emptyLayout, projectLayout, validatePages } from "../src/model/pages";
import { createLayout, entriesOf, keysOf } from "../src/model/layout";

const grid: PageGrid = { columns: 2, rows: 3 };
function bedside() {
  const clock = { entity: "screen.nightstand", name: "", slot: 0, options: { size: "full", background: "none" } };
  return arrangeTiles(emptyLayout("Bedroom"), grid, [
    { tile: clock, slot: 0 },
    { tile: { entity: "light.bedside", name: "Lamp", slot: -1, in: "screen.nightstand", key: 0 }, slot: -1 },
    { tile: { entity: "lock.front", name: "Front door", slot: -1, in: "screen.nightstand", key: 1, options: { guard: "lock_only" } }, slot: -1 },
  ]);
}

describe("bedside clock keys", () => {
  it("keeps keys as children of their clock and lists them as tiles after the placed ones", () => {
    const layout = bedside();
    const clock = layout.pages[0].tiles[0];
    expect(clock.children?.map((child) => child.content.entityId)).toEqual(["light.bedside", "lock.front"]);
    expect(clock.children?.[1].interaction).toEqual({ guard: "lock_only" });
    const view = projectLayout(layout, grid);
    expect(view.tiles.map((tile) => [tile.entity, tile.in, tile.key])).toEqual([
      ["screen.nightstand", undefined, undefined], ["light.bedside", "screen.nightstand", 0], ["lock.front", "screen.nightstand", 1]]);
    expect(entriesOf(view).map((entry) => entry.tile.entity)).toEqual(["screen.nightstand"]);
    expect(keysOf(view, view.tiles[0]).map((tile) => tile.entity)).toEqual(["light.bedside", "lock.front"]);
  });
  it("keeps a key's id when the key is edited like a tile", () => {
    const layout = bedside(), view = projectLayout(layout, grid);
    const lamp = view.tiles.find((tile) => tile.entity === "light.bedside")!;
    lamp.name = "Bed lamp";
    lamp.options = { tap: "detail" };
    const next = arrangeTiles(layout, grid, view.tiles.map((tile) => ({ tile, slot: tile.slot })));
    const child = next.pages[0].tiles[0].children![0];
    expect(child.id).toBe(layout.pages[0].tiles[0].children![0].id);
    expect(child.appearance.label).toBe("Bed lamp");
    expect(child.interaction).toEqual({ tap: "detail" });
  });
  it("keeps a clock's keys when only the placed tiles are arranged", () => {
    const layout = bedside(), view = projectLayout(layout, grid);
    const next = arrangeTiles(layout, grid, entriesOf(view));
    expect(next.pages[0].tiles[0].children).toHaveLength(2);
  });
  it("takes an entity as a key and as a tile (firmware 0.16.0+), but one bedside clock", () => {
    const layout = bedside();
    layout.pages.push({ ...layout.pages[0], id: "a".repeat(16), tiles: [{ id: "tile2", content: { kind: "entity", entityId: "light.bedside" },
      placement: { row: 0, column: 0, columns: 1, rows: 1 }, appearance: { label: "" }, interaction: {} }],
      topbar: { ...layout.pages[0].topbar, leading: [], trailing: [] } });
    expect(() => validatePages(layout, grid)).not.toThrow();
    layout.pages[1].tiles[0].content = { kind: "builtin", name: "nightstand" };
    layout.pages[1].tiles[0].placement = { row: 0, column: 0, columns: grid.columns, rows: grid.rows };
    expect(() => validatePages(layout, grid)).toThrow("bedside clock can only be on a screen once");
  });
  it("gives children only to the bedside clock", () => {
    const layout = bedside();
    layout.pages[0].tiles[0].content = { kind: "builtin", name: "clock" };
    expect(() => validatePages(layout, grid)).toThrow();
  });
  it("never packs a key into a cell, also on a screen whose pages are all full", () => {
    const { hasGaps, normalize } = createLayout(() => grid);
    const tiles = Array.from({ length: 8 }, (_, page) => ({ entity: page ? `sensor.page_${page}` : "screen.nightstand", name: "", slot: page * 6, options: { size: "full" } }));
    const layout = { title: "B", tiles: [...tiles, { entity: "light.bedside", name: "Lamp", slot: -1, in: "screen.nightstand", key: 0 }] };
    expect(() => hasGaps(layout.tiles)).not.toThrow();
    normalize(layout);
    expect(layout.tiles.at(-1)!.entity).toBe("light.bedside");
  });
});
