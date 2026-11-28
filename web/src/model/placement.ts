// Placing tiles on pages (docs/AUTO_LAYOUT.md, "Placing"): the one path that puts groups of tiles on a screen's pages, for
// the first layout (model/auto-layout.ts) and for Layoutbot. Pure: units of tiles in, each with what it heads for, and
// pages with every tile at its own cell and a section block around each group of two tiles or more out, held to the
// screen's grid, its pages, its tiles and its memory as a proposal holds to it (model/memory.ts proposalHolds).
// What a tile shows and how large it is, what a unit is and what its page is called are the caller's; nothing here reads
// Home Assistant or the catalogue. tests: web/tests/placement.spec.ts.
import type { Page, PageTile, ScreenMemory, Section } from "../types";
import { memoryUse, proposalHolds, type PricedPage, type PricedTile } from "./memory";
import { copyBar, emptyPage, instanceId, SECTION_TITLE_BYTES, SECTIONS_MAX } from "./pages";
import rules from "./page-rules.json";
import type { PluginTileLookup } from "./plugins";

/** The icons a section or a page may take: the fixed set every screen carries (tile_icons.ICONS). */
export const ICONS: ReadonlySet<string> = new Set(rules.icons);

/** A card a tile can take: its size and what it shows. */
export type Face = { columns: number; rows: number; tile: Omit<PageTile, "id" | "placement"> };
/** One tile to place: what it is and shows (`tile`), its size in cells, and how much it matters (a smaller `rank` stays
 * when room runs short). `entity`: what its memory is priced by. With `PlaceTarget.grow`, `faces` are the cards it may
 * grow into (plainest first, `face` the one it has now) and `alike` the tiles that grow together (every light of a room
 * as large as the others). */
export type PlaceTile = { tile: Omit<PageTile, "id" | "placement">; columns: number; rows: number; rank: number; entity: string;
  faces?: Face[]; face?: number; alike?: string };
/** A group of tiles that stand together: a section with its `title` (and `icon`, `summary`) where it holds two tiles or
 * more and the screen draws sections, else loose tiles side by side.
 * - `page`: the title and icon of the page it heads for (a page of several units is named by `PlaceTarget.title`).
 * - `share`: units of one share may stand on one page; another share starts a new page. With sections, a share's units
 *   are blocks side by side; without them, a share's units follow each other as one row of tiles over its pages. A
 *   caller that groups otherwise at the two densities (rooms together in sections, a room to its own pages without)
 *   gives the share that fits the screen.
 * - `fills`: it may also fill what is left of a page of another share (the weather beside a room).
 * - `waits`: when its own share's page is full it waits for what later pages leave, before it gets a page of its own.
 *   The two stay two: `waits` says when a unit is placed (after the other shares' pages), `fills` where it may go (into
 *   their free cells). Auto layout gives the house's groups without a room both the first and not the second, so they
 *   never stand under a room's page title.
 * - `loose`: its tiles stand loose, never in a section of their own. */
export type PlaceUnit<T extends PlaceTile = PlaceTile> = {
  key: string; title: string; icon?: string; summary?: string; tiles: T[]; loose?: boolean;
  page: { title: string; icon?: string }; share: string; fills?: boolean; waits?: boolean;
};
export type PlaceTarget<T extends PlaceTile = PlaceTile> = {
  grid: { columns: number; rows: number };
  /** The pages and tiles the placement may add at most (a caller keeps room for what the person adds itself). */
  pages: number; tiles: number;
  /** Sections where the screen draws them. */
  sections: boolean;
  /** The screen's memory for tiles, null while it is not known or still measured; `existing`: what stays of the draft
   * beside the new pages, priced with them; `plugins` prices a plugin tile among those. */
  memory?: ScreenMemory | null;
  existing?: { tiles: readonly PricedTile[]; pages: readonly PricedPage[] };
  plugins?: PluginTileLookup;
  /** The top bar new pages take; left out, a Home key and the clock. */
  topbar?: Page["topbar"];
  /** The share of the pages' cells the tiles may take before the least wanted go (room around sections); left out, all. */
  fill?: number;
  /** A page's title and icon from the units that stand on it; left out, its first unit's page. */
  title?: (units: PlaceUnit<T>[]) => { title: string; icon?: string };
  /** After placing, every new page's tiles step up through their `faces` while the page still holds everything: alike
   * tiles together first, then single tiles, the smaller rank first. Only the faces given, never a size made up to fill
   * a hole. */
  grow?: boolean;
};
/** A tile that found no room, with its unit and why: the screen's tile ceiling (`tiles`), the pages' cells (`cells`), its
 * memory (`memory`) or its pages (`pages`). Data, so each caller says it in its own words. */
