// Plugins (docs/PLUGINS.md): what the add-on offers and what each screen runs, shared by the Plugins page (every plugin, and on
// which screens it is) and a screen's own Plugins tab (what this screen has, and what it can add). A plugin lives in a
// screen's firmware, so every change is per screen; the page only sets several screens at once.
import { reactive } from "vue";
import { getJson, send } from "./api";
import { t } from "./i18n";
import { choiceKey, fit, knowTileTypes, pluginTileId, testPlugin, text, type Installed, type Plugin,
  type PluginTileOption, type Texts, pluginTileOf, pluginDefaults} from "./model/plugins";
import { pluginTiles } from "./model/page-validation";
import { computed, watch } from "vue";
import { buildOf, copyText, state, toast } from "./store";
import type { Screen } from "./types";

export const plugins = reactive({
  index: [] as Plugin[],
  installed: {} as Record<string, Installed[]>,
  loaded: false,
  // What a person filled in when adding a plugin (inputs) and which optional parts are on, per screen node and plugin.
  // A secret is kept by the add-on and never comes back to the page; here it only says that one is set.
  values: {} as Record<string, Record<string, Record<string, string>>>,
  // A plugin whose details the screen's Plugins tab opens next (Screen settings sends a person there).
  focus: null as string | null,
  parts: {} as Record<string, Record<string, string[]>>,
  attached: {} as Record<string, boolean>,
  // From the add-on: which secrets are set (never their values), the plugins file of a screen with its own YAML, and the
  // lists of choices it fetched. What a screen is building is the store's (buildOf), as every build is.
  secrets: {} as Record<string, Record<string, boolean>>,
  files: {} as Record<string, { file: string; content: string; line: string }>,
  choices: {} as Record<string, { value: string; label: Texts }[]>,
  // What the add-on drew of a tile's data, by plugin tile and its options (previewFor), and when it was asked.
  previews: {} as Record<string, { items: PreviewRow[]; at: number }>,
  // Entities of the domains the plugins name that the editor's own list lacks (a calendar), from the add-on.
  entities: [] as { id: string; name: string }[],
  // Per plugin: the person agreed to the other rights an update asks for (needsConsent).
  consented: {} as Record<string, boolean>,
  folders: { path: "", errors: {} as Record<string, string> },
});

// Plugins are on in the dev app (editor_features.plugins, docs/PLUGINS.md) and in `npm run dev`: a person with a
// released add-on never sees the page or the tab.
export const pluginsEnabled = computed(() => import.meta.env.DEV || state.inventory.editor_features?.plugins === true);
// The layout model, the memory price and the tile card ask the model's register for a plugin tile; it follows the index.
watch(() => plugins.index, (index) => knowTileTypes(index), { immediate: true });
// The plugins load as soon as they are on, not when the Plugins page opens: a page with a plugin tile needs its type.
watch(pluginsEnabled, (on) => { pluginTiles.enabled = on; if (on) loadPlugins(); }, { immediate: true });

type Payload = {
  plugins: Plugin[]; installed: Record<string, Installed[]>; secrets: typeof plugins.secrets;
  folders: typeof plugins.folders; entities?: typeof plugins.entities;
};
// The add-on's plugins (api/plugins). Asked again when a plugin build of some screen starts or ends (the store's builds,
// live from the add-on), so a record's state and version follow the build without a poll of its own.
export function reloadPlugins(refresh = false) {
  return getJson<Payload>(refresh ? "plugins?refresh=1" : "plugins").then((data) => {
    plugins.index = data.plugins;
    plugins.installed = data.installed;
    plugins.secrets = data.secrets || {};
    plugins.folders = data.folders || { path: "", errors: {} };
    plugins.entities = data.entities || [];
  }).catch(() => undefined);
}
watch(() => Object.entries(state.inventory.builds || {}).filter(([, build]) => build.by === "plugins")
  .map(([screen, build]) => `${screen}:${build.state}`).join(), (now, before) => { if (plugins.loaded && now !== before) reloadPlugins(); });
