// A page's tiles and its sections (docs/PAGES.md "Sections"), without anything else of the page model, so every module
// that walks a page's tiles can use it (model/pages.ts re-exports it).
//
// Every tile of a page stands in `page.tiles` at its own cell, as before sections. A section is a block of cells with a
// title; it holds no tiles of its own. A tile belongs to the section whose block it lies in (sectionOf): that is the one
// place the editor says what belonging is, as page_layout.section_of says it for the add-on. So nothing that counts,
// finds or checks a page's tiles has to know sections, and a tile's section is never said twice.
import type { Page, PageTile, Section } from "../types";

type Block = { row: number; column: number; columns: number; rows: number };
export const sectionsOf = (page: Page): Section[] => page.sections ?? [];
/** Every tile of a page. The objects are the document's own. */
export const allTiles = (page: Page): PageTile[] => page.tiles;
/** Whether a placement lies wholly in a block of cells (a section's). */
export const inside = (place: Block, block: Block) => place.row >= block.row && place.column >= block.column &&
  place.row + place.rows <= block.row + block.rows && place.column + place.columns <= block.column + block.columns;
/** The section a tile of the page stands in: the one whose block holds its cells. */
export const sectionOf = (page: Page, tile: PageTile): Section | undefined => sectionsOf(page).find((section) => inside(tile.placement, section.placement));
/** The tiles of a page that stand in a section, in the document's order. */
export const tilesIn = (page: Page, section: Section): PageTile[] => page.tiles.filter((tile) => inside(tile.placement, section.placement));
/** The tiles of a page that stand in no section. */
export const looseTiles = (page: Page): PageTile[] => page.tiles.filter((tile) => !sectionOf(page, tile));
/** Every tile of a page at its row and column, in reading order, with the section it stands in. */
export function placedTiles(page: Page): { tile: PageTile; row: number; column: number; section?: Section }[] {
  return page.tiles.map((tile) => ({ tile, row: tile.placement.row, column: tile.placement.column, section: sectionOf(page, tile) }))
    .sort((a, b) => a.row - b.row || a.column - b.column);
}
/** A layout whose sections still hold tiles of their own, placed from the block's corner (the first form of sections,
 * on dev from 2026-11-15 and never released), as it is kept now. A draft kept in a browser from those days comes
 * through here (model/kept-draft.ts); the add-on does the same for its store and for an imported file
 * (page_layout.flattened). */
export function flattenSections<T extends { pages: Page[] }>(layout: T): T {
  for (const page of layout.pages ?? []) for (const section of sectionsOf(page)) {
    const nested = section as Section & { tiles?: PageTile[] };
    if (!Array.isArray(nested.tiles)) continue;
    for (const tile of nested.tiles) page.tiles.push({ ...tile, placement: { ...tile.placement,
      row: tile.placement.row + section.placement.row, column: tile.placement.column + section.placement.column } });
    delete nested.tiles;
  }
  return layout;
}
/** Keep only the tiles of a page `keep` says. */
export function keepTiles(page: Page, keep: (tile: PageTile) => boolean) {
  page.tiles = page.tiles.filter(keep);
}