export type LeftOut<T extends PlaceTile = PlaceTile> = { tile: T; unit: string; why: "tiles" | "cells" | "memory" | "pages" };
export type Placed<T extends PlaceTile = PlaceTile> = { pages: Page[]; sections: number; left: LeftOut<T>[] };

// ---- One group's block ----

export type Place<T extends PlaceTile = PlaceTile> = { tile: T; row: number; column: number };
/** Items in reading order into `columns` columns from the top, each at the first place it fits, at the size `fit` gives
 * it for that width: the one packer of the editor. A group's block here (tiles at their own size, no wider than the
 * block) and a section's tiles in model/sections.ts packTiles (a tile wider than its section shrunk to the size the grid
 * names for what is left) differ only in that rule. */
export function packInOrder<I>(items: readonly I[], columns: number, fit: (item: I) => { columns: number; rows: number }) {
  const taken = new Set<string>(), places: { item: I; row: number; column: number; columns: number; rows: number }[] = [];
  let height = 0;
  for (const item of items) {
    const { columns: w, rows: h } = fit(item);
    for (let row = 0; ; row++) {
      let column = -1;
      for (let c = 0; c + w <= columns && column < 0; c++) {
        let free = true;
        for (let y = row; y < row + h && free; y++) for (let x = c; x < c + w; x++) if (taken.has(`${y}:${x}`)) { free = false; break; }
        if (free) column = c;
      }
      if (column < 0) continue;
      for (let y = row; y < row + h; y++) for (let x = column; x < column + w; x++) taken.add(`${y}:${x}`);
      places.push({ item, row, column, columns: w, rows: h });
      height = Math.max(height, row + h);
      break;
    }
  }
  return { places, rows: height };
}
/** Tiles in reading order into `columns` columns from the top, each at the first place it fits, at its own size. */
export function pack<T extends PlaceTile>(tiles: T[], columns: number) {
  const packed = packInOrder(tiles, columns, (tile) => ({ columns: Math.min(tile.columns, columns), rows: tile.rows }));
  return { places: packed.places.map(({ item, row, column }): Place<T> => ({ tile: item, row, column })), rows: packed.rows };
}
type Grid = { columns: number; rows: number };
type Shape<T extends PlaceTile> = { columns: number; rows: number; places: Place<T>[]; waste: number };
/** The shapes a unit's block may take on a grid: each width its tiles fit, the rows they then take. */
function shapes<T extends PlaceTile>(unit: PlaceUnit<T>, grid: Grid): Shape<T>[] {
  const widest = Math.max(...unit.tiles.map((tile) => tile.columns));
  const area = unit.tiles.reduce((sum, tile) => sum + tile.columns * tile.rows, 0);
  const out: Shape<T>[] = [];
  for (let columns = Math.min(widest, grid.columns); columns <= grid.columns; columns++) {
    const { places, rows } = pack(unit.tiles, columns);
    if (rows <= grid.rows && !out.some((shape) => shape.rows === rows)) out.push({ columns, rows, places, waste: columns * rows - area });
  }
  return out;
}
/** A unit cut into parts that each fit a page: the tiles in reading order on the page's width, a page high each. */
function split<T extends PlaceTile>(unit: PlaceUnit<T>, grid: Grid): PlaceUnit<T>[] {
  if (shapes(unit, grid).length) return [unit];
  const parts: PlaceUnit<T>[] = [];
  let current: T[] = [];
  for (const tile of unit.tiles) {
    if (current.length && pack([...current, tile], grid.columns).rows > grid.rows) { parts.push({ ...unit, tiles: current }); current = []; }
    current.push(tile);
  }
  if (current.length) parts.push({ ...unit, tiles: current });
  return parts.map((part, i) => ({ ...part, key: `${unit.key}:${i}` }));
}

// ---- Units on pages, with sections ----