export function loadPlugins() {
  if (plugins.loaded) return;
  plugins.loaded = true;
  reloadPlugins();
}
// The choices of an option: its own, or those of one of the plugin's fetches (a stop's lines), asked of the add-on with
// the tile's other options.
const asking = new Set<string>();
export function choicesFor(plugin: Plugin, option: PluginTileOption, values: Record<string, unknown>) {
  if (!option.options_from) return option.choices || [];
  const key = choiceKey(plugin, option, values);
  if (!(key in plugins.choices) && !asking.has(key)) {
    asking.add(key);
    const query = new URLSearchParams(Object.entries(values).filter(([k, v]) => k !== option.id && v !== "" && v !== undefined)
      .map(([k, v]) => [k, String(v)])).toString();
    getJson<{ choices: { value: string; label: string }[] }>(`plugins/${plugin.id}/choices/${option.options_from}${query ? `?${query}` : ""}`)
      .then((data) => { plugins.choices[key] = data.choices.map((c) => ({ value: c.value, label: { en: c.label } })); })
      .catch(() => { plugins.choices[key] = []; })
      .finally(() => asking.delete(key));
  }
  return plugins.choices[key] || [];
}

// A plugin tile's look in the mockup (the editor cannot run its C++): the manifest's `preview` filled in by the add-on
// from the tile's data, its first rows; asked again once a minute while a page shows it.
export type PreviewRow = { badge?: string; title?: string; value?: string; at?: number };
const drawing = new Set<string>();
export function previewFor(entity: string, options: Record<string, unknown> | undefined, bound?: string): PreviewRow[] | null {
  const kind = pluginTileOf(entity);
  if (!kind?.tile.preview) return null;
  const values = { ...pluginDefaults(kind.tile), ...(options || {}), ...(bound ? { entity: bound } : {}) };
  const key = `${entity}|${JSON.stringify(values)}`;
  const known = plugins.previews[key];
  if ((!known || Date.now() - known.at > 60000) && !drawing.has(key)) {
    drawing.add(key);
    const query = new URLSearchParams(Object.entries(values).filter(([, v]) => v !== "" && v !== undefined).map(([k, v]) => [k, String(v)])).toString();
    getJson<{ items: PreviewRow[] }>(`plugins/${kind.plugin.id}/preview/${kind.tile.id}${query ? `?${query}` : ""}`)
      .then((data) => { plugins.previews[key] = { items: data.items || [], at: Date.now() }; })
      .catch(() => { plugins.previews[key] = { items: [], at: Date.now() }; })
      .finally(() => drawing.delete(key));
  }
  return known ? known.items : null;
}

// The tap actions a tile of this domain can take on this screen: those of the plugins it runs, as tap choices.
export function tapActionsFor(screen: Screen | undefined, domain: string): [string, string][] {
  if (!screen || screen.virtual) return [];
  return plugins.index.filter((plugin) => installedOn(screen, plugin.id)).flatMap((plugin) =>
    (plugin.tap_actions || []).filter((action) => action.domains.includes(domain))
      .map((action) => [`plugin:${plugin.id}.${action.id}`, text(action.label)] as [string, string]));
}

// The top bar items of the plugins this screen runs: [{ item, label, icon, example }].
export function barItemsFor(screen: Screen | undefined) {
  if (!screen || screen.virtual) return [];
  return plugins.index.filter((plugin) => installedOn(screen, plugin.id)).flatMap((plugin) =>
    (plugin.bar_items || []).map((bar) => ({ item: `plugin:${plugin.id}.${bar.id}`, label: text(bar.label), icon: bar.icon,
      example: bar.example ? text(bar.example) : "", plugin: text(plugin.name) })));
}

// Every entity of these domains: the editor's own and those the add-on sent for plugins, each once.
export function entitiesIn(domains: string[] = []) {
  const seen = new Set<string>();
  return [...state.inventory.entities, ...plugins.entities].filter((e) => domains.includes(e.id.split(".")[0]) && !seen.has(e.id) && seen.add(e.id))
    .map((e) => ({ id: e.id, name: e.name || e.id }));
}

