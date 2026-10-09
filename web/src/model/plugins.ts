// Plugins (docs/PLUGINS.md): what the add-on says about a plugin (plugins.editor_plugin, from the index, a link or a
// test folder), and whether it fits a screen. Pure functions only, so the Plugins page and its tests share one rule.
import { editorLanguage } from "../i18n";
import type { Screen } from "../types";

// A plugin's own words per language, "en" always present. In its repo they live in translations/<language>.json, in two
// parts like Tessera's own files: `screen` (built into the firmware in the screen's language) and `app` (what the editor
// shows); its README is README.md with README.<language>.md beside it. The add-on hands the editor this per-language form.
export type Texts = Record<string, string>;
// An input of kind entity is an entity the plugin's ESPHome part reads itself, of one of `domains`.
export type PluginInput = { id: string; kind: "secret" | "text" | "gpio" | "entity"; label: Texts; hint?: Texts; scope: "all" | "screen"; domains?: string[] };
export type PluginPart = { id: string; label: Texts; hint: Texts; flash_kb: number; default: boolean };
// A tile type of a plugin (docs: the plugins proposal, "Een plugin-tegel"): its sizes as the catalogue names them, its
// price in the screen's memory, the entity it belongs to if any, and the options the inspector draws. An option's
// `options_from` names a fetch of the plugin, whose answer the add-on hands the inspector as a list of choices.
export type PluginTileOption = {
  id: string; kind: "text" | "choice" | "number" | "toggle"; label: Texts; hint?: Texts;
  default?: string | number | boolean; choices?: { value: string; label: Texts }[]; options_from?: string;
  min?: number; max?: number; step?: number; unit?: string;
};
export type PluginTile = {
  id: string; name: Texts; icon?: string; min: string; max: string; memory: number;
  domains?: string[]; options?: PluginTileOption[]; example?: Texts;
  // The add-on draws a preview of it from its data (api/plugins/<id>/preview/<tile>): the manifest names one.
  preview?: boolean;
  // The entities that have every attribute the tile needs (the manifest's `has_attributes`), from the add-on; absent
  // when the tile takes any entity of its domains.
  entities?: string[];
};

// The entities the inspector offers a tile of an entity: those the add-on found with the attributes it needs, and
// always the one it has, which may lack them for a while (an entity that is unavailable has no attributes).
export function offeredEntities<T extends { id: string }>(all: T[], tile: Pick<PluginTile, "entities">, chosen = ""): T[] {
  if (!tile.entities) return all;
  const keep = new Set([...tile.entities, chosen]);
  return all.filter((entity) => keep.has(entity.id));
}
export type PluginSource = "index" | "link" | "branch" | "folder";
export type PluginLabel = "tessera" | "community" | "test";
export type PluginKind = "hardware" | "behaviour";
export type PluginStage = "stable" | "beta" | "example";
export type Plugin = {
  id: string;
  name: Texts;
  summary: Texts;
  icon: string;                       // a Material Design Icons codepoint the editor's font holds (the add-on resolves the name)
  maintainer: string;
  tessera: boolean;                   // a plugin Tessera ships and reviews itself
  version: string;
  repo: string;
  ref?: string | null;                // the commit it is pinned to (a branch's name for one to test), from the add-on
  license: string;
  stage?: PluginStage;                // how far along, in the maker's word (the manifest's `stage`, beta when it says none)
  kind: PluginKind;
  boards: string[] | "any";
  board_names?: string[];             // how a person knows those boards; the add-on fills it from boards.json
  requires: { psram?: boolean };
  flash_kb: number;
  permissions: { home_assistant: string[]; network: string[]; read_entities?: string[] };
  readme: Texts;                      // markdown; the app shows it in the editor's language, else in English
  languages: string[];                // the languages its own texts are complete in
  inputs?: PluginInput[];             // what a person fills in when adding it: a key, a pin, a name
  parts?: PluginPart[];               // optional parts, on or off per screen, each with its own room
  attributes: string[];               // cloud, commercial, ai-developed
  // From the add-on (plugins.py): where it comes from (the index, or a folder someone is making it in), its label, the
  // reason it is blocked, whether this app's plugin API takes it, and its privacy statement.
  source?: PluginSource;
  label?: PluginLabel;
  blocked?: string | null;
  fits_api?: boolean;
  permission_hash?: string;
  privacy?: string;
  // What it adds (the add-on's payload, the manifest's parts; docs/PLUGINS.md "What a plugin can add"): its tiles,
  // its cards, tap actions for tiles of Home Assistant's own, items for the top bar, and its settings.
  tiles?: PluginTile[];
  cards?: { id: string; name: Texts }[];
  tap_actions?: { id: string; label: Texts; domains: string[] }[];
  bar_items?: { id: string; label: Texts; icon: string; example?: Texts | null }[];
  settings?: { key: string; label: Texts }[];
};
// A plugin on a screen, as the add-on keeps it (plugins.json): its source and commit, its parts and what was filled in
// (never a secret), and its state: building, active, or failed with the reason.
export type Installed = {
  id: string; version: string; source: PluginSource; ref?: string | null; parts?: string[]; values?: Record<string, string>;
  state?: "building" | "active" | "failed"; reason?: string | null;
  // The fingerprint of the rights the person agreed to when it went on (Plugin.permission_hash then).
  consent?: string | null;
};

