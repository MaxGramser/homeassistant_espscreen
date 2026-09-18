// One reactive state for the whole editor. The Python API (server.py) is unchanged: this file is the
// former app.js state and its calls, with the DOM work moved into the components.
import { computed, reactive, toRaw } from "vue";
import { api, getJson, send, setCsrf } from "./api";
import {
  arrange, cellsOf, entriesOf, firstFree, fits, isFull, isWide, MAX_PAGES, nearestFree, newTile, normalize, occupied, pageCount, pageOf,
  pageTarget, rowStart, sizeOf, SLOTS_PER_PAGE, strandedPages, supportsFirmware as supportsVersion, tileLimit as limitFor,
} from "./model/layout";
import { agoText, BAR_METRICS, clockText, dateText, itemKey, type ItemView, whenBarFontsLoad } from "./model/topbar";
import { versionAtLeast } from "./model/layout";
import type { Capability, ChangelogSection, EntityAction, HeaderItem, Inventory, Layout, Screen, Tile } from "./types";

export type Inspector =
  | { kind: "tile" }
  | { kind: "bar"; index: number }
  | { kind: "bar-add" }
  | { kind: "inspect"; entity?: string };
export type DragState = { active: boolean; moving: Tile | null; preview: { tile: Tile; slot: number }[] | null };
// What Home Assistant reports for an entity right now: the state, its word and the attributes a card shows.
export type Live = { state: string; word?: string | null; a: Record<string, any> };

export const state = reactive({
  inventory: { screens: [], entities: [] } as Inventory,
  connected: false,
  reachable: true,
  selected: null as string | null,
  layout: null as Layout | null,
  dirty: false,
  busy: false,
  saved: 0,
  tab: "layout" as "layout" | "settings",
  // The tile itself, not its entity: several tiles can go to the same page (firmware 0.2.65).
  selectedTile: null as Tile | null,
  inspector: null as Inspector | null,
  iconPickerOpen: false,
  actionPickerOpen: false,
  actionSearch: "",
  insertAt: -1,
  filter: "",
  search: "",
  capabilities: {} as Record<string, Capability | null>,
  entityActions: {} as Record<string, EntityAction[] | null | undefined>,
  topbarPreviews: {} as Record<string, any>,
  topbarAdded: null as null | { key: string; time: number },
  topbarOverflow: [] as number[],
  settingEdits: {} as Record<string, { value: any; at: number }>,
  settingPending: false,
  updating: [] as string[],
  toast: null as null | { message: string; action?: { label: string; run: () => void } },
  now: Date.now(),
  fontsVersion: 0,
  route: location.hash,
  overrideProfile: null as string | null,
  overrideFriendly: "",
  drag: { active: false, moving: null, preview: null } as DragState,
  menuOpen: false,
  liveStates: {} as Record<string, Live>,
  room: "",
  hidePlaced: false,
  palette: false,
  firmwareJob: null as null | { job: any; logs: string[] },
});

export const currentScreen = computed<Screen | undefined>(() => state.inventory.screens.find((s) => s.id === state.selected));
// The firmware version a screen's features go by, as the add-on works it out (firmware_known, app 0.2.78; null when it
// can't tell). A screen entry without the field goes by the firmware text, as before.
export const firmwareVersion = (screen: Screen | undefined) =>
  (screen && "firmware_known" in screen ? screen.firmware_known : screen?.firmware) || "";
export const firmwareOf = computed(() => firmwareVersion(currentScreen.value));
export const supports = (major: number, minor: number, patch: number) => supportsVersion(firmwareOf.value, major, minor, patch);
// What the screen holds and draws, as the add-on says (app 0.2.78), so a screen whose version Home Assistant can't
// report for a moment keeps its 48 tiles instead of dropping to ten, and a copied or imported layout isn't cut to ten.
export const tileLimit = computed(() => {
  const limit = currentScreen.value?.tile_limit;
  return typeof limit === "number" && Number.isInteger(limit) && limit > 0 ? limit : limitFor(firmwareOf.value);
});
export const fullPage = computed(() => {
  const full = currentScreen.value?.full_page;
  return typeof full === "boolean" ? full : supports(0, 2, 62);
});
// Several tiles that go to the same page, such as a way back to page 1 on every sub-page (firmware 0.2.65); every
// other entity stays once per screen.
export const pageTilesRepeat = computed(() => {
  const repeat = currentScreen.value?.page_tiles_repeat;
  return typeof repeat === "boolean" ? repeat : supports(0, 2, 65);
});
export const repeatable = (id: string) => pageTilesRepeat.value && pageTarget(id) > 0;
export const isGuition = computed(() => ["guition", "jc8012p4a1"].includes(currentScreen.value?.board || ""));
export const barMetrics = computed(() => BAR_METRICS[isGuition.value ? "guition" : "cyd"]);
export const currentTile = computed<Tile | undefined>(() =>
  state.selectedTile && state.layout?.tiles.includes(state.selectedTile) ? state.selectedTile : undefined);
// The reactive copy and the plain object are the same tile.
export const isSelected = (tile: Tile) => Boolean(state.selectedTile) && toRaw(state.selectedTile) === toRaw(tile);

