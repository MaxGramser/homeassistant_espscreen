// What a drag shows (stores/drag.ts): the tile it carries and the arrangement are the draft's own tiles, not copies, so the
// arrangement knows a tile from the grid from a new one; a page on its way follows its place; and nothing is left once it
// ends.
import { describe, expect, it } from "vitest";
import { createLayout } from "../../src/model/layout";
import { useDragStore } from "../../src/stores/drag";
import type { Tile } from "../../src/types";

describe("a drag", () => {
  it("carries the draft's own tile, so an arrangement takes it for the tile on the grid", () => {
    const dragging = useDragStore(), layout = createLayout(() => ({ columns: 2, rows: 3 }));
    const tiles: Tile[] = [{ id: "a", entity: "light.a", name: "", slot: 0 }, { id: "b", entity: "light.b", name: "", slot: 1 }];
    dragging.moving = tiles[0];
    expect(dragging.moving).toBe(tiles[0]);
    // Moved onto the next cell, the two trade places: the tile on its way is the one from the grid, not a new one.
    dragging.preview = layout.arrange(tiles, dragging.moving!, 1);
    expect(dragging.preview!.map(({ tile, slot }) => [tile.id, slot])).toEqual([["b", 0], ["a", 1]]);
    expect(dragging.preview![1].tile).toBe(tiles[0]);
  });
  it("follows a page on its way, and leaves nothing once it ends", () => {
    const dragging = useDragStore();
    dragging.$patch({ active: true, page: { from: 2, to: 2, order: [0, 1, 2] }, key: { holder: "clock", key: 1 }, refused: 1 });
    dragging.page!.to = 1;
    dragging.page!.order = [0, 2, 1];
    expect(dragging.page).toEqual({ from: 2, to: 1, order: [0, 2, 1] });
    dragging.clear();
    expect([dragging.active, dragging.moving, dragging.preview, dragging.page, dragging.key, dragging.refused]).toEqual([false, null, null, null, null, null]);
  });
});
