// How much of a screen's memory a layout takes (firmware 0.34.0+, docs/TILE_MEMORY.md). The price of each type is the
// tile catalogue's (catalogue/<type>.yaml `memory`); the screen says how much room it has and what its board adds (PSRAM
// or not, the size of a tile and of its block of extras). The screen (tile_memory::cost) and the add-on (core.tile_cost)
// price a tile the same way: tests/fixtures/memory-conformance.json holds the cases all three answer alike.
import { TILE, TYPES, type TypeMemory } from "./catalogue";
import type { ScreenMemory } from "../types";

/** A tile as its price counts it: its entity and the choices that keep something of their own. */
export type PricedTile = { entity: string; options?: { tap?: string; sub?: string } | Record<string, unknown> };

const DEAREST: TypeMemory = Object.values(TYPES).reduce<TypeMemory>((most, type) => (type.memory.bytes > most.bytes ? type.memory : most), { bytes: 0, extras: true });

/** What one tile costs on that screen, in bytes: its type's price, what its own action and second line add, and on a
 * board without PSRAM the tile itself and, where it keeps one, its block of extras. */
export function tileCost(tile: PricedTile, memory: Pick<ScreenMemory, "psram" | "tile" | "extra">) {
  const type = TYPES.screen?.cards?.[tile.entity] ?? TYPES[tile.entity.split(".", 1)[0]]?.memory ?? DEAREST;
  const options = (tile.options || {}) as { tap?: string; sub?: string };
  const action = options.tap === "action", line = typeof options.sub === "string" && options.sub.startsWith("attr:");
  let bytes = type.bytes + (action ? TILE.memory.action : 0) + (line ? TILE.memory.line : 0);
  if (!memory.psram) bytes += memory.tile + (type.extras || action || line ? memory.extra : 0);
  return bytes;
}

/** A page as its price counts it: its top bar's items, of which the entity items keep a text. */
export type PricedPage = { topbar: { trailing: readonly { type: string }[] } };

/** What one page costs: its title, each entity item of its top bar, and on a board without PSRAM its own record. */
export const pageCost = (page: PricedPage, memory: Pick<ScreenMemory, "psram" | "page">) =>
  TILE.memory.page + page.topbar.trailing.filter((item) => item.type === "entity").length * TILE.memory.bar_text + (memory.psram ? 0 : memory.page ?? 0);

/** What these tiles (the keys of a bedside clock included) and pages take together. */
export const layoutCost = (tiles: readonly PricedTile[], memory: ScreenMemory, pages: readonly PricedPage[] = []) =>
  tiles.reduce((sum, tile) => sum + tileCost(tile, memory), 0) + pages.reduce((sum, page) => sum + pageCost(page, memory), 0);

export type MemoryUse = { need: number; room: number; share: number; level: "fine" | "close" | "full" | "over" };

/** Whether the screen is still measuring its room (firmware 0.51.0): it samples it only once a layout has settled, a minute
 * after it starts or gets a new one, and says no room until then. */
export const measuring = (memory: ScreenMemory) => memory.room === null || memory.room === undefined;

/** A layout against the room: how much it needs, the share of the room, and how close to full that is. A layout that
 * takes no more than the tiles on the screen now always counts as fitting, as the add-on lets it through. A screen that is
 * still measuring counts as having no room; the editor asks `measuring` first. */
export function memoryUse(tiles: readonly PricedTile[], memory: ScreenMemory, pages: readonly PricedPage[] = []): MemoryUse {
  const need = layoutCost(tiles, memory, pages), room = memory.room ?? 0;
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
export function memoryCrossing(tiles: readonly PricedTile[], tile: PricedTile, memory: ScreenMemory, pages: readonly PricedPage[] = []) {
  const before = memoryUse(tiles, memory, pages), after = memoryUse([...tiles, tile], memory, pages);
  if (after.level === "over") return before.level === "over" ? null : { line: noRoom(after) ? "none" as const : "over" as const, share: after.share };
  return after.share >= NEARLY_FULL && before.share < NEARLY_FULL ? { line: "close" as const, share: after.share } : null;
}

/** Kilobytes as the editor shows them: whole numbers, rounded up for what is needed, down for what there is. */
export const kilobytes = (bytes: number, up = false) => (up ? Math.ceil(bytes / 1024) : Math.floor(bytes / 1024));