// ---- Toasts ----
let toastTimer = 0;
export function toast(message: string, action?: { label: string; run: () => void }) {
  state.toast = { message, action };
  clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => (state.toast = null), action ? 8000 : 5000);
}
export function dismissToast() {
  state.toast = null;
}
export async function copyText(text: string, element?: Element | null, what = "API key") {
  try {
    if (!navigator.clipboard || !window.isSecureContext) throw new Error();
    await navigator.clipboard.writeText(text);
    toast(`${what} copied.`);
  } catch {
    if (element) {
      const range = document.createRange();
      range.selectNodeContents(element);
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);
    }
    toast(document.execCommand("copy") ? `${what} copied.` : `${what} is selected. Copy with Ctrl+C or Command+C.`);
  }
}
export function openIntegrations() {
  // Pairing happens in Home Assistant itself. This page lives in HA's ingress iframe,
  // so send the top window to Devices & services (same origin); elsewhere open a tab.
  const path = "/config/integrations/dashboard";
  try {
    window.top!.location.assign(path);
  } catch {
    window.open(path, "_blank");
  }
}

// ---- Routes: the hash keeps a view open across a reload (#settings did before) ----
export const routes = ["", "#settings", "#new-screen", "#firmware", "#alerts", "#override"] as const;
export type Route = (typeof routes)[number];
export const route = computed<Route>(() => (routes.includes(state.route as Route) ? (state.route as Route) : ""));
export function go(target: Route) {
  if (location.hash === target) { state.route = target; return; }
  location.hash = target;
}
window.addEventListener("hashchange", () => { state.route = location.hash; window.scrollTo(0, 0); });

// ---- Names and icons ----
export function entityName(id: string) {
  return state.inventory.entities.find((e) => e.id === id)?.name || state.inventory.builtin?.find((e) => e.id === id)?.name || id;
}
let iconIndex: { source: unknown; byName: Record<string, { name: string; cp: string; label: string }> } = { source: null, byName: {} };
export function iconNamed(name: string | undefined) {
  if (iconIndex.source !== state.inventory.icons)
    iconIndex = { source: state.inventory.icons, byName: Object.fromEntries((state.inventory.icons?.groups || []).flatMap((g) => g.icons.map((i) => [i.name, i]))) };
  return name ? iconIndex.byName[name] : undefined;
}
// What the firmware draws without a choice: Home Assistant's own icon, else the domain icon.
export function automaticIcon(id: string): string {
  const icons = state.inventory.icons;
  if (!icons) return "F0335";
  const entity = state.inventory.entities.find((e) => e.id === id), domain = id.split(".")[0];
  if (icons.builtin?.[id]) return icons.builtin[id];
  if (entity?.icon) return entity.icon;
  if (domain === "weather") return icons.weather[entity?.state || ""] || icons.weather.partlycloudy;
  if (domain === "sun") return icons.sun[entity?.state || ""] || icons.sun.below_horizon;
  return icons.defaults[domain] || icons.fallback;
}
export const tileIconCp = (tile: Tile) => iconNamed(tile.options?.icon)?.cp || automaticIcon(tile.entity);

// ---- Capabilities and actions from Home Assistant ----
const askedCapabilities = new Set<string>();
export async function loadCapabilities(entities: string[]) {
  const wanted = [...new Set(entities)].filter((id) => !askedCapabilities.has(id) && !id.startsWith("screen."));
  if (!wanted.length) return;
  wanted.forEach((id) => askedCapabilities.add(id));
  try {
    for (let i = 0; i < wanted.length; i += 40) {
      const query = wanted.slice(i, i + 40).map((id) => `entity=${encodeURIComponent(id)}`).join("&");
      Object.assign(state.capabilities, (await getJson(`capabilities?${query}`)).capabilities || {});
    }
  } catch {
    wanted.forEach((id) => askedCapabilities.delete(id));
  }
}
const askedActions = new Set<string>();
export async function loadEntityActions(entity: string) {
  if (askedActions.has(entity)) return;
  askedActions.add(entity);
  try {
    state.entityActions[entity] = (await getJson(`entity-actions?entity=${encodeURIComponent(entity)}`)).actions;
  } catch {
    askedActions.delete(entity);
  }
}

// ---- Live values on the mockup (app 0.2.73): what the screen shows right now ----
let statesFlight = false;
export async function loadStates() {
  const entities = [...new Set((state.layout?.tiles || []).map((t) => t.entity).filter((id) => !id.startsWith("screen.")))];
  if (!entities.length || statesFlight) return;
  statesFlight = true;
  try {
    for (let i = 0; i < entities.length; i += 60) {
      const query = entities.slice(i, i + 60).map((id) => `entity=${encodeURIComponent(id)}`).join("&");
      Object.assign(state.liveStates, (await getJson(`states?${query}`)).states || {});
    }
  } catch {
    // The next tick tries again; the mockup keeps the last values.
  } finally {
    statesFlight = false;
  }
}
// The live value, else what the inventory knew when it was fetched, else nothing.
export function liveOf(entity: string): Live | null {
  const live = state.liveStates[entity];
  if (live) return live;
  const known = state.inventory.entities.find((e) => e.id === entity);
  return known?.state ? { state: known.state, word: null, a: {} } : null;
}