// An update of a plugin on this screen that asks for other rights than the person agreed to: the details ask again.
export function needsConsent(screen: Screen, plugin: Plugin) {
  const have = installedOn(screen, plugin.id);
  return Boolean(have && have.consent && plugin.permission_hash && have.consent !== plugin.permission_hash);
}

export const realScreens = () => state.inventory.screens.filter((screen) => !screen.virtual);
// A test (a branch or a folder) takes what it holds now at every build, so it never waits for an update; a release from
// the index or a link does, pinned to its commit.
export const isTest = (item: Installed | undefined) => item?.source === "branch" || item?.source === "folder";
// Whether this screen has an older release of the plugin than the one on offer, and is not building it now.
export function hasUpdate(screen: Screen, plugin: Plugin) {
  const have = installedOn(screen, plugin.id);
  return Boolean(have && !isTest(have) && have.version !== plugin.version && !buildingOn(screen, plugin.id));
}
// Every plugin of this screen with an update: "Update all on this screen" takes them in one build.
export const updatesOn = (screen: Screen) => plugins.index.filter((plugin) => hasUpdate(screen, plugin));
// The tile types a screen can place: those of the plugins it runs (the library's Plugins group). A preview screen has none.
export function tilesOn(screen: Screen | undefined) {
  if (!screen || screen.virtual) return [];
  return plugins.index.filter((plugin) => installedOn(screen, plugin.id)).flatMap((plugin) =>
    (plugin.tiles || []).map((tile) => ({ id: pluginTileId(plugin.id, tile.id), name: text(tile.name), tile: true,
      plugin: [text(plugin.name), stageOf(plugin) && t(`editor.plugins.stage.${stageOf(plugin)}`)].filter(Boolean).join(" · ") })));
}
// A screen built from its own YAML (in ESPHome Device Builder, with no profile in Tessera): the add-on cannot add a
// plugin to it, so the page shows the lines to paste instead.
export const ownYaml = (screen: Screen) => !screen.update?.profile;
// What is chosen on this page, else what the add-on keeps for this screen (an update sends it again, so nothing filled in
// when the plugin was added is lost), else the manifest's defaults.
export const partsOn = (screen: Screen, plugin: Plugin) => plugins.parts[screen.node || screen.id]?.[plugin.id]
  ?? installedOn(screen, plugin.id)?.parts ?? (plugin.parts || []).filter((part) => part.default).map((part) => part.id);
export function setParts(screen: Screen, plugin: Plugin, ids: string[]) {
  ((plugins.parts[screen.node || screen.id] ||= {})[plugin.id] = ids);
}
export const valueOf = (screen: Screen, plugin: Plugin, id: string) => plugins.values[screen.node || screen.id]?.[plugin.id]?.[id]
  ?? installedOn(screen, plugin.id)?.values?.[id] ?? "";
