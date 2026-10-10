/** A tile's options as the add-on keeps them, and which choices the inspector may offer (app 0.4.0, GitHub #47).
 *
 * The add-on refuses a page document whose options its own normalizer would still change
 * (page_layout.validate_document: "Tile options need normalization"). So the editor stores the canonical form,
 * and a choice is offered only when the tile, with that choice applied the way the editor applies it, still passes
 * the same card check the save runs (validateCardOptions). Both ask here, so a choice that shows is a choice that saves.
 */
import { t } from "../i18n";
import rules from "./page-rules.json";
import { isTallSize, isWideSize } from "./sizes";
import { validateCardOptions } from "./page-validation";
import { controlOption, drawable, fits, ofType } from "./catalogue";
import { ACTS_ON_TAP, holdHintKey, SLIDER_DOMAINS, SWITCHES_ON_TAP, TOGGLE_BEFORE } from "./layout";
import { coverPrimary, hasCoverTilt, withCoverTilt } from "./tall-controls";
import type { Capability, PageTile, Tile, TileOptions } from "../types";
import { BUILTIN_CARDS, type BuiltinName } from "../types";
import { PLUGIN_TILE } from "./plugins";

const APPEARANCE = { display: "display", icon: "icon", background: "background", historyHours: "history_hours", refresh: "refresh", subtitle: "sub", fit: "fit", overlay: "overlay",
  mapEntities: "map", mapFraming: "framing", mapDistance: "distance",
  mapFollow: "follow", mapMarkers: "markers", mapNames: "names", mapZones: "zones", mapStreets: "streets", mapLook: "look",
  energyFlow: "flow" } as const;
const INTERACTION = ["tap", "inline", "controls", "action", "play", "speaker", "shuffle", "repeat"] as const;
const PICTURE_OWN = ["refresh", ...Object.keys(rules.picture)];
// A map card's own choices (app 0.4.33); its name on the picture is the live picture's `overlay`.
const MAP = ofType("person")?.map;
const MAP_OWN = ["map", "framing", "distance", "follow", "markers", "names", "zones", "streets", "look"];
// The map tile of the screen's own cards (app 0.4.36): a map and nothing else.
const MAP_TILE = "screen.map";

// What a choice that asks a second step stands for while the inspector tries it: Perform action asks which action,
// a value of the entity which value, words of your own the words. The step itself is checked when it is taken.
const SAMPLE_ACTION = { action: "homeassistant.turn_on" };
// The value an option means when it is not stored, where the add-on drops the stored one (core.validate_layout).
export const DEFAULTS: Record<string, unknown> = { sub: "auto", fit: rules.picture.fit[0], overlay: rules.picture.overlay[0],
  framing: MAP?.framing[0], distance: MAP?.distance[0], follow: MAP?.follow[0], markers: MAP?.markers[0], names: MAP?.names[0],
  zones: MAP?.zones[0], streets: MAP?.streets[0], look: MAP?.look[0], flow: rules.energyFlow[0] };

const pageTile = (entity: string) => /^screen\.page_\d+$/.test(entity);

