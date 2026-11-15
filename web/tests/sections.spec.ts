// Sections on a page (docs/PAGES.md "Sections", model/sections.ts): the rows they make, and every edit a section takes,
// over the slot view and back into the document through arrangeTiles, as the editor does it.
import { describe, expect, it } from "vitest";
import type { Page, PageGrid, PageLayout, PageTile, Section } from "../src/types";
import { adaptGrid, arrangeTiles, emptyLayout, looseTiles, projectLayout, removeSection, tilesIn, validatePages } from "../src/model/pages";
import { createLayout, sectionTile } from "../src/model/layout";
import { readKept } from "../src/model/kept-draft";
import { emptySection, insertIntoSection, insideMargins, looseBeside, looseRowAbove, makeSection, movedSection, packTiles, resizeSection, roundDiv,
  type SectionEdit } from "../src/model/sections";

const grid: PageGrid = { columns: 4, rows: 3 };
let n = 0;
const tile = (entity: string, row: number, column: number, columns = 1, rows = 1): PageTile => ({ id: `t${++n}`, content: { kind: "entity", entityId: entity },
  placement: { row, column, columns, rows }, appearance: { label: entity }, interaction: {} });
// A test names a section with the tiles in it, each placed from the section's corner, because that reads well. The
// document keeps none of that: every tile stands on its page at its own cell, and is its section's by lying in its block.
type Named = Section & { tiles?: PageTile[] };
function layoutOf(tiles: PageTile[], sections?: Named[], g = grid): PageLayout {
  const layout = emptyLayout("House");
  layout.pages[0].tiles = [...tiles];
  for (const { tiles: mine = [], ...section } of sections ?? []) {
    (layout.pages[0].sections ??= []).push(section);
    for (const t of mine) layout.pages[0].tiles.push({ ...t, placement: { ...t.placement, row: t.placement.row + section.placement.row,
      column: t.placement.column + section.placement.column } });
  }
  return validatePages(layout, g);
}
/** A section's tiles as a test reads them: placed from the section's corner. */
const held = (page: Page, section: Section): PageTile[] => tilesIn(page, section).map((t) => ({ ...t, placement: { ...t.placement,
  row: t.placement.row - section.placement.row, column: t.placement.column - section.placement.column } }));
const applied = (layout: PageLayout, edit: SectionEdit, g = grid) => {
  if ("refused" in edit) throw new Error(edit.refused);
  return arrangeTiles(layout, g, edit.entries, edit.blocks);
};
const cells = (layout: PageLayout, g = grid) => Object.fromEntries(projectLayout(layout, g).tiles.map((t) => [t.entity, t.slot]));

describe("the room a section takes from its own tiles", () => {
  // The cases of tests/test_section_layout.cpp: the 10.1-inch at 6 x 5, header 49, padding 11, three rows.
  const m = { header: 49, titleTop: 19, inset: 22, pad: 11 };
  it("is the firmware's, rounded half away from zero, and every tile inside is the same height", () => {
    expect(insideMargins(m, 3, 0, 0)).toEqual({ top: 49, bottom: -29 });
    expect(insideMargins(m, 3, 1, 1)).toEqual({ top: 29, bottom: -9 });
    expect(insideMargins(m, 3, 2, 2)).toEqual({ top: 9, bottom: 11 });
    expect(insideMargins(m, 3, 0, 2)).toEqual({ top: 49, bottom: 11 });
    expect(insideMargins(m, 1, 0, 0)).toEqual({ top: 49, bottom: 11 });
    expect([roundDiv(5, 2), roundDiv(-5, 2), roundDiv(4, 3), roundDiv(-4, 3)]).toEqual([3, -3, 1, -1]);
  });
});

