// Tiles that show nothing any more: their entity is no longer in Home Assistant, or Home Assistant has had no word from
// it for a while. A moment of "unavailable" (a device restarting, Home Assistant starting) is not broken: only an
// entity unavailable for UNAVAILABLE_MS, by Home Assistant's own last change (the inventory's unavailable_since), and
// one the page knows the state of now as something else is fine again. Only the entity a tile must have counts: a
// tile of an entity and a bedside clock's key, and a plugin's tile that names one (its entity is optional, so a plugin
// tile without one is fine). The screen's own cards and Go to page tiles have none. Pure: the stores hand in what they
// know (stores/broken.ts), and the words come from the translations.
import { t } from "../i18n";
import { matchesWords, prefixRank, queryWords } from "./search";
import type { Entity, PageLayout, Screen } from "../types";

export const UNAVAILABLE_MS = 5 * 60_000;
export type Health = { kind: "missing" } | { kind: "unavailable"; since: number };
export type HealthFacts = {
  /** Whether Home Assistant is connected and its entities are known: without them nothing can be said to be gone. */
  ready: boolean;
  /** The entity as the inventory has it (an entity, a card of the screen's own or a tracker), if it does. */
  known: (id: string) => Entity | undefined;
  /** Its state as the page asked for it last (the open layout's live values), if it did. */
  live: (id: string) => string | undefined;
  now: number;
};
/** Whether an entity a tile shows is gone or has been unavailable for a while; null when it is fine or nobody can say. */
export function entityHealth(id: string, facts: HealthFacts): Health | null {
  if (!facts.ready) return null;
  const known = facts.known(id);
  if (!known) return { kind: "missing" };
  const live = facts.live(id);
  if (live !== undefined && live !== "unavailable") return null;
  if ((live ?? known.state) !== "unavailable" || known.unavailable_since === undefined) return null;
  const since = known.unavailable_since * 1000;
  return facts.now - since >= UNAVAILABLE_MS ? { kind: "unavailable", since } : null;
}

/** The entity one tile must have, where it stands: its page, its tile (or the clock a key stands under) and its label. */
export type TileEntity = { pageId: string; page: number; pageTitle: string; tileId: string; entity: string; label: string; holder?: string; plugin?: boolean };
export function tileEntities(layout: PageLayout): TileEntity[] {
  const out: TileEntity[] = [];
  layout.pages.forEach((page, index) => {
    // A page with a title of its own is named by it, one with the screen's title by its number.
    const where = { pageId: page.id, page: index, pageTitle: page.topbar.title.source === "text" ? page.topbar.title.text : "" };
    for (const tile of page.tiles) {
      const content = tile.content;
      if (content.kind === "entity") out.push({ ...where, tileId: tile.id, entity: content.entityId, label: tile.appearance.label });
      else if (content.kind === "plugin" && content.entityId) out.push({ ...where, tileId: tile.id, entity: content.entityId, label: tile.appearance.label, plugin: true });
      for (const child of tile.children || [])
        out.push({ ...where, tileId: child.id, entity: child.content.entityId, label: child.appearance.label, holder: tile.id });
    }
  });
  return out;
}

export type BrokenTile = TileEntity & { screen: Screen; health: Health };
/** Every broken tile of these screens, screen by screen and page by page; `layoutOf` is the layout a screen has (the
 * open one's draft, the others' saved document). */
export function brokenTiles(screens: readonly Screen[], layoutOf: (screen: Screen) => PageLayout | null, health: (id: string) => Health | null): BrokenTile[] {
  const out: BrokenTile[] = [];
  for (const screen of screens) {
    const layout = layoutOf(screen);
    if (!layout) continue;
    for (const tile of tileEntities(layout)) {
      const found = health(tile.entity);
      if (found) out.push({ ...tile, screen, health: found });
    }
  }
  return out;
}
/** `screen`: the one screen's name, when they are all on one. */
export type BrokenSummary = { tiles: number; screens: number; kind: "missing" | "unavailable" | "mixed"; screen?: string };
export function brokenSummary(list: readonly BrokenTile[]): BrokenSummary | null {
  if (!list.length) return null;
  const kinds = new Set(list.map((tile) => tile.health.kind));
  const screens = new Set(list.map((tile) => tile.screen.id)).size;
  return { tiles: list.length, screens, kind: kinds.size > 1 ? "mixed" : [...kinds][0], ...(screens === 1 ? { screen: list[0].screen.name } : {}) };
}
/** "3 tiles on 2 screens show an entity that no longer exists"; on one screen, that screen by its name. */
export function summaryText(summary: BrokenSummary) {
  const screens = summary.screen ?? t("editor.broken.screens", summary.screens);
  return t(`editor.broken.summary.${summary.kind}`, { screens, n: summary.tiles }, summary.tiles);
}
/** What is wrong with one tile's entity: gone, or how long it has been unavailable. */
export function healthText(health: Health, now: number) {
  if (health.kind === "missing") return t("editor.broken.missing");
  const minutes = Math.max(1, Math.floor((now - health.since) / 60000));
  if (minutes < 60) return t("editor.broken.unavailable_minutes", minutes);
  if (minutes < 48 * 60) return t("editor.broken.unavailable_hours", Math.floor(minutes / 60));
  return t("editor.broken.unavailable_days", Math.floor(minutes / 1440));
}
/** Where a broken tile stands: its screen and its page. */
export const whereText = (tile: BrokenTile, withScreen = true) =>
  [withScreen ? tile.screen.name : "", tile.pageTitle || t("editor.page.label", { page: tile.page + 1 })]
    .filter(Boolean).join(" · ");

// ---- Another entity for a tile ----
const words = (id: string) => id.toLocaleLowerCase().split(/[._\s-]+/).filter((word) => word.length > 1);
/** The entities a tile could show instead of `old`: with nothing typed those of its kind, the ones whose names share the
 * most words with it first (sensor.kitchen_temperature_2 for a sensor.kitchen_temperature that went); with something
 * typed, what the search finds, its kind first, ranked as the library ranks. */
export function replacementCandidates(old: string, entities: readonly Entity[], query: string, limit = 30): Entity[] {
  const domain = old.split(".")[0], wanted = queryWords(query);
  const pool = entities.filter((entity) => entity.tile !== false && entity.id !== old);
  if (!wanted.length) {
    const own = new Set(words(old.split(".").slice(1).join(".")));
    const shared = (entity: Entity) => [...new Set([...words(entity.id.split(".").slice(1).join(".")), ...words(entity.name)])].filter((word) => own.has(word)).length;
    return pool.filter((entity) => entity.id.startsWith(`${domain}.`)).map((entity, index) => ({ entity, index, score: shared(entity) }))
      .sort((a, b) => b.score - a.score || a.index - b.index).slice(0, limit).map(({ entity }) => entity);
  }
  const found = pool.filter((entity) => matchesWords(wanted, entity.name, entity.id, entity.area, entity.device));
  const rank = (entity: Entity) => (entity.id.startsWith(`${domain}.`) ? 0 : 3) + prefixRank(entity.name, wanted[0]);
  return found.map((entity, index) => ({ entity, index })).sort((a, b) => rank(a.entity) - rank(b.entity) || a.index - b.index)
    .slice(0, limit).map(({ entity }) => entity);
}