/** Mirrors core.validate_layout's normalization, so the document the editor saves is already canonical. */
export function canonicalOptions(entity: string, options: TileOptions = {}, key = false): TileOptions {
  const out: TileOptions = { ...options };
  if (entity === MAP_TILE) { out.display = "map"; for (const field of ["inline", "controls", "history_hours", "sub"]) delete out[field]; }
  if (typeof out.sub === "string" && out.sub.startsWith("text:")) {
    const words = out.sub.slice(5).trim();
    out.sub = words ? `text:${words}` : "none";
  }
  if (out.sub === "auto") delete out.sub;
  // Perform action keeps its action; another tap choice leaves none behind.
  if (out.tap !== "action") delete out.action;
  // A live picture's pace and fill belong to the live picture, and their defaults are not stored. A bedside clock's key
  // keeps whether its name shows (`overlay`, firmware 0.17.0), as a picture does.
  if (out.display !== "live") for (const field of PICTURE_OWN) if (!((key || out.display === "map") && field === "overlay")) delete out[field];
  // A map keeps who rides along and how it frames them; an empty list is no list, as the add-on stores it.
  if (out.display !== "map") for (const field of MAP_OWN) delete out[field];
  // A favourite (app 0.4.42) keeps what it plays and its speaker; it plays on a tap, so it has no slider or controls.
  if (out.display !== "favorite") { delete out.play; delete out.speaker; delete out.shuffle; delete out.repeat; }
  else { delete out.inline; delete out.controls; if (out.tap === "action") delete out.tap; }
  if (Array.isArray(out.map) && !out.map.length) delete out.map;
  // Following is the map tile's own; a person's map follows that person.
  if (entity !== MAP_TILE) delete out.follow;
  // How power shows along a line is the energy card's own (catalogue/screen.yaml `energy`).
  if (entity !== "screen.energy") delete out.flow;
  for (const [key, value] of Object.entries(DEFAULTS)) if (out[key] === value) delete out[key];
  // A Go to page tile has a name, an icon, a colour and a width, nothing else.
  if (pageTile(entity)) for (const key of ["display", "inline", "controls", "history_hours"]) delete out[key];
  if (rules.wideOnly.includes(String(out.display)) && !isWideSize(out.size ?? "single")) out.size = "wide";
  return out;
}

/** What else changes with one choice, as the inspector applies it: a watch face has no slider or controls, a slider
 * no controls, direct controls the standard face. `controlled`: the domain has direct controls at all. */
export function coupledOptions(options: TileOptions = {}, key: string, value: unknown, controlled: boolean): TileOptions {
  const out: TileOptions = { ...options, [key]: value };
  const size = String(out.size ?? "single");
  if (key === "display" && value === "watch") { out.inline = "none"; if (controlled) out.controls = "none"; }
  if (key === "inline" && value === "slider") { out.display = "standard"; if (controlled) out.controls = "none"; }
  if (key === "controls" && value === "none" && isTallSize(size)) out.inline = "none";
  if (key === "controls" && value !== "none") { if (out.display !== "cover") out.display = "standard"; out.inline = "none"; }
  // A map is the whole card: no small slider, no controls on it.
  if (key === "display" && (value === "map" || value === "favorite")) { delete out.inline; delete out.controls; }
  // Choosing an action is choosing Perform action.
  if (key === "action") out.tap = "action";
  return out;
}

/** The card the add-on checks, built from a tile and a set of options. */
function cardOf(tile: Tile, options: TileOptions): PageTile {
  const appearance: PageTile["appearance"] = { label: tile.name };
  for (const [key, wire] of Object.entries(APPEARANCE)) if (options[wire] !== undefined) Object.assign(appearance, { [key]: options[wire] });
  const interaction: PageTile["interaction"] = {};
  for (const key of INTERACTION) if (options[key] !== undefined) Object.assign(interaction, { [key]: options[key] });
  const content: PageTile["content"] = pageTile(tile.entity) ? { kind: "navigation", target: { kind: "home" } }
    : BUILTIN_CARDS.includes(tile.entity) ? { kind: "builtin", name: tile.entity.slice(7) as BuiltinName }
    : PLUGIN_TILE.test(tile.entity) ? { kind: "plugin", plugin: PLUGIN_TILE.exec(tile.entity)![1], tile: PLUGIN_TILE.exec(tile.entity)![2], ...(options.plugin ? { options: options.plugin } : {}) }
    : { kind: "entity", entityId: tile.entity };
  return { id: tile.id || "trial", content, appearance, interaction, placement: { row: 0, column: 0, columns: 1, rows: 1 } };
}

/** Whether the add-on would save a tile with these options as they are. */
export function optionsSave(tile: Tile, options: TileOptions): boolean {
  try {
    validateCardOptions(cardOf(tile, options), tile.entity, String(options.size ?? "single"));
    return true;
  } catch {
    return false;
  }
}

