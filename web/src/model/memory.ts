// How much of a screen's memory a layout takes (firmware 0.34.0+, docs/TILE_MEMORY.md). The price of each type is the
// tile catalogue's (catalogue/<type>.yaml `memory`); the screen says how much room it has and what its board adds (PSRAM
// or not, the size of a tile and of its block of extras). The screen (tile_memory::cost) and the add-on (core.tile_cost)
// price a tile the same way: tests/fixtures/memory-conformance.json holds the cases all three answer alike.
import { DOMAINS, TILE, TYPES, type TypeMemory } from "./catalogue";
import type { ScreenMemory } from "../types";
import { noPluginTiles, type PluginTileLookup } from "./plugins";

/** A tile as its price counts it: its entity and the choices that keep something of their own. */
export type PricedTile = { entity: string; options?: { tap?: string; sub?: string } | Record<string, unknown> };

const DEAREST: TypeMemory = Object.values(TYPES).reduce<TypeMemory>((most, type) => (type.memory.bytes > most.bytes ? type.memory : most), { bytes: 0, extras: true });

/** What one tile costs on that screen, in bytes: its type's price, what its own action and second line add, and on a
 * board without PSRAM the tile itself and, where it keeps one, its block of extras. A plugin's tile costs what its manifest
 * says (`plugins`: the tile types the editor knows, model/plugins.ts). */
export function tileCost(tile: PricedTile, memory: Pick<ScreenMemory, "psram" | "tile" | "extra">, plugins: PluginTileLookup = noPluginTiles) {
  const plugin = plugins(tile.entity);
  const type = plugin ? { bytes: plugin.tile.memory, extras: false } : TYPES.screen?.cards?.[tile.entity] ?? TYPES[tile.entity.split(".", 1)[0]]?.memory ?? DEAREST;
  const options = (tile.options || {}) as { tap?: string; sub?: string };
  const action = options.tap === "action", line = typeof options.sub === "string" && options.sub.startsWith("attr:");
  let bytes = type.bytes + (action ? TILE.memory.action : 0) + (line ? TILE.memory.line : 0);
  if (!memory.psram) bytes += memory.tile + (type.extras || action || line ? memory.extra : 0);
  return bytes;
}

/** A page as its price counts it: its top bar's items, of which the entity items keep a text, and its sections. */
export type PricedPage = { topbar: { trailing: readonly { type: string; entity?: string }[] }; sections?: readonly unknown[] };

/** The entities in the pages' top bars that are on none of `tiles`, once each: the tiles of the top bar a screen that takes
 * cards from its top bar gets (firmware 0.56.0), one without a cell for each, so a tap on its item opens its card. Only a
 * type the screen draws a card for. The add-on picks the same ones (core.bar_entities). */
export function barEntities(pages: readonly PricedPage[], tiles: readonly PricedTile[]) {
  const onTiles = new Set(tiles.map((tile) => tile.entity)), out: string[] = [];
  for (const page of pages)
    for (const item of page.topbar.trailing)
      if (item.type === "entity" && item.entity && !onTiles.has(item.entity) && !out.includes(item.entity) &&
          !item.entity.startsWith("screen.") && DOMAINS.has(item.entity.split(".", 1)[0])) out.push(item.entity);
  return out;
}

/** What one page costs: its title, each entity item of its top bar, each of its sections on a screen that draws them (any
 * other is sent none), and on a board without PSRAM its own record. */
export const pageCost = (page: PricedPage, memory: Pick<ScreenMemory, "psram" | "page" | "sections">) =>
  TILE.memory.page + page.topbar.trailing.filter((item) => item.type === "entity").length * TILE.memory.bar_text +
  (memory.sections ? (page.sections?.length ?? 0) * TILE.memory.section : 0) + (memory.psram ? 0 : memory.page ?? 0);

/** The alarms a screen wakes for (`alarms`, the app's alarm_screens) that are on neither its tiles nor its top bar: each
 * comes as a tile without a cell, as core.layout_cost counts it. */
export function alarmEntities(pages: readonly PricedPage[], tiles: readonly PricedTile[], memory: Pick<ScreenMemory, "alarms" | "bar_cards">) {
  if (!memory.bar_cards) return [];
  const on = new Set([...tiles.map((tile) => tile.entity), ...barEntities(pages, tiles)]);
  return (memory.alarms ?? []).filter((entity) => !on.has(entity));
}

