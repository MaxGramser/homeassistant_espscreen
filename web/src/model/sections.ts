// Sections on a page (docs/PAGES.md "Sections"): the rows they make, their band's numbers, and the edits that make,
// move, size and take away a section, as pure functions over the editor's slot view (projectLayout's tiles and
// sections). The store's side is editor/sections.ts; the document's rules are model/pages.ts.
//
// The page's rows stay what they are (the block model): a section's header and padding come out of its own cells, as
// the firmware works it out (components/smart_display/section_layout.h inside, tests/test_section_layout.cpp). The
// header's height comes from boards.json (`section`, tools/generate_board_shapes.py), worked out from the fonts as
// module_sections.h does, so the mockup's cards are as high as the glass makes them.
import type { Layout, PageGrid, SectionBlock, Tile } from "../types";
import { dimensions, isKey, sizeOf, type Size } from "./layout";
import { instanceId } from "./pages";
import { packInOrder } from "./placement";
import { sizeFor } from "./sizes";

export type SectionMetrics = { header: number; titleTop: number; inset: number; pad: number };
type ShapeLike = { section: { band: number; title_top: number }; spacing: { gap_y?: number; gap: number; tile_pad: number } };

/** The header of a section (the title's top, its line and a gap), the title's top in it, the inset of its title and
 * its padding, in glass pixels (module_sections.h header, title_top, inset, gap). The numbers are the board's own, from
 * boards.json (`section`, `spacing`): there is no guess here for a board without them, and
 * tests/test_editor_parity.py (Sections) holds them to what the firmware preview lays out on every board that draws
 * sections. */
export function sectionMetrics(shape: ShapeLike): SectionMetrics {
  const gap = shape.spacing.gap_y ?? shape.spacing.gap, pad = shape.spacing.tile_pad;
  return { header: shape.section.band + gap, titleTop: shape.section.title_top, inset: gap + pad, pad: gap };
}
/** n / d rounded half away from zero, in whole numbers (section_layout.h round_div). */
export const roundDiv = (n: number, d: number) => (n >= 0 ? Math.floor((2 * n + d) / (2 * d)) : -Math.floor((-2 * n + d) / (2 * d)));
/** The room a section's header and padding take from a tile inside it, rows `first` to `last` of a section of `rows`
 * rows: shared evenly by its rows, so every tile inside is the same height and the page's rows stay what they are
 * (section_layout.h inside, the block model). */
export function insideMargins(m: SectionMetrics, rows: number, first: number, last: number) {
  const n = Math.max(1, rows), total = m.header + m.pad;
  return { top: roundDiv(m.header * n - first * total, n), bottom: roundDiv((last + 1) * total - m.header * n, n) };
}

/** A card in a section whose tiles follow its contrast, drawn in the other look: the mockup draws its cards in the light
 * look, and this turns one into the dark one's values closely (a white card to #1A1A1A, ink #1B1B1B to #D0D0D0, a
 * hairline #DDDDDD to #353535; the firmware's are #1A1A1A, #DADADA and #292929), its hues kept. */
export const OTHER_LOOK = "invert(0.9) hue-rotate(180deg)";
/** A card's margins in the mockup's CSS: glass pixels times the page's zoom (`--glass`). */
export function glassMargins(m: { left: number; right: number; top: number; bottom: number }) {
  const css = (n: number) => `calc(var(--glass) * ${n}px)`;
  return { ...(m.left ? { marginLeft: css(m.left) } : {}), ...(m.right ? { marginRight: css(m.right) } : {}),
    ...(m.top ? { marginTop: css(m.top) } : {}), ...(m.bottom ? { marginBottom: css(m.bottom) } : {}) };
}

