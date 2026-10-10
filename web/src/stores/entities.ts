// What Home Assistant says of its entities, as the editor asks for it: what each can do (capabilities, its actions, the
// values its second line may say), its state now (the mockup's live values, app 0.2.73), the top bar's entity texts as the
// screen will show them, a sensor's history, and an entity's name and icon. What to ask for comes in from whoever asks
// (the open layout, the library, the overview); the store keeps the answers and what it already asked.
import { defineStore } from "pinia";
import { computed, ref, toRaw } from "vue";
import { getJson, send } from "../api";
import type { HistoryPreview } from "../model/history-preview";
import { homeView, type HomeView } from "../model/overview";
import { text as pluginText } from "../model/plugins";
import { itemKey } from "../model/topbar";
import { state } from "../store";
import type { Capability, EntityAction, Tile } from "../types";
import { lookups } from "./lookup";
import { usePluginsStore } from "./plugins";

// What Home Assistant reports for an entity right now: the state, its word and the attributes a card shows.
export type Live = { state: string; word?: string | null; a: Record<string, any> };
/** Whether an answer is still wanted when it comes (the screen it was asked for is still open); always by default. */
export type Still = () => boolean;
const always: Still = () => true;
// A query of entity ids, as the add-on reads several at once.
const query = (ids: string[]) => ids.map((id) => `entity=${encodeURIComponent(id)}`).join("&");
const own = (ids: string[]) => [...new Set(ids)].filter((id) => !id.startsWith("screen."));