/** Whether the inspector may offer `value` for `key`: applied as the inspector applies it, the tile still saves and the
 * choice is still there (a default the add-on drops counts as there). A choice with a second step is tried with a
 * sample of that step. */
export function choiceOffered(tile: Tile, key: string, value: unknown, controlled: boolean): boolean {
  let options = canonicalOptions(tile.entity, coupledOptions(tile.options, key, value, controlled), tile.in !== undefined);
  if (key === "tap" && value === "action" && !options.action) options = { ...options, action: tile.options?.action ?? SAMPLE_ACTION };
  if (!optionsSave(tile, options)) return false;
  const kept = options[key];
  return JSON.stringify(kept) === JSON.stringify(value) || (kept === undefined && DEFAULTS[key] === value);
}

/** The choices of one field the inspector may show: those `choiceOffered` allows, and the one the tile has now, so a
 * stored choice never disappears from sight. */
export function offeredChoices<T extends string | number>(tile: Tile, key: string, choices: [T, string][], current: unknown, controlled: boolean,
  sample: (value: T) => unknown = (value) => value): [T, string][] {
  return choices.filter(([value]) => value === current || choiceOffered(tile, key, sample(value), controlled));
}

// ---- What the tile panel offers, and what it says of a choice ----
// The choices of each field and the hint under it, from the tile, what Home Assistant says the entity can do and what
// the screen's firmware draws. Every list goes through offeredChoices: a choice that shows is a choice that saves.

/** Whether the screen's firmware is at least this version (the screen store's supports). */
export type Supports = (major: number, minor: number, patch: number) => boolean;
export type TilePanel = {
  /** What Home Assistant says the entity can do (api/capabilities); unknown while it cannot say. */
  caps?: Capability | null;
  supports: Supports;
  /** The board draws pictures: a live camera, an album cover, a map. */
  pictures: boolean;
  /** The domain's control sets as the add-on lists them (inventory.controls), when it has any. */
  catalogue?: { default: string; choices: { key: string; label: string }[] };
  /** The page's columns, for a control that asks for a wide card. */
  columns: number;
  /** What Home Assistant reports of the entity now. */
  attributes: Record<string, any>;
  /** The screen draws no thermostat range (its firmware's climate_range is false). */
  rangeless: boolean;
};
export type Hint = { text: string; warn: boolean };
const option = (tile: Tile, key: string, fallback: unknown) => tile.options?.[key] ?? fallback;
const domainOf = (tile: Tile) => tile.entity.split(".")[0];
const sizeOfTile = (tile: Tile) => String(option(tile, "size", "single"));
const offer = <T extends string | number>(tile: Tile, panel: TilePanel, key: string, choices: [T, string][], now: unknown, sample?: (value: T) => unknown) =>
  offeredChoices(tile, key, choices, now, Boolean(panel.catalogue), sample);

/** The face a tile has: a settings card has none to pick (GitHub #47), a clock is digital until it is given another. */
export const tileDisplay = (tile: Tile) => tile.entity === "screen.settings" ? "standard" : String(option(tile, "display", tile.entity === "screen.clock" ? "digital" : "standard"));
/** A live camera fills its card on every size (app 0.3.13, firmware 0.3.7; 1x2 and 2x2 since app 0.3.8, firmware 0.3.3). */
export const cardFilled = (tile: Tile, supports: Supports) => supports(0, 3, 7) || (isTallSize(sizeOfTile(tile)) && supports(0, 3, 3));
// The calm dial and the flip clock (firmware 0.3.6).
const clockFace = (tile: Tile) => tile.entity === "screen.clock" && ["dial", "flip"].includes(tileDisplay(tile));