// ---- Edits, over the slot view ----
// An edit gives back what model/pages.ts arrangeTiles takes: every tile's slot and every section's block. A plain
// reason (an i18n key) instead when it cannot be done.
export type SectionEdit = { entries: { tile: Tile; slot: number }[]; blocks: SectionBlock[] } | { refused: string };
type Cell = { row: number; column: number };
const pageOf = (slot: number, grid: PageGrid) => Math.floor(slot / (grid.columns * grid.rows));
const cellOf = (slot: number, grid: PageGrid): Cell => {
  const local = slot % (grid.columns * grid.rows);
  return { row: Math.floor(local / grid.columns), column: local % grid.columns };
};
const slotOf = (page: number, row: number, column: number, grid: PageGrid) => page * grid.columns * grid.rows + row * grid.columns + column;
const sizeIn = (tile: Tile, grid: PageGrid) => dimensions(sizeOf(tile), grid);
const inBlock = (b: { row: number; column: number; columns: number; rows: number }, row: number, column: number) =>
  row >= b.row && row < b.row + b.rows && column >= b.column && column < b.column + b.columns;
/** The section a tile stands in, by its cell. */
export function blockOf(layout: Layout, tile: Tile, grid: PageGrid): SectionBlock | undefined {
  if (tile.slot < 0) return undefined;
  const page = pageOf(tile.slot, grid), { row, column } = cellOf(tile.slot, grid);
  return (layout.sections ?? []).find((b) => b.page === page && inBlock(b, row, column));
}
/** Tiles in reading order, packed into `columns` columns from the top: each at the first place it fits, shrunk to
 * the width where it is wider (model/placement.ts packInOrder, with this shrinking as its rule). Their places relative
 * to the block, and the rows they take. */
export function packTiles(tiles: Tile[], columns: number, grid: PageGrid) {
  const sizes = new Map<Tile, Size>();
  const packed = packInOrder(tiles, columns, (tile) => {
    let { columns: w, rows: h } = sizeIn(tile, grid), size = sizeOf(tile);
    if (w > columns) { w = columns; size = sizeFor(w, h, grid) ?? "single"; if (size === "single") h = 1; }
    sizes.set(tile, size);
    return { columns: w, rows: h };
  });
  const places = new Map(packed.places.map(({ item, row, column }) => [item, { row, column, size: sizes.get(item)! }] as const));
  return { places, rows: Math.max(1, packed.rows) };
}
const withSize = (tile: Tile, size: Size): Tile => size === sizeOf(tile) ? tile
  : { ...tile, options: { ...(tile.options || {}), ...(size === "single" ? { size: undefined } : { size }) } };

/** The cells every tile and block of a page takes, but the ones `skip` names. */
function takenOn(layout: Layout, page: number, grid: PageGrid, skip: (tile: Tile) => boolean, skipBlock = "") {
  const taken = new Set<string>();
  for (const tile of layout.tiles) {
    if (isKey(tile) || pageOf(tile.slot, grid) !== page || skip(tile)) continue;
    const { row, column } = cellOf(tile.slot, grid), { columns, rows } = sizeIn(tile, grid);
    for (let y = row; y < row + rows; y++) for (let x = column; x < column + columns; x++) taken.add(`${y}:${x}`);
  }
  for (const b of layout.sections ?? []) if (b.page === page && b.id !== skipBlock)
    for (let y = b.row; y < b.row + b.rows; y++) for (let x = b.column; x < b.column + b.columns; x++) taken.add(`${y}:${x}`);
  return taken;
}
const blockFree = (taken: Set<string>, b: Cell & { columns: number; rows: number }, grid: PageGrid) => {
  if (b.row < 0 || b.column < 0 || b.row + b.rows > grid.rows || b.column + b.columns > grid.columns) return false;
  for (let y = b.row; y < b.row + b.rows; y++) for (let x = b.column; x < b.column + b.columns; x++) if (taken.has(`${y}:${x}`)) return false;
  return true;
};

/** Room for a block on its page: the loose tiles in its way, each to the nearest free cell of the page outside every
 * block (as a drag moves tiles aside, model/layout.ts arrange). Their new slots, or null where one finds no room. */