export const useEntitiesStore = defineStore("entities", () => {
  const plugins = usePluginsStore();

  // ---- Names and icons ----
  // A plugin's tile is named and drawn as its manifest says (stores/plugins.ts).
  function entityName(id: string) {
    const plugin = plugins.pluginTileOf(id);
    if (plugin) return pluginText(plugin.tile.name);
    return state.inventory.entities.find((e) => e.id === id)?.name || state.inventory.builtin?.find((e) => e.id === id)?.name ||
      state.inventory.trackers?.find((e) => e.id === id)?.name || id;
  }
  // The icons the add-on offers, by name: worked out again only when it sends others (its list as a whole, not each icon
  // followed on its own).
  const iconsByName = computed<Record<string, { name: string; cp: string; label: string }>>(() =>
    Object.fromEntries((toRaw(state.inventory.icons)?.groups || []).flatMap((g) => g.icons.map((i) => [i.name, i]))));
  const iconNamed = (name: string | undefined) => (name ? iconsByName.value[name] : undefined);
  // What the firmware draws without a choice: Home Assistant's own icon, else the domain icon.
  function automaticIcon(id: string): string {
    const plugin = plugins.pluginTileOf(id);
    if (plugin) return plugin.tile.icon || plugin.plugin.icon;
    const icons = state.inventory.icons;
    if (!icons) return "F0335";
    const entity = state.inventory.entities.find((e) => e.id === id), domain = id.split(".")[0];
    if (icons.builtin?.[id]) return icons.builtin[id];
    if (entity?.icon) return entity.icon;
    if (domain === "weather") return icons.weather[entity?.state || ""] || icons.weather.partlycloudy;
    if (domain === "sun") return icons.sun[entity?.state || ""] || icons.sun.below_horizon;
    return icons.defaults[domain] || icons.fallback;
  }
  const tileIconCp = (tile: Tile) => iconNamed(tile.options?.icon)?.cp || automaticIcon(tile.entity);

  // ---- Capabilities and actions from Home Assistant ----
  // Each asked once while the page is open; one that could not be asked is asked again next time.
  const capabilities = ref<Record<string, Capability | null>>({});
  const entityActions = ref<Record<string, EntityAction[] | null | undefined>>({});
  // Per entity, the values its second line may say: Home Assistant's own named attributes (app 0.2.105).
  const subtitleValues = ref<Record<string, { key: string; name: string }[] | undefined>>({});
  const askedCapabilities = new Set<string>(), askedSubtitles = new Set<string>(), askedActions = new Set<string>();
  async function loadCapabilities(entities: string[]) {
    const wanted = [...new Set(entities)].filter((id) => !askedCapabilities.has(id) && !id.startsWith("screen."));
    if (!wanted.length) return;
    wanted.forEach((id) => askedCapabilities.add(id));
    try {
      for (let i = 0; i < wanted.length; i += 40)
        Object.assign(capabilities.value, (await getJson(`capabilities?${query(wanted.slice(i, i + 40))}`)).capabilities || {});
    } catch {
      wanted.forEach((id) => askedCapabilities.delete(id));
    }
  }
  // The values one entity's second line may say (app 0.2.105). The list is Home Assistant's own - the attributes its
  // frontend translations name - so nothing here is a list we keep, and an entity it names none of answers empty.
  async function loadSubtitleValues(entity: string) {
    if (askedSubtitles.has(entity)) return;
    askedSubtitles.add(entity);
    try {
      subtitleValues.value[entity] = (await getJson(`entity-subtitle?entity=${encodeURIComponent(entity)}`)).values ?? [];
    } catch {
      askedSubtitles.delete(entity);
    }
  }
  async function loadEntityActions(entity: string) {
    if (askedActions.has(entity)) return;
    askedActions.add(entity);
    try {
      entityActions.value[entity] = (await getJson(`entity-actions?entity=${encodeURIComponent(entity)}`)).actions;
    } catch {
      askedActions.delete(entity);
    }
  }

  // ---- Live values on the mockup (app 0.2.73): what the screen shows right now ----
  const liveStates = ref<Record<string, Live>>({});
  let statesFlight = false;
  /** The states of the open layout's entities, one request at a time; an answer no longer `still` wanted is dropped. */
  async function loadStates(ids: string[], still: Still = always) {
    const entities = own(ids);
    if (!entities.length || statesFlight) return;
    statesFlight = true;
    try {
      for (let i = 0; i < entities.length; i += 60) {
        const values = await getJson(`states?${query(entities.slice(i, i + 60))}`);
        if (!still()) return;
        Object.assign(liveStates.value, values.states || {});
      }
    } catch {
      // The next tick tries again; the mockup keeps the last values.
    } finally {
      statesFlight = false;
    }
  }
  /** The states of what the library shows, the first 80 of them. */
  async function loadLibraryStates(ids: string[], still: Still = always) {
    const entities = own(ids).slice(0, 80);
    try {
      for (let i = 0; i < entities.length; i += 60) {
        const values = await getJson(`states?${query(entities.slice(i, i + 60))}`);
        if (!still()) return;
        Object.assign(liveStates.value, values.states || {});
      }
    } catch { /* Inventory state remains visible until the next refresh. */ }
  }
  // The live value, else what the inventory knew when it was fetched, else nothing.
  function liveOf(entity: string): Live | null {
    const live = liveStates.value[entity];
    if (live) return live;
    const known = state.inventory.entities.find((e) => e.id === entity);
    return known?.state ? { state: known.state, word: null, a: {} } : null;
  }

  // ---- The top bar's entity items as the screen will show them (header-preview), by item (model/topbar.ts itemKey) ----
  const topbarPreviews = ref<Record<string, any>>({});

  // ---- The overview (app 0.4.0): every screen of the home with its home page, as its mockup draws it (model/overview.ts) ----
  // What the overview draws with: the states of every home page's tiles and the values in their top bars.
  let overviewFlight = false;
  async function loadOverview() {
    if (overviewFlight) return;
    overviewFlight = true;
    try {
      const views = state.inventory.screens.map(homeView).filter((view): view is HomeView => Boolean(view));
      const entities = own(views.flatMap((view) => [...view.tiles.map(({ tile }) => tile.entity), ...view.keys.map((tile) => tile.entity)]));
      for (let i = 0; i < entities.length; i += 60) {
        const values = await getJson(`states?${query(entities.slice(i, i + 60))}`);
        Object.assign(liveStates.value, values.states || {});
      }
      // One bar at a time: each home page's bar is one the add-on already accepted, which a mix of several bars is not
      // (the same entity twice with another content is refused as a double).
      const asked = new Set<string>();
      for (const view of views) {
        const batch = view.items.filter((item) => item.type === "entity" && !asked.has(itemKey(item)));
        if (!batch.length) continue;
        batch.forEach((item) => asked.add(itemKey(item)));
        const data = await send("header-preview", "POST", { header: { items: batch.map(({ id: _id, ...item }) => item) } });
        batch.forEach((item, i) => { topbarPreviews.value[itemKey(item)] = data.items[i]; });
      }
    } catch {
      // The overview keeps what it has; the next visit asks again.
    } finally {
      overviewFlight = false;
    }
  }

  // ---- A sensor's history (the graph card, the map, a focused page and the navigation preview) ----
  // Asked once a minute at most per entity and span, 64 of them kept; a request that failed is asked again next time.
  const histories = new Map<string, { time: number; result: Promise<HistoryPreview | null> }>();
  function loadHistory(entity: string, hours: number) {
    const key = `${entity}:${hours}`, previous = histories.get(key);
    if (previous && Date.now() - previous.time < 60000) return previous.result;
    const result = getJson<{ history: HistoryPreview | null }>(`history-preview?entity=${encodeURIComponent(entity)}&hours=${hours}`).then((data) => data.history);
    histories.set(key, { time: Date.now(), result });
    while (histories.size > 64) histories.delete(histories.keys().next().value!);
    result.catch(() => { if (histories.get(key)?.result === result) histories.delete(key); });
    return result;
  }

  return {
    ...lookups({ entityName, iconNamed, automaticIcon, tileIconCp, liveOf }),
    capabilities, entityActions, subtitleValues, loadCapabilities, loadSubtitleValues, loadEntityActions,
    liveStates, loadStates, loadLibraryStates, topbarPreviews, loadOverview, loadHistory,
  };
});