// ---- Plugin tiles in a layout: the tile's entity is plugin:<plugin>.<tile>, the type the screen's protocol carries ----
export const PLUGIN_TILE = /^plugin:([a-z0-9_]+)\.([a-z0-9_]+)$/;
export const pluginTileId = (plugin: string, tile: string) => `plugin:${plugin}.${tile}`;
export const isPluginTile = (entity: string) => PLUGIN_TILE.test(entity);
// The tile types of the plugins the editor knows, kept by the plugin state as its index changes, so the layout model,
// the memory price and the tile card can ask without depending on it.
const tileTypes = new Map<string, { plugin: Plugin; tile: PluginTile }>();
export function knowTileTypes(index: Plugin[]) {
  tileTypes.clear();
  for (const plugin of index) for (const tile of plugin.tiles || []) tileTypes.set(pluginTileId(plugin.id, tile.id), { plugin, tile });
  barTypes.clear();
  for (const plugin of index) for (const bar of plugin.bar_items || []) barTypes.set(`plugin:${plugin.id}.${bar.id}`, { plugin, ...bar });
}
export const pluginTileOf = (entity: string) => tileTypes.get(entity);
// A plugin's top bar item by its key (plugin:<plugin>.<item>), from the same index.
const barTypes = new Map<string, { plugin: Plugin; label: Texts; icon: string; example?: Texts | null }>();
export function barItemOf(key: string | undefined) {
  const known = key ? barTypes.get(key) : undefined;
  return known ? { label: text(known.label), icon: known.icon, example: known.example ? text(known.example) : "", plugin: text(known.plugin.name) } : null;
}
// The key of one list of choices: plugin, fetch, and the other options it is asked with (plugin-state keeps the lists).
export const choiceKey = (plugin: Plugin, option: PluginTileOption, values: Record<string, unknown>) =>
  `${plugin.id}.${option.options_from}.${JSON.stringify(Object.entries(values).filter(([k]) => k !== option.id).sort())}`;
// What a plugin tile's options are when nothing is chosen yet.
export const pluginDefaults = (tile: PluginTile) =>
  Object.fromEntries((tile.options || []).filter((option) => option.default !== undefined).map((option) => [option.id, option.default!]));

// The words in the editor's language, else English.
const own = (texts: Texts) => texts[editorLanguage()] ?? texts[editorLanguage().split("-")[0]];
export const text = (texts: Texts) => own(texts) ?? texts.en ?? "";
// Whether these words exist in the editor's language, or the page falls back to English and says so.
export const inEditorLanguage = (texts: Texts) => own(texts) !== undefined;

