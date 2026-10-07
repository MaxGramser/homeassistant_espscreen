// The tile catalogue in the editor (app 0.4.32): what a tile of each entity type can do, read from catalogue.json, which
// tools/generate_catalogue.py writes from catalogue/*.yaml (docs/CATALOGUE.md). The same answers as the add-on's
// screen_manager/app/catalogue.py, function for function; tests/fixtures/catalogue-conformance.json holds cases both
// must answer alike. What an entity may do at all comes from the add-on (api/capabilities, catalogue.offers there, which
// asks Home Assistant); this module answers what a card of a size draws and what a screen gets.
import data from "./catalogue.json";
import { spanOf } from "./sizes";

type Needs = { actions?: { action: string; field?: string }[]; features?: string[]; attributes?: string[]; history?: string; unless?: Needs };
type Screen = { firmware?: string; feature?: string; pictures?: boolean; else?: string };
type Option = { key: string; needs?: Needs; screen?: Screen; sizes?: { full: boolean }; wide?: boolean; rows?: number; of?: string[];
  one_row?: string; fallback?: string; range?: { when?: Needs; screen?: Screen } };
// What one tile of a type keeps in the memory inside a screen's chip (firmware 0.34.0+, model/memory.ts).
export type TypeMemory = { bytes: number; extras: boolean };
type Type = { firmware: string | null; key: boolean; memory: TypeMemory; cards?: Record<string, TypeMemory>; features: Record<string, number>; actions: Record<string, string[][]>;
  displays: Option[]; controls: Option[]; inline: Option | null; toggle: Needs | null; taps: string[]; guards: string[]; picture: Record<string, unknown[]> | null;
  map: { framing: string[]; distance: string[]; overlay: string[]; follow: string[]; markers: string[]; names: string[];
    zones: string[]; streets: string[]; look: string[]; with: string[]; max: number } | null; favorite?: Option[] };
type Attributes = Record<string, any>;

export const TYPES = data.domains as unknown as Record<string, Type>;
export const TILE = data.tile as { taps: string[]; sizes: string[]; history_hours: number[]; memory: { action: number; line: number; page: number; bar_text: number } };
export const DOMAINS = new Set(Object.keys(TYPES));

export const ofType = (domain: string): Type | undefined => TYPES[domain];
export const controlKeys = (domain: string) => (TYPES[domain]?.controls ?? []).map((item) => item.key);
export const displayKeys = (domain: string) => (TYPES[domain]?.displays ?? []).map((item) => item.key);
export const controlOption = (domain: string, key: string | null | undefined) => TYPES[domain]?.controls.find((item) => item.key === key);
export const displayOption = (domain: string, key: string | null | undefined) => TYPES[domain]?.displays.find((item) => item.key === key);
/** Home Assistant's feature bits of a type by their names (catalogue/_ha.json, from its source), joined. */
export const bits = (domain: string, ...names: string[]) => names.reduce((sum, name) => sum | (TYPES[domain]?.features[name] ?? 0), 0);

/** Any of these features where Home Assistant reports the entity's; `strict` (a condition) only on what it reports. */
export function featuresHold(domain: string, names: string[] | undefined, attributes: Attributes, strict = false) {
  const flags = attributes.supported_features;
  if (!names?.length) return true;
  if (typeof flags !== "number") return !strict;
  return names.some((name) => flags & (TYPES[domain]?.features[name] ?? 0));
}
function holdsStrictly(domain: string, needs: Needs, attributes: Attributes) {
  const flags = attributes.supported_features, features = TYPES[domain]?.features ?? {};
  if (needs.features?.length && !(typeof flags === "number" && needs.features.every((name) => flags & (features[name] ?? 0)))) return false;
  return (needs.attributes ?? []).every((name) => attributes[name] != null);
}
/** A variant's `when`: its features reported, its attributes present, and not its `unless`. */
export function condition(domain: string, when: Needs | undefined, attributes: Attributes) {
  if (!when) return true;
  if (!featuresHold(domain, when.features, attributes, true)) return false;
  if ((when.attributes ?? []).some((name) => attributes[name] == null)) return false;
  return !(when.unless && holdsStrictly(domain, when.unless, attributes));
}
/** Whether a screen meets `screen`; what is not known (null) is not held against it. */
export function screenHolds(requirement: Screen | undefined, features: Set<string> | null = null) {
  return !requirement?.feature || features === null || features.has(requirement.feature);
}

/** Rows a size is high on the card: tall and square two, a span its own, the rest one. */
const sizeRows = (size: unknown) => spanOf(size)?.rows ?? (size === "tall" || size === "square" ? 2 : 1);

/** The control set a card draws, or null (catalogue.resolve_controls): the chosen one or its type's default, and on a
 * card one row high what fits there (`one_row`). */
export function resolveControls(tile: { entity: string; options?: Record<string, any> }): string | null {
  const o = tile.options || {}, domain = tile.entity.split(".")[0], keys = controlKeys(domain), size = o.size, span = spanOf(size);
  if (!keys.length || (!["wide", "tall", "square", "full"].includes(size) && !span)
      || !["standard", "cover"].includes(o.display ?? "standard") || o.inline === "slider") return null;
  const fallback = ["tall", "full"].includes(size) || span?.columns === 1 ? "none" : keys[0];
  let choice: string = o.controls ?? fallback;
  const item = controlOption(domain, choice);
  if (item?.one_row && sizeRows(size) === 1 && size !== "full") choice = item.one_row;
  return choice === "none" ? null : choice;
}

/** The control a screen draws for this entity in place of `key` (catalogue.drawable): the type's `fallback` where the
 * entity does not meet its features, the range's `else` where the screen draws no range, and of a pair what is left.
 * `features`: the screen's hello list (null: not known, drawn as chosen). */
export function drawable(domain: string, key: string, attributes: Attributes, features: Set<string> | null): string {
  const item = controlOption(domain, key);
  if (!item) return key;
  if (item.of) {
    const parts = item.of.map((part) => drawable(domain, part, attributes, features));
    if (parts.every((part, i) => part === item.of![i])) return key;
    const kept = item.of.filter((part, i) => parts[i] === part);
    return kept.length === 1 ? kept[0] : kept.length === 0 ? "none" : key;
  }
  if (!featuresHold(domain, item.needs?.features, attributes)) return item.fallback ?? "none";
  if (item.range && condition(domain, item.range.when, attributes) && !screenHolds(item.range.screen, features))
    return item.range.screen?.else ?? "none";
  return key;
}

/** Whether a card of this size has room for an option: a second row where it asks one (the mode keys, the slats), two
 * columns for a wide display, not the whole page where it may not stand there. */
export function fits(item: Option | undefined, size: unknown, columns = 2) {
  if (!item) return true;
  if (item.rows && item.rows > 1 && sizeRows(size) < item.rows && size !== "full") return false;
  if (item.wide && !(size === "wide" || size === "square" || size === "full" || (spanOf(size)?.columns ?? 1) > 1) && columns > 1) return false;
  if (item.sizes && item.sizes.full === false && size === "full") return false;
  return true;
}

/** The taps a tile of this type may have: every tile's, and its own (an automation's run). */
export const taps = (domain: string) => [...TILE.taps, ...(TYPES[domain]?.taps ?? [])];
