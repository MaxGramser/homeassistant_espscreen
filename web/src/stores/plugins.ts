// Plugins (docs/PLUGINS.md): what the add-on offers and what each screen runs, shared by the Plugins page (every plugin, and on
// which screens it is) and a screen's own Plugins tab (what this screen has, and what it can add). A plugin lives in a
// screen's firmware, so every change is per screen; the page only sets several screens at once. The tile types and bar
// items of the plugins the editor knows, and what only the add-on knows about a plugin on a screen, are kept here and
// handed to the model's rules (model/plugins.ts), which stay pure.
import { defineStore } from "pinia";
import { computed, effectScope, onScopeDispose, reactive, ref, watch } from "vue";
import { getJson, send } from "../api";
import { t } from "../i18n";
import { attachLine, barItemView, barTypesOf, choiceKey, fit, isTest, nodeOf, ownYaml, pluginDefaults, pluginTileId, testPlugin,
  text, tileTypesOf, type AppFit, type Installed, type Plugin, type PluginTileOption, type Texts } from "../model/plugins";
import { state } from "../store";
import type { Screen } from "../types";
import { useBuildsStore } from "./builds";
import { useScreenStore } from "./screen";
import { lookups } from "./lookup";
import { useUiStore } from "./ui";

export type PlanStep = { id: string; source: string; auto: boolean; for: string[]; flash_kb: number; permission_hash: string };
export type Plan = {
  error: string | null; needed_by?: Record<string, string[]>; add?: PlanStep[]; remove?: string[];
  choose?: { feature: string; for: string; options: string[] }[]; orphans?: string[];
};
// A plugin tile's look in the mockup (the editor cannot run its C++): the manifest's `preview` filled in by the add-on
// from the tile's data, its first rows; asked again once a minute while a page shows it.
export type PreviewRow = { badge?: string; title?: string; value?: string; at?: number };
// ---- One line of state: for one screen (its tab), or over all screens (the page) ----
export type Status = { kind: "installed" | "update" | "building" | "test" | "misfit" | "failed" | ""; label: string };
// A screen's plugins set aside together, one build (the tray).
export type TrayGroup = { screen: Screen; plugins: Plugin[] };
type Payload = {
  plugins: Plugin[]; installed: Record<string, Installed[]>; secrets: Record<string, Record<string, boolean>>;
  folders: { path: string; errors: Record<string, string> }; entities?: { id: string; name: string }[];
  features?: Record<string, string[]>; fit?: AppFit; likes?: { consented?: boolean };
};

