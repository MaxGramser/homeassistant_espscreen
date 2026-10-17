// Tiles copied and pasted (Cmd+C, Cmd+V): every setting of a tile goes along, on this screen or another one. A copy keeps
// the tiles as the page document has them, with the page they stood on and its grid. A paste puts new tiles (new ids) on
// a page: in the same arrangement where the group fits there whole, else one after the other in reading order, and what
// the page has no room for on new pages right after it, so tiles from a larger screen spread over pages of a smaller
// one. A tile larger than the grid it lands on takes the largest size that grid has for it; a page-filling tile stays
// one. Pure functions over the page document; editor/clipboard.ts brings the stores.
import { clone, emptyPage, footprintSize, instanceId } from "./pages";
import { validateCardOptions } from "./page-validation";
import { spanOffered } from "./sizes";
import type { Size } from "./layout";
import type { Page, PageGrid, PageLayout, PageTile } from "../types";

export type CopiedTile = { tile: PageTile; page: number };
export type CopiedTiles = { tiles: CopiedTile[]; grid: { columns: number; rows: number } };
/** What a paste may not do, as the editor knows it: a tile it leaves out (`allowed` false), the sizes a tile may take
 * there, and how many tiles the screen still takes. */
export type PasteRules = {
  allowed: (tile: PageTile, entity: string, layout: PageLayout) => boolean;
  sizes: (tile: PageTile, entity: string) => readonly string[];
  entityOf: (layout: PageLayout, tile: PageTile) => string;
  room: number;
  pages: number;
};
export type Pasted = { layout: PageLayout; added: string[]; skipped: number; newPages: number };

/** The tiles with these ids, in reading order: page by page, row by row. Keys under a bedside clock go with their clock. */
export function copyTiles(layout: PageLayout, grid: { columns: number; rows: number }, ids: readonly string[]): CopiedTiles {
  const wanted = new Set(ids), tiles: CopiedTile[] = [];
  layout.pages.forEach((page, index) => {
    for (const tile of page.tiles) if (wanted.has(tile.id)) tiles.push({ tile: clone(tile), page: index });
  });
  tiles.sort((a, b) => a.page - b.page || a.tile.placement.row - b.tile.placement.row || a.tile.placement.column - b.tile.placement.column);
  return { tiles, grid: { columns: grid.columns, rows: grid.rows } };
}

// The name of a rectangle on a grid, as the page document reads it (pages.ts footprintSize); null where it has none.
function sizeNamed(columns: number, rows: number, grid: PageGrid): Size | null {
  if (columns < 1 || rows < 1 || columns > grid.columns || rows > grid.rows) return null;
  if (columns === 1 && rows === 1) return "single";
  if (columns === Math.min(2, grid.columns) && rows === 1) return "wide";
  if (columns === 1 && rows === 2) return "tall";
  if (columns === 2 && rows === 2) return "square";
  if (spanOffered(columns, rows, grid)) return `${columns}x${rows}` as Size;
  return null;
}
/** The tile as it stands on this grid: its own size where the grid takes it, else the largest that fits, else none. */
export function fitTile(tile: PageTile, grid: PageGrid, entity: string, sizes: readonly string[]): PageTile | null {
  const { columns, rows } = tile.placement, c = Math.min(columns, grid.columns), r = Math.min(rows, grid.rows);
  const candidates = tile.appearance.presentation === "full" ? ["full" as Size]
    : [sizeNamed(c, r, grid), sizeNamed(c, 1, grid), sizeNamed(1, r, grid), "single" as Size].filter((size): size is Size => size !== null);
  for (const size of new Set(candidates)) {
    if (size !== "single" && !sizes.includes(size)) continue;
    const next = clone(tile);
    const span = size === "full" ? { columns: grid.columns, rows: grid.rows } : size === "single" ? { columns: 1, rows: 1 }
      : size === "wide" ? { columns: Math.min(2, grid.columns), rows: 1 } : size === "tall" ? { columns: 1, rows: 2 }
      : size === "square" ? { columns: 2, rows: 2 } : { columns: Number(size.split("x")[0]), rows: Number(size.split("x")[1]) };
    next.placement = { row: 0, column: 0, ...span };
    if (size === "single") delete next.appearance.presentation;
    else next.appearance.presentation = size;
    try { footprintSize(next, grid); validateCardOptions(next, entity, size); return next; }
    catch { /* the next size down */ }
  }
  return null;
}

// The cells of a page that tiles stand on.
function takenOn(page: Page, grid: PageGrid) {
  const taken = new Set<number>();
  for (const { placement: p } of page.tiles)
    for (let y = p.row; y < p.row + p.rows; y++) for (let x = p.column; x < p.column + p.columns; x++) taken.add(y * grid.columns + x);
  return taken;
}
const cellsAt = (row: number, column: number, tile: PageTile, grid: PageGrid) => {
  const cells: number[] = [];
  for (let y = row; y < row + tile.placement.rows; y++) for (let x = column; x < column + tile.placement.columns; x++) cells.push(y * grid.columns + x);
  return cells;
};
const fitsAt = (taken: Set<number>, row: number, column: number, tile: PageTile, grid: PageGrid) =>
  row >= 0 && column >= 0 && row + tile.placement.rows <= grid.rows && column + tile.placement.columns <= grid.columns &&
  cellsAt(row, column, tile, grid).every((cell) => !taken.has(cell));