describe("adding an empty section", () => {
  it("takes two by two around the chosen cell, shifted to stay on free cells, and moves nothing", () => {
    const layout = layoutOf([tile("light.a", 0, 0), tile("lock.c", 2, 3)]);
    const view = projectLayout(layout, grid);
    const result = applied(layout, emptySection(view, grid, 0, { row: 1, column: 3 }, "New"));
    const section = result.pages[0].sections![0];
    expect(section).toMatchObject({ title: "New", placement: { row: 0, column: 2, columns: 2, rows: 2 } });
    expect(tilesIn(result.pages[0], section)).toEqual([]);
    expect(cells(result)).toEqual(cells(layout));
  });
  it("gets smaller where the cell has no room around it, and refuses a page with no free cell", () => {
    const tiles = [tile("light.a", 0, 0), tile("light.b", 0, 2), tile("light.c", 1, 0), tile("light.d", 1, 1), tile("light.e", 1, 2)];
    const layout = layoutOf(tiles);
    const one = emptySection(projectLayout(layout, grid), grid, 0, { row: 0, column: 1 }, "Lights");
    expect("refused" in one ? null : one.blocks.at(-1)).toMatchObject({ row: 0, column: 1, columns: 1, rows: 1 });
    const full = layoutOf(Array.from({ length: 12 }, (_, i) => tile(`light.f${i}`, Math.floor(i / 4), i % 4)));
    expect(emptySection(projectLayout(full, grid), grid, 0, null, "None")).toEqual({ refused: "editor.sections.no_room" });
  });
  it("without a cell goes to the first free place in reading order", () => {
    const layout = layoutOf([tile("light.a", 0, 0), tile("light.b", 0, 1)]);
    const edit = emptySection(projectLayout(layout, grid), grid, 0, null, "Next");
    expect("refused" in edit ? null : edit.blocks.at(-1)).toMatchObject({ row: 0, column: 2, columns: 2, rows: 2 });
  });
});

describe("making a section of chosen tiles", () => {
  it("makes the block where a rectangle of chosen tiles stands, and nothing else moves", () => {
    const layout = layoutOf([tile("light.a", 0, 0), tile("light.b", 0, 1), tile("lock.c", 2, 3)]);
    const view = projectLayout(layout, grid);
    const chosen = view.tiles.filter((t) => t.entity.startsWith("light."));
    const result = applied(layout, makeSection(view, grid, chosen, "Lights"));
    const section = result.pages[0].sections![0];
    expect(section).toMatchObject({ title: "Lights", placement: { row: 0, column: 0, columns: 2, rows: 1 } });
    expect(held(result.pages[0], section).map((t) => t.placement)).toEqual([{ row: 0, column: 0, columns: 1, rows: 1 }, { row: 0, column: 1, columns: 1, rows: 1 }]);
    expect(looseTiles(result.pages[0]).map((t) => t.content)).toEqual([{ kind: "entity", entityId: "lock.c" }]);
    // The slots the screen gets are the ones it had: a section adds its block, never moves a tile in place.
    expect(cells(result)).toEqual(cells(layout));
  });
  it("gives a choice that is no rectangle a block at its first tile, in reading order, and moves loose tiles aside", () => {
    const layout = layoutOf([tile("light.a", 0, 0), tile("switch.x", 0, 1), tile("light.b", 1, 2)]);
    const view = projectLayout(layout, grid);
    const result = applied(layout, makeSection(view, grid, view.tiles.filter((t) => t.entity.startsWith("light.")), "Lights"));
    const section = result.pages[0].sections![0];
    expect(section.placement).toEqual({ row: 0, column: 0, columns: 3, rows: 1 });
    expect(cells(result)["light.a"]).toBe(0);
    expect(cells(result)["light.b"]).toBe(1);
    // The switch was in the block's way: it stands loose on the nearest free cell.
    expect(cells(result)["switch.x"]).not.toBeLessThan(3);
  });
  it("refuses tiles of two pages, a tile already in a section and a tile over the whole page", () => {
    const layout = layoutOf([tile("light.a", 0, 0)], [{ id: "5ec7000000000001", title: "In", placement: { row: 1, column: 0, columns: 2, rows: 1 },
      tiles: [tile("light.b", 0, 0)] }]);
    const view = projectLayout(layout, grid);
    expect(makeSection(view, grid, view.tiles, "Both")).toEqual({ refused: "editor.sections.already_in" });
  });
});