type Block<T extends PlaceTile> = { unit: PlaceUnit<T>; row: number; column: number; shape: Shape<T> };
type Sheet<T extends PlaceTile> = { blocks: Block<T>[]; taken: Set<string> };
const freeAt = (sheet: Sheet<PlaceTile>, row: number, column: number, shape: Grid, grid: Grid) => {
  if (row + shape.rows > grid.rows || column + shape.columns > grid.columns) return false;
  for (let y = row; y < row + shape.rows; y++) for (let x = column; x < column + shape.columns; x++) if (sheet.taken.has(`${y}:${x}`)) return false;
  return true;
};
/** Where a unit goes on a page: the first free place in reading order for any of its shapes, the least waste there. */
function placeOn<T extends PlaceTile>(sheet: Sheet<T>, unit: PlaceUnit<T>, grid: Grid): Block<T> | null {
  const options = shapes(unit, grid);
  for (let row = 0; row < grid.rows; row++) for (let column = 0; column < grid.columns; column++) {
    const fitting = options.filter((shape) => freeAt(sheet as Sheet<PlaceTile>, row, column, shape, grid)).sort((a, b) => a.waste - b.waste || b.columns - a.columns);
    if (fitting.length) return { unit, row, column, shape: fitting[0] };
  }
  return null;
}
const claim = <T extends PlaceTile>(sheet: Sheet<T>, block: Block<T>) => {
  sheet.blocks.push(block);
  for (let y = block.row; y < block.row + block.shape.rows; y++) for (let x = block.column; x < block.column + block.shape.columns; x++) sheet.taken.add(`${y}:${x}`);
};
/** A block of one tile: it goes on the page as a loose tile. A section groups two tiles or more (the owner's rule: a
 * section is for grouping); one made by hand with one tile stays as it is, only a placement never proposes one. */
const alone = (block: Block<PlaceTile>) => block.unit.tiles.length === 1 || Boolean(block.unit.loose);
/** A page's blocks grown a little, so the panels line up: one row lower where the block beside it at the same top is one
 * row lower (a shelf), then into a gap of one column or one row that no block could fill. Their tiles laid out again on
 * the width they have now; a lone tile keeps its own size. */
function grow<T extends PlaceTile>(sheet: Sheet<T>, grid: Grid) {
  const free = (y: number, x: number) => y >= 0 && x >= 0 && y < grid.rows && x < grid.columns && !sheet.taken.has(`${y}:${x}`);
  const take = (cells: [number, number][]) => { for (const [y, x] of cells) sheet.taken.add(`${y}:${x}`); };
  const right = (b: Block<T>) => Array.from({ length: b.shape.rows }, (_, i) => [b.row + i, b.column + b.shape.columns] as [number, number]);
  const below = (b: Block<T>) => Array.from({ length: b.shape.columns }, (_, i) => [b.row + b.shape.rows, b.column + i] as [number, number]);
  const ordered = [...sheet.blocks].filter((block) => !alone(block)).sort((a, b) => a.row - b.row || a.column - b.column);
  for (const block of ordered) {
    const shelf = Math.max(...sheet.blocks.filter((other) => other.row === block.row).map((other) => other.row + other.shape.rows));
    if (shelf === block.row + block.shape.rows + 1 && below(block).every(([y, x]) => free(y, x))) {
      take(below(block)); block.shape = { ...block.shape, rows: block.shape.rows + 1 };
    }
  }
  for (const block of ordered) {
    const column = right(block);
    if (column.every(([y, x]) => free(y, x)) && column.every(([y, x]) => !free(y, x + 1))) { take(column); block.shape = { ...block.shape, columns: block.shape.columns + 1 }; }
    const row = below(block);
    if (row.every(([y, x]) => free(y, x)) && row.every(([y, x]) => !free(y + 1, x))) { take(row); block.shape = { ...block.shape, rows: block.shape.rows + 1 }; }
  }
  for (const block of ordered) {
    const again = pack(block.unit.tiles, block.shape.columns);
    if (again.rows <= block.shape.rows) block.shape = { ...block.shape, places: again.places };
  }
}

/** Pages of blocks: each unit at the first free place of its page, a few later ones of its share pulled forward to fill a
 * page before the next begins; what is left of a page takes the units that fill (the largest first); units that wait
 * go after the others when their own page is full. */