/** The faces the panel offers: the add-on's own table of displays per domain (page-rules.json), so the editor never
 * offers one it refuses to save (a camera has no large value, app 0.3.8), narrowed by what Home Assistant says the entity
 * can do and what the board draws. The face the tile has stays. */
export function displayChoices(tile: Tile, panel: TilePanel) {
  const c = panel.caps, display = tileDisplay(tile), size = sizeOfTile(tile);
  const keys = ((rules.displays as Record<string, string[]>)[domainOf(tile)] || ["standard", "watch"]).filter((key) => {
    if (key === "forecast") return !c || c.displays.includes("forecast") || display === "forecast";
    if (key === "graph") return !c || c.displays.includes("graph") || display === "graph";
    // The album cover on a media tile (app 0.2.92), on a board that draws pictures; the tile over the whole page has the card's big cover.
    if (key === "cover") return (panel.pictures || display === "cover") && size !== "full";
    // A map (app 0.4.33) is a picture the add-on draws: only on a board that draws pictures.
    if (key === "map") return panel.pictures || display === "map";
    // A favourite (app 0.4.42): a player whose library Home Assistant browses; never the whole page, where the card is the player.
    if (key === "favorite") return ((!c || c.displays.includes("favorite")) && size !== "full") || display === "favorite";
    return true;
  });
  return offer(tile, panel, "display", keys.map((key) => [key, t(`editor.tile.display.${key}`)] as [string, string]), display);
}
/** What the panel says of the face: what it needs or does, a warning unless the screen's firmware already does it. */
export function displayHint(tile: Tile, panel: TilePanel): Hint | null {
  const c = panel.caps, display = tileDisplay(tile), supports = panel.supports, filled = cardFilled(tile, supports), taller = isTallSize(sizeOfTile(tile));
  let text = "";
  if (c && display === "graph" && !c.displays.includes("graph")) text = t("editor.tile.display.no_graph");
  else if (c && display === "forecast" && !c.displays.includes("forecast")) text = t("editor.tile.display.no_forecast");
  else if (display === "live") text = t(filled ? "editor.tile.display.live_card_hint" : supports(0, 2, 77) ? "editor.tile.display.live_card_needs_firmware" : "editor.tile.display.live_needs_firmware");
  else if (display === "map") text = t(supports(0, 20, 0) ? "editor.tile.display.map_hint" : "editor.tile.display.map_needs_firmware");
  else if (display === "favorite") text = t(supports(0, 24, 0) ? "editor.tile.display.favorite_hint" : "editor.tile.display.favorite_needs_firmware");
  else if (display === "cover" && taller) text = t("editor.tile.display.tall_cover_hint");
  else if (display === "cover") text = t(supports(0, 2, 78) ? "editor.tile.display.cover_hint" : "editor.tile.display.cover_needs_firmware");
  // The calm dial and the flip clock (firmware 0.3.6): an older screen shows the digital clock until it is updated.
  else if (clockFace(tile) && !supports(0, 3, 6)) text = t("editor.tile.display.face_needs_firmware");
  if (!text) return null;
  const warn = !(display === "live" && filled) && !(display === "cover" && supports(0, 2, 78)) && !(display === "favorite" && supports(0, 24, 0))
    && !(display === "map" && supports(0, 20, 0)) && !(clockFace(tile) && supports(0, 3, 6));
  return { text, warn };
}

/** The control set the panel shows as chosen: the small slider's kind on a taller card that has one, else the tile's own
 * or its domain's default (none on a card two rows high or the whole page). */
export function tileControls(tile: Tile, panel: TilePanel, inlineKind: string) {
  const size = sizeOfTile(tile);
  return isTallSize(size) && option(tile, "inline", "none") === "slider" ? inlineKind
    : option(tile, "controls", ["tall", "full"].includes(size) ? "none" : panel.catalogue?.default) as string;
}
/** The control sets the panel offers: a blind's slats are a switch of their own; room for it on a card of this size (the
 * mode keys and the slats ask a second row) and a screen that draws it for this entity (a range: firmware 0.19.0+), as
 * the tile catalogue says (model/catalogue.ts); what Home Assistant says the entity can do. The tile's own stays. */