describe("a section's size", () => {
  const sectioned = () => layoutOf([tile("light.x", 1, 0)], [{ id: "5ec7000000000001", title: "Lights", placement: { row: 0, column: 0, columns: 2, rows: 1 },
    tiles: [tile("light.a", 0, 0), tile("light.b", 0, 1)] }]);
  it("narrower lays its tiles out again in reading order and pushes a loose tile in the way aside", () => {
    const layout = sectioned(), view = projectLayout(layout, grid);
    const result = applied(layout, resizeSection(view, grid, "5ec7000000000001", 1, 1));
    expect(result.pages[0].sections![0].placement).toEqual({ row: 0, column: 0, columns: 1, rows: 2 });
    expect(cells(result)["light.a"]).toBe(0);
    expect(cells(result)["light.b"]).toBe(4);
    expect(cells(result)["light.x"]).not.toBe(4);
  });
  it("wider keeps its tiles where they are", () => {
    const layout = sectioned(), view = projectLayout(layout, grid);
    const result = applied(layout, resizeSection(view, grid, "5ec7000000000001", 4, 1));
    expect(result.pages[0].sections![0].placement.columns).toBe(4);
    expect(cells(result)["light.b"]).toBe(1);
  });
  it("is taken away with its tiles kept loose where they are, or with them", () => {
    const layout = sectioned();
    const kept = removeSection(layout, grid, "5ec7000000000001");
    expect(kept.pages[0].sections).toBeUndefined();
    expect(cells(kept)).toEqual(cells(layout));
    const gone = removeSection(layout, grid, "5ec7000000000001", true);
    expect(Object.keys(cells(gone))).toEqual(["light.x"]);
  });
});

describe("a section carried whole", () => {
  it("lands with its tiles and pushes loose tiles out of its way", () => {
    const layout = layoutOf([tile("light.x", 2, 0)], [{ id: "5ec7000000000001", title: "Lights", placement: { row: 0, column: 0, columns: 2, rows: 1 },
      tiles: [tile("light.a", 0, 0), tile("light.b", 0, 1)] }]);
    const view = projectLayout(layout, grid), editor = createLayout(() => grid, () => 8, () => view.sections ?? []);
    const block = view.sections![0];
    const own = new Set(view.tiles.filter((t) => t.entity !== "light.x"));
    const arranged = editor.arrange(view.tiles.filter((t) => !own.has(t)), sectionTile(block, 0), 8);
    const result = applied(layout, movedSection(view, grid, block.id, arranged));
    expect(result.pages[0].sections![0].placement).toMatchObject({ row: 2, column: 0 });
    expect(cells(result)["light.a"]).toBe(8);
    expect(cells(result)["light.x"]).not.toBe(8);
  });
});

describe("loose tiles beside sections", () => {
  it("are found, and become a row of their own above the sections", () => {
    const layout = layoutOf([tile("lock.a", 0, 2), tile("lock.b", 0, 3)], [{ id: "5ec7000000000001", title: "Lights",
      placement: { row: 0, column: 0, columns: 2, rows: 2 }, tiles: [tile("light.a", 0, 0)] }]);
    const view = projectLayout(layout, grid);
    expect(looseBeside(view, grid, 0).map((t) => t.entity)).toEqual(["lock.a", "lock.b"]);
    const result = applied(layout, looseRowAbove(view, grid, 0));
    expect(cells(result)["lock.a"]).toBe(0);
    expect(cells(result)["lock.b"]).toBe(1);
    expect(result.pages[0].sections![0].placement.row).toBe(1);
  });
});

describe("a draft from the days sections held their own tiles", () => {
  it("comes back with every tile on its page at its own cell", () => {
    const layout = layoutOf([tile("lock.a", 0, 0)]);
    const first = JSON.parse(JSON.stringify(layout));
    first.pages[0].sections = [{ id: "5ec7000000000001", title: "Lights", placement: { row: 1, column: 1, columns: 2, rows: 1 },
      tiles: [tile("light.a", 0, 0), tile("light.b", 0, 1)] }];
    const kept = readKept(JSON.stringify({ v: 1, tab: "t", revision: null, at: 1, layout: first, grid }))!;
    const page = validatePages(kept.layout, grid).pages[0];
    expect(page.tiles.map((t) => [t.placement.row, t.placement.column])).toEqual([[0, 0], [1, 1], [1, 2]]);
    expect(tilesIn(page, page.sections![0]).length).toBe(2);
    expect("tiles" in page.sections![0]).toBe(false);
  });
});

