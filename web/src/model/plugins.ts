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
// `features`: a part that uses a feature the screen may have (a voice answering out loud: a speaker), offered only then.
export type PluginPart = { id: string; label: Texts; hint: Texts; flash_kb: number; default: boolean; features?: string[] };
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
// What a plugin adds, read by the add-on from its manifest (plugin_manifest.plugin_type): tiles to put on a page, something
// for the whole screen, or a board's hardware. The Plugins page's tabs.
export type PluginType = "tiles" | "functions" | "hardware";
export const PLUGIN_TYPES: PluginType[] = ["tiles", "functions", "hardware"];
// What a plugin is about, in its maker's word (plugin_manifest.TOPICS): the chips under the tabs.
export const PLUGIN_TOPICS = ["time", "weather", "calendar", "home", "energy", "travel", "money", "sports", "news", "media",
  "photos", "fun", "voice", "tech"] as const;
// What a screen can have that a plugin needs (plugin_manifest.FEATURES): each a promise about one ESPHome id.
export const PLUGIN_FEATURES = ["speaker", "microphone", "media_player"] as const;
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
  type?: PluginType;
  topics?: string[];
  // Which plugin of this id (github.com/<owner>/<repo>[/<folder>], or "folder"), the branch a test follows, its day.
  origin?: string;
  branch?: string | null;
  date?: string | null;
  featured?: boolean;                 // one Tessera recommends to start with (the index's featured.yaml)
  likes?: number;                     // how many like it (the website's count, copied hourly into likes.json)
  liked?: boolean;                    // this app likes it
  boards: string[] | "any";
  board_names?: string[];             // how a person knows those boards; the add-on fills it from boards.json
  // What it needs: PSRAM, other plugins (they come along), features of the screen (a speaker), an ESPHome to build with.
  requires: { psram?: boolean; plugins?: string[]; features?: string[]; esphome?: string };
  provides?: string[];                // the features it brings for other plugins
  flash_kb: number;
  permissions: { home_assistant: string[]; network: string[]; read_entities?: string[] };
  readme: Texts;                      // markdown; the app shows it in the editor's language, else in English
  changelog?: Texts;                  // its CHANGELOG.md: a `## <version>` heading per release, newest first
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
  settings?: { key: string; label: Texts; status?: string | null }[];
};
// A plugin on a screen, as the add-on keeps it (plugins.json): its source and commit, its parts and what was filled in
// (never a secret), and its state: building, active, or failed with the reason.
// `origin` says which plugin of this id it is; `auto` that it came along with another plugin that needs it; `blocked` why
// the index blocks this release (the next build leaves it out).
export type Installed = {
  id: string; version: string; source: PluginSource; ref?: string | null; parts?: string[]; values?: Record<string, string>;
  origin?: string; branch?: string | null; auto?: boolean; blocked?: string | null;
  state?: "building" | "active" | "failed"; reason?: string | null;
  // The fingerprint of the rights the person agreed to when it went on (Plugin.permission_hash then).
  consent?: string | null;
};

// ---- Plugin tiles in a layout: the tile's entity is plugin:<plugin>.<tile>, the type the screen's protocol carries ----
export const PLUGIN_TILE = /^plugin:([a-z0-9_]+)\.([a-z0-9_]+)$/;
export const pluginTileId = (plugin: string, tile: string) => `plugin:${plugin}.${tile}`;
export const isPluginTile = (entity: string) => PLUGIN_TILE.test(entity);
// A plugin's tile type by its entity (plugin:<plugin>.<tile>), and what finds one: the plugins store keeps the tile types
// of the plugins the editor knows (tileTypesOf its index) and hands its lookup to the layout model, the memory price and
// the tile card, which ask it without depending on the store.
export type PluginTileType = { plugin: Plugin; tile: PluginTile };
export type PluginTileLookup = (entity: string) => PluginTileType | undefined;
export const noPluginTiles: PluginTileLookup = () => undefined;
export function tileTypesOf(index: Plugin[]) {
  const types = new Map<string, PluginTileType>();
  for (const plugin of index) for (const tile of plugin.tiles || []) types.set(pluginTileId(plugin.id, tile.id), { plugin, tile });
  return types;
}
// A plugin's top bar item by its key (plugin:<plugin>.<item>), from the same index.
export type PluginBarType = { plugin: Plugin; label: Texts; icon: string; example?: Texts | null };
export function barTypesOf(index: Plugin[]) {
  const types = new Map<string, PluginBarType>();
  for (const plugin of index) for (const bar of plugin.bar_items || []) types.set(`plugin:${plugin.id}.${bar.id}`, { plugin, ...bar });
  return types;
}
/** A known bar item as the editor shows it: its label, icon and example in the editor's language, and its plugin's name. */
export const barItemView = (known: PluginBarType | undefined) =>
  known ? { label: text(known.label), icon: known.icon, example: known.example ? text(known.example) : "", plugin: text(known.plugin.name) } : null;
