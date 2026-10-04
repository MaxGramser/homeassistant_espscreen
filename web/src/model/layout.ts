// ---- Grid positions ----
// A screen's page is a grid of cells: two columns and three rows on the boards that shipped first, and
// whatever a newer screen reports for itself (firmware 0.2.80 says "800x480 3x2"). A tile's `slot` is its
// absolute cell (page * cells + row * columns + column); a wide tile starts in a column that has a cell to its
// right and covers both; a full tile (firmware 0.2.62+) starts a page and covers every cell of it. Empty cells
// are allowed and stay exactly where they are.
//
// Grid-dependent operations belong to an explicit layout instance. Its shape is read
// directly from the owning document, without a watcher or mutable module-global grid.
import { t } from "../i18n";
import { NAMED_SIZES, isSize, isWideSize, spanOf, type Size } from "./sizes";
import { resolveControls } from "./catalogue";
import type { Inventory, Layout, Tile, PageGrid } from "../types";

// The firmware's own caps (components/smart_display/page_protocol.h): the same pages whatever the grid, and never more
// tiles on one screen than its board takes, so a page need not be full (firmware 0.18.0+). That is eight pages and 64
// tiles, or more on a board that says so in its hello (firmware 0.34.0+). Older firmware had as many pages as 64 tiles
// fill (legacyPages). The add-on counts the same way (core.Grid) and tells the editor the tile and page limit per screen
// (tile_limit, page_limit); STORE_MAX_PAGES is the most any board may state (core.STORE_MAX_PAGES).
export const FIRMWARE_MAX_PAGES = 8;
export const FIRMWARE_MAX_TILES = 64;
export const STORE_MAX_PAGES = 32;
// The items one page's top bar takes: six, or what the screen says (firmware 0.34.0+); the most any board states.
export const FIRMWARE_MAX_BAR_ITEMS = 6;
export const STORE_MAX_BAR_ITEMS = 16;
export const DEFAULT_GRID = { columns: 2, rows: 3 };
/** The pages firmware before 0.18.0 takes on a grid: as many as 64 tiles fill, eight at most. */
export const legacyPages = (grid: PageGrid) => Math.min(FIRMWARE_MAX_PAGES, Math.floor(FIRMWARE_MAX_TILES / (grid.columns * grid.rows)));
export type Entry = { tile: Tile; slot: number };
// Dimensions are resolved on the screen's grid; `true` still means wide. A span ("3x2", app 0.4.32) is its own
// rectangle (model/sizes.ts).
export type { Size } from "./sizes";
export const SIZES: Size[] = [...NAMED_SIZES];
type SizeLike = Size | boolean;
const asSize = (size: SizeLike): Size => (size === true ? "wide" : size === false ? "single" : size);

// A navigation tile (screen.page_<n>, firmware 0.2.62+) and the page it opens; 0 for any other entity. Two digits past
// nine, without a leading zero, on a screen with more pages (firmware 0.34.0+).
export const pageTarget = (id: string) => Number(/^screen\.page_([1-9][0-9]?)$/.exec(id)?.[1] ?? 0);
export const sizeOf = (tile: Tile): Size => (isSize(tile.options?.size) ? (tile.options!.size as Size) : "single");
export const isWide = (tile: Tile) => isWideSize(sizeOf(tile));
export const isFull = (tile: Tile) => sizeOf(tile) === "full";
// Wide spans at most two columns; full spans the complete supplied grid.
export function dimensions(size: SizeLike, shape: PageGrid = DEFAULT_GRID) {
  const value = asSize(size);
  const span = spanOf(value);
  if (span) return span;
  return value === "full" ? { columns: shape.columns, rows: shape.rows }
    : value === "square" ? { columns: 2, rows: 2 }
    : value === "tall" ? { columns: 1, rows: 2 }
    : { columns: value === "wide" ? Math.min(2, shape.columns) : 1, rows: 1 };
}
// A page moves as a whole (app 0.2.121). `pageOrder` is the row after the page at `from` is dropped at `to`:
// `order[position]` is the page that ends up there. Moving is a move, not a swap, so the pages in between shift
// up or down one, the way a list reorders. An index outside the row leaves the order as it was.
export function pageOrder(pages: number, from: number, to: number) {
  const order = Array.from({ length: Math.max(0, pages) }, (_, page) => page);
  if (from < 0 || to < 0 || from >= order.length || to >= order.length) return order;
  order.splice(to, 0, ...order.splice(from, 1));
  return order;
}
// Where each page ends up: `places[page]` is the position it stands in afterwards.
export function pagePlaces(order: number[]) {
  const places = order.map(() => 0);
  order.forEach((page, position) => (places[page] = position));
  return places;
}
// The page titles once the pages stand in `order`. A title belongs to its page and travels with it, page 1
// included (app 0.2.123): a page without a title of its own says the screen's title, wherever it stands, so
// reordering the row costs no names. Trailing empty entries go, as they do everywhere else.
export function reorderTitles(titles: string[] | undefined, order: number[]) {
  const names = order.map((page) => titles?.[page] ?? "").concat((titles || []).slice(order.length));
  while (names.length && !names[names.length - 1]) names.pop();
  return names;
}
// A Go to page tile means the page it points at, not the number it happens to have: `to` gives a page's new number
// (both count from 1). Anything else, and a number no page can have, is left alone.
export function retargetedPage(id: string, to: (page: number) => number) {
  const target = pageTarget(id);
  const moved = target ? to(target) : 0;
  return moved !== target && moved >= 1 && moved <= STORE_MAX_PAGES ? `screen.page_${moved}` : id;
}
// A key of a bedside clock has no cell; its clock's card draws it.
export const isKey = (tile: Tile) => tile.in !== undefined;
export const entriesOf = (layout: Layout): Entry[] => layout.tiles.filter((tile) => !isKey(tile)).map((tile) => ({ tile, slot: tile.slot }));
/** The keys under a tile, in their order. */
export const keysOf = (layout: Layout | null | undefined, holder: Tile) =>
  (layout?.tiles || []).filter((tile) => tile.in === holder.entity).sort((a, b) => (a.key ?? 0) - (b.key ?? 0));

