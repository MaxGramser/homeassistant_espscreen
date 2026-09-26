// The grid rules: the same ones the add-on applies (core.pack_slots, validate_layout) and the firmware draws.
import { describe, expect, it } from "vitest";
import { createLayout, controlsLabel, defaultOptions, effectiveControls, newTile, pageOrder, pagePlaces, pageTarget, reorderTitles, retargetedPage, sizeOf, versionAtLeast } from "../src/model/layout";
let shape = { columns: 2, rows: 3 };
const setGrid = (columns = 2, rows = 3) => { shape = { columns, rows }; };
const { arrange, cellsOf, firstFree, fits, grid, hasGaps, nearestFree, normalize, occupied, packSlots, pageCount, pageStart, reorderPages, rowStart, spanOf, strandedPages, tileLimit } = createLayout(() => shape);
import type { Inventory, Layout, Tile } from "../src/types";

const tile = (entity: string, slot: number, options: Tile["options"] = {}): Tile => ({ entity, name: "", slot, options });
const entries = (tiles: Tile[]) => tiles.map((t) => ({ tile: t, slot: t.slot }));

describe("packing and positions", () => {
  it("keeps the adjacent column free for tall cards and refuses rectangles crossing a page", () => {
    setGrid(2, 3);
    expect(cellsOf(1, 'tall')).toEqual([1, 3]);
    expect(cellsOf(0, 'square')).toEqual([0, 1, 2, 3]);
    expect(fits(new Set([1, 3]), 2, 'single')).toBe(true);
    expect(fits(new Set([1, 3]), 2, 'wide')).toBe(false);
    expect(fits(new Set(), 4, 'tall')).toBe(false);
    expect(packSlots([tile('a', -1, { size: 'tall' }), tile('b', -1), tile('c', -1)])).toEqual([0, 1, 3]);
    const moving = tile('a', 0, { size: 'tall' }), neighbor = tile('b', 1);
    const result = arrange([moving, neighbor], moving, 1)!;
    expect(result.find((entry) => entry.tile === neighbor)!.slot).toBe(0);
    expect(occupied(result).size).toBe(3);
  });
  it("packs in reading order and moves a wide tile to the start of a row", () => {
    const tiles = [tile("a", -1), tile("b", -1, { size: "wide" }), tile("c", -1)];
    expect(packSlots(tiles)).toEqual([0, 2, 4]);
    expect(hasGaps(tiles)).toBe(true);
    const layout: Layout = { title: "T", tiles: [tile("z", 7), tile("y", 3)] };
    normalize(layout);
    expect(layout.tiles.map((t) => [t.entity, t.slot])).toEqual([["y", 3], ["z", 7]]);
  });
  it("gives every tile a slot when an old layout has none", () => {
    const layout: Layout = { title: "T", tiles: [{ entity: "a", name: "" } as Tile, { entity: "b", name: "", options: { size: "wide" } } as Tile] };
    normalize(layout);
    expect(layout.tiles.map((t) => t.slot)).toEqual([0, 2]);
  });
  it("knows where a tile fits", () => {
    const taken = occupied(entries([tile("a", 0), tile("w", 2, { size: "wide" })]));
    expect([...taken].sort((x, y) => x - y)).toEqual([0, 2, 3]);
    expect(fits(taken, 1, false)).toBe(true);
    expect(fits(taken, 2, false)).toBe(false);
    expect(fits(taken, 1, true)).toBe(false); // a wide tile starts in the left column
    expect(fits(taken, 4, true)).toBe(true);
    expect(fits(taken, grid.maxSlots - 1, true)).toBe(false);
    expect(fits(taken, grid.maxSlots, false)).toBe(false);
    expect(firstFree(taken, false)).toBe(1);
    expect(firstFree(taken, true)).toBe(4);
    expect(rowStart(5)).toBe(4);
  });
  it("prefers the later cell on a tie, so a nudged tile moves down", () => {
    const taken = occupied(entries([tile("a", 2)]));
    expect(nearestFree(taken, false, 2)).toBe(3);
    expect(nearestFree(new Set([3]), false, 2)).toBe(2);
  });
});

