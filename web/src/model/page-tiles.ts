// A page's tiles, loose and in its sections (docs/PAGES.md "Sections"), without anything else of the page model, so every
// module that walks a page's tiles can use it (model/pages.ts re-exports it). A section's tiles stand relative to its
// block's top-left corner; placedTiles gives every tile its row and column on the page's grid.
import type { Page, PageTile, Section } from "../types";

export const sectionsOf = (page: Page): Section[] => page.sections ?? [];
/** Every tile of a page: its loose tiles, then each section's. The objects are the document's own. */
export const allTiles = (page: Page): PageTile[] => [...page.tiles, ...sectionsOf(page).flatMap((section) => section.tiles)];
/** Every tile of a page at its row and column on the page's grid (a section's moved by its block's corner), in reading
 * order, with the section it stands in. */
export function placedTiles(page: Page): { tile: PageTile; row: number; column: number; section?: Section }[] {
  const out: { tile: PageTile; row: number; column: number; section?: Section }[] = page.tiles.map((tile) => ({ tile, row: tile.placement.row, column: tile.placement.column }));
  for (const section of sectionsOf(page)) for (const tile of section.tiles)
    out.push({ tile, row: section.placement.row + tile.placement.row, column: section.placement.column + tile.placement.column, section });
  return out.sort((a, b) => a.row - b.row || a.column - b.column);
}
/** Keep only the tiles of a page `keep` says, loose and in its sections alike. */
export function keepTiles(page: Page, keep: (tile: PageTile) => boolean) {
  page.tiles = page.tiles.filter(keep);
  for (const section of sectionsOf(page)) section.tiles = section.tiles.filter(keep);
}