/** A document-owned view of placement rules. Reading a new shape is synchronous. */
export function createLayout(shape: () => PageGrid, pageLimit: () => number | undefined = () => undefined) {
  const grid = {
    get columns() { return shape().columns; },
    get rows() { return shape().rows; },
    get slots() { return this.columns * this.rows; },
    get pages() { return Math.min(STORE_MAX_PAGES, pageLimit() ?? FIRMWARE_MAX_PAGES); },
    get maxSlots() { return this.pages * this.slots; },
  };
  const tileDimensions = (size: SizeLike) => dimensions(size, grid);
  const pageStart = (slot: number) => slot - (slot % grid.slots);
  const rowStart = (slot: number) => slot - (slot % grid.columns);
  const pageOf = (slot: number) => Math.floor(slot / grid.slots);
  const spanOf = (size: SizeLike) => { const d = tileDimensions(size); return d.columns * d.rows; };
  const cellsOf = (slot: number, size: SizeLike) => {
    const d = tileDimensions(size), first = asSize(size) === "full" ? pageStart(slot) : slot;
    return Array.from({ length: d.rows }, (_, row) => Array.from({ length: d.columns }, (_, column) => first + row * grid.columns + column)).flat();
  };
  // Keep the requested row, fitting the rectangle horizontally. Vertical overflow is refused.
  const startOf = (slot: number, size: SizeLike) => asSize(size) === "full" ? pageStart(slot)
    : rowStart(slot) + Math.min(slot % grid.columns, Math.max(0, grid.columns - tileDimensions(size).columns));

  // In-order packing: the rule before positions existed, and what firmware below 0.2.26 still draws.
  function packSlots(tiles: Tile[]) {
    let position = 0;
    const taken = new Set<number>();
    return tiles.map((tile) => {
      const size = sizeOf(tile), slot = firstFree(taken, size, position);
      if (slot < 0) throw new Error("Tiles do not fit this screen grid");
      for (const cell of cellsOf(slot, size)) taken.add(cell);
      position = slot + tileDimensions(size).columns;
      return slot;
    });
  }

  // Keys of a bedside clock have no cell, so they are never packed (app 0.4.12).
  function hasGaps(tiles: Tile[]) {
    const placed = tiles.filter((tile) => !isKey(tile)), packed = packSlots(placed);
    return placed.some((tile, i) => tile.slot !== packed[i]);
  }
  // Every tile gets a position (older layouts pack in order) and the list stays in reading order.
  function normalize(layout: Layout) {
    const placed = layout.tiles.filter((tile) => !isKey(tile)), keys = layout.tiles.filter(isKey);
    if (placed.some((t) => !Number.isInteger(t.slot))) {
      const packed = packSlots(placed);
      placed.forEach((t, i) => (t.slot = packed[i]));
    }
    layout.tiles = [...placed.sort((a, b) => a.slot - b.slot), ...keys];
  }
  function occupied(entries: Entry[]) {
    const taken = new Set<number>();
    for (const { tile, slot } of entries) for (const cell of cellsOf(slot, sizeOf(tile))) taken.add(cell);
    return taken;
  }
  const fits = (taken: Set<number>, slot: number, size: SizeLike) =>
    Number.isInteger(slot) && slot >= 0 && slot < grid.maxSlots &&
    (asSize(size) !== "full" || slot % grid.slots === 0) &&
    slot % grid.columns + tileDimensions(size).columns <= grid.columns &&
    Math.floor(slot % grid.slots / grid.columns) + tileDimensions(size).rows <= grid.rows &&
    cellsOf(slot, size).every((c) => !taken.has(c));
  function firstFree(taken: Set<number>, size: SizeLike, from = 0) {
    for (let slot = from; slot < grid.maxSlots; slot++) if (fits(taken, slot, size)) return slot;
    return -1;
  }
  // The free position closest to `origin`; on a tie the later one, so a nudged tile moves down, not up.
  function nearestFree(taken: Set<number>, size: SizeLike, origin: number) {
    let best = -1;
    for (let slot = 0; slot < grid.maxSlots; slot++)
      if (fits(taken, slot, size) && (best < 0 || Math.abs(slot - origin) <= Math.abs(best - origin))) best = slot;
    return best;
  }
  // The arrangement after putting `moving` (a tile on the grid, or a new one) at `target`:
  // it lands exactly there; tiles in its way take the cells it left (a swap) or else the
  // nearest free cell of their own page; everything else stays put. Null when the target is off the grid, or when a
  // tile in the way has no room left on its page: a wide tile never lands on a new page at the end because a single
  // one took its place (app 0.4.2).
  function arrange(tiles: Tile[], moving: Tile, target: number): Entry[] | null {
    const size = sizeOf(moving);
    target = startOf(target, size);
    if (!fits(new Set(), target, size)) return null;
    const footprint = cellsOf(target, size);
    const vacated = tiles.includes(moving) ? cellsOf(moving.slot, size) : [];
    const result: Entry[] = [{ tile: moving, slot: target }];
    const displaced: Tile[] = [];
    for (const tile of tiles) {
      if (tile === moving) continue;
      if (cellsOf(tile.slot, sizeOf(tile)).some((c) => footprint.includes(c))) displaced.push(tile);
      else result.push({ tile, slot: tile.slot });
    }
    for (const tile of displaced) {
      const w = sizeOf(tile), taken = occupied(result);
      let slot = vacated.map((c) => startOf(c, w)).find((c) => fits(taken, c, w));
      if (slot === undefined) {
        const page = pageOf(tile.slot);
        slot = -1;
        for (let cell = page * grid.slots; cell < (page + 1) * grid.slots; cell++)
          if (fits(taken, cell, w) && (slot < 0 || Math.abs(cell - tile.slot) < Math.abs(slot - tile.slot))) slot = cell;
      }
      if (slot < 0) return null;
      result.push({ tile, slot });
    }
    return result.sort((a, b) => a.slot - b.slot);
  }
  // ---- Whole pages ----
  // The tiles once the pages stand in `order`: every tile keeps its own cell of its own page, the page itself moves.
  // A tile on a page the order doesn't name stays exactly where it is.
  function reorderPages(entries: Entry[], order: number[]): Entry[] {
    const places = pagePlaces(order);
    return entries
      .map(({ tile, slot }) => {
        const place = places[pageOf(slot)];
        return { tile, slot: place === undefined ? slot : place * grid.slots + (slot % grid.slots) };
      })
      .sort((a, b) => a.slot - b.slot);
  }
  // Pages the tiles need, or more when the user keeps empty pages on purpose (`layout.pages`).
  function pageCount(entries: Entry[], wanted = 1) {
    const last = Math.max(0, ...entries.map(({ tile, slot }) => slot + spanOf(sizeOf(tile))));
    return Math.min(grid.pages, Math.max(1, Math.ceil(last / grid.slots), wanted || 1));
  }
  // With the page buttons and swiping both off (firmware 0.2.69+) only Go to page tiles change the page. Pages count
  // from 1: `tiles` is how many Go to page tiles lead to a page the screen has, `targets` the pages they lead to,
  // `unreachable` the pages no chain of them reaches from page 1, `noWayBack` the reachable ones they never lead back from.
  function strandedPages(entries: Entry[], pages: number) {
    const links = Array.from({ length: pages }, () => new Set<number>());
    let tiles = 0;
    for (const { tile, slot } of entries) {
      const to = pageTarget(tile.entity) - 1, from = pageOf(slot);
      if (to < 0 || to >= pages || from >= pages) continue;
      tiles++;
      links[from].add(to);
    }
    const reach = (next: (page: number) => number[]) => {
      const seen = new Set([0]), queue = [0];
      while (queue.length) for (const page of next(queue.shift()!)) if (!seen.has(page)) { seen.add(page); queue.push(page); }
      return seen;
    };
    const forward = reach((page) => [...links[page]]);
    const back = reach((page) => links.flatMap((to, from) => (to.has(page) ? [from] : [])));
    const all = Array.from({ length: pages }, (_, page) => page);
    const numbers = (list: number[]) => list.map((page) => page + 1);
    return {
      tiles,
      targets: numbers(all.filter((page) => links.some((to) => to.has(page)))),
      unreachable: numbers(all.filter((page) => !forward.has(page))),
      noWayBack: numbers(all.filter((page) => forward.has(page) && !back.has(page))),
    };
  }

  function tileLimit(firmware: string | undefined | null) {
    if (parseVersion(firmware).length !== 3) return 10;
    if (versionAtLeast(firmware, "0.18.0")) return Math.min(FIRMWARE_MAX_TILES, grid.maxSlots);
    return versionAtLeast(firmware, "0.2.62") ? legacyPages(grid) * grid.slots : versionAtLeast(firmware, "0.2.7") ? 20 : 10;
  }
  return { grid, dimensions: tileDimensions, pageStart, rowStart, pageOf, spanOf, cellsOf, startOf, packSlots, hasGaps, normalize, occupied, fits, firstFree, nearestFree, arrange, reorderPages, pageCount, strandedPages, tileLimit };
}