function blockSheets<T extends PlaceTile>(list: PlaceUnit<T>[], grid: Grid) {
  type Page2 = { sheet: Sheet<T>; units: PlaceUnit<T>[]; share: string };
  const sheets: Page2[] = [];
  const queue = list.flatMap((unit) => split(unit, grid));
  let current: Page2 | null = null;
  const room = (page: Page2) => page.sheet.blocks.length < SECTIONS_MAX;
  const deferred = new Set<PlaceUnit<T>>();
  const area = (unit: PlaceUnit<T>) => unit.tiles.reduce((n, x) => n + x.columns * x.rows, 0);
  const close = () => {
    if (!current) return;
    const page: Page2 = current;
    for (const next of queue.filter((item) => item.fills && item.share !== page.share).sort((a, b) => area(b) - area(a))) {
      const fits = room(page) ? placeOn(page.sheet, next, grid) : null;
      if (!fits) continue;
      claim(page.sheet, fits);
      page.units.push(next);
      queue.splice(queue.indexOf(next), 1);
    }
    grow(page.sheet, grid);
    sheets.push(page);
    current = null;
  };
  while (queue.length) {
    const unit = queue[0];
    // Closing a page may take filling units out of the queue: then look at the queue's head again.
    if (current && current.share !== unit.share) { close(); continue; }
    if (!current) current = { sheet: { blocks: [], taken: new Set() }, units: [], share: unit.share };
    const block = room(current) ? placeOn(current.sheet, unit, grid) : null;
    if (block) { claim(current.sheet, block); current.units.push(unit); queue.shift(); continue; }
    const page: Page2 = current;
    const ahead = queue.slice(1, 5).findIndex((next) => next.share === page.share && room(page) && placeOn(page.sheet, next, grid));
    if (ahead >= 0) {
      const next = queue.splice(ahead + 1, 1)[0];
      claim(page.sheet, placeOn(page.sheet, next, grid)!);
      page.units.push(next);
      continue;
    }
    if (!current.sheet.blocks.length) { queue.shift(); continue; }
    if (unit.waits && !deferred.has(unit)) {
      const later = queue.filter((item) => item.waits && item.share === page.share);
      later.forEach((item) => deferred.add(item));
      queue.splice(0, queue.length, ...queue.filter((item) => !later.includes(item)), ...later);
    }
    close();
  }
  close();
  return sheets;
}

/** Pages of loose tiles (no sections): each share's units as one run on pages of its own, continued on the next where it runs over; when the
 * screen has fewer pages than that, a run that spills a tile or two onto a page leaves its least wanted ones, and
 * neighbouring pages whose tiles fit one page become one, the smallest pair first. */
function plainSheets<T extends PlaceTile>(list: PlaceUnit<T>[], grid: Grid, pages: number) {
  type Plain = { places: Place<T>[]; units: PlaceUnit<T>[] };
  const runs: { units: PlaceUnit<T>[]; tiles: T[] }[] = [];
  for (const unit of list) {
    const last = runs.at(-1);
    if (last && last.units[0].share === unit.share) { last.units.push(unit); last.tiles.push(...unit.tiles); }
    else runs.push({ units: [unit], tiles: [...unit.tiles] });
  }
  const cells = grid.columns * grid.rows, size = (tiles: T[]) => tiles.reduce((n, tile) => n + tile.columns * tile.rows, 0);
  const dropped: LeftOut<T>[] = [];
  if (runs.reduce((n, run) => n + Math.ceil(size(run.tiles) / cells), 0) > pages)
    for (const run of runs) {
      const over = size(run.tiles) % cells;
      if (size(run.tiles) <= cells || over === 0 || over > Math.max(1, Math.floor(cells / 3))) continue;
      const worst = [...run.tiles].map((tile, i) => ({ tile, i })).sort((a, b) => b.tile.rank - a.tile.rank || b.i - a.i);
      let freed = 0;
      const gone = new Set<T>();
      for (const { tile } of worst) { if (freed >= over) break; gone.add(tile); freed += tile.columns * tile.rows; }
      run.tiles = run.tiles.filter((tile) => !gone.has(tile));
      for (const tile of gone) dropped.push({ tile, unit: run.units.find((u) => u.tiles.includes(tile))?.key ?? run.units[0].key, why: "pages" });
    }
  let out: Plain[] = runs.flatMap((run) => split({ ...run.units[0], tiles: run.tiles }, grid).map((part) => ({
    places: pack(part.tiles, grid.columns).places, units: run.units })));
  while (out.length > pages) {
    let best = -1, least = Infinity;
    for (let i = 0; i + 1 < out.length; i++) {
      const tiles = [...out[i].places, ...out[i + 1].places].map((place) => place.tile);
      if (pack(tiles, grid.columns).rows <= grid.rows && tiles.length < least) { best = i; least = tiles.length; }
    }
    if (best < 0) break;
    const a = out[best], b = out[best + 1];
    out = [...out.slice(0, best), { places: pack([...a.places, ...b.places].map((p) => p.tile), grid.columns).places, units: [...a.units, ...b.units] },
      ...out.slice(best + 2)];
  }
  return { sheets: out, dropped };
}