// ---- Selecting a screen and editing its layout ----
// Every edit counts, so a save only clears the edits it sent (app 0.2.78).
let edits = 0;
export function markDirty() {
  state.dirty = true;
  state.saved = 0;
  edits++;
}
export function select(id: string | null) {
  // The open screen again, the way back from Firmware & USB, Alerts or Settings: its unsaved edits stay (app 0.2.78).
  // Without edits it reads the stored layout again, which picks up what Claude or another tab changed meanwhile.
  if (id === state.selected && state.layout && state.dirty) {
    closeInspector();
    state.tab = "layout";
    state.menuOpen = false;
    go("");
    return;
  }
  if (id !== state.selected && state.dirty && !confirm("You have unsaved changes. Open a different screen anyway?")) return;
  if (id !== state.selected) {
    flushSettings();
    state.settingEdits = {};
  }
  state.selected = id;
  state.selectedTile = null;
  state.inspector = null;
  state.tab = "layout";
  state.menuOpen = false;
  const screen = state.inventory.screens.find((s) => s.id === id);
  if (!screen) { state.layout = null; return; }
  // A plain copy: the inventory is reactive, and structuredClone refuses a proxy.
  const layout: Layout = JSON.parse(JSON.stringify(screen.layout));
  normalize(layout);
  layout.pages = pageCount(entriesOf(layout), layout.pages);
  state.layout = layout;
  state.insertAt = -1;
  state.dirty = false;
  state.saved = 0;
  loadTopbarPreview(0);
  loadCapabilities(layout.tiles.map((t) => t.entity));
  loadStates();
  go("");
}
export const liveEntries = () => (state.layout ? entriesOf(state.layout) : []);
// Apply an arrangement; a new tile joins the layout. True when anything changed.
function commit(result: { tile: Tile; slot: number }[]) {
  const layout = state.layout!;
  const before = layout.tiles.map((t) => `${t.entity}@${t.slot}`).join();
  for (const { tile, slot } of result) { tile.slot = slot; if (!layout.tiles.includes(tile)) layout.tiles.push(tile); }
  normalize(layout);
  layout.pages = pageCount(entriesOf(layout), layout.pages);
  const changed = layout.tiles.map((t) => `${t.entity}@${t.slot}`).join() !== before;
  if (changed) markDirty();
  return changed;
}
export function placeTile(tile: Tile, target: number) {
  if (!state.layout) return false;
  loadCapabilities([tile.entity]);
  const result = arrange(state.layout.tiles, tile, target);
  const placed = result ? commit(result) : false;
  if (placed && !state.liveStates[tile.entity]) loadStates();
  return placed;
}
// A click in the picker: the marked empty cell, else the first free cell.
export function addTile(id: string) {
  const layout = state.layout;
  if (!layout || (!repeatable(id) && layout.tiles.some((t) => t.entity === id)) || layout.tiles.length >= tileLimit.value) return;
  const tile = newTile(id);
  const slot = state.insertAt >= 0 ? state.insertAt : firstFree(occupied(entriesOf(layout)), sizeOf(tile));
  state.insertAt = -1;
  if (slot >= 0 && placeTile(tile, slot)) openTile(tile);
}
export function removeTile(tile: Tile) {
  const layout = state.layout;
  if (!layout) return;
  const index = layout.tiles.indexOf(tile);
  if (index < 0) return;
  layout.tiles.splice(index, 1);
  if (isSelected(tile)) closeInspector();
  markDirty();
  layout.pages = pageCount(entriesOf(layout), layout.pages);
  toast(`${tile.name || entityName(tile.entity)} removed`, { label: "Undo", run: () => placeTile(tile, tile.slot) });
}
export function addPage() {
  const layout = state.layout;
  if (!layout) return;
  layout.pages = Math.min(MAX_PAGES, pageCount(entriesOf(layout), layout.pages) + 1);
  markDirty();
}
// An empty page goes; the pages after it move up.
export function removePage(page: number) {
  const layout = state.layout;
  if (!layout) return;
  for (const tile of layout.tiles) if (pageOf(tile.slot) > page) tile.slot -= SLOTS_PER_PAGE;
  layout.pages = Math.max(1, pageCount(entriesOf(layout), layout.pages) - 1);
  markDirty();
}
// Moving a tile without dragging it (app 0.2.78), for a finger on a phone and for anyone who can't drag: the first
// free cell of that page, else its first cell, where the tile in the way swaps places as it does for a drop or an
// arrow key. `page` counts from 0; the page after the last one starts a new page.
export function moveTileToPage(tile: Tile, page: number) {
  const layout = state.layout;
  if (!layout || !Number.isInteger(page) || page < 0 || page >= MAX_PAGES || page === pageOf(tile.slot)) return false;
  const slot = firstFree(occupied(entriesOf(layout).filter((e) => e.tile !== tile)), sizeOf(tile), page * SLOTS_PER_PAGE);
  const moved = placeTile(tile, slot >= 0 && pageOf(slot) === page ? slot : page * SLOTS_PER_PAGE);
  if (!moved) toast(`There is no room for this tile on page ${page + 1}.`);
  return moved;
}
export function pagesShown() {
  const layout = state.layout;
  if (!layout) return 1;
  const entries = state.drag.preview || entriesOf(layout);
  const pages = pageCount(entries, layout.pages);
  // While dragging, one more page waits after the last one.
  return state.drag.active && pages < MAX_PAGES ? pages + 1 : pages;
}
// The tile's options change live; a card that becomes double-wide keeps its row when the cell beside it is
// free, else it takes the nearest free row (below first); every other tile stays where it is.
export function setTileOption(tile: Tile, key: string, value: unknown) {
  const domain = tile.entity.split(".")[0], caps = state.capabilities[tile.entity], wasWide = isWide(tile), wasSize = sizeOf(tile);
  tile.options = { ...tile.options, [key]: value };
  // Direct controls need the standard layout without a mini slider, and vice versa.
  if (key === "display" && value === "watch") { tile.options.inline = "none"; if (state.inventory.controls?.[domain]) tile.options.controls = "none"; }
  if (key === "display" && ["forecast", "sunpath"].includes(value as string)) tile.options.size = "wide";
  if (key === "inline" && value === "slider") { tile.options.display = "standard"; if (state.inventory.controls?.[domain]) tile.options.controls = "none"; }
  if (key === "controls" && value !== "none") { tile.options.display = "standard"; tile.options.inline = "none"; }
  // A card that becomes wide gets the first direct control Home Assistant offers when the usual one isn't there.
  const catalogue = state.inventory.controls?.[domain];
  if (key === "size" && value === "wide" && caps && catalogue && !("controls" in tile.options) && !caps.controls.includes(catalogue.default))
    tile.options.controls = catalogue.choices.find((c) => c.key !== "none" && caps.controls.includes(c.key))?.key || "none";
  markDirty();
  const layout = state.layout;
  if (!layout) return;
  // A card that grows to the whole page keeps its page: the other tiles there move to the first free
  // cells after it. With no room for them it takes the first empty page, or stays as it was.
  if (isFull(tile) && wasSize !== "full") {
    const page = pageOf(tile.slot), others = layout.tiles.filter((t) => t !== tile && pageOf(t.slot) === page);
    const taken = occupied(entriesOf(layout).filter((e) => e.tile !== tile && !others.includes(e.tile)));
    const moved: [Tile, number][] = [];
    for (const other of others) {
      const slot = firstFree(taken, sizeOf(other), (page + 1) * SLOTS_PER_PAGE);
      if (slot < 0) { moved.length = 0; break; }
      moved.push([other, slot]);
      for (const c of cellsOf(slot, sizeOf(other))) taken.add(c);
    }
    if (moved.length === others.length) { for (const [other, slot] of moved) other.slot = slot; tile.slot = page * SLOTS_PER_PAGE; }
    else {
      const slot = firstFree(occupied(entriesOf(layout).filter((e) => e.tile !== tile)), "full");
      if (slot >= 0) tile.slot = slot;
      else { tile.options.size = wasSize; toast("No page is free for a full-page tile. Free a page first."); }
    }
  } else if (isWide(tile) && !wasWide) {
    const taken = occupied(entriesOf(layout).filter((e) => e.tile !== tile)), own = rowStart(tile.slot);
    const slot = fits(taken, own, "wide") ? own : nearestFree(taken, "wide", own);
    if (slot >= 0) tile.slot = slot;
  }
  normalize(layout);
  layout.pages = pageCount(entriesOf(layout), layout.pages);
}
// A navigation tile goes to another page: its entity changes (screen.page_<n>). One tile per page it goes to, unless
// the firmware takes several (0.2.65). The page after the last one becomes a new, empty page to fill (app 0.2.78).
export function retargetPageTile(tile: Tile, page: number) {
  const entity = `screen.page_${page}`, layout = state.layout;
  if (!layout || entity === tile.entity || !pageTarget(entity)) return false;
  if (!repeatable(entity) && layout.tiles.some((t) => t.entity === entity)) { toast(`This screen already has a tile that goes to page ${page}.`); return false; }
  tile.entity = entity;
  layout.pages = Math.max(pageCount(entriesOf(layout), layout.pages), page);
  markDirty();
  return true;
}