export function controlChoices(tile: Tile, panel: TilePanel, controls: string) {
  const c = panel.caps, domain = domainOf(tile), size = sizeOfTile(tile);
  const primary = domain === "cover" ? coverPrimary(controls) : controls, tilt = domain === "cover" && hasCoverTilt(controls);
  const choices = (panel.catalogue?.choices || []).filter((ch) => domain !== "cover" || !hasCoverTilt(ch.key))
    .filter((ch) => ch.key === "none" || fits(controlOption(domain, ch.key), size, panel.columns))
    .filter((ch) => ch.key === "none" || drawable(domain, ch.key, panel.attributes, panel.rangeless ? new Set<string>() : null) === ch.key)
    .filter((ch) => !c || ch.key === "none" || ch.key === primary || c.controls.includes(ch.key)).map((ch) => [ch.key, ch.label] as [string, string]);
  return offer(tile, panel, "controls", choices, primary, (key) => domain === "cover" ? withCoverTilt(key, tilt) : key);
}
/** Whether a blind's slats can go beside its control: on a card two rows high or the whole page, where the blind has slats. */
export function tiltOffered(tile: Tile, panel: TilePanel, controls: string) {
  const domain = domainOf(tile), size = sizeOfTile(tile), tilt = domain === "cover" && hasCoverTilt(controls);
  return domain === "cover" && (isTallSize(size) || size === "full")
    && (tilt || Boolean(panel.caps?.controls.includes("tilt") && choiceOffered(tile, "controls", withCoverTilt(coverPrimary(controls), true), Boolean(panel.catalogue))));
}
/** What the panel says of the control: a warning for one Home Assistant does not offer, else where it stands. */
export function controlHint(tile: Tile, panel: TilePanel, controls: string): Hint {
  const c = panel.caps, size = sizeOfTile(tile);
  if (c && controls !== "none" && !c.controls.includes(controls)) return { text: t("editor.tile.controls.not_offered"), warn: true };
  return { text: panel.supports(0, 2, 19)
    ? t(isTallSize(size) ? "editor.tile.controls.tall_hint" : size === "full" ? "editor.tile.controls.full_hint" : "editor.tile.controls.wide_hint")
    : t("editor.tile.controls.needs_firmware"), warn: false };
}

/** What a tap may do: an automation (firmware 0.7.0+) switches or runs, holding it does the other one; any other tile
 * opens its card, nothing, switches where Home Assistant can toggle it, or performs an action (a favourite plays and
 * keeps none). `plugins`: the taps the plugins on this screen offer for this kind of tile (docs/PLUGINS.md); one set to a
 * plugin that left the screen stays listed under its own name until it is changed. */