// ---- Does it fit this screen ----
// The reasons a plugin is not offered for a screen, in the order a person can do something about them.
export type Misfit = "board" | "psram" | "firmware" | "flash" | "blocked";
export type Fit = { ok: true } | { ok: false; reason: Misfit };

// The 4 MB boards (the classic ESP32: the CYD, its ILI9342 sibling, the Hosyond) run close to the top of their slot.
// What a plugin may add there keeps the image under the 93 % line of docs/RELEASING.md: the CYD's 0.51.0 image is
// 1,853,664 B of 2,031,616 B, which leaves 34 KB below it.
// The add-on reports a 4 MB screen's own last image and slot (firmware_image, Firmware.image_room); before its first
// build the CYD's numbers stand in for every 4 MB board.
export const SMALL_FLASH = { image: 1_853_664, slot: 2_031_616, ceiling: 0.93 };
const SMALL_FLASH_BOARDS = ["cyd", "cyd9342", "hosyond40"];
const imageOf = (screen: Screen) => screen.firmware_image
  || (screen.board && SMALL_FLASH_BOARDS.includes(screen.board) ? { size: SMALL_FLASH.image, slot: SMALL_FLASH.slot } : null);
// Only a slot this full is worth a meter: on 8 MB and more a plugin of a few hundred KB fits without a thought.
const smallFlash = (screen: Screen) => { const image = imageOf(screen); return Boolean(image && image.slot <= 2_100_000); };
export const headroomKb = (screen?: Screen) => {
  const image = (screen && imageOf(screen)) || { size: SMALL_FLASH.image, slot: SMALL_FLASH.slot };
  return Math.max(0, Math.floor((image.slot * SMALL_FLASH.ceiling - image.size) / 1024));
};
// The pins of a board's connector a plugin with its own wiring can use (docs/CYD.md, the CN1 connector, GitHub #189);
// a board not listed takes a pin by its name in a text field.
export const FREE_PINS: Record<string, string[]> = { cyd: ["GPIO22", "GPIO27"], cyd9342: ["GPIO22", "GPIO27"] };
export const freePins = (screen: Screen) => (screen.board && FREE_PINS[screen.board]) || [];

export function fit(plugin: Plugin, screen: Screen | null): Fit {
  if (!screen) return { ok: true };
  if (plugin.blocked) return { ok: false, reason: "blocked" };
  if (plugin.fits_api === false) return { ok: false, reason: "firmware" };
  if (plugin.boards !== "any" && !(screen.board && plugin.boards.includes(screen.board))) return { ok: false, reason: "board" };
  if (plugin.requires.psram && !screen.pictures) return { ok: false, reason: "psram" };
  if (smallFlash(screen) && plugin.flash_kb > headroomKb(screen)) return { ok: false, reason: "flash" };
  return { ok: true };
}

// What its image would take of the update slot on a 4 MB board, before and after: the meter in the details.
export function flashShare(plugin: Plugin, screen: Screen | null, extra_kb = 0) {
  if (!screen || !smallFlash(screen)) return null;
  const image = imageOf(screen)!;
  return { before: image.size / image.slot, after: (image.size + (plugin.flash_kb + extra_kb) * 1024) / image.slot };
}

// A plugin on a screen whose manifest the add-on no longer has (a test folder that went): the page knows it only by its
// record, so it can still be removed.
export const testPlugin = (installed: Installed): Plugin => ({
  id: installed.id, icon: "F0A66", maintainer: "", tessera: false, version: installed.version, repo: "", license: "",
  kind: "behaviour", boards: "any", requires: {}, flash_kb: 0, permissions: { home_assistant: [], network: [] }, attributes: [],
  name: { en: installed.id.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()) }, summary: { en: "" },
  readme: { en: "" }, languages: [], source: installed.source,
});