// ---- Inspector (the drawer) ----
export function openTile(tile: Tile) {
  if (!isSelected(tile)) { state.iconPickerOpen = false; state.actionPickerOpen = false; state.actionSearch = ""; }
  state.selectedTile = tile;
  state.inspector = { kind: "tile" };
  loadCapabilities([tile.entity]);
}
export function openBar(index: number) {
  if (!(state.inspector?.kind === "bar" && state.inspector.index === index)) state.iconPickerOpen = false;
  state.selectedTile = null;
  state.inspector = { kind: "bar", index };
}
export function openBarAdd() {
  state.selectedTile = null;
  state.inspector = { kind: "bar-add" };
}
export function closeInspector() {
  state.inspector = null;
  state.selectedTile = null;
}

// ---- Save ----
export async function save() {
  if (state.busy || !state.layout || !state.selected) return;
  state.busy = true;
  // The layout as it leaves: a drag, the drawer or Add still work while the request is on its way (the add-on's check
  // can take seconds after Copy or Import), and those changes aren't in it (app 0.2.78).
  const sent = edits, screen = state.selected;
  try {
    // Screen settings apply on their own (flushSettings); the stored ones stay as they are.
    const { settings: _settings, ...tiles } = state.layout;
    await send(`screens/${encodeURIComponent(state.selected)}`, "PUT", tiles);
    if (state.selected !== screen) toast(`Saved. ${state.inventory.screens.find((s) => s.id === screen)?.name || "The screen"} is being updated.`);
    else if (edits === sent) {
      state.dirty = false;
      state.saved = Date.now();
      toast("Saved. Your screen is being updated.");
    } else toast("Saved. Your newest change isn't sent yet: press Save & send again.");
    await refresh();
  } catch (e: any) {
    toast(e.message);
  } finally {
    state.busy = false;
  }
}

// ---- Identify and the test alert (app 0.2.73): a screen's own show_alert action ----
export const canAlert = (screen: Screen | undefined) =>
  Boolean(screen && screen.alert_action && versionAtLeast(firmwareVersion(screen), state.inventory.alerts?.min_firmware || "0.2.31"));
export async function identify(screen: Screen) {
  try {
    await send(`screens/${encodeURIComponent(screen.id)}/identify`, "POST");
    toast(`${screen.name} blinks and shows a card for a few seconds.`);
  } catch (e: any) {
    toast(e.message);
  }
}
export async function sendTestAlert(target: string, data: Record<string, unknown>) {
  return (await send("alerts/test", "POST", { screen: target, data })) as { sent: number; failed: number; skipped: number; unusable?: string[] };
}