describe("a grid change with sections", () => {
  it("keeps a section's place where it is free and moves it whole otherwise", () => {
    const layout = layoutOf([tile("lock.a", 0, 0)], [{ id: "5ec7000000000001", title: "Lights", placement: { row: 1, column: 1, columns: 3, rows: 2 },
      tiles: [tile("light.a", 0, 0), tile("light.b", 0, 2), tile("light.c", 1, 1)] }]);
    const kept = adaptGrid(layout, grid, { columns: 4, rows: 4 });
    expect(kept.pages[0].sections![0].placement).toEqual({ row: 1, column: 1, columns: 3, rows: 2 });
    // Two columns: the section is too wide, gets narrower, and its tiles go in reading order.
    const narrow = adaptGrid(layout, grid, { columns: 2, rows: 4 });
    const page = narrow.pages.find((p) => p.sections?.length)!, section = page.sections![0];
    expect(section.placement.columns).toBe(2);
    expect(held(page, section).map((t) => [t.placement.row, t.placement.column]).sort()).toEqual([[0, 0], [0, 1], [1, 0]]);
  });
  it("leaves a page without sections exactly as before", () => {
    const layout = layoutOf([tile("lock.a", 0, 3), tile("lock.b", 2, 2)]);
    const result = adaptGrid(layout, grid, { columns: 3, rows: 3 });
    expect(result.pages[0].sections).toBeUndefined();
    expect(result.pages[0].tiles.map((t) => [t.placement.row, t.placement.column])).toEqual([[2, 2], [0, 0]]);
  });
});

it("packs tiles in reading order, a tile wider than the block shrunk to it", () => {
  const view = projectLayout(layoutOf([tile("light.a", 0, 0, 2), tile("light.b", 1, 0)]), grid);
  const packed = packTiles(view.tiles, 1, grid);
  expect([...packed.places.values()].map((p) => [p.row, p.column, p.size])).toEqual([[0, 0, "single"], [1, 0, "single"]]);
  expect(packed.rows).toBe(2);
});

describe("a tile dropped into a section, as an app into a folder", () => {
  const full = () => layoutOf([tile("lock.x", 2, 0), tile("lock.y", 1, 2)], [{ id: "5ec7000000000001", title: "Lights",
    placement: { row: 0, column: 0, columns: 2, rows: 1 }, tiles: [tile("light.a", 0, 0), tile("light.b", 0, 1)] },
    { id: "5ec7000000000002", title: "Doors", placement: { row: 0, column: 2, columns: 2, rows: 1 }, tiles: [tile("lock.d", 0, 0)] }]);
  it("takes its place in reading order and the section grows by a row, loose tiles making room", () => {
    const layout = full(), view = projectLayout(layout, grid);
    const moving = view.tiles.find((t) => t.entity === "lock.y")!;
    // Let go on light.b: lock.y goes before it, light.b moves on to the next row.
    const result = applied(layout, insertIntoSection(view, grid, moving, "5ec7000000000001", 1));
    const lights = result.pages[0].sections![0];
    expect(lights.placement.rows).toBe(2);
    expect(held(result.pages[0], lights).map((t) => [t.content.kind === "entity" && t.content.entityId, t.placement.row, t.placement.column]))
      .toEqual(expect.arrayContaining([["light.a", 0, 0], ["lock.y", 0, 1], ["light.b", 1, 0]]));
    expect(looseTiles(result.pages[0]).map((t) => t.content.kind === "entity" && t.content.entityId)).toEqual(["lock.x"]);
  });
  it("goes from one section into another", () => {
    const layout = full(), view = projectLayout(layout, grid);
    const moving = view.tiles.find((t) => t.entity === "light.b")!;
    const result = applied(layout, insertIntoSection(view, grid, moving, "5ec7000000000002", 3));
    const doors = result.pages[0].sections![1];
    expect(tilesIn(result.pages[0], doors).map((t) => t.content.kind === "entity" && t.content.entityId).sort()).toEqual(["light.b", "lock.d"]);
    expect(tilesIn(result.pages[0], result.pages[0].sections![0]).length).toBe(1);
  });
  it("takes a new tile from the library", () => {
    const layout = full(), view = projectLayout(layout, grid);
    const fresh = { entity: "light.new", name: "New", slot: -1 };
    const result = applied(layout, insertIntoSection(view, grid, fresh, "5ec7000000000002", 3));
    expect(tilesIn(result.pages[0], result.pages[0].sections![1]).map((t) => t.content.kind === "entity" && t.content.entityId)).toContain("light.new");
  });
});

describe("a section whose tiles follow its contrast", () => {
  it("is only taken beside the contrast itself, and the slot view carries it", () => {
    const section = { id: "5ec7000000000001", title: "Doors", placement: { row: 0, column: 0, columns: 2, rows: 1 }, tiles: [tile("lock.a", 0, 0)] };
    expect(() => layoutOf([], [{ ...section, contrastTiles: true }])).toThrow();
    const layout = layoutOf([], [{ ...section, contrast: true, contrastTiles: true }]);
    expect(projectLayout(layout, grid).sections![0]).toMatchObject({ contrast: true, contrastTiles: true });
  });
});