export function setValue(screen: Screen, plugin: Plugin, id: string, value: string) {
  const node = screen.node || screen.id;
  ((plugins.values[node] ||= {})[plugin.id] ||= {})[id] = value;
}
// Every screen's plugins live in one file only the add-on writes, <node>.plugins.yaml beside its YAML, attached once by
// one line under `packages:`, the way Override YAML attaches <node>.local.yaml. A screen Tessera installed gets the line
// from the add-on; a screen with its own YAML gets it pasted once. After that ESPHome Device Builder, another computer
// sharing the config folder, or the add-on's own update builds the same plugins.
export const fileOf = (screen: Screen) => `${screen.node || screen.id}.plugins.yaml`;
export const attachLine = (screen: Screen) => `packages:\n  tessera_plugins: !include ${fileOf(screen)}`;
// An own-YAML screen counts as attached once the person says the line is in its YAML (the app cannot build it, so it
// cannot check).
export const needsAttach = (screen: Screen) => ownYaml(screen) && !plugins.attached[screen.node || screen.id];
export function markAttached(screen: Screen) { plugins.attached[screen.node || screen.id] = true; }
export const copyAttach = (screen: Screen) => copyText(attachLine(screen), undefined, "yaml");
// The plugins file of a screen with its own YAML, as the add-on wrote it ("" until it has): the add-on pins each plugin to
// the commit of its release, so the page never writes one of its own.
export const pluginsFile = (screen: Screen) => plugins.files[screen.id]?.content || "";
// Whether everything a plugin asks for is filled in on these screens: the button waits until it is.
// Whether what is filled in for a plugin this screen runs differs from what its build has: then "Save and build" applies
// it. A secret counts once something new is typed; the add-on never sends one back.
export function setupChanged(screen: Screen, plugin: Plugin) {
  const have = installedOn(screen, plugin.id);
  if (!have) return false;
  const node = screen.node || screen.id;
  const drafted = plugins.values[node]?.[plugin.id] || {};
  const values = (plugin.inputs || []).some((input) => input.id in drafted && (input.kind === "secret"
    ? drafted[input.id].trim() !== "" : drafted[input.id].trim() !== (have.values?.[input.id] ?? "")));
  const parts = plugins.parts[node]?.[plugin.id];
  return values || (parts !== undefined && [...parts].sort().join() !== [...(have.parts || [])].sort().join());
}
// Open a plugin's details on the screen's Plugins tab: from Screen settings, where its settings used to be.
export function openPluginOn(id: string) { plugins.focus = id; state.tab = "plugins"; }
export const setupReady = (plugin: Plugin, screens: Screen[]) =>
  screens.every((screen) => (plugin.inputs || []).every((input) => valueOf(screen, plugin, input.id).trim() !== ""
    || (input.kind === "secret" && plugins.secrets[plugin.id]?.[input.id])));
// The room the chosen optional parts add.
export const partsKb = (screen: Screen, plugin: Plugin) =>
  partsOn(screen, plugin).reduce((sum, id) => sum + (plugin.parts?.find((part) => part.id === id)?.flash_kb || 0), 0);
// The add-on keeps a screen's plugins by its inbox, the id every screen route takes.
export const nodeOf = (screen: Screen) => screen.id;
export const installedOn = (screen: Screen, id: string) => plugins.installed[nodeOf(screen)]?.find((item) => item.id === id);
// Whether this screen's build (the store's, live from the add-on) brings this plugin, or the page is asking for it now.
const sending = reactive<Record<string, string[]>>({});
export const buildingOn = (screen: Screen, id: string) => {
  const build = buildOf(screen);
  return Boolean((build?.by === "plugins" && build.plugins?.includes(id)) || sending[screen.id]?.includes(id));
};
// A plugin on a screen the add-on has no manifest of any more (a test folder that went): known only by its record.
export const testsOn = (screen: Screen) => (plugins.installed[nodeOf(screen)] || [])
  .filter((item) => item.source !== "index" && !plugins.index.some((p) => p.id === item.id)).map(testPlugin);
export const allTests = () => {
  const seen = new Map<string, Plugin>();
  for (const screen of realScreens()) for (const plugin of testsOn(screen)) seen.set(plugin.id, plugin);
  return [...seen.values()];
};
// Tessera's own, someone else's from the index, or a test the screen runs from a branch, a folder or a link.
export const labelOf = (plugin: Plugin) => plugin.label
  || (plugin.tessera ? "tessera" : plugins.index.some((p) => p.id === plugin.id) ? "community" : "test");
// The badge of its stage: beta or example, none for a stable plugin or one under test (its label says that already).
export const stageOf = (plugin: Plugin): "beta" | "example" | "" =>
  labelOf(plugin) !== "test" && (plugin.stage === "beta" || plugin.stage === "example") ? plugin.stage : "";