function makeRoom(layout: Layout, grid: PageGrid, page: number, block: Cell & { columns: number; rows: number }, own: (tile: Tile) => boolean, skipBlock = "") {
  const moved = new Map<Tile, number>();
  const inWay = layout.tiles.filter((tile) => !isKey(tile) && !own(tile) && pageOf(tile.slot, grid) === page && !blockOf(layout, tile, grid) && blockCovers(block, tile, grid));
  const taken = takenOn(layout, page, grid, (tile) => own(tile) || inWay.includes(tile), skipBlock);
  for (let y = block.row; y < block.row + block.rows; y++) for (let x = block.column; x < block.column + block.columns; x++) taken.add(`${y}:${x}`);
  for (const tile of inWay) {
    const { columns, rows } = sizeIn(tile, grid), from = cellOf(tile.slot, grid);
    let best: Cell | null = null, distance = Infinity;
    for (let row = 0; row + rows <= grid.rows; row++) for (let column = 0; column + columns <= grid.columns; column++) {
      if (!blockFree(taken, { row, column, columns, rows }, grid)) continue;
      const d = Math.abs(row - from.row) * grid.columns + Math.abs(column - from.column);
      if (d < distance) { best = { row, column }; distance = d; }
    }
    if (!best) return null;
    for (let y = best.row; y < best.row + rows; y++) for (let x = best.column; x < best.column + columns; x++) taken.add(`${y}:${x}`);
    moved.set(tile, slotOf(page, best.row, best.column, grid));
  }
  return moved;
}
/** Whether a block on its page would cover another section. */
const coversBlock = (layout: Layout, page: number, block: Cell & { columns: number; rows: number }, skip = "") =>
  (layout.sections ?? []).some((b) => b.page === page && b.id !== skip && b.row < block.row + block.rows && block.row < b.row + b.rows &&
    b.column < block.column + block.columns && block.column < b.column + b.columns);

/** A new section of the chosen loose tiles, named `title` (docs/PAGES.md "Sections", "Making a section"). A choice that
 * fills a rectangle with nothing else in it becomes that block where it stands, its tiles in their places. Any other
 * choice gets a block at its first tile, as wide as the choice, its tiles in reading order; loose tiles in its way move
 * to the nearest free cells of their page. */
