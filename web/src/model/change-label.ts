// What one step of undo did, in words (app 0.4.x, "Undo: Kitchen light moved to page 2"): worked out from the draft before
// and after it, so every change has a name without each edit naming itself, and a new kind of edit is named the day it
// exists. An edit that knows better says so itself (a copied layout, the screen stood up). The words are the editor's
// (editor.undo.what), written to follow "Undo: " and "Undone: " in every language; a label keeps its key and values, not
// its text, so it is said in the language the editor speaks when it is shown. Pure: the names of the tiles come from
// `nameOf`, which the store hands in.
import type { ChildTile, Page, PageGrid, PageLayout, PageTile } from "../types";
import { sameValue } from "./pages";

/** A change's words: a key under editor.undo.what, its values, and the count for a text with plural forms. */
export type ChangeLabel = { key: string; named?: Record<string, unknown>; count?: number };
/** A tile's name as the mockup shows it: its own, else Home Assistant's. */
export type NameOf = (tile: PageTile | ChildTile, layout: PageLayout) => string;

export const label = (key: string, named?: Record<string, unknown>, count?: number): ChangeLabel =>
  ({ key, ...(named ? { named } : {}), ...(count === undefined ? {} : { count }) });

// Every tile of a layout by its id: where it stands (its page, or the clock it is a key of) and the tile itself.
type Placed = { tile: PageTile | ChildTile; page: number; holder?: string; key?: number };
function placedTiles(layout: PageLayout) {
  const placed = new Map<string, Placed>();
  layout.pages.forEach((page, index) => {
    for (const tile of page.tiles) {
      placed.set(tile.id, { tile, page: index });
      tile.children?.forEach((child, key) => placed.set(child.id, { tile: child, page: index, holder: tile.id, key }));
    }
  });
  return placed;
}

// What changed of one tile, the most telling first: what it opens, its name, its face (a forecast also widens it), its
// size, its icon, its colour, what a tap does, another of its settings, and last where it stands.
type TileChange = "link" | "renamed" | "resized" | "icon" | "color" | "look" | "tap" | "option" | "moved";
const ORDER: TileChange[] = ["link", "renamed", "look", "resized", "icon", "color", "tap", "option"];
function tileChange(was: Placed, now: Placed): TileChange | null {
  const a = was.tile, b = now.tile;
  if (!sameValue(a.content, b.content)) return "link";
  if (a.appearance.label !== b.appearance.label) return "renamed";
  const appearance = (tile: typeof a, key: string) => (tile.appearance as Record<string, unknown>)[key];
  if (appearance(a, "display") !== appearance(b, "display")) return "look";
  const placeA = "placement" in a ? a.placement : undefined, placeB = "placement" in b ? b.placement : undefined;
  if (placeA && placeB && (placeA.columns !== placeB.columns || placeA.rows !== placeB.rows)) return "resized";
  if (appearance(a, "icon") !== appearance(b, "icon")) return "icon";
  if (appearance(a, "background") !== appearance(b, "background")) return "color";
  const interaction = (tile: typeof a) => tile.interaction as Record<string, unknown>;
  if (!sameValue(interaction(a).tap, interaction(b).tap) || !sameValue(interaction(a).action, interaction(b).action)) return "tap";
  const rest = (tile: typeof a) => ({ ...tile, appearance: { ...tile.appearance, presentation: undefined }, placement: undefined, children: undefined });
  if (!sameValue(rest(a), rest(b))) return "option";
  const moved = was.page !== now.page || was.holder !== now.holder || was.key !== now.key ||
    (placeA && placeB && (placeA.row !== placeB.row || placeA.column !== placeB.column)) || Boolean(placeA) !== Boolean(placeB);
  return moved ? "moved" : null;
}

// The one page whose place in the row changed: the others stand in the same order without it.
function movedPage(before: Page[], after: Page[]) {
  const ids = (pages: Page[], without: string) => pages.map((page) => page.id).filter((id) => id !== without).join(",");
  return after.findIndex((page, index) => before[index]?.id !== page.id && ids(before, page.id) === ids(after, page.id));
}

