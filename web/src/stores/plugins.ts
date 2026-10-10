// Plugins (docs/PLUGINS.md): what the add-on offers and what each screen runs, shared by the Plugins page (every plugin, and on
// which screens it is) and a screen's own Plugins tab (what this screen has, and what it can add). A plugin lives in a
// screen's firmware, so every change is per screen; the page only sets several screens at once. The tile types and bar
// items of the plugins the editor knows, and what only the add-on knows about a plugin on a screen, are kept here and
// handed to the model's rules (model/plugins.ts), which stay pure.
import { defineStore } from "pinia";
import { computed, effectScope, onScopeDispose, reactive, ref, watch } from "vue";
import { getJson, send } from "../api";
import { t } from "../i18n";
import { boardTitle } from "../model/boards";
import { attachLine, barItemView, barTypesOf, choiceKey, compareUrl, fit, isTest, nodeOf, ownYaml, pluginDefaults, pluginTileId, testPlugin,
  text, tileTypesOf, type AppFit, type Installed, type Plugin, type PluginTileOption, type Texts } from "../model/plugins";
import type { Screen } from "../types";
import { useBuildsStore } from "./builds";
import { useInventoryStore } from "./inventory";
import { lookups } from "./lookup";
import { useScreenStore } from "./screen";
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
// A screen's changes set aside together, one build (the tray): the plugins to add and the ones to take off.
export type TrayGroup = { screen: Screen; plugins: Plugin[]; removes: Plugin[] };
type Payload = {
  plugins: Plugin[]; installed: Record<string, Installed[]>; secrets: Record<string, Record<string, boolean>>;
  folders: { path: string; errors: Record<string, string> }; entities?: { id: string; name: string }[];
  features?: Record<string, string[]>; fit?: AppFit; likes?: { consented?: boolean };
};