// New tiles start with the card that shows the entity best. `covers`: the screen draws an album cover on a tile (a board
// that draws pictures, firmware 0.2.78+), where a new media tile starts with it (app 0.4.42); a screen without pictures
// keeps the name and status, as does every tile that was already there.
export function defaultOptions(id: string, covers = false): Partial<Tile> {
  const domain = id.split(".")[0];
  if (domain === "media_player" && covers) return { options: { display: "cover" } };
  if (domain === "sun") return { options: { display: "sunpath", size: "wide" } };
  if (domain === "weather") return { options: { display: "forecast", size: "wide" } };
  if (pageTarget(id)) return {};
  // The clock is the one built-in card with a face; the settings card is a plain card, as the screen draws it (GitHub #47).
  // A new clock starts with the calm dial (app 0.3.12): it reads well on every size of card.
  if (id === "screen.clock") return { options: { display: "dial", size: "wide" } };
  // The bedside clock is the whole page, always, and starts without a card: its digits on the dark page (app 0.4.12).
  if (id === "screen.nightstand") return { options: { size: "full", background: "none" } };
  // The map tile (app 0.4.36) starts double width, following everyone Home Assistant knows the place of.
  if (id === "screen.map") return { options: { display: "map", size: "wide" } };
  return {};
}
export const newTile = (id: string, covers = false): Tile => ({ entity: id, name: "", slot: -1, ...defaultOptions(id, covers) } as Tile);