// ---- Growing into larger faces ----

/** One page's units with their tiles grown: a group of alike tiles (or a single tile) takes its next face together, kept
 * where the page still `holds` every unit, until none can grow; alike groups first, then single tiles, the smaller rank
 * first. The tiles are copies; the units given are not changed. */
function grown<T extends PlaceTile>(units: PlaceUnit<T>[], holds: (units: PlaceUnit<T>[]) => boolean): PlaceUnit<T>[] {
  const out = units.map((unit) => ({ ...unit, tiles: unit.tiles.map((tile) => ({ ...tile, face: tile.face ?? 0 })) }));
  const tiles = out.flatMap((unit) => unit.tiles).filter((tile) => (tile.faces?.length ?? 0) > 1);
  const step = (tile: T, by: number) => {
    const face = tile.faces![tile.face! + by];
    Object.assign(tile, { face: tile.face! + by, columns: face.columns, rows: face.rows, tile: face.tile });
  };
  const byRank = (group: T[]) => Math.min(...group.map((tile) => tile.rank));
  const alike = new Map<string, T[]>();
  for (const tile of tiles) if (tile.alike) alike.set(tile.alike, [...(alike.get(tile.alike) ?? []), tile]);
  const phases = [[...alike.values()].sort((a, b) => byRank(a) - byRank(b)), tiles.map((tile) => [tile]).sort((a, b) => byRank(a) - byRank(b))];
  for (const groups of phases) {
    for (let changed = true; changed;) {
      changed = false;
      for (const group of groups) {
        if (!group.every((tile) => tile.face === group[0].face && tile.face! + 1 < tile.faces!.length)) continue;
        group.forEach((tile) => step(tile, 1));
        if (holds(out)) changed = true;
        else group.forEach((tile) => step(tile, -1));
      }
    }
  }
  return out;
}

// ---- What the screen holds ----

/** The units trimmed to what the screen holds: its tile ceiling, the cells the pages offer and its memory as a proposal
 * holds to it (proposalHolds: the whole draft after against before, the new pages' top bars priced at the most pages the placement may take),
 * the least wanted (largest rank, latest) going first. */
function trim<T extends PlaceTile>(list: PlaceUnit<T>[], target: PlaceTarget<T>) {
  const all = list.flatMap((unit) => unit.tiles.map((tile) => ({ unit, tile })));
  const memory = target.memory && target.memory.room !== null && target.memory.room !== undefined ? target.memory : null;
  const existing = target.existing ?? { tiles: [], pages: [] };
  const bar = { topbar: { trailing: target.topbar?.trailing ?? [] } };
  const newPages = Array.from({ length: Math.max(1, target.pages) }, () => bar);
  const before = memory ? memoryUse(existing.tiles, memory, existing.pages, target.plugins) : null;
  const crosses = (kept: typeof all) => memory !== null && before !== null && !proposalHolds(before, memoryUse(
    [...existing.tiles, ...kept.map(({ tile }): PricedTile => ({ entity: tile.entity, options: {} }))], memory, [...existing.pages, ...newPages], target.plugins));
  const cells = Math.max(1, target.pages) * target.grid.columns * target.grid.rows * (target.fill ?? 1);
  let kept = all.slice();
  const over = (): LeftOut["why"] | null => kept.length > target.tiles ? "tiles"
    : kept.reduce((sum, item) => sum + item.tile.columns * item.tile.rows, 0) > cells ? "cells" : crosses(kept) ? "memory" : null;
  const index = new Map(all.map((item, i) => [item, i]));
  const left: LeftOut<T>[] = [];
  for (let why = over(); kept.length && why; why = over()) {
    const drop = kept.reduce((worst, item) => item.tile.rank > worst.tile.rank || (item.tile.rank === worst.tile.rank && index.get(item)! > index.get(worst)!) ? item : worst);
    kept = kept.filter((item) => item !== drop);
    left.push({ tile: drop.tile, unit: drop.unit.key, why });
  }
  const keep = new Set(kept.map((item) => item.tile));
  return { list: list.map((unit) => ({ ...unit, tiles: unit.tiles.filter((tile) => keep.has(tile)) })).filter((unit) => unit.tiles.length), left };
}

// ---- Pages out ----