// The first place in reading order where the tile fits, or null.
function firstPlace(taken: Set<number>, tile: PageTile, grid: PageGrid) {
  for (let row = 0; row < grid.rows; row++) for (let column = 0; column < grid.columns; column++)
    if (fitsAt(taken, row, column, tile, grid)) return { row, column };
  return null;
}
// The group in its own arrangement, moved so its top left corner is at (row, column): the places, or null where any of
// its tiles would leave the grid or cover another.
function groupAt(taken: Set<number>, group: { tile: PageTile; row: number; column: number }[], row: number, column: number, grid: PageGrid) {
  const used = new Set(taken), places: { row: number; column: number }[] = [];
  for (const item of group) {
    const r = item.row + row, c = item.column + column;
    if (!fitsAt(used, r, c, item.tile, grid)) return null;
    for (const cell of cellsAt(r, c, item.tile, grid)) used.add(cell);
    places.push({ row: r, column: c });
  }
  return places;
}

/** The layout with the copied tiles on page `target` (from 0). `anchor`: the cell the group's top left corner goes to,
 * when one was marked; else it keeps the places it had, where they are free. */
export function pasteTiles(layout: PageLayout, grid: PageGrid, copied: CopiedTiles, target: number, rules: PasteRules,
  anchor?: { row: number; column: number }): Pasted {
  const draft = clone(layout), added: string[] = [];
  let skipped = 0, room = rules.room;
  if (!draft.pages[target]) return { layout: draft, added, skipped: copied.tiles.length, newPages: 0 };
  // Each tile as it stands on this grid, with new ids, and only the tiles this screen takes.
  const fitted: { tile: PageTile; row: number; column: number; page: number }[] = [];
  for (const { tile, page } of copied.tiles) {
    const next = { ...clone(tile), id: instanceId() };
    if (next.children) next.children = next.children.map((child) => ({ ...child, id: instanceId() }));
    // A Go to page tile leads to a page of the screen it came from: here only when that page is here too.
    const leads = next.content.kind === "navigation" && next.content.target.kind === "page" ? next.content.target.pageId : null;
    let entity: string;
    try { if (leads && !draft.pages.some((item) => item.id === leads)) throw new Error(); entity = rules.entityOf(draft, next); }
    catch { skipped++; continue; }
    const cost = 1 + (next.children?.length || 0);
    const fit = cost <= room && rules.allowed(next, entity, draft) ? fitTile(next, grid, entity, rules.sizes(next, entity)) : null;
    if (!fit) { skipped++; continue; }
    room -= cost;
    fitted.push({ tile: fit, row: tile.placement.row, column: tile.placement.column, page });
  }
  if (!fitted.length) return { layout: draft, added, skipped, newPages: 0 };
  const place = (pageIndex: number, tile: PageTile, row: number, column: number) => {
    tile.placement.row = row; tile.placement.column = column;
    draft.pages[pageIndex].tiles.push(tile);
    added.push(tile.id);
  };
  // The whole group in its own arrangement, from one page and as far as the grid allows: at the marked cell, else where
  // it stood, else the first place it fits.
  const onePage = fitted.every((item) => item.page === fitted[0].page);
  if (onePage) {
    const top = Math.min(...fitted.map((item) => item.row)), left = Math.min(...fitted.map((item) => item.column));
    const group = fitted.map((item) => ({ tile: item.tile, row: item.row - top, column: item.column - left }));
    const taken = takenOn(draft.pages[target], grid);
    const corners = [anchor ?? { row: top, column: left }];
    for (let row = 0; row < grid.rows; row++) for (let column = 0; column < grid.columns; column++) corners.push({ row, column });
    for (const corner of corners) {
      const places = groupAt(taken, group, corner.row, corner.column, grid);
      if (!places) continue;
      group.forEach((item, index) => place(target, item.tile, places[index].row, places[index].column));
      return { layout: draft, added, skipped, newPages: 0 };
    }
  }
  // One after the other: the first free place on the page, or on a page this paste started, else a new page after the
  // last of those, as many as the screen takes. A small tile fills a gap a larger one left behind.
  const own = [{ page: draft.pages[target], taken: takenOn(draft.pages[target], grid) }];
  let newPages = 0;
  for (const item of fitted) {
    let into = own.find((entry) => firstPlace(entry.taken, item.tile, grid));
    if (!into && draft.pages.length < rules.pages) {
      const page = emptyPage(draft.pages[target].topbar);
      draft.pages.splice(target + own.length, 0, page);
      into = { page, taken: new Set() };
      own.push(into); newPages += 1;
    }
    const spot = into && firstPlace(into.taken, item.tile, grid);
    if (!into || !spot) { skipped++; continue; }
    place(draft.pages.indexOf(into.page), item.tile, spot.row, spot.column);
    for (const cell of cellsAt(spot.row, spot.column, item.tile, grid)) into.taken.add(cell);
  }
  return { layout: draft, added, skipped, newPages };
}