/** The words for the change from `before` to `after` (and from one grid to another). */
export function describeChange(before: PageLayout, after: PageLayout, beforeGrid: PageGrid | null, afterGrid: PageGrid | null, nameOf: NameOf): ChangeLabel {
  if (beforeGrid && afterGrid && (beforeGrid.columns !== afterGrid.columns || beforeGrid.rows !== afterGrid.rows))
    return label("grid", { grid: `${afterGrid.columns} × ${afterGrid.rows}` });
  const beforeIds = new Set(before.pages.map((page) => page.id)), afterIds = new Set(after.pages.map((page) => page.id));
  const newPages = after.pages.map((page, index) => ({ page, index })).filter(({ page }) => !beforeIds.has(page.id));
  const gonePages = before.pages.map((page, index) => ({ page, index })).filter(({ page }) => !afterIds.has(page.id));
  const was = placedTiles(before), now = placedTiles(after);
  const added = [...now.keys()].filter((id) => !was.has(id)), removed = [...was.keys()].filter((id) => !now.has(id));
  const name = (placed: Placed, layout: PageLayout) => nameOf(placed.tile, layout);

  // A page that went takes its tiles with it.
  if (gonePages.length === 1 && !newPages.length) return label("page_removed", { page: gonePages[0].index + 1 });
  // A tile added from the library may bring the page it leads to: the tile is what was done.
  const onNewPage = (id: string) => newPages.some(({ index }) => now.get(id)!.page === index);
  if (newPages.length && added.every(onNewPage) && !removed.length) {
    const first = newPages[0];
    return label(first.page.tiles.length ? "page_copied" : "page_added", { page: first.index + 1 });
  }
  if (added.length === 1 && !removed.length) return label("tile_added", { name: name(now.get(added[0])!, after) });
  if (removed.length === 1 && !added.length) return label("tile_removed", { name: name(was.get(removed[0])!, before) });
  if (removed.length > 1 && !added.length) return label("tiles_removed", { n: removed.length }, removed.length);
  if (added.length > 1 && !removed.length) return label("tiles_added", { n: added.length }, added.length);
  if (!newPages.length && !gonePages.length && before.pages.length === after.pages.length && before.pages.some((page, index) => page.id !== after.pages[index].id)) {
    const moved = movedPage(before.pages, after.pages);
    return moved >= 0 ? label("page_moved", { page: moved + 1 }) : label("pages_moved");
  }

  // The tiles that are on both sides: one that changed more than its place is the change; else what moved.
  const changes = [...now.keys()].filter((id) => was.has(id)).map((id) => ({ id, change: tileChange(was.get(id)!, now.get(id)!) }))
    .filter((item): item is { id: string; change: TileChange } => item.change !== null);
  const telling = changes.filter((item) => item.change !== "moved").sort((a, b) => ORDER.indexOf(a.change) - ORDER.indexOf(b.change));
  if (telling.length === 1) {
    const { id, change } = telling[0];
    const target = name(was.get(id)!, before);
    if (change === "link") {
      const content = now.get(id)!.tile.content;
      const page = content.kind === "navigation" ? after.pages.findIndex((item) => item.id === (content.target.kind === "home" ? after.homePageId : content.target.pageId)) : -1;
      return page >= 0 ? label("tile_link", { name: target, page: page + 1 }) : label("tile_option", { name: target });
    }
    return label(`tile_${change}`, { name: target });
  }
  if (telling.length > 1) return label("tiles_changed", { n: telling.length }, telling.length);
  const moves = changes.filter((item) => item.change === "moved");
  if (moves.length === 1) {
    const { id } = moves[0], from = was.get(id)!, to = now.get(id)!;
    return from.page !== to.page ? label("tile_moved_page", { name: name(to, after), page: to.page + 1 }) : label("tile_moved", { name: name(to, after) });
  }
  if (moves.length > 1) return label("tiles_moved", { n: moves.length }, moves.length);

  // What the pages say of themselves: the screen's title, a page's title, the home page, the page buttons, the top bar.
  if (before.title !== after.title) return label("screen_title");
  if (before.homePageId !== after.homePageId) return label("home_page", { page: after.pages.findIndex((page) => page.id === after.homePageId) + 1 });
  const pageChanges = (part: (page: Page) => unknown) => after.pages.map((page, index) => ({ page, index }))
    .filter(({ page }) => { const old = before.pages.find((item) => item.id === page.id); return old && !sameValue(part(old), part(page)); });
  const titled = pageChanges((page) => page.topbar.title);
  if (titled.length === 1) return label("page_title", { page: titled[0].index + 1 });
  const buttons = pageChanges((page) => page.navigation);
  if (buttons.length === 1) return label("page_buttons", { page: buttons[0].index + 1 });
  const home = pageChanges((page) => page.topbar.leading.length);
  if (home.length === 1) return label("home_key", { page: home[0].index + 1 });
  const bars = pageChanges((page) => page.topbar);
  if (bars.length === 1) return label("top_bar", { page: bars[0].index + 1 });
  if (bars.length > 1) return label("top_bars");
  return label("changed");
}