// A screen says what its page looks like (firmware 0.2.80, "800x480 3x2"); the editor places tiles on that grid.
describe("the grid of the screen being edited", () => {
  it("packs a wide tile so it never straddles two rows, whatever the columns", () => {
    setGrid(3, 2);
    expect(grid.slots).toBe(6);
    // Three single tiles fill the first row; a wide one then starts the second, not the last cell of the first.
    const tiles = [tile("a", -1), tile("b", -1), tile("c", -1), tile("d", -1, { size: "wide" })];
    expect(packSlots(tiles)).toEqual([0, 1, 2, 3]);
    expect(fits(new Set(), 2, "wide")).toBe(false);   // the last column has no cell beside it
    expect(fits(new Set(), 3, "wide")).toBe(true);
    expect(cellsOf(3, "wide")).toEqual([3, 4]);
    expect(rowStart(5)).toBe(3);
    setGrid(2, 3);
  });
  it("gives a one-column screen a wide tile that is simply the cell itself", () => {
    setGrid(1, 4);
    expect(grid.slots).toBe(4);
    expect(spanOf("wide")).toBe(1);
    expect(packSlots([tile("a", -1, { size: "wide" }), tile("b", -1)])).toEqual([0, 1]);
    expect(pageStart(5)).toBe(4);
    setGrid(2, 3);
  });
  it("takes the pages from the firmware's cap of 64 tiles", () => {
    // components/smart_display/runtime_model.h: grid.pages = min(64 / grid.slots, 8).
    setGrid(3, 3);
    expect([grid.pages, grid.maxSlots, grid.pages]).toEqual([7, 63, 7]);
    expect(pageCount(entries([tile("a", 0)]), 99)).toBe(7);
    expect(tileLimit("0.2.80")).toBe(63);
    setGrid(4, 4);
    expect([grid.pages, grid.maxSlots]).toEqual([4, 64]);
    setGrid(1, 4);
    expect([grid.pages, grid.maxSlots]).toEqual([8, 32]);
    setGrid(2, 3);
  });
  it("comes back to two columns and three rows for the boards that shipped first", () => {
    setGrid(undefined, undefined);
    expect([grid.slots, grid.pages, grid.maxSlots, spanOf("full")]).toEqual([6, 8, 48, 6]);
  });
});

describe("arrange", () => {
  it("swaps two tiles when one is dropped on the other", () => {
    const a = tile("a", 0), b = tile("b", 1);
    const result = arrange([a, b], a, 1)!;
    expect(result.map((e) => [e.tile.entity, e.slot])).toEqual([["b", 0], ["a", 1]]);
  });
  it("pushes a displaced tile to the nearest free cell when the vacated cells do not fit it", () => {
    const wide = tile("w", 0, { size: "wide" }), c = tile("c", 2), d = tile("d", 3);
    // A new single tile lands on the wide one's row: the wide tile needs two cells and takes the next free row.
    const fresh = newTile("light.x");
    const result = arrange([wide, c, d], fresh, 0)!;
    const by = Object.fromEntries(result.map((e) => [e.tile.entity, e.slot]));
    expect(by["light.x"]).toBe(0);
    expect(by.w).toBe(4);
    expect(by.c).toBe(2);
  });
  it("snaps a wide tile to the start of its row and refuses a target off the grid", () => {
    const w = tile("w", 0, { size: "wide" });
    expect(arrange([w], w, 3)![0].slot).toBe(2);
    expect(arrange([w], w, grid.maxSlots)).toBeNull();
    const single = tile("s", 0);
    expect(arrange([single], single, -1)).toBeNull();
    expect(arrange([single], single, grid.maxSlots)).toBeNull();
  });
  it("counts the pages the tiles need, never more than eight", () => {
    expect(pageCount(entries([tile("a", 0)]))).toBe(1);
    expect(pageCount(entries([tile("a", 6)]))).toBe(2);
    expect(pageCount(entries([tile("w", 4, { size: "wide" })]))).toBe(1);
    expect(pageCount(entries([tile("a", 0)]), 3)).toBe(3);
    expect(pageCount(entries([tile("a", 0)]), 99)).toBe(grid.pages);
    expect(grid.slots * grid.pages).toBe(grid.maxSlots);
  });
});