export function tapChoices(tile: Tile, panel: TilePanel, tap: string, plugins: [string, string][]) {
  const domain = domainOf(tile);
  if (domain === "automation") {
    const keys = ["auto", "run", "none", "action"];
    if (!keys.includes(tap)) keys.splice(2, 0, tap);
    return offer(tile, panel, "tap", keys.map((key) => [key, t(key === "auto" ? "editor.tile.tap.toggle" : `editor.tile.tap.${key}`)] as [string, string]), tap);
  }
  const keys = ["auto", "detail", "none"];
  // On / off where Home Assistant can toggle the entity, such as a cover; a speaker without on and off gets none.
  if ((panel.caps ? panel.caps.toggle : TOGGLE_BEFORE.includes(domain)) || tap === "toggle") keys.push("toggle");
  if (tileDisplay(tile) !== "favorite") keys.push("action");
  const fromPlugins = [...plugins];
  if (tap.startsWith("plugin:") && !fromPlugins.some(([key]) => key === tap)) fromPlugins.push([tap, tap]);
  return [...offer(tile, panel, "tap", keys.map((key) => [key, t(`editor.tile.tap.${key}`)] as [string, string]), tap), ...fromPlugins];
}
/** What the panel says of the tap: what holding the tile does, or what a firmware or Home Assistant lacks for it. */
export function tapHint(tile: Tile, panel: TilePanel, tap: string): Hint | null {
  const domain = domainOf(tile), supports = panel.supports;
  if (domain === "automation" && !supports(0, 7, 0)) return { text: t("editor.tile.tap.automation_needs_firmware"), warn: true };
  if (domain === "automation" && ["auto", "toggle", "run"].includes(tap))
    return { text: t(tap === "run" ? "editor.tile.tap.hold_toggle" : "editor.tile.tap.hold_run"), warn: false };
  if (tap === "toggle" && panel.caps && !panel.caps.toggle) return { text: t("editor.tile.tap.no_toggle"), warn: true };
  if (tap === "toggle" && !TOGGLE_BEFORE.includes(domain) && !supports(0, 2, 58)) return { text: t("editor.tile.tap.toggle_needs_firmware"), warn: false };
  if (tap === "detail" && SWITCHES_ON_TAP.includes(domain))
    return { text: t("editor.tile.tap.detail_no_toggle", { auto: t("editor.tile.tap.auto") }), warn: false };
  // A camera opens full screen either way; every other tile opens its card when held.
  if ((tap === "auto" && ACTS_ON_TAP.includes(domain)) || ((tap === "toggle" || tap === "action") && !["camera", "image"].includes(domain)))
    return { text: t(holdHintKey(domain)), warn: false };
  return null;
}

/** The ways to fill the second line (app 0.2.105, firmware 0.2.90+): the screen's own line, nothing, a value of the entity
 * where Home Assistant names one, or words of your own; the last two tried with a sample of the step they ask. */
export function subChoices(tile: Tile, panel: TilePanel, kind: string, values: number, attribute: string) {
  const keys = ["auto", "none"];
  if (values || kind === "attr") keys.push("attr");
  keys.push("text");
  const sample = (key: string) => key === "attr" ? `attr:${attribute || "state"}` : key === "text" ? "text:x" : key;
  return offer(tile, panel, "sub", keys.map((key) => [key, t(`editor.tile.sub.${key}`)] as [string, string]), kind, sample);
}
/** Whether the panel offers the small slider: on a card of one row whose domain has one, where Home Assistant does not
 * say it has nothing to slide; one the tile has stays. */
export function sliderOffered(tile: Tile, panel: TilePanel) {
  const inline = option(tile, "inline", "none");
  return !isTallSize(sizeOfTile(tile)) && tileDisplay(tile) !== "favorite" && SLIDER_DOMAINS.includes(domainOf(tile)) && (inline === "slider" ||
    ((!panel.caps || panel.caps.inline) && choiceOffered(tile, "inline", "slider", Boolean(panel.catalogue))));
}
/** The pages a Go to page tile may open: the ones the screen has and the empty one after them, where a sub-page starts
 * (app 0.2.78), at most what the screen takes, and a target beyond them so the choice stays in sight. */
export function goesToChoices(target: number, total: number, most: number, empty: (page: number) => boolean) {
  const list = Array.from({ length: Math.min(most, total + 1) }, (_, i) => i + 1);
  if (target > list.length) list.push(target);
  return list.map((n) => [n, empty(n) ? t("editor.tile.goes_to.empty", { page: n }) : String(n)] as [number, string]);
}
/** What the panel says of the page it opens: firmware that cannot, a page that is not there, or what it does. */
export function goesToHint(target: number, total: number, fullPage: boolean): Hint {
  if (!fullPage) return { text: t("editor.tile.goes_to.needs_firmware"), warn: false };
  if (target > total) return { text: t("editor.tile.goes_to.no_page", { page: target }), warn: true };
  return { text: t("editor.tile.goes_to.hint"), warn: false };
}
