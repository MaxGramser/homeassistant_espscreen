// Placing units of tiles on pages (model/placement.ts): the one path the first layout and Layoutbot share. Generic units
// here, no home: sections only around two tiles or more, units of a share together, what fills and what waits, a unit
// cut over pages, screens without sections, and the screen's tiles, pages and memory.
import { describe, expect, it } from "vitest";
import type { PageLayout, ScreenMemory } from "../src/types";
import { memoryUse, NEARLY_FULL } from "../src/model/memory";
import { projectLayout, sectionOf, tilesIn, validatePages } from "../src/model/pages";
import { placeUnits, type PlaceTarget, type PlaceTile, type PlaceUnit } from "../src/model/placement";

let n = 0;
const tile = (columns = 1, rows = 1, rank = 1, entity = `light.t${++n}`): PlaceTile => ({
  tile: { content: { kind: "entity", entityId: entity }, appearance: { label: entity.split(".")[1] }, interaction: {} }, columns, rows, rank, entity });
const unit = (key: string, tiles: PlaceTile[], extra: Partial<PlaceUnit> = {}): PlaceUnit => ({
  key, title: key, tiles, page: { title: key }, share: key, run: key, ...extra });
const target = (extra: Partial<PlaceTarget> = {}): PlaceTarget => ({ grid: { columns: 5, rows: 5 }, pages: 8, tiles: 64, sections: true, ...extra });
const valid = (pages: PageLayout["pages"], t: PlaceTarget) => validatePages({ title: "T", homePageId: pages[0].id, pages }, { ...t.grid, pages: t.pages });
const titles = (pages: PageLayout["pages"]) => pages.map((page) => page.topbar.title.source === "text" ? page.topbar.title.text : "");

describe("a section groups", () => {
  it("two tiles or more; a lone tile stands loose", () => {
    const t = target();
    const { pages, sections } = placeUnits([unit("Lights", [tile(), tile()], { share: "a" }), unit("Weather", [tile(2, 2)], { share: "a" })], t);
    valid(pages, t);
    expect(sections).toBe(1);
    expect(pages[0].sections!.map((s) => s.title)).toEqual(["Lights"]);
    expect(pages[0].tiles).toHaveLength(3);
    expect(pages[0].tiles.filter((x) => !sectionOf(pages[0], x))).toHaveLength(1);
  });
  it("is cut over pages, its title kept, when it is taller than a page", () => {
    const t = target({ grid: { columns: 3, rows: 3 } });
    const { pages } = placeUnits([unit("Lights", Array.from({ length: 13 }, () => tile()))], t);
    valid(pages, t);
    expect(pages.length).toBe(2);
    for (const page of pages) expect(page.sections!.map((s) => s.title)).toEqual(["Lights"]);
    expect(pages.flatMap((page) => page.sections!.map((s) => tilesIn(page, s).length))).toEqual([9, 4]);
  });
});

describe("units on pages", () => {
  it("share a page with units of their share, and start a new one for another", () => {
    const { pages } = placeUnits([unit("A", [tile(), tile()], { share: "x" }), unit("B", [tile(), tile()], { share: "x" }), unit("C", [tile(), tile()], { share: "y" })], target());
    expect(pages.map((page) => page.sections!.map((s) => s.title))).toEqual([["A", "B"], ["C"]]);
  });
  it("fill what is left of another share's page, and wait for it when their own page is full", () => {
    const big = unit("Room", [tile(5, 2), tile(), tile()], { share: "room" });
    const house = [unit("W", [tile(2, 2), tile()], { share: "house", fills: true, waits: true }), unit("X", [tile(5, 4), tile(5, 1)], { share: "house", waits: true })];
    const { pages } = placeUnits([house[1], house[0], big], target());
    // X takes the house's page; W does not fit beside it, waits, and fills the room's page.
    expect(pages.map((page) => page.sections!.map((s) => s.title))).toEqual([["X"], ["Room", "W"]]);
  });
  it("take the title the caller gives a page of several", () => {
    const { pages } = placeUnits([unit("A", [tile(), tile()], { share: "x" }), unit("B", [tile(), tile()], { share: "x" })],
      target({ title: (units) => ({ title: units.map((u) => u.key).join(" & ") }) }));
    expect(titles(pages)).toEqual(["A & B"]);
  });
});

describe("a screen without sections", () => {
  const t = target({ grid: { columns: 2, rows: 3 }, sections: false, pages: 3 });
  it("gives each run pages of its own, loose tiles only", () => {
    const { pages } = placeUnits([unit("A", [tile(), tile()], { run: "a" }), unit("A2", [tile()], { run: "a" }), unit("B", [tile()], { run: "b" })], { ...t, pages: 8 });
    valid(pages, { ...t, pages: 8 });
    expect(pages.every((page) => !page.sections)).toBe(true);
    expect(titles(pages)).toEqual(["A", "B"]);
    expect(pages[0].tiles).toHaveLength(3);
  });
  it("puts neighbouring pages together and leaves a run's spilt last tile when pages are short", () => {
    const { pages, left } = placeUnits([unit("A", Array.from({ length: 7 }, (_, i) => tile(1, 1, i))), unit("B", [tile()]), unit("C", [tile()]), unit("D", [tile()])], t);
    expect(pages.length).toBe(3);
    expect(left.map((x) => [x.unit, x.why, x.tile.rank])).toEqual([["A", "pages", 6]]);
    expect(pages[0].tiles).toHaveLength(6);
  });
});

describe("what the screen holds", () => {
  it("its tile ceiling and its pages, the least wanted going first", () => {
    const keep = tile(1, 1, 0), drop = tile(1, 1, 9);
    const { pages, left } = placeUnits([unit("A", [drop, keep, tile(1, 1, 1)])], target({ tiles: 2 }));
    const ids = pages.flatMap((page) => page.tiles.map((x) => (x.content as { entityId: string }).entityId));
    expect(left).toEqual([{ tile: drop, unit: "A", why: "tiles" }]);
    expect(ids).toContain(keep.entity);
    expect(ids).not.toContain(drop.entity);
    expect(placeUnits([unit("A", [tile(4, 5)]), unit("B", [tile(4, 5)])], target({ pages: 1, sections: false })).left.map((x) => [x.unit, x.why])).toEqual([["B", "cells"]]);
  });
  it("its memory, as a proposal holds to it", () => {
    const memory: ScreenMemory = { room: 20000, used: 0, psram: false, tile: 64, extra: 96, page: 32 };
    const t = target({ grid: { columns: 2, rows: 3 }, sections: false, memory });
    const { pages, left } = placeUnits([unit("A", Array.from({ length: 30 }, () => tile(1, 1, 1, `media_player.p${++n}`)))], t);
    expect(left.length).toBeGreaterThan(0);
    expect(new Set(left.map((x) => x.why))).toEqual(new Set(["memory"]));
    const use = memoryUse(projectLayout({ title: "T", homePageId: pages[0].id, pages }, { ...t.grid, pages: 8 }).tiles, memory, pages);
    expect(use.share).toBeLessThan(NEARLY_FULL);
  });
});