// ---- Copying and sharing a layout (app 0.2.73) ----
const LAYOUT_KEYS = ["title", "tiles", "header", "pages"] as const;
function adopt(source: Partial<Layout>, what: string) {
  const layout = state.layout;
  if (!layout) return;
  const tiles = (Array.isArray(source.tiles) ? source.tiles : [])
    .filter((t): t is Tile => Boolean(t && typeof t === "object" && typeof t.entity === "string" && t.entity.includes(".")))
    .map((t) => ({ entity: t.entity, name: typeof t.name === "string" ? t.name : "", slot: Number.isInteger(t.slot) ? t.slot : -1,
                   ...(t.options && typeof t.options === "object" ? { options: { ...t.options } } : {}) }) as Tile);
  const seen = new Set<string>();
  const unique = tiles.filter((t) => repeatable(t.entity) || (!seen.has(t.entity) && seen.add(t.entity)));
  const kept = unique.slice(0, tileLimit.value);
  layout.tiles = kept;
  if (source.header && Array.isArray(source.header.items)) layout.header = { items: source.header.items.map((i) => ({ ...i })) };
  else delete layout.header;
  layout.pages = Number.isInteger(source.pages) ? (source.pages as number) : 1;
  normalize(layout);
  layout.pages = pageCount(entriesOf(layout), layout.pages);
  closeInspector();
  markDirty();
  loadCapabilities(kept.map((t) => t.entity));
  loadStates();
  loadTopbarPreview(0);
  toast(kept.length < unique.length
    ? `${what}: ${kept.length} of ${unique.length} tiles fit this screen's firmware. Save & send when it looks right.`
    : `${what}. Save & send when it looks right.`);
}
export function copyLayoutFrom(id: string) {
  const other = state.inventory.screens.find((s) => s.id === id);
  if (!other || !state.layout) return;
  adopt(JSON.parse(JSON.stringify(other.layout)), `Layout of ${other.name} copied`);
}
export function layoutJson() {
  const layout = state.layout;
  if (!layout) return "";
  const out: Record<string, unknown> = { esp_screens_layout: 1 };
  for (const key of LAYOUT_KEYS) if (layout[key] !== undefined) out[key] = layout[key];
  return JSON.stringify(out, null, 2);
}
export function exportLayout() {
  const text = layoutJson();
  if (!text) return;
  const name = `${(currentScreen.value?.name || "screen").toLowerCase().replace(/[^a-z0-9]+/g, "-")}.layout.json`;
  const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
  copyText(text, undefined, "Layout JSON");
}
export function importLayout(text: string) {
  let data: any;
  try { data = JSON.parse(text); } catch { toast("That isn't JSON. Export a layout first, or paste one from another ESP Screens."); return; }
  if (!data || typeof data !== "object" || !Array.isArray(data.tiles)) { toast("No tiles in this file. Expected a layout exported from ESP Screens."); return; }
  adopt(data, "Layout imported");
}

// ---- Updates with content (app 0.2.73): what a screen gets, and how far its update is ----
// The changelog comes with the full inventory only (app 0.2.78): the live payload goes out every few seconds.
export function whatsNew(screen: Screen): string[] {
  const target = state.inventory.updates?.target;
  const sections: ChangelogSection[] | undefined = state.inventory.changelog;
  if (!Array.isArray(sections) || !target) return [];
  const since = firmwareVersion(screen);
  const lines: string[] = [];
  for (const section of sections) {
    if (versionAtLeast(section.firmware, target) && section.firmware !== target) continue;
    if (since && versionAtLeast(since, section.firmware)) continue;
    for (const line of section.lines) if (!lines.includes(line)) lines.push(line);
  }
  return lines;
}
let firmwareFlight = false;
export async function loadFirmwareJob() {
  if (firmwareFlight) return;
  firmwareFlight = true;
  try {
    const data = await getJson("firmware");
    state.firmwareJob = { job: data.job, logs: data.logs || [] };
  } catch {
    // Keep what we have.
  } finally {
    firmwareFlight = false;
  }
}
export const anyUpdating = () => state.inventory.screens.some((s) => s.update?.state === "running") || state.updating.length > 0;
// Progress of a running update, from its phase and the ESPHome stage of the build.
export function updateProgress(screen: Screen): { percent: number; text: string } | null {
  const u = screen.update || {};
  if (!(u.state === "running" || state.updating.includes(screen.id))) return null;
  const stage = state.firmwareJob?.job?.stage as string | undefined;
  if (u.phase === "verify") return { percent: 78, text: PHASES.verify };
  if (u.phase === "settle") return { percent: 92, text: PHASES.settle };
  if (u.phase === "install" || !u.phase) {
    if (stage === "upload") return { percent: 66, text: "Writing the firmware over Wi-Fi…" };
    if (stage) return { percent: 40, text: "Building the firmware…" };
    return { percent: 12, text: PHASES.install };
  }
  return { percent: 12, text: PHASES[u.phase] || "Starting update…" };
}

// ---- Top bar ----
// Without a stored top bar the screen shows what it always did: the clock of show_clock.
export const topbarItems = (): HeaderItem[] =>
  state.layout?.header?.items ?? ((state.layout?.settings?.show_clock ?? true) ? [{ type: "clock" }] : []);