describe("defaults, controls and versions", () => {
  const inventory = { screens: [], entities: [], controls: { light: { default: "toggle", choices: [{ key: "toggle", label: "On/off switch" }, { key: "brightness", label: "Brightness slider" }, { key: "none", label: "None" }] } } } as unknown as Inventory;
  it("starts a new tile with the card that shows the entity best", () => {
    expect(defaultOptions("weather.home")).toEqual({ options: { display: "forecast", size: "wide" } });
    expect(defaultOptions("sun.sun")).toEqual({ options: { display: "sunpath", size: "wide" } });
    expect(defaultOptions("screen.clock")).toEqual({ options: { display: "dial", size: "wide" } });
    // The settings card is a plain card, not a second clock (GitHub #47).
    expect(defaultOptions("screen.settings")).toEqual({});
    expect(defaultOptions("light.a")).toEqual({});
    expect(newTile("light.a")).toEqual({ entity: "light.a", name: "", slot: -1 });
  });
  it("shows direct controls only on a wide standard card without a mini slider", () => {
    expect(effectiveControls(tile("light.a", 0, { size: "wide" }), inventory)).toBe("toggle");
    expect(effectiveControls(tile("light.a", 0, { size: "wide", controls: "brightness" }), inventory)).toBe("brightness");
    expect(effectiveControls(tile("light.a", 0, { size: "wide", controls: "none" }), inventory)).toBeNull();
    expect(effectiveControls(tile("light.a", 0, { size: "wide", inline: "slider" }), inventory)).toBeNull();
    expect(effectiveControls(tile("light.a", 0, { size: "wide", display: "watch" }), inventory)).toBeNull();
    expect(effectiveControls(tile("light.a", 0), inventory)).toBeNull();
    expect(controlsLabel(tile("light.a", 0, { size: "wide" }), inventory)).toBe("On/off switch");
    expect(controlsLabel(tile("sensor.t", 0, { size: "wide" }), inventory)).toBe("none");
  });
  it("compares firmware versions and knows the tile limit", () => {
    expect(versionAtLeast("0.2.60", "0.2.58")).toBe(true);
    expect(versionAtLeast("0.2.58", "0.2.58")).toBe(true);
    expect(versionAtLeast("0.2.9", "0.2.10")).toBe(false);
    expect(versionAtLeast("1.0.0", "0.9.9")).toBe(true);
    expect(versionAtLeast(undefined, "0.2.1")).toBe(false);
    expect(versionAtLeast("unknown", "0.2.1")).toBe(false);
    // Strict X.Y.Z: anything else is not a firmware release (the add-on works out firmware_known, app 0.2.78).
    expect(versionAtLeast("0.2.63 (ESPHome 2026.6.2)", "0.2.1")).toBe(false);
    expect(versionAtLeast(null, "0.2.1")).toBe(false);
    expect(tileLimit("0.2.6")).toBe(10);
    expect(tileLimit("0.2.7")).toBe(20);
    expect(tileLimit("0.2.60")).toBe(20);
    expect(tileLimit(undefined)).toBe(10);
  });
});

