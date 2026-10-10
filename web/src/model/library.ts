// The library (app 0.4.32): the entities a tile can show, as components/Library.vue lists them. What a search, a kind and
// a room leave, ranked the way Spotlight ranks; grouped by room while browsing, with the screen's own cards and the
// plugins' tiles last; the kinds and rooms the results hold with their counts; and how each entity is named and marked.
// Pure, with the words from the translations.
import { t } from "../i18n";
import { domainInfo, pageTarget } from "./layout";
import { isPluginTile } from "./plugins";
import { matchesQuery, prefixRank } from "./search";
import type { Tile } from "../types";

/** An entity the library offers: Home Assistant's, a card of the screen's own, or a plugin's tile type. */
export type Entry = { id: string; name: string; area?: string; device?: string; state?: string; tile?: boolean };
// The domains to filter on; the label of each is editor.library.filters.<domain>, "" for no filter.
export const FILTERS = [
  "", "light", "climate", "humidifier", "switch", "binary_sensor", "button", "script", "automation", "fan", "cover", "scene", "vacuum", "sensor",
  "media_player", "remote", "weather", "number", "select", "person", "timer", "screen", "alarm_control_panel", "lock",
];
// A kind that takes a second domain along: an input helper with its entity, the sun with the weather.
const ALIAS: Record<string, string> = { switch: "input_boolean", number: "input_number", select: "input_select", weather: "sun", button: "input_button" };
/** The first so many of what is found are listed. */
export const SHOWN = 80;

/** How many tiles each entity has on the screen. */
export function tileCounts(tiles: readonly Tile[]) {
  const counts = new Map<string, number>();
  for (const tile of tiles) counts.set(tile.entity, (counts.get(tile.entity) || 0) + 1);
  return counts;
}
/** Its mark: how often it is on the screen (×2), there once (✓), or to add (+). */
export const markOf = (id: string, counts: Map<string, number>) => (counts.get(id) || 0) > 1 ? `×${counts.get(id)}` : counts.has(id) ? "✓" : "+";
/** Whether an entity is of a kind, the kind's second domain included; every entity for no kind. */
export const inDomain = (id: string, filter: string) => !filter || id.startsWith(filter + ".") || ALIAS[filter] === id.split(".")[0];

export type LibraryFilter = {
  /** What is typed, in lower case. */
  query: string;
  /** The Go to page tiles offered: those of the pages there are and the next one. */
  pages: number;
  /** The board draws pictures: camera and image tiles, and the map tile. */
  pictures: boolean;
  /** Leave out what is on the screen already. */
  hidePlaced: boolean;
  /** How many tiles each entity has on the screen. */
  counts: Map<string, number>;
};
/** What the search and the hide switch leave over: the rooms are counted off this, the kinds off it narrowed to the room. */
export function libraryBase(entries: readonly Entry[], filter: LibraryFilter) {
  return entries.filter((e) => e.tile !== false && pageTarget(e.id) <= filter.pages &&
    (filter.pictures || (!["camera", "image"].includes(e.id.split(".")[0]) && e.id !== "screen.map")) &&
    (!filter.hidePlaced || !filter.counts.has(e.id)) && matchesQuery(filter.query, e.name, e.id, e.device, e.area));
}
/** What a kind leaves of the room's entries: ranked by the search as Spotlight ranks (a name that starts with it first,
 * then one with a word that does), in Home Assistant's order without one. */
export function libraryMatches(pool: readonly Entry[], kind: string, query: string) {
  const found = pool.filter((e) => inDomain(e.id, kind));
  return query ? [...found].sort((a, b) => prefixRank(a.name, query) - prefixRank(b.name, query)) : found;
}
const PLUGINS = "\u0002plugins", SCREEN = "\u0001screen", NONE = "\u0000none";
/** The entities under their room while browsing, the screen's own cards and the plugins' tiles last; a search or a room
 * is one list. */
export function libraryGroups(list: readonly Entry[], grouped: boolean) {
  if (!grouped) return [{ key: "", title: "", entities: [...list] }];
  const byRoom = new Map<string, Entry[]>();
  for (const e of list) {
    const key = isPluginTile(e.id) ? PLUGINS : e.id.startsWith("screen.") ? SCREEN : e.area || NONE;
    byRoom.set(key, [...(byRoom.get(key) || []), e]);
  }
  const order = (key: string) => key === PLUGINS ? 3 : key === SCREEN ? 2 : key === NONE ? 1 : 0;
  return [...byRoom.keys()].sort((a, b) => order(a) - order(b) || a.localeCompare(b)).map((key) => ({
    key, entities: byRoom.get(key)!,
    title: key === PLUGINS ? t("editor.library.plugins") : key === SCREEN ? t("editor.library.filters.screen") : key === NONE ? t("editor.library.no_room") : key,
  }));
}
/** The kinds the results hold, each with its count; the chosen one stays even when nothing matches it any more, otherwise
 * an empty list would have nothing to explain it. */
export function kindCounts(pool: readonly Entry[], chosen: string) {
  const counts = new Map<string, number>();
  for (const e of pool) for (const d of FILTERS) if (d && inDomain(e.id, d)) counts.set(d, (counts.get(d) || 0) + 1);
  return FILTERS.filter((d) => !d || d === chosen || counts.has(d)).map((d) => [d, d ? counts.get(d) || 0 : pool.length] as [string, number]);
}
/** The rooms the results hold with their counts, in order; the chosen one stays. */
export function roomCounts(base: readonly Entry[], chosen: string) {
  const counts = new Map<string, number>();
  for (const e of base) if (e.area) counts.set(e.area, (counts.get(e.area) || 0) + 1);
  if (chosen && !counts.has(chosen)) counts.set(chosen, 0);
  return [...counts.entries()].sort(([a], [b]) => a.localeCompare(b));
}
/** The avatar's tone at a glance: lit for on, grey for an entity Home Assistant can't reach. */
export function entryTone(e: { id: string; state?: string }) {
  const domain = e.id.split(".")[0];
  if (e.state === "unavailable" || e.state === "unknown") return "gone";
  if (["light", "switch", "input_boolean", "automation", "remote", "fan", "humidifier"].includes(domain) && e.state === "on") return "on";
  return "";
}
/** The name without its device's name in front, the way Home Assistant shows an entity on its device's card:
 * "Bedroom screen Night mode" is "Night mode" under "Bedroom screen". A name that is only the device's stays whole. */
export function shortName(e: Entry) {
  const device = e.device?.trim();
  if (!device || !e.name.toLocaleLowerCase().startsWith(device.toLocaleLowerCase() + " ")) return e.name;
  const rest = e.name.slice(device.length).trim();
  return rest.charAt(0).toLocaleUpperCase() + rest.slice(1);
}
/** Under the name: a plugin's tile its plugin, the device it was shortened by, else what it is, and its room where the list
 * doesn't already stand under it. */
export const entryDetail = (e: Entry, grouped: boolean, plugin: string) => isPluginTile(e.id) ? plugin : e.id.startsWith("screen.") ? ""
  : [shortName(e) !== e.name ? e.device : domainInfo(e.id)[0], grouped ? "" : e.area].filter(Boolean).join(" · ");