const cutBytes = (text: string, most: number) => {
  const encoder = new TextEncoder();
  let out = text.trim();
  while (encoder.encode(out).length > most) out = [...out].slice(0, -1).join("");
  return out.trim();
};
const tileAt = (place: Place, row: number, column: number): PageTile => ({
  id: instanceId(), ...JSON.parse(JSON.stringify(place.tile.tile)),
  placement: { row, column, columns: place.tile.columns, rows: place.tile.rows },
});
function newPage<T extends PlaceTile>(units: PlaceUnit<T>[], target: PlaceTarget<T>): Page {
  const { title, icon } = target.title ? target.title(units) : { title: units[0]?.page.title ?? "", icon: units[0]?.page.icon };
  const page = emptyPage(target.topbar ? copyBar(target.topbar) : undefined);
  const text = cutBytes(title, 96);
  page.topbar.title = text ? { source: "text", text } : { source: "screen" };
  if (icon && ICONS.has(icon)) page.icon = icon;
  return page;
}

/** Units of tiles on new pages: trimmed to what the screen holds, then with sections (the screen draws them) each unit a
 * block at the first free place of a page of its share, or without them each share's run on pages of its own. Every tile stands
 * in its page's tiles at its own cell; a block of two tiles or more gets a section around it. `left`: the tiles that found
 * no room, each with why. */
export function placeUnits<T extends PlaceTile>(units: PlaceUnit<T>[], target: PlaceTarget<T>): Placed<T> {
  const most = Math.max(0, target.pages), grid = target.grid;
  const { list, left } = trim(units, target);
  const pages: Page[] = [];
  const leftOut = [...left];
  let sections = 0;
  if (target.sections) {
    // One page's units, with sections: still one page with every tile on it.
    const one = (units: PlaceUnit<T>[]) => blockSheets(units.map((unit) => ({ ...unit, share: "", fills: false, waits: false })), grid);
    const holds = (units: PlaceUnit<T>[]) => {
      const sheets = one(units);
      return sheets.length === 1 && sheets[0].sheet.blocks.reduce((n, block) => n + block.unit.tiles.length, 0) === units.reduce((n, unit) => n + unit.tiles.length, 0);
    };
    for (let sheet of blockSheets(list, grid)) {
      if (target.grow) sheet = { ...one(grown(sheet.units, holds))[0], units: sheet.units };
      if (pages.length >= most) { for (const block of sheet.sheet.blocks) leftOut.push(...block.unit.tiles.map((tile) => ({ tile, unit: block.unit.key, why: "pages" as const }))); continue; }
      const page = newPage(sheet.units, target);
      const blocks = sheet.sheet.blocks.sort((a, b) => a.row - b.row || a.column - b.column);
      page.tiles = blocks.flatMap((block) => block.shape.places.map((place) => tileAt(place, block.row + place.row, block.column + place.column)));
      const grouped = blocks.filter((block) => !alone(block));
      if (grouped.length) page.sections = grouped.map((block): Section => ({
        id: instanceId(), title: cutBytes(block.unit.title, SECTION_TITLE_BYTES) || "·",
        ...(block.unit.icon && ICONS.has(block.unit.icon) ? { icon: block.unit.icon } : {}),
        ...(block.unit.summary ? { summary: block.unit.summary } : {}),
        placement: { row: block.row, column: block.column, columns: block.shape.columns, rows: block.shape.rows },
      }));
      sections += page.sections?.length ?? 0;
      pages.push(page);
    }
  } else {
    const plain = plainSheets(list, grid, most);
    leftOut.push(...plain.dropped);
    const holds = (units: PlaceUnit<T>[]) => pack(units.flatMap((unit) => unit.tiles), grid.columns).rows <= grid.rows;
    for (let sheet of plain.sheets) {
      if (pages.length >= most) { leftOut.push(...sheet.places.map((place) => ({ tile: place.tile, unit: sheet.units.find((u) => u.tiles.includes(place.tile))?.key ?? "", why: "pages" as const }))); continue; }
      // A page grows only once it is one that stays.
      if (target.grow) {
        const tiles = new Set(sheet.places.map((place) => place.tile));
        const units = grown(sheet.units.map((unit) => ({ ...unit, tiles: unit.tiles.filter((tile) => tiles.has(tile)) })).filter((unit) => unit.tiles.length), holds);
        sheet = { ...sheet, places: pack(units.flatMap((unit) => unit.tiles), grid.columns).places };
      }
      const page = newPage(sheet.units, target);
      page.tiles = sheet.places.map((place) => tileAt(place, place.row, place.column));
      pages.push(page);
    }
  }
  return { pages, sections, left: leftOut };
}