describe("full-page tiles and navigation tiles (firmware 0.2.62+)", () => {
  it("knows the three sizes and what they cover", () => {
    expect(sizeOf(tile("a", 0))).toBe("single");
    expect(sizeOf(tile("a", 0, { size: "wide" }))).toBe("wide");
    expect(sizeOf(tile("a", 0, { size: "full" }))).toBe("full");
    expect(sizeOf(tile("a", 0, { size: "huge" }))).toBe("single");
    expect(spanOf("full")).toBe(6);
    expect(cellsOf(8, "full")).toEqual([6, 7, 8, 9, 10, 11]);
    expect(cellsOf(3, true)).toEqual([3, 4]);
    expect(pageStart(11)).toBe(6);
  });
  it("packs a full tile at the start of a page and lets only a page start fit it", () => {
    expect(packSlots([tile("a", -1), tile("f", -1, { size: "full" }), tile("b", -1)])).toEqual([0, 6, 12]);
    const taken = occupied(entries([tile("a", 0)]));
    expect(fits(taken, 0, "full")).toBe(false);
    expect(fits(taken, 6, "full")).toBe(true);
    expect(fits(taken, 8, "full")).toBe(false);
    expect(firstFree(taken, "full")).toBe(6);
    expect(firstFree(taken, "single", 6)).toBe(6);
    expect(pageCount(entries([tile("f", 6, { size: "full" })]))).toBe(2);
  });
  it("drops a full tile on its page and moves what was there to the next free cells", () => {
    const a = tile("a", 0), b = tile("b", 3), f = tile("f", 6, { size: "full" });
    const result = arrange([a, b, f], f, 2)!;
    const by = Object.fromEntries(result.map((e) => [e.tile.entity, e.slot]));
    expect(by.f).toBe(0);
    // The displaced tiles take the cells the full tile left, in order.
    expect(by.a).toBe(6);
    expect(by.b).toBe(7);
  });
  it("knows a navigation tile and gives it no default card", () => {
    expect(pageTarget("screen.page_3")).toBe(3);
    expect(pageTarget("screen.page_9")).toBe(0);
    expect(pageTarget("screen.clock")).toBe(0);
    expect(defaultOptions("screen.page_2")).toEqual({});
  });
  it("holds 48 tiles from firmware 0.2.62 and shows no control on a full card without a choice", () => {
    expect(tileLimit("0.2.62")).toBe(48);
    expect(tileLimit("0.2.61")).toBe(20);
    const inventory = { screens: [], entities: [], controls: { light: { default: "toggle", choices: [{ key: "toggle", label: "On/off" }, { key: "none", label: "None" }] } } } as unknown as Inventory;
    expect(effectiveControls(tile("light.a", 0, { size: "full" }), inventory)).toBeNull();
    expect(effectiveControls(tile("light.a", 0, { size: "full", controls: "toggle" }), inventory)).toBe("toggle");
  });
});

describe("pages that only Go to page tiles reach (firmware 0.2.69)", () => {
  const nav = (page: number, slot: number) => tile(`screen.page_${page}`, slot);
  it("finds a page no tile leads to, and one without a way back", () => {
    // Page 1 goes to 2 and 3; page 2 goes back to 1; page 3 leads nowhere; nothing goes to page 4.
    const layout = entries([nav(2, 0), nav(3, 1), tile("light.a", 2), nav(1, 6), tile("light.b", 12), tile("light.c", 18)]);
    expect(strandedPages(layout, 4)).toEqual({ tiles: 3, targets: [1, 2, 3], unreachable: [4], noWayBack: [3] });
  });
  it("follows a chain of pages, and ignores a tile to a page the screen lacks or to its own page", () => {
    const chain = entries([nav(2, 0), nav(3, 6), nav(1, 12), nav(8, 13), nav(3, 14)]);
    expect(strandedPages(chain, 3)).toEqual({ tiles: 4, targets: [1, 2, 3], unreachable: [], noWayBack: [] });
    // A tile to page 3 that sits on a page nobody reaches leaves page 3 out too.
    expect(strandedPages(entries([nav(3, 6)]), 3)).toEqual({ tiles: 1, targets: [3], unreachable: [2, 3], noWayBack: [] });
    expect(strandedPages(entries([tile("light.a", 0)]), 1)).toEqual({ tiles: 0, targets: [], unreachable: [], noWayBack: [] });
  });
});