// ---- One line of state: for one screen (its tab), or over all screens (the page) ----
export type Status = { kind: "installed" | "update" | "building" | "test" | "misfit" | "failed" | ""; label: string };
export function statusOn(plugin: Plugin, screen: Screen): Status {
  // A screen in the add-on's build queue waits its turn; one at a time builds (docs/PLUGINS.md).
  if (buildingOn(screen, plugin.id))
    return { kind: "building", label: t(buildOf(screen)?.state === "queued" ? "editor.plugins.state.queued" : "editor.plugins.state.building") };
  const have = installedOn(screen, plugin.id);
  if (have?.state === "failed") return { kind: "failed", label: t("editor.plugins.state.failed") };
  if (isTest(have)) return { kind: "test", label: t(`editor.plugins.source.${have!.source}`) };
  if (hasUpdate(screen, plugin)) return { kind: "update", label: t("editor.plugins.state.update", { version: plugin.version }) };
  if (have) return { kind: "installed", label: t("editor.plugins.state.installed") };
  const result = fit(plugin, screen);
  return result.ok ? { kind: "", label: "" } : { kind: "misfit", label: t(`editor.plugins.misfit_short.${result.reason}`) };
}
export function statusOverall(plugin: Plugin): Status {
  const screens = realScreens();
  if (screens.some((screen) => buildingOn(screen, plugin.id))) return { kind: "building", label: t("editor.plugins.state.building") };
  const on = screens.filter((screen) => installedOn(screen, plugin.id));
  // A test names its screen when it is on one; on more it counts them, so the line fits the card beside its chip.
  if (labelOf(plugin) === "test") return { kind: "test", label: on.length === 1 ? t("editor.plugins.state.test_on", { name: on[0].name })
    : on.length ? t("editor.plugins.state.on_screens", { n: on.length }, on.length) : "" };
  const updates = on.filter((screen) => hasUpdate(screen, plugin)).length;
  if (updates) return { kind: "update", label: t("editor.plugins.state.updates", { n: updates }, updates) };
  if (on.length) return { kind: "installed", label: t("editor.plugins.state.on_screens", { n: on.length }, on.length) };
  if (screens.length && !screens.some((screen) => fit(plugin, screen).ok)) return { kind: "misfit", label: t("editor.plugins.state.fits_none") };
  return { kind: "", label: "" };
}