export function makeSection(layout: Layout, grid: PageGrid, chosen: Tile[], title: string): SectionEdit {
  const tiles = chosen.filter((tile) => !isKey(tile) && tile.slot >= 0).sort((a, b) => a.slot - b.slot);
  if (!tiles.length) return { refused: "editor.sections.choose_tiles" };
  const page = pageOf(tiles[0].slot, grid);
  if (tiles.some((tile) => pageOf(tile.slot, grid) !== page)) return { refused: "editor.sections.one_page" };
  if (tiles.some((tile) => blockOf(layout, tile, grid))) return { refused: "editor.sections.already_in" };
  if (tiles.some((tile) => sizeOf(tile) === "full")) return { refused: "editor.sections.no_full" };
  if ((layout.sections ?? []).filter((b) => b.page === page).length >= 16) return { refused: "addon.errors.pages.sections_full" };
  const ids = new Set(tiles), cells = tiles.map((tile) => ({ ...cellOf(tile.slot, grid), ...sizeIn(tile, grid) }));
  const top = Math.min(...cells.map((c) => c.row)), left = Math.min(...cells.map((c) => c.column));
  const bottom = Math.max(...cells.map((c) => c.row + c.rows)), right = Math.max(...cells.map((c) => c.column + c.columns));
  const others = takenOn(layout, page, grid, (tile) => ids.has(tile));
  const box = { row: top, column: left, columns: right - left, rows: bottom - top };
  const id = instanceId(), keep = { id, page, title: title.trim() };
  const blocks = [...(layout.sections ?? [])];
  // The choice is a rectangle of its own: the block stands where the tiles are.
  if (blockFree(others, box, grid)) return { entries: layout.tiles.map((tile) => ({ tile, slot: tile.slot })), blocks: [...blocks, { ...keep, ...box }] };
  // Otherwise a block at the first tile, as wide as the choice, the tiles in reading order.
  const width = Math.min(box.columns, grid.columns);
  const packed = packTiles(tiles, width, grid);
  const block = { row: cellOf(tiles[0].slot, grid).row, column: Math.min(cellOf(tiles[0].slot, grid).column, grid.columns - width), columns: width, rows: packed.rows };
  if (block.row + block.rows > grid.rows) block.row = Math.max(0, grid.rows - block.rows);
  if (block.row + block.rows > grid.rows) return { refused: "editor.sections.too_tall" };
  if (coversBlock(layout, page, block)) return { refused: "editor.sections.no_room" };
  // The chosen tiles in the block; loose tiles in its way to the nearest free cells of their page.
  const moved = makeRoom(layout, grid, page, block, (tile) => ids.has(tile));
  if (!moved) return { refused: "editor.sections.no_room" };
  const entries: { tile: Tile; slot: number }[] = layout.tiles.map((tile) => {
    const place = ids.has(tile) ? packed.places.get(tile) : undefined;
    if (place) return { tile: withSize(tile, place.size), slot: slotOf(page, block.row + place.row, block.column + place.column, grid) };
    return { tile, slot: moved.get(tile) ?? tile.slot };
  });
  return { entries, blocks: [...blocks, { ...keep, ...block }] };
}
/** A new section with no tiles yet, named `title`, on free cells of `page` (docs/PAGES.md "Sections", "Making a
 * section"): two by two where that fits, else two by one, one by two or one cell. With `at` (an empty cell the person
 * chose) the block holds that cell, shifted left and up where it would leave the grid or meet a tile; without it, the
 * first free place in reading order. Nothing moves. Its cells take tiles as any cell does: a click, a drop. */
export function emptySection(layout: Layout, grid: PageGrid, page: number, at: Cell | null, title: string): SectionEdit {
  if ((layout.sections ?? []).filter((b) => b.page === page).length >= 16) return { refused: "addon.errors.pages.sections_full" };
  const taken = takenOn(layout, page, grid, () => false);
  const sizes = [[2, 2], [2, 1], [1, 2], [1, 1]].filter(([columns, rows]) => columns <= grid.columns && rows <= grid.rows);
  const fits = (box: Cell & { columns: number; rows: number }) => blockFree(taken, box, grid);
  let found: (Cell & { columns: number; rows: number }) | null = null;
  for (const [columns, rows] of sizes) {
    const tries: Cell[] = at
      ? [0, 1].flatMap((up) => [0, 1].map((left) => ({ row: at.row - up, column: at.column - left })))
          .filter((c) => c.row <= at.row && at.row < c.row + rows && c.column <= at.column && at.column < c.column + columns)
      : Array.from({ length: grid.rows * grid.columns }, (_, n) => ({ row: Math.floor(n / grid.columns), column: n % grid.columns }));
    found = tries.map((c) => ({ ...c, columns, rows })).find(fits) ?? null;
    if (found) break;
  }
  if (!found) return { refused: "editor.sections.no_room" };
  return { entries: layout.tiles.map((tile) => ({ tile, slot: tile.slot })),
    blocks: [...(layout.sections ?? []), { id: instanceId(), page, title: title.trim(), ...found }] };
}
function blockCovers(block: Cell & { columns: number; rows: number }, tile: Tile, grid: PageGrid) {
  const { row, column } = cellOf(tile.slot, grid), { columns, rows } = sizeIn(tile, grid);
  return row < block.row + block.rows && block.row < row + rows && column < block.column + block.columns && block.column < column + columns;
}

/** A tile dropped into a section the way an app goes into a folder on a phone (docs/PAGES.md "Sections"): it takes the
 * place in the section's reading order where it was let go, the tiles after it move on, and the section grows by rows
 * when they no longer fit, the loose tiles under it making room. From the library, from the page or from another
 * section alike. Refused only where the page has no rows left for it, or another section stands in the way. */