describe("a whole page that moves (app 0.2.121)", () => {
  it("moves a page in the row instead of swapping two", () => {
    expect(pageOrder(4, 2, 0)).toEqual([2, 0, 1, 3]);
    expect(pageOrder(4, 0, 3)).toEqual([1, 2, 3, 0]);
    expect(pageOrder(4, 1, 2)).toEqual([0, 2, 1, 3]);
    // Moving back is exactly the way back.
    expect(pageOrder(4, 0, 2).map((page) => pageOrder(4, 2, 0)[page])).toEqual([0, 1, 2, 3]);
    // An index off the row leaves it as it was.
    expect(pageOrder(3, 0, 3)).toEqual([0, 1, 2]);
    expect(pageOrder(3, -1, 1)).toEqual([0, 1, 2]);
    expect(pagePlaces([2, 0, 1])).toEqual([1, 2, 0]);
  });
  it("takes every tile with its page, on its own cell", () => {
    setGrid(2, 3);
    const first = tile("a", 0), wide = tile("w", 2, { size: "wide" }), second = tile("b", 7), full = tile("f", 12, { size: "full" });
    const moved = reorderPages(entries([first, wide, second, full]), pageOrder(3, 2, 0));
    expect(moved.map((e) => [e.tile.entity, e.slot])).toEqual([["f", 0], ["a", 6], ["w", 8], ["b", 13]]);
    // A page the order doesn't name keeps its tiles where they are.
    expect(reorderPages(entries([tile("z", 20)]), [0, 1]).map((e) => e.slot)).toEqual([20]);
  });
  it("takes a page's own title with it, wherever it lands", () => {
    expect(reorderTitles(["", "Kitchen", "Bedroom"], pageOrder(3, 2, 1))).toEqual(["", "Bedroom", "Kitchen"]);
    // A page that lands first keeps its name, and page 1 takes its own along (app 0.2.123).
    expect(reorderTitles(["", "Kitchen"], pageOrder(2, 1, 0))).toEqual(["Kitchen"]);
    expect(reorderTitles(["Hall", "Kitchen"], pageOrder(2, 0, 1))).toEqual(["Kitchen", "Hall"]);
    expect(reorderTitles(["", "", "Bedroom"], pageOrder(3, 0, 2))).toEqual(["", "Bedroom"]);
    expect(reorderTitles(undefined, pageOrder(3, 0, 1))).toEqual([]);
  });
  it("keeps a Go to page tile pointing at the page it means", () => {
    const to = (page: number) => (pagePlaces(pageOrder(3, 2, 0))[page - 1] ?? page - 1) + 1;
    expect(retargetedPage("screen.page_3", to)).toBe("screen.page_1");
    expect(retargetedPage("screen.page_1", to)).toBe("screen.page_2");
    expect(retargetedPage("light.a", to)).toBe("light.a");
    // A page number no screen can have is left alone.
    expect(retargetedPage("screen.page_8", () => 9)).toBe("screen.page_8");
    expect(retargetedPage("screen.page_2", () => 0)).toBe("screen.page_2");
  });
});


it('keeps simultaneous layout instances independent and reads a shape change immediately', () => {
  let documentGrid = { columns: 2, rows: 3 };
  const editor = createLayout(() => documentGrid);
  const other = createLayout(() => ({ columns: 3, rows: 3 }));
  expect(editor.cellsOf(0, 'square')).toEqual([0, 1, 2, 3]);
  expect(other.cellsOf(0, 'square')).toEqual([0, 1, 3, 4]);
  documentGrid = { columns: 4, rows: 4 };
  expect(editor.cellsOf(0, 'square')).toEqual([0, 1, 4, 5]);
  expect(editor.grid.pages).toBe(4);
  expect(other.grid.pages).toBe(7);
});

describe("the alarm panel's colours (app 0.3.8)", () => {
  it("paints an alarm as Home Assistant does: armed green, the delays orange, going off red, disarmed grey", async () => {
    const { tilePalette, tileActive } = await import("../src/model/tile-palette");
    const accent = (state: string) => tilePalette("alarm_control_panel.house", { state }).accent;
    expect(accent("armed_away")).toBe("#4caf50");
    expect(accent("armed_night")).toBe("#4caf50");
    for (const state of ["arming", "pending", "disarming"]) expect(accent(state)).toBe("#ff9800");
    expect(accent("triggered")).toBe("#f44336");
    expect(tileActive("alarm_control_panel.house", { state: "disarmed" })).toBe(false);
    expect(accent("disarmed")).toBe("#9e9e9e");
  });
});