// ---- Changes: add, update or remove on one screen ----
// What goes to the add-on for one screen: the plugin, its parts, what was filled in, and the secrets apart.
function addition(screen: Screen, plugin: Plugin) {
  const values: Record<string, string> = {}, secrets: Record<string, string> = {};
  for (const input of plugin.inputs || []) {
    const value = valueOf(screen, plugin, input.id).trim();
    if (value) (input.kind === "secret" ? secrets : values)[input.id] = value;
  }
  return { id: plugin.id, source: plugin.source || "index", parts: partsOn(screen, plugin), values, secrets,
    ...(plugins.consented[plugin.id] ? { consent: true } : {}) };
}
async function change(screen: Screen, body: object) {
  const result = await send<{ own_yaml?: boolean; file?: string; content?: string; line?: string }>(
    `screens/${encodeURIComponent(screen.id)}/plugins`, "POST", body);
  if (result?.own_yaml) plugins.files[screen.id] = { file: result.file || "", content: result.content || "", line: result.line || "" };
}
// What was filled in for a plugin on a screen, once the add-on has it: the build's own values show from then on, and a
// secret, which never comes back, no longer counts as a change.
export function forgetDrafts(screen: Screen, plugin: Plugin) {
  const node = screen.node || screen.id;
  delete plugins.values[node]?.[plugin.id];
  delete plugins.parts[node]?.[plugin.id];
}
export async function addPlugin(screens: Screen[], plugin: Plugin) {
  if (!screens.length) return;
  // One build at a time: the add-on builds the screens one after the other as each build ends.
  for (const screen of screens) {
    try {
      sending[screen.id] = [plugin.id];
      await change(screen, { add: [addition(screen, plugin)] });
      forgetDrafts(screen, plugin);
    } catch (error: any) {
      toast(error.message);
      break;
    } finally {
      delete sending[screen.id];
    }
  }
  await reloadPlugins();
}
// Every update of one screen in one build (the add-on takes several plugins in one request and builds the screen once).
// An update that asks for other rights goes only with the person's yes (plugins.consented), as it does one by one.
export async function updateAll(screen: Screen, list: Plugin[]) {
  if (!list.length) return;
  sending[screen.id] = list.map((plugin) => plugin.id);
  try {
    await change(screen, { add: list.map((plugin) => addition(screen, plugin)) });
  } catch (error: any) {
    toast(error.message);
  } finally {
    delete sending[screen.id];
  }
  await reloadPlugins();
}
// ---- Ready to install: plugins set aside per screen, installed together in one build per screen ----
// Adding a plugin no longer builds at once: it goes into the tray (PluginTray), where a person can set aside more, on
// this screen or another, and press Install once. Each screen then builds once with all of its plugins, the request
// updateAll already makes. What a plugin asks for (its inputs, trust in a community maker) is filled in its details.
export const tray = reactive({ items: [] as { screen: string; plugin: string }[], open: true, sending: false });
export const isSetAside = (screen: Screen, id: string) => tray.items.some((item) => item.screen === screen.id && item.plugin === id);
export function setAside(screen: Screen, plugin: Plugin) {
  if (!isSetAside(screen, plugin.id)) tray.items.push({ screen: screen.id, plugin: plugin.id });
  tray.open = true;
}
export function takeOut(screen: Screen, id: string) {
  const at = tray.items.findIndex((item) => item.screen === screen.id && item.plugin === id);
  if (at >= 0) tray.items.splice(at, 1);
}
export const toggleSetAside = (screen: Screen, plugin: Plugin) => (isSetAside(screen, plugin.id) ? takeOut(screen, plugin.id) : setAside(screen, plugin));
const pluginById = (id: string) => [...plugins.index, ...realScreens().flatMap(testsOn)].find((p) => p.id === id);
// The tray by screen, in the order the screens were first chosen: one group, one build.
export const trayGroups = computed(() => {
  const groups: { screen: Screen; plugins: Plugin[] }[] = [];
  for (const item of tray.items) {
    const screen = realScreens().find((s) => s.id === item.screen), plugin = pluginById(item.plugin);
    if (!screen || !plugin) continue;
    const group = groups.find((g) => g.screen.id === screen.id) || (groups.push({ screen, plugins: [] }), groups[groups.length - 1]);
    group.plugins.push(plugin);
  }
  return groups;
});
// The room what is set aside on a 4 MB screen takes together: two plugins that each fit can be too much together.
export const setAsideKb = (screen: Screen, list: Plugin[]) => list.reduce((sum, p) => sum + p.flash_kb + partsKb(screen, p), 0);
export async function installTray() {
  tray.sending = true;
  try {
    for (const group of trayGroups.value) {
      sending[group.screen.id] = group.plugins.map((p) => p.id);
      try {
        await change(group.screen, { add: group.plugins.map((plugin) => addition(group.screen, plugin)) });
        tray.items = tray.items.filter((item) => item.screen !== group.screen.id);
      } finally {
        delete sending[group.screen.id];
      }
    }
  } catch (error: any) {
    toast(error.message);
  } finally {
    tray.sending = false;
  }
  await reloadPlugins();
}
export async function removePlugin(screens: Screen[], plugin: Plugin) {
  if (!screens.length) return;
  for (const screen of screens) {
    try { await change(screen, { remove: [plugin.id] }); }
    catch (error: any) { toast(error.message); break; }
  }
  await reloadPlugins();
  toast(t("editor.plugins.removed", { name: text(plugin.name), screens: screens.map((s) => s.name).join(", ") }));
}
// A secret for every screen (an API key): kept by the add-on, never shown again.
export async function setSecret(plugin: Plugin, input: string, value: string) {
  await send(`plugins/${plugin.id}/secrets/${input}`, "PUT", { value });
  await reloadPlugins();
}