// The key of one list of choices: plugin, fetch, and the other options it is asked with (the plugins store keeps the lists).
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

// ---- A plugin on a screen ----
// A test: a branch (pinned to the commit it was built from; a newer commit is offered as an update) or a folder (every
// build takes what it holds now).
export const isTest = (item: Installed | undefined) => item?.source === "branch" || item?.source === "folder";
// The add-on keeps a screen's plugins by its inbox, the id every screen route takes.
export const nodeOf = (screen: Screen) => screen.id;
// A screen built from its own YAML (in ESPHome Device Builder, with no profile in Tessera): the add-on cannot add a
// plugin to it, so the page shows the lines to paste instead.
export const ownYaml = (screen: Screen) => !screen.update?.profile;
// Every screen's plugins live in one file only the add-on writes, <node>.plugins.yaml beside its YAML, attached once by
// one line under `packages:`, the way Override YAML attaches <node>.local.yaml. A screen Tessera installed gets the line
// from the add-on; a screen with its own YAML gets it pasted once. After that ESPHome Device Builder, another computer
// sharing the config folder, or the add-on's own update builds the same plugins.
export const fileOf = (screen: Screen) => `${screen.node || screen.id}.plugins.yaml`;
export const attachLine = (screen: Screen) => `packages:\n  tessera_plugins: !include ${fileOf(screen)}`;

// ---- What changed: the releases of a changelog between the version a screen runs and the one on offer ----
const versionOf = (text: string) => text.split(".").map((n) => Number.parseInt(n, 10) || 0);
const newer = (a: string, b: string) => {
  const x = versionOf(a), y = versionOf(b);
  for (let i = 0; i < 3; i++) if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) > (y[i] || 0);
  return false;
};
// The markdown of every release after `from` up to `to` (all of them without `from`), each with its own heading.
export function changesBetween(markdown: string, from?: string | null, to?: string | null) {
  const out: string[] = [];
  let keep = false;
  for (const line of (markdown || "").split("\n")) {
    const heading = /^##\s+v?(\d+\.\d+\.\d+)/.exec(line);
    if (heading) keep = (!from || newer(heading[1], from)) && (!to || !newer(heading[1], to));
    else if (/^#\s/.test(line)) { keep = false; continue; }
    if (keep) out.push(line);
  }
  return out.join("\n").trim();
}

// ---- Does it fit this screen ----
// The reasons a plugin is not offered for a screen, in the order a person can do something about them.
export type Misfit = "board" | "psram" | "firmware" | "flash" | "blocked" | "esphome" | "feature" | "needs" | "built_in";
export type Fit = { ok: true } | { ok: false; reason: Misfit };
// What only the add-on knows about a screen and a plugin (its payload's `fit`, by screen and plugin): a feature nothing
// brings there, a plugin it needs that does not fit, an ESPHome too old to build it. The plugins store keeps it and hands
// fit() the screen's part (`known`), so fit() stays one pure rule.
export type AppFit = Record<string, Record<string, Misfit>>;

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

export function fit(plugin: Plugin, screen: Screen | null, known: Record<string, Misfit> = {}): Fit {
  if (!screen) return { ok: true };
  if (plugin.blocked) return { ok: false, reason: "blocked" };
  if (plugin.fits_api === false) return { ok: false, reason: "firmware" };
  if (plugin.boards !== "any" && !(screen.board && plugin.boards.includes(screen.board))) return { ok: false, reason: "board" };
  if (plugin.requires.psram && !screen.pictures) return { ok: false, reason: "psram" };
  const reason = known[plugin.id];
  if (reason) return { ok: false, reason };
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
  type: "functions", boards: "any", requires: {}, flash_kb: 0, permissions: { home_assistant: [], network: [] }, attributes: [],
  name: { en: installed.id.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()) }, summary: { en: "" },
  readme: { en: "" }, languages: [], source: installed.source,
});
