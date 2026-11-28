// A screen as the sidebar draws it beside its name (ScreenMini.vue): its glass in its own proportions, with the tiles of
// its home page where they stand, so a row of screens is told apart at a glance. A screen that is away is a dark glass.
// Only the places of the tiles are drawn: no states, no names, nothing that would have to be kept up to date.
import { SMALLEST } from "./overview";
import type { Screen } from "../types";

// The room a miniature takes in a row, and the parts of its drawing, in the pixels of the row.
export const MINI_WIDTH = 30, MINI_HEIGHT = 22;
const BEZEL = 1.5, PAD = 1.5, GAP = 1;

export type MiniTile = { x: number; y: number; width: number; height: number };
export type Miniature = { width: number; height: number; bezel: number; lit: boolean; tiles: MiniTile[] };

const round = (value: number) => Math.round(value * 100) / 100;

export function miniatureOf(screen: Screen): Miniature {
  const shape = screen.shape && screen.shape.width > 0 && screen.shape.height > 0 ? screen.shape : SMALLEST;
  const aspect = shape.width / shape.height;
  // As large as its room takes: a wide glass fills the width, a square or upright one the height.
  const wide = aspect >= MINI_WIDTH / MINI_HEIGHT;
  const width = wide ? MINI_WIDTH : round(MINI_HEIGHT * aspect), height = wide ? round(MINI_WIDTH / aspect) : MINI_HEIGHT;
  const lit = Boolean(screen.online || screen.virtual);
  const record = screen.page_document;
  if (!lit || record?.format !== "pages-v2") return { width, height, bezel: BEZEL, lit, tiles: [] };
  const { columns, rows } = record.sourceGrid;
  const page = record.layout.pages.find((one) => one.id === record.layout.homePageId) || record.layout.pages[0];
  if (!page || columns < 1 || rows < 1) return { width, height, bezel: BEZEL, lit, tiles: [] };
  // The cells of the page's grid inside the glass; a grid of many cells keeps a thinner gap, so its tiles stay tiles.
  const left = BEZEL + PAD, innerWidth = width - 2 * left, innerHeight = height - 2 * left;
  const gap = Math.min(GAP, innerWidth / (columns * 4), innerHeight / (rows * 4));
  const cellWidth = (innerWidth - (columns - 1) * gap) / columns, cellHeight = (innerHeight - (rows - 1) * gap) / rows;
  const tiles = page.tiles
    .map((tile) => tile.placement)
    .filter((at) => at.column >= 0 && at.row >= 0 && at.column < columns && at.row < rows)
    .map((at) => {
      const across = Math.min(at.columns, columns - at.column), down = Math.min(at.rows, rows - at.row);
      return {
        x: round(left + at.column * (cellWidth + gap)), y: round(left + at.row * (cellHeight + gap)),
        width: round(across * cellWidth + (across - 1) * gap), height: round(down * cellHeight + (down - 1) * gap),
      };
    });
  return { width, height, bezel: BEZEL, lit, tiles };
}