export const topbarMax = () => state.inventory.header?.max_items || 6;
export function setTopbarItems(items: HeaderItem[]) {
  if (!state.layout) return;
  state.layout.header = { items };
  markDirty();
  loadTopbarPreview();
}
let topbarTimer = 0;
// Entity text as the screen will show it, for the items not previewed yet.
export function loadTopbarPreview(delay = 150) {
  clearTimeout(topbarTimer);
  topbarTimer = window.setTimeout(async () => {
    const items = topbarItems();
    if (!items.some((item) => item.type === "entity")) return;
    try {
      const data = await send("header-preview", "POST", { header: { items } });
      items.forEach((item, i) => (state.topbarPreviews[itemKey(item)] = data.items[i]));
    } catch {
      // Keep the last preview; the next edit or refresh tries again.
    }
  }, delay);
}
export function topbarLabel(item: HeaderItem) {
  if (item.type === "entity") return entityName(item.entity!);
  return state.inventory.header?.builtin.find((b) => b.type === item.type)?.label || item.type;
}
// What the item shows right now: { icon, text, color, shown }. Entities wait for the add-on's preview.
export function topbarView(item: HeaderItem): ItemView {
  const now = new Date(state.now);
  if (item.type === "clock") return { text: clockText(settingValues().clock_24h !== false, now), shown: true };
  if (item.type === "date") return { text: dateText(now), shown: true };
  if (item.type === "analog") return { analog: true, shown: true };
  const p = state.topbarPreviews[itemKey(item)];
  if (!p) return { icon: item.icon === "none" ? null : iconNamed(item.icon)?.cp || automaticIcon(item.entity!), text: "…", shown: true, loading: true };
  return { icon: p.i || null, text: p.k === "ago" ? agoText(p.e, Math.floor(state.now / 1000)) : p.t, color: p.c ? `#${p.c}` : null, shown: p.shown };
}
export function moveTopbarItem(from: number, to: number) {
  const items = [...topbarItems()];
  if (to < 0 || to >= items.length || from === to) return false;
  items.splice(to, 0, ...items.splice(from, 1));
  setTopbarItems(items);
  return true;
}
export function removeTopbarItem(index: number) {
  const items = [...topbarItems()];
  const [item] = items.splice(index, 1);
  if (!item) return;
  if (state.inspector?.kind === "bar") closeInspector();
  setTopbarItems(items);
  toast(`${topbarLabel(item)} removed from the top bar`, {
    label: "Undo",
    run: () => { const back = [...topbarItems()]; back.splice(Math.min(index, back.length), 0, item); setTopbarItems(back); },
  });
}
export function addTopbarItem(item: HeaderItem) {
  const items = topbarItems();
  if (items.length >= topbarMax()) return toast(`The top bar has room for ${topbarMax()} items.`);
  if (items.some((other) => itemKey(other) === itemKey(item))) return toast("This is already in the top bar.");
  // The new chip lights up briefly so the eye finds it.
  state.topbarAdded = { key: itemKey(item), time: Date.now() };
  setTopbarItems([...items, item]);
  openBar(items.length);
}

