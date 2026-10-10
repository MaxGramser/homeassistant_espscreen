// The overview (app 0.4.0): every screen of the home with its home page, as its mockup draws it. Nothing selected is the
// add-on's home. Each screen's home page comes from its own saved document, drawn on its own grid and glass, with what
// Home Assistant reports right now (the store's loadOverview); a click opens the screen in the editor.
import { supportsFirmware } from "./layout";
import { projectLayout } from "./pages";
import { firmwareVersion } from "./screen-status";
import type { HeaderItem, Screen, Tile } from "../types";

// The smallest screen there is: what a screen is drawn as while the add-on has said nothing of its shape.
export const SMALLEST = { width: 320, height: 240, columns: 2, rows: 3, dpi: 143, look: "compact" };

export type HomeView = { screen: Screen; tiles: { tile: Tile; slot: number }[]; keys: Tile[]; grid: { columns: number; rows: number; slots: number };
  shape: NonNullable<Screen["shape"]>; title: string; items: HeaderItem[]; home: boolean; style: Record<string, string>; compact: boolean };
const OVERVIEW_SIDE = 300;
export function homeView(screen: Screen): HomeView | null {
  const record = screen.page_document;
  if (record?.format !== "pages-v2") return null;
  const shape = screen.shape && screen.shape.columns > 0 && screen.shape.rows > 0 ? screen.shape : SMALLEST;
  const source = record.sourceGrid, slots = source.columns * source.rows;
  const index = Math.max(0, record.layout.pages.findIndex((page) => page.id === record.layout.homePageId));
  const page = record.layout.pages[index];
  if (!page) return null;
  const view = projectLayout(record.layout, source);
  const tiles = view.tiles.filter((tile) => tile.in === undefined && Math.floor(tile.slot / slots) === index).map((tile) => ({ tile, slot: tile.slot }));
  // The keys of a bedside clock on that page, which its card draws under the time (app 0.4.12).
  const keys = view.tiles.filter((tile) => tile.in !== undefined && tiles.some(({ tile: clock }) => clock.entity === tile.in));
  // The same proportions as the editor's mockup (deviceStyle), at a size that lets several stand side by side.
  const width = shape.width >= shape.height ? Math.min(560, (OVERVIEW_SIDE * shape.width) / shape.height) : OVERVIEW_SIDE;
  return {
    screen, tiles, keys, grid: { columns: source.columns, rows: source.rows, slots }, shape: shape as NonNullable<Screen["shape"]>,
    title: page.topbar.title.source === "text" ? page.topbar.title.text : record.layout.title,
    items: page.topbar.trailing,
    // The home key on the home page too, as the screen draws it there (homeKeyShown for the screen in the editor).
    home: supportsFirmware(firmwareVersion(screen), 0, 2, 100) && screen.settings?.values?.home_button !== false && page.topbar.leading.length > 0,
    compact: shape.look ? shape.look === "compact" : Math.min(shape.width, shape.height) < 300,
    style: { "--screen-aspect": `${shape.width} / ${shape.height}`, "--screen-columns": String(source.columns), "--screen-rows": String(source.rows),
      "--screen-wide-span": String(Math.min(2, source.columns)), "--mockup-width": `${Math.round(width * 10) / 10}px` },
  };
}