// Same rule as the add-on: only a wide or full card in the standard layout shows direct controls;
// without a choice the domain's first control set applies to a wide card, none to a full one.
/** The control set a card draws (model/catalogue.ts resolveControls, as the add-on sends it): the chosen one or its
 * type's default, and on a card one row high what fits there. `inventory` stays for the callers; the catalogue decides. */
export function effectiveControls(tile: Tile, _inventory?: Inventory): string | null {
  return resolveControls(tile);
}
export function controlsLabel(tile: Tile, inventory: Inventory) {
  const key = effectiveControls(tile, inventory);
  if (!key) return t("editor.inspect.control_none");
  // As the choice itself is labelled, like the other values in the summary: German writes its nouns with a capital.
  return inventory.controls?.[tile.entity.split(".")[0]]?.choices.find((c) => c.key === key)?.label || key;
}

export const parseVersion = (v: string | undefined | null) => (/^(\d+)\.(\d+)\.(\d+)$/.exec(v || "") || []).slice(1).map(Number);
export function versionAtLeast(version: string | undefined | null, minimum: string) {
  const [a, b] = [parseVersion(version), parseVersion(minimum)];
  if (a.length !== 3 || b.length !== 3) return false;
  for (let i = 0; i < 3; i++) if (a[i] !== b[i]) return a[i] > b[i];
  return true;
}
export const supportsFirmware = (firmware: string | undefined | null, major: number, minor: number, patch: number) =>
  versionAtLeast(firmware, `${major}.${minor}.${patch}`);