export const usePluginsStore = defineStore("plugins", () => {
  const inv = useInventoryStore();
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

  // Plugins are on in the dev app and in `npm run dev` (the inventory store's pluginsEnabled, an editor feature the add-on
  // turns on): a person with a released add-on never sees the page or the tab.
  const pluginsEnabled = computed(() => inv.pluginsEnabled);

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
  const shownScreen = () => (scr.selected && !inv.inventory.screens.find((s) => s.id === scr.selected)?.virtual ? scr.selected : "");
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
    return [...inv.inventory.entities, ...entities.value].filter((e) => domains.includes(e.id.split(".")[0]) && !seen.has(e.id) && seen.add(e.id))
      .map((e) => ({ id: e.id, name: e.name || e.id }));
  }
  // An update of a plugin on this screen that asks for other rights than the person agreed to: the details ask again.
  function needsConsent(screen: Screen, plugin: Plugin) {
    const have = installedOn(screen, plugin.id);
    return Boolean(have && have.consent && plugin.permission_hash && have.consent !== plugin.permission_hash);
  }

  const realScreens = () => inv.inventory.screens.filter((screen) => !screen.virtual);
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
  // Whether a secret is kept by the add-on: for every screen, or for this screen alone (never its value).
  const secretSet = (screen: Screen, plugin: Plugin, input: { id: string; scope?: string }) => Boolean(input.scope === "screen"
    ? installedOn(screen, plugin.id)?.secrets?.[input.id] : secrets.value[plugin.id]?.[input.id]);
  // Whether everything a plugin asks for is filled in on these screens: the button waits until it is.
  const setupReady = (plugin: Plugin, screens: Screen[]) =>
    screens.every((screen) => (plugin.inputs || []).every((input) => valueOf(screen, plugin, input.id).trim() !== ""
      || (input.kind === "secret" && secretSet(screen, plugin, input))));
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
  // Build a test again: a folder as it is now, a branch from its newest commit (the add-on asks GitHub at once instead of
  // within the hour, refresh_links), so what a maker just pushed is what the screen gets.
  async function rebuildTest(screen: Screen, plugin: Plugin) {
    if (installedOn(screen, plugin.id)?.source === "branch") {
      try { await reloadPlugins(true); } catch (error: any) { ui.toast(error.message); return; }
    }
    await addPlugin([screen], pluginById(plugin.id) || plugin);
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

  // ---- Ready to install: changes set aside per screen, built together in one build per screen ----
  // Adding a plugin does not build at once: it goes into the tray (PluginTray), where a person can set aside more, on
  // this screen or another, and press Install once. Taking one off goes there too, with what goes along with it, so a
  // screen that gets one plugin and loses another builds once. Each screen then builds once with all of its changes, in
  // one request. What a plugin asks for (its inputs, trust in a community maker) is filled in its details.
  const tray = ref({ items: [] as { screen: string; plugin: string; remove?: boolean }[], open: true, sending: false });
  const trayItem = (screen: Screen, id: string) => tray.value.items.find((item) => item.screen === screen.id && item.plugin === id);
  const isSetAside = (screen: Screen, id: string) => Boolean(trayItem(screen, id) && !trayItem(screen, id)!.remove);
  const isTakingOff = (screen: Screen, id: string) => Boolean(trayItem(screen, id)?.remove);
  function takeOut(screen: Screen, id: string) {
    tray.value.items = tray.value.items.filter((item) => !(item.screen === screen.id && item.plugin === id));
  }
  function setAside(screen: Screen, plugin: Plugin) {
    if (isSetAside(screen, plugin.id)) return;
    takeOut(screen, plugin.id);   // set aside to go: changing one's mind keeps it
    if (!installedOn(screen, plugin.id) || hasUpdate(screen, plugin)) tray.value.items.push({ screen: screen.id, plugin: plugin.id });
    tray.value.open = true;
  }
  const toggleSetAside = (screen: Screen, plugin: Plugin) => (isSetAside(screen, plugin.id) ? takeOut(screen, plugin.id) : setAside(screen, plugin));
  /** Set aside taking a plugin off these screens, with `also` (the ids that go with it, as the person agreed in its
   * details): built with whatever else is set aside for each screen. */
  function setAsideRemoval(screens: Screen[], plugin: Plugin, also: string[] = []) {
    for (const screen of screens) {
      for (const id of [plugin.id, ...also.filter((other) => installedOn(screen, other))]) {
        takeOut(screen, id);
        tray.value.items.push({ screen: screen.id, plugin: id, remove: true });
      }
    }
    tray.value.open = true;
  }
  const pluginById = (id: string) => [...index.value, ...realScreens().flatMap(testsOn)].find((p) => p.id === id);
  // The tray by screen, in the order the screens were first chosen: one group, one build.
  const trayGroups = computed(() => {
    const groups: TrayGroup[] = [];
    for (const item of tray.value.items) {
      const screen = realScreens().find((s) => s.id === item.screen), plugin = pluginById(item.plugin);
      if (!screen || !plugin) continue;
      const group = groups.find((g) => g.screen.id === screen.id) || (groups.push({ screen, plugins: [], removes: [] }), groups[groups.length - 1]);
      (item.remove ? group.removes : group.plugins).push(plugin);
    }
    return groups;
  });
  // What a tray group comes to (the add-on's plan): what comes along with it, a feature to choose for, or why it cannot go.
  const trayPlan = (group: TrayGroup) => planOn(group.screen, group.plugins.map((p) => p.id), group.removes.map((p) => p.id));
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
            ...trayAlong(group).map((row) => addition(group.screen, row.plugin, true))],
            remove: group.removes.map((plugin) => plugin.id), providers: providers.value[group.screen.id] || {} });
          for (const plugin of group.plugins) forgetDrafts(group.screen, plugin);
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
      watch(() => Object.entries(inv.inventory.builds || {}).filter(([, build]) => build.by === "plugins")
        .map(([screen, build]) => `${screen}:${build.state}`).join(), (now, before) => { if (loaded.value && now !== before) reloadPlugins(); });
    });
    running = () => { running = null; scope.stop(); };
    return running;
  }
  onScopeDispose(() => running?.());

  // ---- A plugin's details (PluginDetail): taking it off, what an update brings, a screen's row ----
  /** What taking a plugin off these screens takes with it: the plugins that need it (they go with it), and the ones that
   * only came along with it or with those (they may go too; the person says). */
  function removalPlan(screens: Screen[], plugin: Plugin) {
    const needing = [...new Set(screens.flatMap((screen) => neededBy(screen, plugin.id).map((p) => p.id)))];
    const orphans = [...new Set(screens.flatMap((screen) => (installed.value[nodeOf(screen)] || []).filter((item) => item.auto
      && item.id !== plugin.id && neededBy(screen, item.id).every((p) => p.id === plugin.id || needing.includes(p.id)))
      .map((item) => item.id)))];
    return { with: needing, orphans };
  }
  /** The version an update's changelog starts after: the one this screen runs when it has the update; on the Plugins page
   * (no screen) the oldest of the screens with the update. None without an update. */
  function newsFrom(plugin: Plugin, screen: Screen | null) {
    if (screen) return statusOn(plugin, screen).kind === "update" ? installedOn(screen, plugin.id)?.version ?? null : null;
    return realScreens().filter((s) => hasUpdate(s, plugin)).map((s) => installedOn(s, plugin.id)?.version || "").sort()[0] || null;
  }
  /** GitHub's comparison of the commit this screen (else the first with the update) runs with the one on offer. */
  function compareFor(plugin: Plugin, screen: Screen | null) {
    const shown = screen || realScreens().find((s) => hasUpdate(s, plugin));
    return compareUrl(plugin.repo, shown ? installedOn(shown, plugin.id)?.ref : null, plugin.ref);
  }
  /** A screen's line on the Plugins page: building, a change the box asks for, a test's source, an update, the version it
   * runs, why it does not fit, that its YAML needs the plugins file, or the board it is. `wanted`: its box is ticked. */
  function screenLine(plugin: Plugin, screen: Screen, wanted: boolean) {
    const have = installedOn(screen, plugin.id);
    if (buildingOn(screen, plugin.id)) return t("editor.plugins.state.building");
    if (wanted && isSetAside(screen, plugin.id)) return t("editor.plugins.tray.in_tray");
    if (!wanted && isTakingOff(screen, plugin.id)) return t("editor.plugins.tray.off_set");
    if (wanted && !have) return t("editor.plugins.pending.add");
    if (!wanted && have) return t("editor.plugins.pending.remove");
    if (isTest(have)) return t(`editor.plugins.source.${have!.source}`);
    if (hasUpdate(screen, plugin)) return t("editor.plugins.screen_update", { from: have!.version, to: plugin.version });
    if (have) return t("editor.plugins.screen_version", { version: have.version });
    const result = fits(plugin, screen);
    if (!result.ok) return t(`editor.plugins.misfit_short.${result.reason}`);
    if (needsAttach(screen)) return t("editor.plugins.attach.row");
    return screen.shape?.catalog ? boardTitle(screen.shape.catalog) : "";
  }

  return {
    index, installed, loaded, secrets, files, choices, previews, entities, folders, features, likeConsent, appFit,
    values, parts, attached, focus, consented, plans, providers, tray, pluginsEnabled, trayGroups,
    // What the Plugins page, a screen's tab and the cards read as they draw (stores/lookup.ts); choicesFor, previewFor and
    // planOn answer at once and ask the add-on for what they do not have yet.
    ...lookups({
      pluginTileOf, barItemOf, fits, choicesFor, previewFor, tapActionsFor, barItemsFor, entitiesIn, needsConsent, realScreens,
      otherOrigin, hasUpdate, updatesOn, tilesOn, partsOn, valueOf, needsAttach, pluginsFile, setupChanged, setupReady, secretSet, partsKb,
      installedOn, buildingOn, testsOn, allTests, labelOf, stageOf, statusOn, statusOverall, planOn, comesAlong, neededBy, canLike,
      isSetAside, isTakingOff, trayPlan, trayAlong, trayReady, setAsideKb, removalPlan, newsFrom, compareFor, screenLine,
    }),
    reloadPlugins, loadPlugins, setParts, setValue, markAttached, copyAttach, chooseProvider, like, forgetDrafts,
    addPlugin, rebuildTest, updateAll, setAside, takeOut, toggleSetAside, installTray, setAsideRemoval, switchPlugin, setSecret, start,
  };
});
