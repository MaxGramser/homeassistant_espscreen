import { describe, expect, it } from "vitest";
import { MINI_HEIGHT, MINI_WIDTH, miniatureOf } from "../src/model/miniature";
import { emptyLayout } from "../src/model/pages";
import type { PageTile, Screen } from "../src/types";

// A screen as the inventory gives it, with a home page of the tiles at the given places.
const tileAt = (row: number, column: number, columns = 1, rows = 1): PageTile =>
  ({ id: `t${row}${column}`, content: { kind: "entity", entityId: "light.a" }, placement: { row, column, columns, rows }, appearance: { label: "A" }, interaction: {} });
function screen(shape: { width: number; height: number }, grid: { columns: number; rows: number }, tiles: PageTile[], more: Partial<Screen> = {}): Screen {
  const layout = emptyLayout("Hall");
  layout.pages[0].tiles = tiles;
  return { id: "text.hall", name: "Hall", online: true, shape: { ...shape, ...grid },
    page_document: { format: "pages-v2", layout, sourceGrid: grid, revision: "r1" }, ...more } as unknown as Screen;
}

describe("a screen's miniature in the sidebar", () => {
  it("keeps the proportions of its glass inside its room", () => {
    const square = miniatureOf(screen({ width: 480, height: 480 }, { columns: 3, rows: 3 }, []));
    expect([square.width, square.height]).toEqual([MINI_HEIGHT, MINI_HEIGHT]);
    const wide = miniatureOf(screen({ width: 1280, height: 800 }, { columns: 8, rows: 5 }, []));
    expect(wide.width).toBe(MINI_WIDTH);
    expect(wide.height).toBeCloseTo(MINI_WIDTH * 800 / 1280, 2);
    const upright = miniatureOf(screen({ width: 480, height: 800 }, { columns: 3, rows: 5 }, []));
    expect(upright.height).toBe(MINI_HEIGHT);
    expect(upright.width).toBeCloseTo(MINI_HEIGHT * 480 / 800, 2);
  });
  it("draws the tiles of the home page where they stand, a wide one over its cells", () => {
    const mini = miniatureOf(screen({ width: 480, height: 480 }, { columns: 3, rows: 3 }, [tileAt(0, 0, 2), tileAt(0, 2), tileAt(2, 1, 2, 1)]));
    expect(mini.lit).toBe(true);
    expect(mini.tiles).toHaveLength(3);
    const [wide, single, low] = mini.tiles;
    // The wide tile starts where the first cell does and ends where the second one does; the single one follows it.
    expect(wide.x).toBe(3);
    expect(wide.width).toBeCloseTo(2 * single.width + 1, 1);
    expect(single.x).toBeCloseTo(wide.x + wide.width + 1, 1);
    expect(single.y).toBe(wide.y);
    // Every tile stays inside the glass.
    for (const tile of mini.tiles) {
      expect(tile.x + tile.width).toBeLessThanOrEqual(mini.width - 3 + 0.01);
      expect(tile.y + tile.height).toBeLessThanOrEqual(mini.height - 3 + 0.01);
    }
    expect(low.y).toBeGreaterThan(single.y);
  });
  it("cuts a tile that reaches past the grid and leaves out one that lies outside it", () => {
    const mini = miniatureOf(screen({ width: 320, height: 240 }, { columns: 2, rows: 3 }, [tileAt(0, 1, 3), tileAt(5, 0)]));
    expect(mini.tiles).toHaveLength(1);
    expect(mini.tiles[0].x + mini.tiles[0].width).toBeLessThanOrEqual(mini.width - 3 + 0.01);
  });
  it("is a dark glass for a screen that is away, and an empty one without a saved page", () => {
    const away = miniatureOf(screen({ width: 480, height: 480 }, { columns: 3, rows: 3 }, [tileAt(0, 0)], { online: false }));
    expect(away.lit).toBe(false);
    expect(away.tiles).toEqual([]);
    const fresh = miniatureOf({ id: "text.new", name: "New", online: true } as unknown as Screen);
    expect(fresh.lit).toBe(true);
    expect(fresh.tiles).toEqual([]);
    // Without a shape it is the smallest screen there is.
    expect(fresh.width / fresh.height).toBeCloseTo(320 / 240, 1);
  });
  it("lights a preview screen, which is never online", () => {
    expect(miniatureOf(screen({ width: 480, height: 480 }, { columns: 3, rows: 3 }, [tileAt(0, 0)], { online: false, virtual: true })).lit).toBe(true);
  });
});