export function insertIntoSection(layout: Layout, grid: PageGrid, moving: Tile, id: string, target: number): SectionEdit {
  const block = (layout.sections ?? []).find((b) => b.id === id);
  if (!block || sizeOf(moving) === "full") return { refused: "editor.sections.no_room" };
  const page = block.page;
  const same = (tile: Tile) => tile === moving || (Boolean(moving.id) && tile.id === moving.id);
  const inside = layout.tiles.filter((tile) => !same(tile) && !isKey(tile) && blockOf(layout, tile, grid)?.id === id).sort((a, b) => a.slot - b.slot);
  const order = [...inside];
  const at = order.findIndex((tile) => tile.slot >= target);
  order.splice(at < 0 ? order.length : at, 0, moving);
  // Taller first, as a folder grows; where the page has no rows left, wider, as far as the page reaches.
  const own = (tile: Tile) => same(tile) || inside.includes(tile);
  let found: { packed: ReturnType<typeof packTiles>; next: SectionBlock; moved: Map<Tile, number> } | null = null;
  for (let columns = block.columns; columns <= grid.columns - block.column && !found; columns++) {
    const packed = packTiles(order, columns, grid);
    const next = { ...block, columns, rows: Math.max(block.rows, packed.rows) };
    if (next.row + next.rows > grid.rows || coversBlock(layout, page, next, id)) continue;
    const moved = makeRoom(layout, grid, page, next, own, id);
    if (moved) found = { packed, next, moved };
  }
  if (!found) return { refused: "editor.sections.no_room" };
  const { packed, next, moved } = found;
  const place = (tile: Tile) => {
    const p = packed.places.get(tile)!;
    return { tile: withSize(tile, p.size), slot: slotOf(page, next.row + p.row, next.column + p.column, grid) };
  };
  const entries = layout.tiles.filter((tile) => !same(tile))
    .map((tile) => (inside.includes(tile) ? place(tile) : { tile, slot: moved.get(tile) ?? tile.slot }));
  return { entries: [...entries, place(moving)].sort((a, b) => a.slot - b.slot), blocks: (layout.sections ?? []).map((b) => (b.id === id ? next : b)) };
}
/** A section `columns` wide and `rows` high, its top left corner where it is. It grows only into free cells; a
 * narrower one keeps its tiles where they still fit, else lays them out again in reading order; it is never less
 * high than its tiles need. */
export function resizeSection(layout: Layout, grid: PageGrid, id: string, columns: number, rows: number): SectionEdit {
  const block = (layout.sections ?? []).find((b) => b.id === id);
  if (!block) return { refused: "addon.errors.pages.fields" };
  columns = Math.max(1, Math.min(columns, grid.columns - block.column));
  const inside = layout.tiles.filter((tile) => !isKey(tile) && blockOf(layout, tile, grid)?.id === id).sort((a, b) => a.slot - b.slot);
  const local = (tile: Tile) => { const c = cellOf(tile.slot, grid); return { row: c.row - block.row, column: c.column - block.column }; };
  const fits = inside.every((tile) => local(tile).column + sizeIn(tile, grid).columns <= columns);
  const packed = fits ? null : packTiles(inside, columns, grid);
  const needed = fits ? Math.max(1, ...inside.map((tile) => local(tile).row + sizeIn(tile, grid).rows)) : packed!.rows;
  rows = Math.max(needed, Math.min(rows, grid.rows - block.row));
  const next = { ...block, columns, rows };
  // Another section in the way stops it; loose tiles in the way make room, as for a tile dragged there.
  if (next.row + next.rows > grid.rows || coversBlock(layout, block.page, next, id)) return { refused: "editor.sections.no_room" };
  const moved = makeRoom(layout, grid, block.page, next, (tile) => blockOf(layout, tile, grid)?.id === id, id);
  if (!moved) return { refused: "editor.sections.no_room" };
  const entries = layout.tiles.map((tile) => {
    const place = packed?.places.get(tile);
    return place ? { tile: withSize(tile, place.size), slot: slotOf(block.page, block.row + place.row, block.column + place.column, grid) }
      : { tile, slot: moved.get(tile) ?? tile.slot };
  });
  return { entries, blocks: (layout.sections ?? []).map((b) => (b.id === id ? next : b)) };
}
/** A section moved whole to `target` (the slot of its new top left corner), its tiles with it; loose tiles in the way
 * make room as for a tile (layout.ts arrange, with the block carried as a tile of its size). */