// ---- Screen settings: the same groups and rows as the settings page on the screen itself ----
// Every change applies at once, like on the screen; no Save needed. A screen with firmware 0.2.49+ owns its
// settings and ESP Screens changes them through its entities in Home Assistant.
export const SETTING_GROUPS = [
  { title: "Brightness", icon: "F0599", rows: [
    { key: "brightness", label: "Brightness", kind: "number", min: 5, max: 100, step: 5, unit: "%" },
    { key: "dark_mode", label: "Dark mode", kind: "toggle" },
    { key: "standby_enabled", label: "Auto standby", kind: "toggle" },
    { key: "standby_seconds", label: "Standby after", kind: "duration", min: 60, max: 86400, needs: "standby_enabled" },
    { key: "standby_brightness", label: "Standby brightness", kind: "number", min: 0, max: 100, step: 5, unit: "%", needs: "standby_enabled", cap: "brightness" },
  ] },
  { title: "Night", icon: "F0594", rows: [
    { key: "night_enabled", label: "Night mode", kind: "toggle" },
    { key: "night_start", label: "Starts", kind: "moment", needs: "night_enabled" },
    { key: "night_end", label: "Ends", kind: "moment", needs: "night_enabled" },
    { key: "night_brightness", label: "Night brightness", kind: "number", min: 0, max: 100, step: 5, unit: "%", needs: "night_enabled", cap: "brightness" },
  ] },
  { title: "Screen", icon: "F0379", rows: [
    { key: "clock_24h", label: "Clock", kind: "choice", options: [[false, "12 hour"], [true, "24 hour"]] },
    { key: "auto_home", label: "Back to page 1", kind: "toggle" },
    { key: "auto_home_seconds", label: "After", kind: "duration", min: 30, max: 3600, needs: "auto_home" },
    { key: "home_on_standby", label: "Also on standby", kind: "toggle" },
    { key: "swipe_pages", label: "Swipe between pages", kind: "toggle" },
    { key: "page_buttons", label: "Page buttons", kind: "toggle" },
    { key: "rotation", label: "Rotation", kind: "choice", options: [[0, "0°"], [90, "90°"], [180, "180°"], [270, "270°"]] },
  ] },
] as const;
export type SettingRow = (typeof SETTING_GROUPS)[number]["rows"][number] & { min?: number; max?: number; step?: number; unit?: string; needs?: string; cap?: string; options?: readonly (readonly [unknown, string])[] };
// Page buttons and swiping both off (firmware 0.2.69+): only Go to page tiles change the page, so the editor says which
// pages the Go to page tiles lead to and which page that leaves out, or has no way back to page 1. Empty when either
// is on or still unknown, or every page can be reached and left.
export function pageReachWarning(entries = liveEntries(), pages = state.layout ? pageCount(entries, state.layout.pages) : 1) {
  const values = settingValues();
  if (pages < 2 || values.page_buttons !== false || values.swipe_pages !== false) return "";
  const { tiles, targets, unreachable, noWayBack } = strandedPages(entries, pages);
  if (!unreachable.length && !noWayBack.length) return "";
  const named = (list: number[]) => (list.length === 1 ? `page ${list[0]}` : `pages ${list.slice(0, -1).join(", ")} and ${list[list.length - 1]}`);
  // A page that tiles lead to but only from pages that can't be reached themselves.
  const missing = unreachable.filter((page) => !targets.includes(page)), cutOff = unreachable.filter((page) => targets.includes(page));
  let text = "Page buttons and swiping are off, so only Go to page tiles change the page. ";
  text += tiles ? `You have ${tiles} Go to page ${tiles === 1 ? "tile" : "tiles"}, to ${named(targets)}` : "You have no Go to page tiles";
  text += missing.length ? `${tiles ? ", but none" : ""} to ${named(missing)}, so you can't reach ${missing.length === 1 ? "it" : "them"}.` : ".";
  if (cutOff.length) text += ` The tiles to ${named(cutOff)} are only on pages you can't reach.`;
  if (noWayBack.length) text += ` From ${named(noWayBack)} no tile leads back to page 1.`;
  return text;
}
// Changes made here that the screen has not reported back yet win over what Home Assistant still shows for a
// few seconds, so a value never flicks back while it travels.
const SETTING_EDIT_MS = 4000;
let settingQueue: Record<string, any> = {}, settingTarget: string | null = null, settingTimer = 0, settingFlight: Promise<Response> | null = null;
export const settingsView = () => currentScreen.value?.settings;
export function settingValues(): Record<string, any> {
  const view = settingsView(), values = { ...(view?.values || {}) };
  for (const [key, edit] of Object.entries(state.settingEdits)) values[key] = edit.value;
  return values;
}
// The same steps as settings_screen.h: seconds low down, quarters of an hour up top; times by the quarter,
// whole hours while held.
export const ladderStep = (seconds: number) => (seconds < 300 ? 30 : seconds < 900 ? 60 : seconds < 3600 ? 300 : seconds < 7200 ? 900 : 1800);
export function steppedSetting(row: SettingRow, value: number, direction: number, held: boolean, values: Record<string, any>) {
  if (row.kind === "moment") {
    let next = held && value % 60 ? Math.floor(value / 60) * 60 + (direction > 0 ? 60 : 0) : value + direction * (held ? 60 : 15);
    next %= 1440;
    return next < 0 ? next + 1440 : next;
  }
  const step = row.kind === "duration" ? ladderStep(direction < 0 ? value - 1 : value) : row.step!;
  const max = row.cap ? Math.min(row.max!, values[row.cap]) : row.max!;
  return Math.min(max, Math.max(row.min!, value + direction * step));
}
export function durationText(seconds: number) {
  if (seconds < 60) return `${seconds} sec`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min`;
  const hours = Math.floor(seconds / 3600), minutes = Math.floor((seconds % 3600) / 60);
  return minutes ? `${hours} h ${String(minutes).padStart(2, "0")}` : `${hours} h`;
}
export function momentText(minutes: number, clock24: boolean) {
  const hour = Math.floor(minutes / 60), minute = String(minutes % 60).padStart(2, "0");
  return clock24 ? `${String(hour).padStart(2, "0")}:${minute}` : `${hour % 12 || 12}:${minute} ${hour < 12 ? "AM" : "PM"}`;
}
export function settingText(row: SettingRow, values: Record<string, any>) {
  const value = values[row.key];
  // Home Assistant has no value while the screen is offline or the entity is off.
  if (value === null || value === undefined) return "—";
  if (row.kind === "number") return `${value}${row.unit || ""}`;
  if (row.kind === "duration") return durationText(value);
  if (row.kind === "moment") return momentText(value, values.clock_24h !== false);
  return "";
}
export function setSetting(key: string, value: any, delay: number) {
  // One screen's changes at a time: the ones for the screen shown before go out first.
  if (settingTarget && settingTarget !== state.selected && Object.keys(settingQueue).length) {
    flushSettings();
    toast("Still saving the other screen's settings. Try again in a moment.");
    return;
  }
  settingTarget = state.selected;
  const values = settingValues();
  state.settingEdits[key] = { value, at: Date.now() };
  settingQueue[key] = value;
  // A lower brightness pulls both dim levels down with it, as on the screen.
  if (key === "brightness")
    for (const dim of ["standby_brightness", "night_brightness"])
      if (values[dim] > value) state.settingEdits[dim] = { value, at: Date.now() };
  state.settingPending = true;
  clearTimeout(settingTimer);
  settingTimer = window.setTimeout(() => flushSettings(), delay);
}
export async function flushSettings(unloading = false) {
  clearTimeout(settingTimer);
  if (settingFlight || !Object.keys(settingQueue).length || !settingTarget) return;
  const screen = settingTarget, changes = settingQueue;
  settingQueue = {};
  const request = api(`screens/${encodeURIComponent(screen)}/settings`, {
    method: "PUT",
    body: JSON.stringify({ settings: changes }),
    keepalive: unloading,
  });
  settingFlight = request;
  try {
    const view = await (await request).json();
    const current = state.inventory.screens.find((s) => s.id === screen);
    if (current) current.settings = view;
  } catch (e: any) {
    toast(e.message);
    // What did not arrive is not kept: the panel shows the screen's own values again.
    if (screen === state.selected) for (const key of Object.keys(changes)) delete state.settingEdits[key];
    if (screen === state.selected && changes.brightness !== undefined) for (const dim of ["standby_brightness", "night_brightness"]) delete state.settingEdits[dim];
  } finally {
    settingFlight = null;
    if (Object.keys(settingQueue).length) settingTimer = window.setTimeout(() => flushSettings(), 150);
    else settingTarget = null;
    state.settingPending = Boolean(Object.keys(settingQueue).length);
    if (screen === state.selected) settleSettings();
    // A value the screen refused or clamped comes back without a live update: look again once edits expire.
    setTimeout(() => { if (screen === state.selected) settleSettings(); }, SETTING_EDIT_MS + 100);
  }
}
// Values Home Assistant reports take over again once they match a change made here, or after a few seconds
// (the screen refused or clamped it).
export function settleSettings() {
  const view = settingsView();
  for (const [key, edit] of Object.entries(state.settingEdits)) {
    if (settingQueue[key] !== undefined || settingFlight) continue;
    if ((view && view.values[key] === edit.value) || Date.now() - edit.at > SETTING_EDIT_MS) delete state.settingEdits[key];
  }
}

// ---- Updates ----
export const PHASES: Record<string, string> = {
  install: "Building and installing…",
  verify: "Waiting for the screen to come back…",
  settle: "Checking that it stays stable…",
};
export async function startUpdate(screen: Screen, host?: string) {
  state.updating.push(screen.id);
  try {
    await send(`screens/${encodeURIComponent(screen.id)}/update`, "POST", host ? { host } : {});
    await refresh();
  } catch (e: any) {
    state.updating = state.updating.filter((id) => id !== screen.id);
    toast(e.message);
  }
}
export async function runUpdateAll() {
  try {
    await send("updates/run", "POST");
    await refresh();
  } catch (e: any) {
    toast(e.message);
  }
}
export async function setAutoUpdate(auto: boolean) {
  try {
    await send("updates", "PUT", { auto });
    if (state.inventory.updates) state.inventory.updates.auto = auto;
    toast(auto ? "Screens will now update automatically at night." : "Automatic updates are off.");
  } catch (e: any) {
    toast(e.message);
  }
}
export async function installClaudeSkill() {
  try {
    state.inventory.claude_skill = await send("claude-skill", "POST");
    toast(state.inventory.claude_skill?.restart
      ? "Skill installed. Restart Claude Code once so it finds the new skills folder."
      : "Skill installed. Claude Code picks it up right away.");
  } catch (e: any) {
    toast(e.message);
  }
}

// ---- Inventory: full catalogue, light polls, and the live stream ----
export async function refresh(full = true) {
  try {
    const data = await getJson(full ? "inventory" : "inventory?light=1");
    // A light poll carries only screens and update status; keep the catalogues we have.
    state.inventory = full ? data : { ...state.inventory, ...data };
    if (data.csrf) setCsrf(data.csrf);
    state.connected = Boolean(state.inventory.connected);
    state.reachable = true;
    for (const screen of state.inventory.screens) if (screen.update?.state === "running") state.updating = state.updating.filter((id) => id !== screen.id);
    if (state.selected) settleSettings();
  } catch {
    state.reachable = false;
  }
}
function applyLive(data: Partial<Inventory>) {
  state.inventory = { ...state.inventory, ...data } as Inventory;
  state.connected = Boolean(state.inventory.connected);
  for (const screen of state.inventory.screens) if (screen.update?.state === "running") state.updating = state.updating.filter((id) => id !== screen.id);
  if (state.selected) settleSettings();
}
let pollTimer = 0, lastFull = Date.now(), live = false, stream: EventSource | null = null;
function listen() {
  if (stream || typeof EventSource === "undefined") return;
  stream = new EventSource("api/events");
  stream.onopen = () => { live = true; poll(); };
  stream.onmessage = (e) => { if (!document.hidden) applyLive(JSON.parse(e.data)); };
  stream.onerror = () => { live = false; poll(); };
}
// Poll only while the tab is visible; a hidden tab would otherwise keep the add-on busy.
// Live updates arrive over server-sent events; polling is the fallback while the stream is down,
// plus a full catalogue refresh every 5 minutes.
function poll() {
  clearTimeout(pollTimer);
  const wait = live ? 60000 : state.inventory.updates?.busy ? 3000 : 10000;
  pollTimer = window.setTimeout(async () => {
    if (!document.hidden) {
      const full = Date.now() - lastFull >= 300000;
      if (full) lastFull = Date.now();
      if (full || !live) await refresh(full);
    }
    poll();
  }, wait);
}
let booted = false;
export function boot() {
  if (booted) return;
  booted = true;
  refresh();
  listen();
  poll();
  whenBarFontsLoad(() => state.fontsVersion++);
  // The mockup's clocks tick and entity values in the top bar follow Home Assistant while the page is open.
  setInterval(() => {
    if (!state.layout || document.hidden || state.drag.active) return;
    state.now = Date.now();
    loadTopbarPreview(0);
  }, 30000);
  // The mockup follows Home Assistant while it is on screen; a running update reports its stage every few seconds.
  setInterval(() => {
    if (!document.hidden && state.layout && state.tab === "layout" && route.value === "") loadStates();
  }, 8000);
  setInterval(() => {
    if (!document.hidden && anyUpdating()) loadFirmwareJob();
    else if (state.firmwareJob && !anyUpdating()) state.firmwareJob = null;
  }, 3000);
  document.addEventListener("visibilitychange", async () => {
    if (document.hidden) return;
    lastFull = Date.now();
    state.now = Date.now();
    await refresh();
    poll();
  });
  // A change still waiting for its short pause goes out when the page closes.
  window.addEventListener("pagehide", () => flushSettings(true));
  window.addEventListener("beforeunload", (e) => {
    if (state.dirty) { e.preventDefault(); e.returnValue = ""; }
  });
}