export const usePluginsStore = defineStore("plugins", () => {
  const ui = useUiStore();
  const builds = useBuildsStore();
  const scr = useScreenStore();

  // ---- What the add-on says (api/plugins) ----
  const index = ref<Plugin[]>([]);
  const installed = ref<Record<string, Installed[]>>({});
  const loaded = ref(false);
  // From the add-on: which secrets are set (never their values), the plugins file of a screen with its own YAML, and the
  // lists of choices it fetched. What a screen is building is the builds store's (buildOf), as every build is.
  const secrets = ref<Record<string, Record<string, boolean>>>({});
  const files = ref<Record<string, { file: string; content: string; line: string }>>({});
  const choices = ref<Record<string, { value: string; label: Texts }[]>>({});
  // What the add-on drew of a tile's data, by plugin tile and its options (previewFor), and when it was asked.
  const previews = ref<Record<string, { items: PreviewRow[]; at: number }>>({});
  // Entities of the domains the plugins name that the editor's own list lacks (a calendar), from the add-on.
  const entities = ref<{ id: string; name: string }[]>([]);
  const folders = ref<{ path: string; errors: Record<string, string> }>({ path: "", errors: {} });
  // The features each screen has (its board's and its plugins'), by inbox, and whether this app agreed once that a like
  // counts in a public number (plugin_likes.py).
  const features = ref<Record<string, string[]>>({});
  const likeConsent = ref(false);
  // What only the add-on knows about a plugin on a screen (its payload's `fit`): handed to fit() per screen.
  const appFit = ref<AppFit>({});
  // ---- What a person chose on this page ----
  // What was filled in when adding a plugin (inputs) and which optional parts are on, per screen node and plugin. A secret
  // is kept by the add-on and never comes back to the page; here it only says that one is set.
  const values = ref<Record<string, Record<string, Record<string, string>>>>({});
  const parts = ref<Record<string, Record<string, string[]>>>({});
  const attached = ref<Record<string, boolean>>({});
  // A plugin whose details the screen's Plugins tab opens next (Screen settings sends a person there).
  const focus = ref<string | null>(null);
  // Per plugin: the person agreed to the other rights an update asks for (needsConsent).
  const consented = ref<Record<string, boolean>>({});
  // What adding or removing comes to on a screen (the add-on's plan): what comes along, a feature to choose a plugin for,
  // what could go as well, or why it cannot be done. By screen and request (planKey).
  const plans = ref<Record<string, Plan>>({});
  // The plugin a person chose for a feature, per screen: {inbox: {feature: plugin}}.
  const providers = ref<Record<string, Record<string, string>>>({});
  // What is asked for now (a list of choices, a tile's look, a plan) and what this page is sending a screen now.
  const asking = new Set<string>(), drawing = new Set<string>(), planning = new Set<string>();
  const sending = reactive<Record<string, string[]>>({});

  // Plugins are on in the dev app (editor_features.plugins, docs/PLUGINS.md) and in `npm run dev`: a person with a
  // released add-on never sees the page or the tab. The add-on takes plugin tiles and items only then.
  const pluginsEnabled = computed(() => import.meta.env.DEV || state.inventory.editor_features?.plugins === true);

  // ---- The tile types and bar items of the plugins the editor knows, from its index ----
  const tileTypes = computed(() => tileTypesOf(index.value));
  const barTypes = computed(() => barTypesOf(index.value));
  /** A plugin's tile type by its entity (plugin:<plugin>.<tile>): what the layout model, the memory price and the tile card ask. */
  const pluginTileOf = (entity: string) => tileTypes.value.get(entity);
  /** A plugin's top bar item by its key (plugin:<plugin>.<item>), as the editor shows it. */
  const barItemOf = (key: string | undefined) => barItemView(key ? barTypes.value.get(key) : undefined);
  /** Whether a plugin fits a screen, with what only the add-on knows about it there. */
  const fits = (plugin: Plugin, screen: Screen | null) => fit(plugin, screen, (screen && appFit.value[screen.id]) || {});

  // The add-on's plugins (api/plugins). Asked again when a plugin build of some screen starts or ends (start).
  function reloadPlugins(refresh = false) {
    return getJson<Payload>(refresh ? "plugins?refresh=1" : "plugins").then((data) => {
      index.value = data.plugins;
      installed.value = data.installed;
      secrets.value = data.secrets || {};
      folders.value = data.folders || { path: "", errors: {} };
      entities.value = data.entities || [];
      features.value = data.features || {};
      likeConsent.value = Boolean(data.likes?.consented);
      appFit.value = data.fit || {};
      plans.value = {};
    }).catch(() => undefined);
  }
  function loadPlugins() {
    if (loaded.value) return;
    loaded.value = true;
    reloadPlugins();
  }

  // `_screen`: the screen shown, whose own plugin of this id answers (two screens may run two plugins of one id).
  const shownScreen = () => (scr.selected && !state.inventory.screens.find((s) => s.id === scr.selected)?.virtual ? scr.selected : "");
  // The choices of an option: its own, or those of one of the plugin's fetches (a stop's lines), asked of the add-on with
  // the tile's other options.
  function choicesFor(plugin: Plugin, option: PluginTileOption, given: Record<string, unknown>) {
    if (!option.options_from) return option.choices || [];
    const key = `${shownScreen()}|${choiceKey(plugin, option, given)}`;
    if (!(key in choices.value) && !asking.has(key)) {
      asking.add(key);
      const query = new URLSearchParams([...Object.entries(given).filter(([k, v]) => k !== option.id && v !== "" && v !== undefined)
        .map(([k, v]) => [k, String(v)]), ...(shownScreen() ? [["_screen", shownScreen()]] : [])]).toString();
      getJson<{ choices: { value: string; label: string }[] }>(`plugins/${plugin.id}/choices/${option.options_from}${query ? `?${query}` : ""}`)
        .then((data) => { choices.value[key] = data.choices.map((c) => ({ value: c.value, label: { en: c.label } })); })
        .catch(() => { choices.value[key] = []; })
        .finally(() => asking.delete(key));
    }
    return choices.value[key] || [];
  }
  function previewFor(entity: string, options: Record<string, unknown> | undefined, bound?: string): PreviewRow[] | null {
    const kind = pluginTileOf(entity);
    if (!kind?.tile.preview) return null;
    const given = { ...pluginDefaults(kind.tile), ...(options || {}), ...(bound ? { entity: bound } : {}) };
    const key = `${shownScreen()}|${entity}|${JSON.stringify(given)}`;
    const known = previews.value[key];
    if ((!known || Date.now() - known.at > 60000) && !drawing.has(key)) {
      drawing.add(key);
      const query = new URLSearchParams([...Object.entries(given).filter(([, v]) => v !== "" && v !== undefined).map(([k, v]) => [k, String(v)]),
        ...(shownScreen() ? [["_screen", shownScreen()]] : [])]).toString();
      getJson<{ items: PreviewRow[] }>(`plugins/${kind.plugin.id}/preview/${kind.tile.id}${query ? `?${query}` : ""}`)
        .then((data) => { previews.value[key] = { items: data.items || [], at: Date.now() }; })
        .catch(() => { previews.value[key] = { items: [], at: Date.now() }; })
        .finally(() => drawing.delete(key));
    }
    return known ? known.items : null;
  }

  // The tap actions a tile of this domain can take on this screen: those of the plugins it runs, as tap choices.
  function tapActionsFor(screen: Screen | undefined, domain: string): [string, string][] {
    if (!screen || screen.virtual) return [];
    return index.value.filter((plugin) => installedOn(screen, plugin.id)).flatMap((plugin) =>
      (plugin.tap_actions || []).filter((action) => action.domains.includes(domain))
        .map((action) => [`plugin:${plugin.id}.${action.id}`, text(action.label)] as [string, string]));
  }
  // The top bar items of the plugins this screen runs: [{ item, label, icon, example }].
  function barItemsFor(screen: Screen | undefined) {
    if (!screen || screen.virtual) return [];
    return index.value.filter((plugin) => installedOn(screen, plugin.id)).flatMap((plugin) =>
      (plugin.bar_items || []).map((bar) => ({ item: `plugin:${plugin.id}.${bar.id}`, label: text(bar.label), icon: bar.icon,
        example: bar.example ? text(bar.example) : "", plugin: text(plugin.name) })));
  }
  // Every entity of these domains: the editor's own and those the add-on sent for plugins, each once.
  function entitiesIn(domains: string[] = []) {
    const seen = new Set<string>();
    return [...state.inventory.entities, ...entities.value].filter((e) => domains.includes(e.id.split(".")[0]) && !seen.has(e.id) && seen.add(e.id))
      .map((e) => ({ id: e.id, name: e.name || e.id }));
  }
  // An update of a plugin on this screen that asks for other rights than the person agreed to: the details ask again.
  function needsConsent(screen: Screen, plugin: Plugin) {
    const have = installedOn(screen, plugin.id);
    return Boolean(have && have.consent && plugin.permission_hash && have.consent !== plugin.permission_hash);
  }

  const realScreens = () => state.inventory.screens.filter((screen) => !screen.virtual);
  // Whether this screen runs another plugin of the same id than the one on offer (a fork, a folder being made): no update
  // moves it there by itself; its details offer to switch.
  function otherOrigin(screen: Screen, plugin: Plugin) {
    const have = installedOn(screen, plugin.id);
    return Boolean(have?.origin && plugin.origin && have.origin !== plugin.origin);
  }
  // Whether this screen has an older release of the plugin than the one on offer (a branch: an older commit), from the same
  // origin, and is not building it now.
  function hasUpdate(screen: Screen, plugin: Plugin) {
    const have = installedOn(screen, plugin.id);
    if (!have || otherOrigin(screen, plugin) || buildingOn(screen, plugin.id) || have.source === "folder") return false;
    if (have.source === "branch") return Boolean(plugin.ref && have.ref && /^[0-9a-f]{40}$/.test(have.ref) && plugin.ref !== have.ref);
    return have.version !== plugin.version;
  }
  // Every plugin of this screen with an update: "Update all on this screen" takes them in one build.
  const updatesOn = (screen: Screen) => index.value.filter((plugin) => hasUpdate(screen, plugin));
  // The tile types a screen can place: those of the plugins it runs (the library's Plugins group). A preview screen has none.
  function tilesOn(screen: Screen | undefined) {
    if (!screen || screen.virtual) return [];
    return index.value.filter((plugin) => installedOn(screen, plugin.id)).flatMap((plugin) =>
      (plugin.tiles || []).map((tile) => ({ id: pluginTileId(plugin.id, tile.id), name: text(tile.name), tile: true,
        plugin: [text(plugin.name), stageOf(plugin) && t(`editor.plugins.stage.${stageOf(plugin)}`)].filter(Boolean).join(" · ") })));
  }
  // What is chosen on this page, else what the add-on keeps for this screen (an update sends it again, so nothing filled in
  // when the plugin was added is lost), else the manifest's defaults.
  const partsOn = (screen: Screen, plugin: Plugin) => parts.value[screen.node || screen.id]?.[plugin.id]
    ?? installedOn(screen, plugin.id)?.parts ?? (plugin.parts || []).filter((part) => part.default).map((part) => part.id);
  function setParts(screen: Screen, plugin: Plugin, ids: string[]) {
    ((parts.value[screen.node || screen.id] ||= {})[plugin.id] = ids);
  }
  const valueOf = (screen: Screen, plugin: Plugin, id: string) => values.value[screen.node || screen.id]?.[plugin.id]?.[id]
    ?? installedOn(screen, plugin.id)?.values?.[id] ?? "";
  function setValue(screen: Screen, plugin: Plugin, id: string, value: string) {
    const node = screen.node || screen.id;
    ((values.value[node] ||= {})[plugin.id] ||= {})[id] = value;
  }
  // An own-YAML screen counts as attached once the person says the line is in its YAML (the app cannot build it, so it
  // cannot check).
  const needsAttach = (screen: Screen) => ownYaml(screen) && !attached.value[screen.node || screen.id];
  function markAttached(screen: Screen) { attached.value[screen.node || screen.id] = true; }
  const copyAttach = (screen: Screen) => ui.copyText(attachLine(screen), undefined, "yaml");
  // The plugins file of a screen with its own YAML, as the add-on wrote it ("" until it has): the add-on pins each plugin to
  // the commit of its release, so the page never writes one of its own.
  const pluginsFile = (screen: Screen) => files.value[screen.id]?.content || "";
  // Whether what is filled in for a plugin this screen runs differs from what its build has: then "Save and build" applies
  // it. A secret counts once something new is typed; the add-on never sends one back.
  function setupChanged(screen: Screen, plugin: Plugin) {
    const have = installedOn(screen, plugin.id);
    if (!have) return false;
    const node = screen.node || screen.id;
    const drafted = values.value[node]?.[plugin.id] || {};
    const changed = (plugin.inputs || []).some((input) => input.id in drafted && (input.kind === "secret"
      ? drafted[input.id].trim() !== "" : drafted[input.id].trim() !== (have.values?.[input.id] ?? "")));
    const chosen = parts.value[node]?.[plugin.id];
    return changed || (chosen !== undefined && [...chosen].sort().join() !== [...(have.parts || [])].sort().join());
  }
  // Open a plugin's details on the screen's Plugins tab: from Screen settings, where its settings used to be.
  function openPluginOn(id: string) { focus.value = id; state.tab = "plugins"; }
  // Whether everything a plugin asks for is filled in on these screens: the button waits until it is.
  const setupReady = (plugin: Plugin, screens: Screen[]) =>
    screens.every((screen) => (plugin.inputs || []).every((input) => valueOf(screen, plugin, input.id).trim() !== ""
      || (input.kind === "secret" && secrets.value[plugin.id]?.[input.id])));
  // The room the chosen optional parts add.
  const partsKb = (screen: Screen, plugin: Plugin) =>
    partsOn(screen, plugin).reduce((sum, id) => sum + (plugin.parts?.find((part) => part.id === id)?.flash_kb || 0), 0);
  // The add-on keeps a screen's plugins by its inbox, the id every screen route takes.
  const installedOn = (screen: Screen, id: string) => installed.value[nodeOf(screen)]?.find((item) => item.id === id);
  // Whether this screen's build (the builds store's, live from the add-on) brings this plugin, or the page is asking for it now.
  const buildingOn = (screen: Screen, id: string) => {
    const build = builds.buildOf(screen);
    return Boolean((build?.by === "plugins" && build.plugins?.includes(id)) || sending[screen.id]?.includes(id));
  };
  // A plugin on a screen the add-on has no manifest of any more (a test folder that went): known only by its record.
  const testsOn = (screen: Screen) => (installed.value[nodeOf(screen)] || [])
    .filter((item) => item.source !== "index" && !index.value.some((p) => p.id === item.id)).map(testPlugin);
  const allTests = () => {
    const seen = new Map<string, Plugin>();
    for (const screen of realScreens()) for (const plugin of testsOn(screen)) seen.set(plugin.id, plugin);
    return [...seen.values()];
  };
  // Tessera's own, someone else's from the index, or a test the screen runs from a branch, a folder or a link.
  const labelOf = (plugin: Plugin) => plugin.label
    || (plugin.tessera ? "tessera" : index.value.some((p) => p.id === plugin.id) ? "community" : "test");
  // The badge of its stage: beta or example, none for a stable plugin or one under test (its label says that already).
  const stageOf = (plugin: Plugin): "beta" | "example" | "" =>
    labelOf(plugin) !== "test" && (plugin.stage === "beta" || plugin.stage === "example") ? plugin.stage : "";

  function statusOn(plugin: Plugin, screen: Screen): Status {
    // A screen in the add-on's build queue waits its turn; one at a time builds (docs/PLUGINS.md).
    if (buildingOn(screen, plugin.id))
      return { kind: "building", label: t(builds.buildOf(screen)?.state === "queued" ? "editor.plugins.state.queued" : "editor.plugins.state.building") };
    const have = installedOn(screen, plugin.id);
    if (have?.state === "failed") return { kind: "failed", label: t("editor.plugins.state.failed") };
    if (hasUpdate(screen, plugin)) return { kind: "update", label: t("editor.plugins.state.update", { version: plugin.version }) };
    if (isTest(have)) return { kind: "test", label: t(`editor.plugins.source.${have!.source}`) };
    if (have) return { kind: "installed", label: t("editor.plugins.state.installed") };
    const result = fits(plugin, screen);
    return result.ok ? { kind: "", label: "" } : { kind: "misfit", label: t(`editor.plugins.misfit_short.${result.reason}`) };
  }
  function statusOverall(plugin: Plugin): Status {
    const screens = realScreens();
    if (screens.some((screen) => buildingOn(screen, plugin.id))) return { kind: "building", label: t("editor.plugins.state.building") };
    const on = screens.filter((screen) => installedOn(screen, plugin.id));
    // A test names its screen when it is on one; on more it counts them, so the line fits the card beside its chip.
    if (labelOf(plugin) === "test") return { kind: "test", label: on.length === 1 ? t("editor.plugins.state.test_on", { name: on[0].name })
      : on.length ? t("editor.plugins.state.on_screens", { n: on.length }, on.length) : "" };
    const updates = on.filter((screen) => hasUpdate(screen, plugin)).length;
    if (updates) return { kind: "update", label: t("editor.plugins.state.updates", { n: updates }, updates) };
    if (on.length) return { kind: "installed", label: t("editor.plugins.state.on_screens", { n: on.length }, on.length) };
    if (screens.length && !screens.some((screen) => fits(plugin, screen).ok)) return { kind: "misfit", label: t("editor.plugins.state.fits_none") };
    return { kind: "", label: "" };
  }

  // ---- Changes: add, update or remove on one screen ----
  // What goes to the add-on for one screen: the plugin, its parts, what was filled in, and the secrets apart.
  function addition(screen: Screen, plugin: Plugin, auto = false) {
    const filled: Record<string, string> = {}, secret: Record<string, string> = {};
    for (const input of plugin.inputs || []) {
      const value = valueOf(screen, plugin, input.id).trim();
      if (value) (input.kind === "secret" ? secret : filled)[input.id] = value;
    }
    return { id: plugin.id, source: plugin.source || "index", parts: partsOn(screen, plugin), values: filled, secrets: secret,
      ...(consented.value[plugin.id] ? { consent: true } : {}), ...(auto ? { auto: true } : {}) };
  }
  // ---- What comes along: the add-on's plan of a change on one screen (plugins.py _plan) ----
  const planKey = (screen: Screen, add: string[], remove: string[] = []) =>
    `${screen.id}|${[...add].sort().join(",")}|${[...remove].sort().join(",")}|${JSON.stringify(providers.value[screen.id] || {})}`;
  // The plan of adding `add` and removing `remove` on this screen, asked once per request and kept until the plugins load
  // again; null while it is asked.
  function planOn(screen: Screen, add: string[], remove: string[] = []): Plan | null {
    if (!add.length && !remove.length) return { error: null, add: [], remove: [], choose: [], orphans: [] };
    const key = planKey(screen, add, remove);
    if (!(key in plans.value) && !planning.has(key)) {
      planning.add(key);
      send<Plan>(`screens/${encodeURIComponent(screen.id)}/plugins/plan`, "POST", {
        add: add.map((id) => ({ id, source: pluginById(id)?.source || "index" })), remove, providers: providers.value[screen.id] || {},
      }).then((plan) => { plans.value[key] = plan || { error: null }; })
        .catch((error: any) => { plans.value[key] = { error: error?.message || "" }; })
        .finally(() => planning.delete(key));
    }
    return plans.value[key] ?? null;
  }
  // What comes along with these plugins on this screen: the plugins the plan adds that were not asked for.
  const comesAlong = (plan: Plan | null, asked: string[]) =>
    (plan?.add || []).filter((step) => !asked.includes(step.id)).map((step) => ({ step, plugin: pluginById(step.id) }))
      .filter((row): row is { step: PlanStep; plugin: Plugin } => Boolean(row.plugin));
  function chooseProvider(screen: Screen, feature: string, plugin: string) {
    (providers.value[screen.id] ||= {})[feature] = plugin;
  }
  // The plugins on this screen that need this one, and the one it came along with.
  const neededBy = (screen: Screen, id: string) => (installed.value[nodeOf(screen)] || [])
    .map((item) => pluginById(item.id)).filter((p): p is Plugin => Boolean(p && p.id !== id && (p.requires.plugins?.includes(id)
      || (p.requires.features || []).some((f) => pluginById(id)?.provides?.includes(f)))));

  // ---- Likes (plugin_likes.py): a heart for a plugin that runs on one of this app's screens ----
  const canLike = (plugin: Plugin) => plugin.source === "index"
    && realScreens().some((screen) => installedOn(screen, plugin.id) && !otherOrigin(screen, plugin));
  async function like(plugin: Plugin, on: boolean, consent = false) {
    const result = await send<{ liked: boolean; likes: number }>(`plugins/${plugin.id}/like`, "PUT", { like: on, consent });
    const listed = index.value.find((p) => p.id === plugin.id);
    if (listed && result) { listed.liked = result.liked; listed.likes = result.likes; }
    if (consent) likeConsent.value = true;
  }
  async function change(screen: Screen, body: object) {
    const result = await send<{ own_yaml?: boolean; file?: string; content?: string; line?: string }>(
      `screens/${encodeURIComponent(screen.id)}/plugins`, "POST", body);
    if (result?.own_yaml) files.value[screen.id] = { file: result.file || "", content: result.content || "", line: result.line || "" };
  }
  // What was filled in for a plugin on a screen, once the add-on has it: the build's own values show from then on, and a
  // secret, which never comes back, no longer counts as a change.
  function forgetDrafts(screen: Screen, plugin: Plugin) {
    const node = screen.node || screen.id;
    delete values.value[node]?.[plugin.id];
    delete parts.value[node]?.[plugin.id];
  }
  async function addPlugin(screens: Screen[], plugin: Plugin) {
    if (!screens.length) return;
    // One build at a time: the add-on builds the screens one after the other as each build ends.
    for (const screen of screens) {
      try {
        sending[screen.id] = [plugin.id];
        await change(screen, { add: [addition(screen, plugin)] });
        forgetDrafts(screen, plugin);
      } catch (error: any) {
        ui.toast(error.message);
        break;
      } finally {
        delete sending[screen.id];
      }
    }
    await reloadPlugins();
  }
  // Every update of one screen in one build (the add-on takes several plugins in one request and builds the screen once).
  // An update that asks for other rights goes only with the person's yes (consented), as it does one by one.
  async function updateAll(screen: Screen, list: Plugin[]) {
    if (!list.length) return;
    sending[screen.id] = list.map((plugin) => plugin.id);
    try {
      await change(screen, { add: list.map((plugin) => addition(screen, plugin)) });
    } catch (error: any) {
      ui.toast(error.message);
    } finally {
      delete sending[screen.id];
    }
    await reloadPlugins();
  }

  // ---- Ready to install: plugins set aside per screen, installed together in one build per screen ----
  // Adding a plugin no longer builds at once: it goes into the tray (PluginTray), where a person can set aside more, on
  // this screen or another, and press Install once. Each screen then builds once with all of its plugins, the request
  // updateAll already makes. What a plugin asks for (its inputs, trust in a community maker) is filled in its details.
  const tray = ref({ items: [] as { screen: string; plugin: string }[], open: true, sending: false });
  const isSetAside = (screen: Screen, id: string) => tray.value.items.some((item) => item.screen === screen.id && item.plugin === id);
  function setAside(screen: Screen, plugin: Plugin) {
    if (!isSetAside(screen, plugin.id)) tray.value.items.push({ screen: screen.id, plugin: plugin.id });
    tray.value.open = true;
  }
  function takeOut(screen: Screen, id: string) {
    const at = tray.value.items.findIndex((item) => item.screen === screen.id && item.plugin === id);
    if (at >= 0) tray.value.items.splice(at, 1);
  }
  const toggleSetAside = (screen: Screen, plugin: Plugin) => (isSetAside(screen, plugin.id) ? takeOut(screen, plugin.id) : setAside(screen, plugin));
  const pluginById = (id: string) => [...index.value, ...realScreens().flatMap(testsOn)].find((p) => p.id === id);
  // The tray by screen, in the order the screens were first chosen: one group, one build.
  const trayGroups = computed(() => {
    const groups: TrayGroup[] = [];
    for (const item of tray.value.items) {
      const screen = realScreens().find((s) => s.id === item.screen), plugin = pluginById(item.plugin);
      if (!screen || !plugin) continue;
      const group = groups.find((g) => g.screen.id === screen.id) || (groups.push({ screen, plugins: [] }), groups[groups.length - 1]);
      group.plugins.push(plugin);
    }
    return groups;
  });
  // What a tray group comes to (the add-on's plan): what comes along with it, a feature to choose for, or why it cannot go.
  const trayPlan = (group: TrayGroup) => planOn(group.screen, group.plugins.map((p) => p.id));
  const trayAlong = (group: TrayGroup) => comesAlong(trayPlan(group), group.plugins.map((p) => p.id));
  // Whether a group can be built: its plan is known, says no, and asks no choice.
  const trayReady = (group: TrayGroup) => {
    const plan = trayPlan(group);
    return Boolean(plan && !plan.error && !plan.choose?.length);
  };
  // The room what is set aside on a 4 MB screen takes together, with what comes along: two plugins that each fit can be
  // too much together.
  const setAsideKb = (screen: Screen, list: Plugin[]) => list.reduce((sum, p) => sum + p.flash_kb + partsKb(screen, p), 0)
    + comesAlong(planOn(screen, list.map((p) => p.id)), list.map((p) => p.id)).reduce((sum, row) => sum + row.step.flash_kb, 0);
  async function installTray() {
    tray.value.sending = true;
    try {
      for (const group of trayGroups.value) {
        sending[group.screen.id] = [...group.plugins.map((p) => p.id), ...trayAlong(group).map((row) => row.plugin.id)];
        try {
          // What comes along goes in the same request, with what was filled in for it, so the screen builds once.
          await change(group.screen, { add: [...group.plugins.map((plugin) => addition(group.screen, plugin)),
            ...trayAlong(group).map((row) => addition(group.screen, row.plugin, true))], providers: providers.value[group.screen.id] || {} });
          tray.value.items = tray.value.items.filter((item) => item.screen !== group.screen.id);
        } finally {
          delete sending[group.screen.id];
        }
      }
    } catch (error: any) {
      ui.toast(error.message);
    } finally {
      tray.value.sending = false;
    }
    await reloadPlugins();
  }
  // Take plugins off screens. `also`: the ids that go with it on each screen (a plugin that needs it, one that only came
  // along with it), as the person agreed in its details.
  async function removePlugin(screens: Screen[], plugin: Plugin, also: string[] = []) {
    if (!screens.length) return;
    for (const screen of screens) {
      const here = [plugin.id, ...also.filter((id) => installedOn(screen, id))];
      try { await change(screen, { remove: here }); }
      catch (error: any) { ui.toast(error.message); return; }
    }
    await reloadPlugins();
    ui.toast(t("editor.plugins.removed", { name: [plugin, ...also.map(pluginById).filter(Boolean) as Plugin[]].map((p) => text(p.name)).join(", "),
      screens: screens.map((s) => s.name).join(", ") }));
  }
  // Switch a screen to this plugin from another plugin of the same id it runs (a fork, a folder being made): the person
  // asked in its details, so the add-on replaces it (`switch`).
  async function switchPlugin(screen: Screen, plugin: Plugin) {
    sending[screen.id] = [plugin.id];
    try { await change(screen, { add: [{ ...addition(screen, plugin), switch: true }] }); }
    catch (error: any) { ui.toast(error.message); }
    finally { delete sending[screen.id]; }
    await reloadPlugins();
  }
  // A secret for every screen (an API key): kept by the add-on, never shown again.
  async function setSecret(plugin: Plugin, input: string, value: string) {
    await send(`plugins/${plugin.id}/secrets/${input}`, "PUT", { value });
    await reloadPlugins();
  }

  // ---- Started once the page is on the screen (boot.ts); the returned function stops it ----
  let running: (() => void) | null = null;
  function start() {
    if (running) return running;
    const scope = effectScope(true);
    scope.run(() => {
      // The plugins load as soon as they are on, not when the Plugins page opens: a page with a plugin tile needs its type.
      watch(pluginsEnabled, (on) => { if (on) loadPlugins(); }, { immediate: true });
      // A plugin build of some screen that starts or ends (the builds store's, live from the add-on): a record's state and
      // version follow the build without a poll of its own.
      watch(() => Object.entries(state.inventory.builds || {}).filter(([, build]) => build.by === "plugins")
        .map(([screen, build]) => `${screen}:${build.state}`).join(), (now, before) => { if (loaded.value && now !== before) reloadPlugins(); });
    });
    running = () => { running = null; scope.stop(); };
    return running;
  }
  onScopeDispose(() => running?.());

  return {
    index, installed, loaded, secrets, files, choices, previews, entities, folders, features, likeConsent, appFit,
    values, parts, attached, focus, consented, plans, providers, tray, pluginsEnabled, trayGroups,
    // What the Plugins page, a screen's tab and the cards read as they draw (stores/lookup.ts); choicesFor, previewFor and
    // planOn answer at once and ask the add-on for what they do not have yet.
    ...lookups({
      pluginTileOf, barItemOf, fits, choicesFor, previewFor, tapActionsFor, barItemsFor, entitiesIn, needsConsent, realScreens,
      otherOrigin, hasUpdate, updatesOn, tilesOn, partsOn, valueOf, needsAttach, pluginsFile, setupChanged, setupReady, partsKb,
      installedOn, buildingOn, testsOn, allTests, labelOf, stageOf, statusOn, statusOverall, planOn, comesAlong, neededBy, canLike,
      isSetAside, trayPlan, trayAlong, trayReady, setAsideKb,
    }),
    reloadPlugins, loadPlugins, setParts, setValue, markAttached, copyAttach, openPluginOn, chooseProvider, like, forgetDrafts,
    addPlugin, updateAll, setAside, takeOut, toggleSetAside, installTray, removePlugin, switchPlugin, setSecret, start,
  };
});