/** What these tiles (the keys of a bedside clock included) and pages take together, with the tiles of the top bar on a
 * screen that gets them (`bar_cards`, barEntities) and of the alarms it wakes for (alarmEntities). */
export const layoutCost = (tiles: readonly PricedTile[], memory: ScreenMemory, pages: readonly PricedPage[] = [], plugins: PluginTileLookup = noPluginTiles) =>
  tiles.reduce((sum, tile) => sum + tileCost(tile, memory, plugins), 0) + pages.reduce((sum, page) => sum + pageCost(page, memory), 0) +
  (memory.bar_cards ? barEntities(pages, tiles).reduce((sum, entity) => sum + tileCost({ entity }, memory, plugins), 0) : 0) +
  alarmEntities(pages, tiles, memory).reduce((sum, entity) => sum + tileCost({ entity }, memory, plugins), 0);

export type MemoryUse = { need: number; room: number; share: number; level: "fine" | "close" | "full" | "over" };

/** Whether the screen is still measuring its room (firmware 0.51.0): it samples it only once a layout has settled, a minute
 * after it starts or gets a new one, and says no room until then. */
export const measuring = (memory: ScreenMemory) => memory.room === null || memory.room === undefined;

/** A layout against the room: how much it needs, the share of the room, and how close to full that is. A layout that
 * takes no more than the tiles on the screen now always counts as fitting, as the add-on lets it through. A screen that is
 * still measuring counts as having no room; the editor asks `measuring` first. */
export function memoryUse(tiles: readonly PricedTile[], memory: ScreenMemory, pages: readonly PricedPage[] = [], plugins: PluginTileLookup = noPluginTiles): MemoryUse {
  const need = layoutCost(tiles, memory, pages, plugins), room = memory.room ?? 0;
  const share = room > 0 ? need / room : need > 0 ? Infinity : 0;
  const over = need > room && need > memory.used;
  return { need, room, share, level: over ? "over" : share > 0.98 ? "full" : share >= 0.8 ? "close" : "fine" };
}

/** The share of the room past which the editor calls the screen nearly full and asks before one more tile. */
export const NEARLY_FULL = 0.9;

/** Past ten times the room a share says nothing any more: the screen has no memory to spare for tiles, or next to none,
 * and the editor says so in words instead of a number (it read "999 %"). */
export const NO_ROOM_SHARE = 10;
export const noRoom = (use: MemoryUse) => use.room === 0 || use.share >= NO_ROOM_SHARE;

/** The line one more tile takes the layout past, if it was not past it yet: "close" for nine tenths of the room, "over"
 * for all of it, "none" for all of it on a screen with no room to speak of. The budget is a warning since app 0.4.61, not a
 * rule: the editor asks once at each line, and yes may be the answer (GitHub #157). */
export function memoryCrossing(tiles: readonly PricedTile[], tile: PricedTile, memory: ScreenMemory, pages: readonly PricedPage[] = [],
  plugins: PluginTileLookup = noPluginTiles) {
  return memoryLine(memoryUse(tiles, memory, pages, plugins), memoryUse([...tiles, tile], memory, pages, plugins));
}
/** The line a change takes a layout past, from what it took before to what it takes after: the one rule every add holds
 * to (a tile from the library, a paste, a first layout). Null when it crosses none, also when it was past that line already. */
export function memoryLine(before: MemoryUse, after: MemoryUse) {
  if (after.level === "over") return before.level === "over" ? null : { line: noRoom(after) ? "none" as const : "over" as const, share: after.share };
  return after.share >= NEARLY_FULL && before.share < NEARLY_FULL ? { line: "close" as const, share: after.share } : null;
}
/** Whether a proposal (a first layout, a plan of Layoutbot) may take a layout from `before` to `after`: stricter than an add,
 * because nobody is asked on the way. It crosses no line (memoryLine) and ends no higher than it started: a layout below
 * nine tenths stays below them, one between nine tenths and all of the room stays within the room, and one past all of it
 * gets nothing more that costs memory. */
export function proposalHolds(before: MemoryUse, after: MemoryUse) {
  if (before.level === "over") return after.need <= before.need;
  if (before.share >= NEARLY_FULL) return after.level !== "over";
  return memoryLine(before, after) === null && after.share < NEARLY_FULL;
}

/** Kilobytes as the editor shows them: whole numbers, rounded up for what is needed, down for what there is. */
export const kilobytes = (bytes: number, up = false) => (up ? Math.ceil(bytes / 1024) : Math.floor(bytes / 1024));