// Firmware 0.2.62 holds one tile per cell of its pages (48 on two by three); 0.2.7 twenty; older firmware ten. The
// add-on tells the editor per screen (tile_limit, app 0.2.78); this rule stays for a screen entry without it.

// What a tile shows and how big it is, in a few words (editor.displays, editor.sizes); a key it doesn't know stays as it is.
export const DISPLAYS = ["standard", "watch", "forecast", "graph", "digital", "analog", "dial", "flip", "sunpath", "live", "cover"];
export const displayName = (display: string) => (DISPLAYS.includes(display) ? t(`editor.displays.${display}`) : display);
export const sizeName = (size: string | undefined) => t(`editor.sizes.${SIZES.includes(size as Size) ? size : "single"}`);
export const TOGGLE_BEFORE = ["light", "switch", "input_boolean", "automation", "fan", "media_player", "climate"];
// What holding a tile opens, as tile_controls::tap_route routes it: said in the editor because nothing on the screen
// shows that a hold exists (GitHub #67). ACTS_ON_TAP are the domains whose Automatic tap does something other than
// open the card; SWITCHES_ON_TAP those that stop switching when the tap opens the card instead.
export const ACTS_ON_TAP = ["light", "fan", "switch", "input_boolean", "timer", "scene", "script", "button", "input_button", "lock"];
export const SWITCHES_ON_TAP = ["light", "fan", "switch", "input_boolean"];
// A person (firmware 0.21.0+): a tap shows where they are on a map, holding the card with their history.
const HOLD_HINTS: Record<string, string> = { light: "hold_light", fan: "hold_fan", switch: "hold_history", input_boolean: "hold_history", timer: "hold_timer", person: "hold_history" };
export const holdHintKey = (domain: string) => `editor.tile.tap.${HOLD_HINTS[domain] ?? "hold"}`;
const SLIDER_CONTROLS: Record<string, string> = { light: 'brightness', fan: 'speed', cover: 'position', media_player: 'volume', number: 'slider', input_number: 'slider' };
export const SLIDER_DOMAINS = Object.keys(SLIDER_CONTROLS);
export const inlineControlKind = (domain: string) => SLIDER_CONTROLS[domain] || '';

// Per domain its sign and colours; its name is the text editor.domains.<domain> (app 0.2.90).
export const domains: Record<string, [string, string, string]> = {
  light: ["☀", "#ad7600", "#fff3d3"],
  climate: ["❄", "#c86620", "#ffebdc"],
  humidifier: ["≋", "#3476b1", "#e5effa"],
  vacuum: ["◉", "#008577", "#def3ed"],
  fan: ["✣", "#008aab", "#def5fa"],
  cover: ["▤", "#8053af", "#eee5f8"],
  media_player: ["▶", "#007cad", "#def2fc"],
  sensor: ["⌁", "#3476b1", "#e5effa"],
  binary_sensor: ["◈", "#ad7600", "#fff3d3"],
  switch: ["⏻", "#ad7600", "#fff3d3"],
  input_boolean: ["⏻", "#ad7600", "#fff3d3"],
  automation: ["⚙", "#ad7600", "#fff3d3"],
  remote: ["⌘", "#ad7600", "#fff3d3"],
  scene: ["✦", "#8053af", "#eee5f8"],
  script: ["▷", "#8053af", "#eee5f8"],
  weather: ["☁", "#007cad", "#def2fc"],
  number: ["±", "#008577", "#def3ed"],
  input_number: ["±", "#008577", "#def3ed"],
  select: ["≡", "#5862af", "#eaecfa"],
  input_select: ["≡", "#5862af", "#eaecfa"],
  button: ["↗", "#5862af", "#eaecfa"],
  input_button: ["↗", "#5862af", "#eaecfa"],
  screen: ["◷", "#25282c", "#e9ecf1"],
  sun: ["☼", "#c86620", "#ffebdc"],
  timer: ["⏱", "#008577", "#def3ed"],
  person: ["☺", "#2f7d32", "#e1f2e2"],
  camera: ["◧", "#3d4a57", "#e6ebf0"],
  image: ["◧", "#3d4a57", "#e6ebf0"],
  alarm_control_panel: ["⛨", "#2f7d32", "#e1f2e2"],
  lock: ["⚿", "#2f7d32", "#e1f2e2"],
};
// [name, sign, colour, background] of an entity's domain.
export function domainInfo(id: string): [string, string, string, string] {
  const domain = id.split(".")[0], known = domains[domain];
  return known ? [t(`editor.domains.${domain}`), ...known] : [t("editor.domains.entity"), "◇", "#637184", "#edf0f4"];
}