export function movedSection(layout: Layout, grid: PageGrid, id: string, arranged: { tile: Tile; slot: number }[] | null): SectionEdit {
  const block = (layout.sections ?? []).find((b) => b.id === id);
  const carried = arranged?.find((entry) => entry.tile.entity === `section:${id}`);
  if (!block || !arranged || !carried) return { refused: "editor.sections.no_room" };
  const to = cellOf(carried.slot, grid), page = pageOf(carried.slot, grid);
  const dy = to.row - block.row, dx = to.column - block.column;
  const entries = arranged.filter((entry) => entry !== carried);
  for (const tile of layout.tiles) if (!isKey(tile) && blockOf(layout, tile, grid)?.id === id) {
    const c = cellOf(tile.slot, grid);
    entries.push({ tile, slot: slotOf(page, c.row + dy, c.column + dx, grid) });
  }
  return { entries: [...entries, ...layout.tiles.filter(isKey).map((tile) => ({ tile, slot: tile.slot }))],
    blocks: (layout.sections ?? []).map((b) => (b.id === id ? { ...b, page, row: to.row, column: to.column } : b)) };
}
/** Loose tiles that stand beside a section in its rows, on a page whose sections could have them in a row of their own
 * (the hint "Put loose tiles in a row of their own"). */
export function looseBeside(layout: Layout, grid: PageGrid, page: number): Tile[] {
  const blocks = (layout.sections ?? []).filter((b) => b.page === page);
  if (!blocks.length) return [];
  return layout.tiles.filter((tile) => {
    if (isKey(tile) || pageOf(tile.slot, grid) !== page || blockOf(layout, tile, grid)) return false;
    const { row } = cellOf(tile.slot, grid), { rows } = sizeIn(tile, grid);
    return blocks.some((b) => row < b.row + b.rows && b.row < row + rows);
  });
}
/** The loose tiles of a page as a row of their own above its sections: the sections move down as one, keeping their
 * places beside each other, the loose tiles fill the rows above in reading order. Refused when the page has no room. */
export function looseRowAbove(layout: Layout, grid: PageGrid, page: number): SectionEdit {
  const blocks = (layout.sections ?? []).filter((b) => b.page === page);
  const loose = layout.tiles.filter((tile) => !isKey(tile) && pageOf(tile.slot, grid) === page && !blockOf(layout, tile, grid)).sort((a, b) => a.slot - b.slot);
  if (!blocks.length || !loose.length) return { refused: "editor.sections.no_room" };
  const packed = packTiles(loose, grid.columns, grid);
  const top = Math.min(...blocks.map((b) => b.row)), height = Math.max(...blocks.map((b) => b.row + b.rows)) - top;
  if (packed.rows + height > grid.rows) return { refused: "editor.sections.no_room" };
  const shift = packed.rows - top;
  const entries = layout.tiles.map((tile) => {
    if (isKey(tile) || pageOf(tile.slot, grid) !== page) return { tile, slot: tile.slot };
    const place = packed.places.get(tile);
    if (place) return { tile: withSize(tile, place.size), slot: slotOf(page, place.row, place.column, grid) };
    const c = cellOf(tile.slot, grid);
    return { tile, slot: slotOf(page, c.row + shift, c.column, grid) };
  });
  return { entries, blocks: (layout.sections ?? []).map((b) => (b.page === page ? { ...b, row: b.row + shift } : b)) };
}
