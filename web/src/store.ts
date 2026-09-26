// One reactive state for the whole editor. The Python API (server.py) is unchanged: this file is the
// former app.js state and its calls, with the DOM work moved into the components.
import { computed, reactive, toRaw, watch } from "vue";
import { api, getJson, send, setCsrf } from "./api";
import { andList, editorLanguage, languageMeta, loadLanguage, type NumberMarks, pickLanguage, STYLE_MARKS, t } from "./i18n";
import { entriesOf, effectiveControls, isFull, isWide, newTile, pageOrder, pagePlaces, pageTarget, reorderTitles, retargetedPage, sizeOf, supportsFirmware as supportsVersion } from "./model/layout";
import { agoText, barMetricsFor, clockText, dateText, itemKey, type ItemView, whenBarFontsLoad } from "./model/topbar";
import { createLayout, dimensions, type Size, versionAtLeast } from "./model/layout";
import type { Capability, FeedbackView, ChangelogSection, EntityAction, HeaderItem, Inventory, Layout, Screen, Tile, PageLayout, PageDocument, PageGrid, PageWorkspace } from "./types";

import * as pages from "./model/pages";
import { DraftHistory, type HistoryScope } from './model/draft-history';
import { suggestedPageTitle } from './model/page-naming';
import { validateCardOptions } from './model/page-validation';
import { completePositions, workspaceSaver } from './model/page-workspace';
import { resolveConflict, savedDraft } from './model/page-conflict';

export type Inspector =
  | { kind: "tile" }
  | { kind: "bar"; index: number }
  | { kind: "bar-add" }
  | { kind: "page"; id: string }
  | { kind: "inspect"; entity?: string };
// A whole page on its way to another place in the row (app 0.2.121): where it came from, where it is heading, and
// the row as it stands while it is in the air (`order[position]` is the page drawn there).
export type PageDrag = { from: number; to: number; order: number[] };
export type DragState = { active: boolean; moving: Tile | null; preview: { tile: Tile; slot: number }[] | null; page: PageDrag | null };
// What Home Assistant reports for an entity right now: the state, its word and the attributes a card shows.
export type Live = { state: string; word?: string | null; a: Record<string, any> };

export const state = reactive({
  inventory: { screens: [], entities: [] } as Inventory,
  connected: false,
  reachable: true,
  selected: null as string | null,
  document: null as PageLayout | null,
  gridReview: null as { record: PageDocument; layout: PageLayout; target: PageGrid; copy: boolean; message: string } | null,
  documentRevision: null as string | null,
  documentGrid: null as PageGrid | null,
  workspace: { revision: "", positions: {} } as PageWorkspace,
  workspaceDirty: false,
  editorMode: "simple" as "simple" | "advanced",
  focusedPageId: null as string | null,
  connectingTileId: null as string | null,
  selectedPageId: null as string | null,
  conflict: false,
  undoCount: 0,
  redoCount: 0,
  get layout(): Layout | null { return renderedLayout.value; },
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
  // Per entity, the values its second line may say: Home Assistant's own named attributes (app 0.2.105).
  subtitleValues: {} as Record<string, { key: string; name: string }[] | undefined>,
  // Index projection for older view helpers; selection itself is always an ID.
  get barPage(): number { return Math.max(0, state.document?.pages.findIndex(page => page.id === state.selectedPageId) ?? 0); },
  topbarPreviews: {} as Record<string, any>,
  topbarAdded: null as null | { key: string; time: number },
  topbarOverflow: [] as number[],
  settingEdits: {} as Record<string, { value: any; at: number }>,
  settingPending: false,
  updating: [] as string[],
  // The screen whose removal is running, so its button waits instead of being pressed twice (app 0.2.112).
  removing: null as string | null,
  toast: null as null | { message: string; action?: { label: string; run: () => void } },
  now: Date.now(),
  fontsVersion: 0,
  route: location.hash,
  overrideProfile: null as string | null,
  overrideFriendly: "",
  drag: { active: false, moving: null, preview: null, page: null } as DragState,
  menuOpen: false,
  liveStates: {} as Record<string, Live>,
  room: "",
  hidePlaced: false,
  palette: false,
  firmwareJob: null as null | { job: any; logs: string[] },
});

// This is a cached render projection of the one canonical draft. Mutations go
// through document operations below, never through this flattened view.
const renderedLayout = computed<Layout | null>(() => state.document && state.documentGrid
  ? pages.projectLayout(state.document, state.documentGrid) : null);

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
// Whether the screen's board draws pictures (camera tiles, an album cover): the add-on says so per screen from the
// board's own camera sizes (app 0.2.94), and this page always comes with that add-on.
export const pictures = computed(() => Boolean(currentScreen.value?.pictures));
// What the screen being edited looks like. The manager works it out (core.shape_of): what the screen reported
// itself, else the board package its YAML builds from, else its board. The editor only draws it, and falls
// back to the smallest screen there is while it has heard nothing at all.
const SMALLEST = { width: 320, height: 240, columns: 2, rows: 3, dpi: 143, look: "compact" };
export const screenShape = computed(() => {
  const shape = currentScreen.value?.shape;
  return shape && shape.columns > 0 && shape.rows > 0 ? shape : SMALLEST;
});
// The top bar of the mockup at the screen's own width and density (topbar.ts).
export const barMetrics = computed(() => barMetricsFor(screenShape.value));
// The tile grid of a page, as CSS variables: the mockup is the screen's own shape, whatever board it is.
// Every mockup has the same shorter side (MOCKUP_SIDE), so a screen keeps its size against its neighbours: a
// 800 x 480 page lying down is wider than a square 480 x 480 one, and the same glass standing up is taller, not
// narrower. Drawn the same height instead, a 480 x 800 screen came out 180 px wide, smaller than the 480 x 480
// Guition though it has more glass. Very wide glass is capped so it still fits beside a neighbour on a laptop.
const MOCKUP_SIDE = 300;
export const deviceStyle = computed(() => {
  const shape = screenShape.value;
  // To a tenth of a pixel, not a whole one: on a 1280 x 800 screen the nearest whole pixel of width would make
  // the mockup a pixel taller than the rest. Every board lying down lands on a whole number anyway.
  const width = shape.width >= shape.height ? Math.min(560, (MOCKUP_SIDE * shape.width) / shape.height) : MOCKUP_SIDE;
  const rounded = Math.round(width * 10) / 10;
  return {
    "--screen-aspect": `${shape.width} / ${shape.height}`,
    "--screen-columns": String(state.documentGrid?.columns ?? shape.columns),
    "--screen-rows": String(state.documentGrid?.rows ?? shape.rows),
    // A wide tile is two cells, or the only one on a single-column screen (layout.ts: spanOf).
    "--screen-wide-span": String(Math.min(2, state.documentGrid?.columns ?? shape.columns)),
    "--mockup-width": `${rounded}px`,
  };
});
// The compact look: the board declares it (LOOK in its board file, served with the shape); a shape from an add-on
// that does not say it is taken by its shorter side, the CYD being the only compact board there was. The shorter
// side and not the width, because a screen keeps its look when it is built standing up: a 480 x 800 Waveshare is
// still the standard look, and on its width alone it would have read as a CYD.
export const isCompact = computed(() =>
  screenShape.value.look ? screenShape.value.look === "compact" : Math.min(screenShape.value.width, screenShape.value.height) < 300);
export const editorLayout = createLayout(() => state.documentGrid ?? screenShape.value);
export const grid = editorLayout.grid;
const { arrange, cellsOf, firstFree, fits, nearestFree, normalize, occupied, pageCount, pageOf, reorderPages, rowStart, startOf, strandedPages, tileLimit: limitFor } = editorLayout;
export const currentTile = computed<Tile | undefined>(() => state.selectedTile?.id
  ? state.layout?.tiles.find((tile) => tile.id === state.selectedTile!.id) : undefined);
export const isSelected = (tile: Tile) => Boolean(tile.id) && state.selectedTile?.id === tile.id;
const currentView = (tile: Tile, layout = state.layout) => tile.id ? layout?.tiles.find((item) => item.id === tile.id) : tile;
export const pageReady = computed(() => currentScreen.value?.page_capability === "ready" ||
  (currentScreen.value?.page_capability === "offline" && currentScreen.value?.page_last_capability === "ready"));
export const pageAt = (index: number) => state.document?.pages[state.drag.page?.order[index] ?? index];

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
// What was copied, each with its own sentences so every language can say it its own way.
export type Copied = "api_key" | "layout_json" | "action_name" | "yaml" | "icon_name" | "empty_color" | "color_name" | "screen_name";
export async function copyText(text: string, element?: Element | null, what: Copied = "api_key") {
  try {
    if (!navigator.clipboard || !window.isSecureContext) throw new Error();
    await navigator.clipboard.writeText(text);
    toast(t(`editor.copy.${what}.copied`));
  } catch {
    // Home Assistant over plain http is no secure context, so the Clipboard API is missing there. The old way copies
    // what is selected: the text on the page when there is one, else a hidden textarea holding it. Without anything
    // selected, execCommand still says it copied, and the clipboard stays empty (GitHub #33).
    let spare: HTMLTextAreaElement | null = null;
    const focused = document.activeElement as HTMLElement | null;
    const selection = window.getSelection();
    if (element) {
      const range = document.createRange();
      range.selectNodeContents(element);
      selection?.removeAllRanges();
      selection?.addRange(range);
    } else {
      spare = document.createElement("textarea");
      spare.value = text;
      spare.setAttribute("readonly", "");
      spare.style.cssText = "position: fixed; top: 0; left: 0; width: 1px; height: 1px; opacity: 0";
      document.body.appendChild(spare);
      spare.focus();
      spare.select();
    }
    let copied = false;
    try {
      copied = document.execCommand("copy");
    } catch {
      copied = false;
    }
    if (spare) {
      spare.remove();
      selection?.removeAllRanges();
      focused?.focus?.();
      // Nothing on the page to leave selected: a prompt shows the text selected, which is what "selected" promises.
      if (!copied) {
        window.prompt(t(`editor.copy.${what}.selected`), text);
        return;
      }
    }
    toast(t(copied ? `editor.copy.${what}.copied` : `editor.copy.${what}.selected`));
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
// The values one entity's second line may say (app 0.2.105). The list is Home Assistant's own - the attributes its
// frontend translations name - so nothing here is a list we keep, and an entity it names none of answers empty.
const askedSubtitles = new Set<string>();
export async function loadSubtitleValues(entity: string) {
  if (askedSubtitles.has(entity)) return;
  askedSubtitles.add(entity);
  try {
    state.subtitleValues[entity] = (await getJson(`entity-subtitle?entity=${encodeURIComponent(entity)}`)).values ?? [];
  } catch {
    askedSubtitles.delete(entity);
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
  const selection = selectionEpoch;
  const entities = [...new Set((state.layout?.tiles || []).map((t) => t.entity).filter((id) => !id.startsWith("screen.")))];
  if (!entities.length || statesFlight) return;
  statesFlight = true;
  try {
    for (let i = 0; i < entities.length; i += 60) {
      const query = entities.slice(i, i + 60).map((id) => `entity=${encodeURIComponent(id)}`).join("&");
      const values = await getJson(`states?${query}`);
      if (selection !== selectionEpoch) return;
      Object.assign(state.liveStates, values.states || {});
    }
  } catch {
    // The next tick tries again; the mockup keeps the last values.
  } finally {
    statesFlight = false;
  }
}
export async function loadLibraryStates(ids: string[]) {
  const selection = selectionEpoch;
  const entities = [...new Set(ids.filter((id) => !id.startsWith('screen.')))].slice(0, 80);
  try {
    for (let i = 0; i < entities.length; i += 60) {
      const values = await getJson(`states?${entities.slice(i, i + 60).map((id) => `entity=${encodeURIComponent(id)}`).join('&')}`);
      if (selection !== selectionEpoch) return;
      Object.assign(state.liveStates, values.states || {});
    }
  } catch { /* Inventory state remains visible until the next refresh. */ }
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
let committedLayout: PageLayout | null = null;
let committedGrid: PageGrid | null = null;
let selectionEpoch = 0;
export function markDirty() {
  state.dirty = JSON.stringify(state.document) !== JSON.stringify(committedLayout) || JSON.stringify(state.documentGrid) !== JSON.stringify(committedGrid);
  state.saved = 0;
  edits++;
}
type DraftSnapshot = { layout: PageLayout; grid: PageGrid; positions: PageWorkspace["positions"]; page: string | null; tile: string | null };
const draftHistory = new DraftHistory<DraftSnapshot>();
const snapshot = (): DraftSnapshot => ({ layout: pages.clone(state.document!), grid: pages.clone(state.documentGrid!), positions: pages.clone(state.workspace.positions),
  page: state.selectedPageId, tile: state.selectedTile?.id || null });
function historyCounts() {
  // A removal toast only belongs to the latest history entry. Once another
  // edit, map move, undo or screen selection changes history, retire it.
  if (state.toast?.action?.run === undo) dismissToast();
  const counts = draftHistory.counts(state.editorMode === 'advanced');
  state.undoCount = counts.undo; state.redoCount = counts.redo;
}
function applyDocument(next: PageLayout, remember = true, nextGrid = state.documentGrid) {
  if (!state.document || !state.documentGrid) return false;
  if (!nextGrid) return false;
  pages.validatePages(next, nextGrid);
  if (JSON.stringify(next) === JSON.stringify(state.document) && pages.sameGrid(nextGrid, state.documentGrid)) return false;
  if (remember) {
    draftHistory.remember(snapshot());
    historyCounts();
  }
  state.documentGrid = pages.clone(nextGrid);
  state.document = next;
  const ids = new Set(next.pages.map((page) => page.id));
  const positions = Object.fromEntries(Object.entries(state.workspace.positions).filter(([id]) => ids.has(id)));
  if (Object.keys(positions).length !== Object.keys(state.workspace.positions).length) {
    state.workspace.positions = positions; state.workspaceDirty = true;
  }
  if (state.editorMode === "advanced" || Object.keys(positions).length) initializeWorkspace();
  if (state.selectedPageId && !ids.has(state.selectedPageId)) state.selectedPageId = next.homePageId;
  if (state.focusedPageId && !ids.has(state.focusedPageId)) state.focusedPageId = null;
  if (state.selectedTile?.id && !next.pages.some((page) => page.tiles.some((tile) => tile.id === state.selectedTile!.id))) closeInspector();
  markDirty();
  loadTopbarPreview();
  return true;
}
let focusedField: string | null = null, groupedEdit = -1;
export function beginFieldEdit(key: string) { focusedField = key; groupedEdit = -1; }
export function endFieldEdit() { focusedField = null; groupedEdit = -1; }
export function editDocument(apply: (draft: PageLayout) => void, field?: string) {
  if (!state.document || !state.documentGrid) return false;
  try {
    const grouped = field !== undefined && focusedField === field;
    const changed = applyDocument(pages.changePages(state.document, state.documentGrid, apply), !(grouped && groupedEdit === edits));
    if (changed) groupedEdit = grouped ? edits : -1;
    return changed;
  }
  catch (error: any) { toast(error.message); return false; }
}
function restoreSnapshot(value: DraftSnapshot, scope: HistoryScope) {
  endFieldEdit();
  if (scope === 'document') {
    const positions = pages.clone(state.workspace.positions);
    applyDocument(value.layout, false, value.grid);
    // Keep current positions; recover a deleted page's position from its snapshot.
    state.workspace.positions = Object.fromEntries(value.layout.pages.flatMap((page) => {
      const point = positions[page.id] || value.positions[page.id];
      return point ? [[page.id, point]] : [];
    }));
    state.selectedPageId = value.page;
    state.selectedTile = state.layout?.tiles.find((tile) => tile.id === value.tile) || null;
  } else {
    const ids = new Set(state.document!.pages.map((page) => page.id));
    state.workspace.positions = Object.fromEntries(Object.entries(value.positions).filter(([id]) => ids.has(id)));
  }
  if (state.editorMode === 'advanced') initializeWorkspace();
  state.workspaceDirty = true;
  historyCounts();
  scheduleWorkspaceSave();
}
function historyStep(direction: 'undo' | 'redo') {
  if (!state.document || !state.documentGrid) return;
  const entry = draftHistory.step(direction, snapshot(), state.editorMode === 'advanced');
  if (entry) restoreSnapshot(entry.value, entry.scope);
}
export function undo() { historyStep('undo'); }
export function redo() { historyStep('redo'); }
function readMode(id: string): "simple" | "advanced" {
  try { return localStorage.getItem(`esp-screens-mode:${id}`) === "advanced" ? "advanced" : "simple"; } catch { return "simple"; }
}
export function setEditorMode(mode: "simple" | "advanced") {
  state.editorMode = mode;
  historyCounts();
  state.focusedPageId = null;
  state.connectingTileId = null;
  state.drag.active = false; state.drag.preview = null; state.drag.page = null; state.drag.moving = null;
  if (mode === "advanced") initializeWorkspace();
  try { if (state.selected) localStorage.setItem(`esp-screens-mode:${state.selected}`, mode); } catch {}
}
function loadDocument(screen: Screen) {
  endFieldEdit();
  selectionEpoch++;
  const record = screen.page_document;
  state.document = record?.format === "legacy-v1" ? null : record?.format === "pages-v2"
    ? pages.clone(record.layout) : pages.emptyLayout(screen.layout.title || screen.name);
  state.documentGrid = record?.format === "pages-v2" ? pages.clone(record.sourceGrid)
    : screen.source_grid ? pages.clone(screen.source_grid) : null;
  committedLayout = pages.clone(state.document);
  committedGrid = pages.clone(state.documentGrid);
  state.gridReview = null;
  state.documentRevision = record?.format === "pages-v2" ? record.revision : null;
  state.workspace = record?.format === "pages-v2" && record.workspace ? pages.clone(record.workspace) : { revision: "", positions: {} };
  state.workspaceDirty = false;
  state.selectedPageId = state.document?.homePageId || null;
  state.focusedPageId = null;
  state.conflict = false;
  draftHistory.clear(); historyCounts();
}
export function select(id: string | null) {
  if (id === state.selected && state.document && state.dirty) {
    state.tab = "layout"; state.menuOpen = false; closeInspector(); go(""); return;
  }
  if (id !== state.selected && state.dirty && !confirm(t("editor.screen_view.confirm.switch"))) return;
  if (id !== state.selected) { flushSettings(); state.settingEdits = {}; }
  state.selected = id; state.selectedTile = null; state.inspector = null;
  state.tab = "layout"; state.menuOpen = false;
  const screen = state.inventory.screens.find((item) => item.id === id);
  if (!screen) { state.document = null; state.documentGrid = null; return; }
  loadDocument(screen);
  state.editorMode = readMode(screen.id);
  if (state.editorMode === "advanced") initializeWorkspace();
  state.insertAt = -1; state.dirty = false; state.saved = 0;
  loadTopbarPreview(0);
  loadCapabilities(state.layout?.tiles.map((tile) => tile.entity) || []);
  loadStates(); go("");
}
export const liveEntries = () => (state.layout ? entriesOf(state.layout) : []);
// Apply an arrangement; a new tile joins the layout. True when anything changed.
export function commitArrangement(result: { tile: Tile; slot: number }[]) {
  if (!state.document || !state.documentGrid) return false;
  try {
    // Adding a numbered destination from the library explicitly creates that
    // page, in the same undo operation as its navigation tile.
    const draft = pages.clone(state.document);
    const count = Math.max(draft.pages.length, ...result.filter(({ tile }) => !tile.id).map(({ tile }) => pageTarget(tile.entity)));
    if (count > pages.pageLimit(state.documentGrid)) throw new Error(t("addon.errors.pages.pages_full"));
    while (draft.pages.length < count) draft.pages.push(pages.emptyPage(draft.pages.at(-1)!.topbar));
    const arranged = pages.arrangeTiles(draft, state.documentGrid, result);
    const existing = new Set(state.document.pages.map(page => page.id));
    for (const page of arranged.pages) if (!existing.has(page.id)) {
      const title = suggestedPageTitle(page, state.inventory.entities);
      page.topbar.title = title ? { source: 'text', text: title } : { source: 'screen' };
    }
    return applyDocument(arranged);
  }
  catch (error: any) { toast(error.message); return false; }
}
export function placeTile(tile: Tile, target: number) {
  if (!state.layout) return false;
  loadCapabilities([tile.entity]);
  const result = arrange(state.layout.tiles, currentView(tile) || tile, target);
  const placed = result ? commitArrangement(result) : false;
  if (placed && !state.liveStates[tile.entity]) loadStates();
  return placed;
}
// A click in the picker: the marked empty cell, else the selected page's first
// free cell. Never silently spill a library click onto another page.
export function addTile(id: string) {
  const layout = state.layout;
  if (!layout || (!repeatable(id) && layout.tiles.some((t) => t.entity === id)) || layout.tiles.length >= tileLimit.value) return;
  const tile = newTile(id);
  const page = Math.max(0, state.document!.pages.findIndex((page) => page.id === state.selectedPageId));
  const target = state.insertAt >= 0 ? state.insertAt : firstFree(occupied(entriesOf(layout)), sizeOf(tile), page * grid.slots);
  const slot = state.insertAt >= 0 || target < (page + 1) * grid.slots ? target : -1;
  state.insertAt = -1;
  if (slot < 0) return toast(t('editor.pages.selected_full'));
  if (slot >= 0 && placeTile(tile, slot)) {
    const added = state.layout!.tiles.find((item) => item.entity === id && item.slot === slot);
    if (added) openTile(added);
  }
}
export function removeTile(tile: Tile) {
  if (!tile.id) return;
  if (editDocument((draft) => { for (const page of draft.pages) page.tiles = page.tiles.filter((item) => item.id !== tile.id); }))
    toast(t("editor.layout.removed", { name: tile.name || entityName(tile.entity) }), { label: t("editor.common.undo"), run: undo });
}
export function addPage(bar?: PageLayout["pages"][number]["topbar"]) {
  let created = '';
  if (editDocument((draft) => {
    const selected = draft.pages.find((page) => page.id === state.selectedPageId) || draft.pages.at(-1)!;
    const page = pages.emptyPage(bar || selected.topbar); created = page.id; draft.pages.push(page);
  })) { state.selectedPageId = created; return true; }
  return false;
}
export function movePage(from: number, to: number) {
  if (!state.document || !state.documentGrid || from === to || !Number.isInteger(from) || !Number.isInteger(to) ||
      from < 0 || to < 0 || from >= state.document.pages.length || to >= state.document.pages.length) return false;
  try { return applyDocument(pages.reorderPage(state.document, state.documentGrid, state.document.pages[from]?.id, to)); }
  catch (error: any) { toast(error.message); return false; }
}
export function removePage(page: number) {
  if (!state.document || !state.documentGrid || !state.document.pages[page] || state.document.pages.length === 1) return;
  const id = state.document.pages[page].id;
  try {
    const next = pages.deletePage(state.document, state.documentGrid, id);
    const removed = state.layout!.tiles.length - pages.projectLayout(next, state.documentGrid).tiles.length;
    if (applyDocument(next)) toast(removed ? t("editor.layout.page_removed_tiles", { page: page + 1 }, removed)
      : t("editor.layout.page_removed", { page: page + 1 }), { label: t("editor.common.undo"), run: undo });
  } catch (error: any) { toast(error.message); }
}
export function setHomePage(id: string) { return editDocument((draft) => { draft.homePageId = id; }); }
export function openPage(id: string) {
  state.selectedPageId = id; state.selectedTile = null;
  state.inspector = { kind: "page", id };
}
export function connectTile(tileId: string, target: string | "home") {
  return editDocument((draft) => {
    const tile = draft.pages.flatMap((page) => page.tiles).find((item) => item.id === tileId);
    if (tile?.content.kind !== "navigation") throw new Error(t("addon.errors.pages.select_link"));
    tile.content.target = target === "home" ? { kind: "home" } : { kind: "page", pageId: target };
  });
}
export function setPageExcluded(id: string, excluded: boolean) {
  return editDocument((draft) => { const page = draft.pages.find((item) => item.id === id); if (page) page.navigation.excludeFromPagination = excluded; });
}
export function duplicateEditorPage(id: string, empty: boolean) {
  if (!state.document || !state.documentGrid) return false;
  try { return applyDocument(pages.duplicatePage(state.document, state.documentGrid, id, empty)); }
  catch (error: any) { toast(error.message); return false; }
}
export function setPageHomeControl(id: string, visible: boolean) {
  return editDocument((draft) => { const page = draft.pages.find((item) => item.id === id); if (page)
    page.topbar.leading = visible ? page.topbar.leading.length ? page.topbar.leading : [{ id: pages.instanceId(), kind: "home" }] : []; });
}
export function moveWorkspacePage(id: string, x: number, y: number) {
  endFieldEdit();
  if (!state.document?.pages.some((page) => page.id === id)) return;
  const positions = workspacePositions();
  if (![x, y].every(Number.isInteger) || x < 0 || y < 0 || x > 100 || y > 100) return;
  if (Object.entries(positions).some(([key, point]) => key !== id && point.x === x && point.y === y)) {
    toast(t("editor.pages.position_occupied")); return;
  }
  if (positions[id]?.x === x && positions[id]?.y === y) return;
  draftHistory.remember(snapshot(), 'workspace'); historyCounts();
  state.workspace.positions = { ...positions, [id]: { x, y } };
  state.workspaceDirty = true; scheduleWorkspaceSave();
}
export function workspacePositions() {
  return completePositions(state.document, state.workspace.positions);
}
function initializeWorkspace() {
  const positions = workspacePositions();
  if (JSON.stringify(positions) === JSON.stringify(state.workspace.positions)) return;
  state.workspace.positions = positions;
  state.workspaceDirty = true;
  scheduleWorkspaceSave();
}
export function arrangeFromHome() {
  if (!state.document) return;
  draftHistory.remember(snapshot(), 'workspace'); historyCounts();
  state.workspace.positions = pages.initialPositions(state.document);
  state.workspaceDirty = true; scheduleWorkspaceSave();
}
// Moving a tile without dragging it (app 0.2.78), for a finger on a phone and for anyone who can't drag: the first
// free cell of that page, else its first cell, where the tile in the way swaps places as it does for a drop or an
// arrow key. `page` counts from 0; the page after the last one starts a new page.
export function moveTileToPage(tile: Tile, page: number) {
  const layout = state.layout;
  tile = currentView(tile) || tile;
  if (!layout || !Number.isInteger(page) || page < 0 || page >= grid.pages || page === pageOf(tile.slot)) return false;
  const slot = firstFree(occupied(entriesOf(layout).filter((e) => e.tile !== tile)), sizeOf(tile), page * grid.slots);
  const moved = placeTile(tile, slot >= 0 && pageOf(slot) === page ? slot : page * grid.slots);
  if (!moved) toast(t("editor.layout.no_room", { page: page + 1 }));
  return moved;
}
export function pagesShown() {
  const layout = state.layout;
  if (!layout) return 1;
  const entries = state.drag.preview || entriesOf(layout);
  const pages = pageCount(entries, layout.pages);
  // While a tile is being dragged, one more page waits after the last one. A page on the move is looking for a place
  // in the row it is already in, so the row stays as long as it is.
  return state.drag.active && !state.drag.page && pages < grid.pages ? pages + 1 : pages;
}
/** UI experiments are opt-in; saved documents and device support stay independent. */
export const tallerTilesEnabled = computed(() => state.inventory.editor_features?.tall_tiles === true);
export function tileSizeChoices(tile: Tile): Size[] {
  const choices: Size[] = ['single', 'wide'];
  if (tallerTilesEnabled.value) for (const size of ['tall', 'square'] as const) {
    if (!currentScreen.value?.tile_sizes?.includes(size) || grid.rows < 2 || (size === 'square' && grid.columns < 2)) continue;
    if (size === 'tall' && ['forecast', 'sunpath'].includes(String(tile.options?.display))) continue;
    choices.push(size);
  }
  if (!pageTarget(tile.entity)) choices.push('full');
  return choices;
}
/** Edge resizing keeps the anchor and every neighbouring tile in place. */
export function resizeChoices(tile: Tile, axis: 'columns' | 'rows'): Size[] {
  const current = currentView(tile);
  if (!current || !state.layout || isFull(current) || (axis === 'rows' && !tallerTilesEnabled.value)) return [];
  const before = dimensions(sizeOf(current), grid), other = axis === 'columns' ? 'rows' : 'columns';
  const taken = occupied(entriesOf(state.layout).filter(entry => entry.tile.id !== current.id));
  const owned = state.document?.pages.flatMap(page => page.tiles).find(item => item.id === current.id);
  return tileSizeChoices(current).filter(size => {
    if (!owned || size === 'full' || dimensions(size, grid)[other] !== before[other] || !fits(taken, current.slot, size)) return false;
    try { validateCardOptions(owned, current.entity, size); return true; }
    catch { return false; }
  });
}
export function resizeTile(tile: Tile, size: Size, axis: 'columns' | 'rows') {
  const current = currentView(tile);
  if (!current || size === sizeOf(current) || !resizeChoices(current, axis).includes(size)) return false;
  return editDocument(draft => {
    const owned = draft.pages.flatMap(page => page.tiles).find(item => item.id === current.id)!;
    // Gaining height exposes choices, it never opts into a default control.
    if (owned.placement.rows === 1 && dimensions(size, grid).rows > 1 && owned.interaction.controls === undefined)
      owned.interaction.controls = effectiveControls(current, state.inventory) || 'none';
    Object.assign(owned.placement, dimensions(size, grid));
    if (size === 'single') delete owned.appearance.presentation;
    else owned.appearance.presentation = size;
  });
}
// Inspector resizing may find the nearest fitting rectangle. Edge handles above
// keep the anchor fixed so that dragging an edge never moves the tile.
export function setTileOption(tile: Tile, key: string, value: unknown) {
  if (!state.layout) return;
  const layout = pages.clone(state.layout);
  tile = currentView(tile, layout) || tile;
  const domain = tile.entity.split(".")[0], caps = state.capabilities[tile.entity], wasSize = sizeOf(tile);
  if (key === "size" && ["tall", "square"].includes(String(value)) && (!tallerTilesEnabled.value || !currentScreen.value?.tile_sizes?.includes(String(value)))) return;
  if (key === "size" && value === "tall" && ["forecast", "sunpath"].includes(String(tile.options?.display))) return;
  const previousControls = effectiveControls(tile, state.inventory);
  tile.options = { ...tile.options, [key]: value };
  if (key === 'size' && ['tall', 'square'].includes(String(value)) && dimensions(wasSize, grid).rows === 1 && !('controls' in tile.options))
    tile.options.controls = previousControls || 'none';
  // Direct controls need the standard layout without a mini slider, and vice versa.
  if (key === "display" && value === "watch") { tile.options.inline = "none"; if (state.inventory.controls?.[domain]) tile.options.controls = "none"; }
  if (key === "display" && ["forecast", "sunpath"].includes(value as string) && !isWide(tile)) tile.options.size = "wide";
  // A live picture's own settings leave with it, and a default is not stored (the add-on's canonical form, app 0.3.8).
  if (key === "display" && value !== "live") for (const own of ["refresh", "fit", "overlay"]) delete tile.options[own];
  if ((key === "fit" && value === "fill") || (key === "overlay" && value === "name")) delete tile.options[key];
  if (key === "inline" && value === "slider") { tile.options.display = "standard"; if (state.inventory.controls?.[domain]) tile.options.controls = "none"; }
  if (key === "controls" && value === "none" && ["tall", "square"].includes(sizeOf(tile))) tile.options.inline = "none";
  if (key === "controls" && value !== "none") { if (tile.options.display !== "cover") tile.options.display = "standard"; tile.options.inline = "none"; }
  // A card that becomes wide gets the first direct control Home Assistant offers when the usual one isn't there.
  const catalogue = state.inventory.controls?.[domain];
  if (key === "size" && ["wide", "square"].includes(String(value)) && caps && catalogue && !("controls" in tile.options) && !caps.controls.includes(catalogue.default))
    tile.options.controls = catalogue.choices.find((c) => c.key !== "none" && caps.controls.includes(c.key))?.key || "none";
  // A card that grows to the whole page keeps its page: the other tiles there move to the first free
  // cells after it. With no room for them it takes the first empty page, or stays as it was.
  if (isFull(tile) && wasSize !== "full") {
    const page = pageOf(tile.slot), others = layout.tiles.filter((t) => t !== tile && pageOf(t.slot) === page);
    const taken = occupied(entriesOf(layout).filter((e) => e.tile !== tile && !others.includes(e.tile)));
    const moved: [Tile, number][] = [];
    for (const other of others) {
      const slot = firstFree(taken, sizeOf(other), (page + 1) * grid.slots);
      if (slot < 0) { moved.length = 0; break; }
      moved.push([other, slot]);
      for (const c of cellsOf(slot, sizeOf(other))) taken.add(c);
    }
    if (moved.length === others.length) { for (const [other, slot] of moved) other.slot = slot; tile.slot = page * grid.slots; }
    else {
      const slot = firstFree(occupied(entriesOf(layout).filter((e) => e.tile !== tile)), "full");
      if (slot >= 0) tile.slot = slot;
      else { tile.options.size = wasSize; toast(t("editor.layout.no_free_page")); }
    }
  } else if (sizeOf(tile) !== wasSize) {
    const size = sizeOf(tile), taken = occupied(entriesOf(layout).filter((e) => e.tile !== tile)), own = startOf(tile.slot, size);
    const slot = fits(taken, own, size) ? own : nearestFree(taken, size, own);
    if (slot >= 0) tile.slot = slot;
    else { tile.options.size = wasSize; toast(t("editor.layout.no_room", { page: pageOf(tile.slot) + 1 })); return; }
  }
  normalize(layout);
  commitArrangement(layout.tiles.map((item) => ({ tile: item, slot: item.slot })));
}
// A navigation tile goes to another page: its entity changes (screen.page_<n>). One tile per page it goes to, unless
// the firmware takes several (0.2.65). The page after the last one becomes a new, empty page to fill (app 0.2.78).
export function retargetPageTile(tile: Tile, page: number) {
  if (!tile.id || !Number.isInteger(page) || page < 1 || page > grid.pages) return false;
  if (!pageTilesRepeat.value && state.layout?.tiles.some((other) => other.id !== tile.id && pageTarget(other.entity) === page)) {
    toast(t("editor.layout.page_taken", { page })); return false;
  }
  return editDocument((draft) => {
    while (draft.pages.length < page) draft.pages.push(pages.emptyPage(draft.pages.at(-1)!.topbar));
    const source = draft.pages.flatMap((item) => item.tiles).find((item) => item.id === tile.id);
    if (!source || source.content.kind !== "navigation") throw new Error(t("addon.errors.pages.tile_missing"));
    source.content.target = { kind: "page", pageId: draft.pages[page - 1].id };
  });
}
export function setTileName(tile: Tile, value: string) {
  editDocument((draft) => { const found = draft.pages.flatMap((page) => page.tiles).find((item) => item.id === tile.id); if (found) found.appearance.label = value; }, `tile:${tile.id}`);
}

// ---- Inspector (the drawer) ----
export function openTile(tile: Tile) {
  if (!isSelected(tile)) { state.iconPickerOpen = false; state.actionPickerOpen = false; state.actionSearch = ""; }
  state.selectedTile = tile;
  state.selectedPageId = state.document?.pages.find((page) => page.tiles.some((item) => item.id === tile.id))?.id || state.selectedPageId;
  state.inspector = { kind: "tile" };
  loadCapabilities([tile.entity]);
}
// The screen's own title: what the top bar says on every page that has no title of its own, and what the editor
// asks for first. Nothing is named after it - a screen's actions and sensors carry its device name - so renaming
// it breaks no automation.
export const screenTitle = () => state.layout?.title ?? "";
export function setScreenTitle(value: string) {
  if (!state.layout) return;
  editDocument((draft) => { draft.title = value; }, 'screen-title');
}
// The title of one page (app 0.2.105), the one thing the top bar's inspector asks per page. A title belongs to the
// page and travels with it, page 1 included (app 0.2.123), so reordering the row never costs a name. Stored as one
// entry per page, empty meaning the screen's own title, trailing empty ones dropped, so a screen where nobody set
// one carries nothing.
export const pageTitle = (page: number) => state.layout?.page_titles?.[page] ?? "";
// What stands above a position in the row: the title of the page drawn there, which while a page is being moved is
// not the page that started there, and the screen's own title for a page that has none.
export const pageTitleShown = (page: number) => {
  const order = state.drag.page?.order;
  return pageTitle(order ? order[page] ?? page : page) || state.layout?.title || "";
};
export function setPageTitle(page: number, value: string) {
  editDocument((draft) => { if (draft.pages[page]) draft.pages[page].topbar.title = value.trim() ? { source: "text", text: value } : { source: "screen" }; }, `page:${state.document?.pages[page]?.id}`);
}
// `page` is the page whose bar was clicked (app 0.2.105): the inspector changes that page's own title there,
// which is where you look for it after clicking the bar.
export function openBar(index: number, page = state.barPage) {
  if (!(state.inspector?.kind === "bar" && state.inspector.index === index)) state.iconPickerOpen = false;
  state.selectedTile = null;
  state.selectedPageId = state.document?.pages[page]?.id || null;
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
function acceptSave(record: PageDocument, submitted: PageLayout, submittedWorkspace: PageWorkspace | undefined, sent: number) {
  state.documentRevision = record.revision;
  committedLayout = pages.clone(submitted);
  committedGrid = pages.clone(record.sourceGrid);
  if (record.workspace) {
    state.workspace.revision = record.workspace.revision;
    if (!submittedWorkspace || JSON.stringify(state.workspace.positions) === JSON.stringify(submittedWorkspace.positions)) {
      state.workspace.positions = pages.clone(record.workspace.positions); state.workspaceDirty = false;
    }
  }
  state.dirty = JSON.stringify(state.document) !== JSON.stringify(committedLayout) || JSON.stringify(state.documentGrid) !== JSON.stringify(committedGrid);
  state.conflict = false;
  if (edits === sent) { state.saved = Date.now(); toast(t("editor.screen_view.saved.current")); }
  else toast(t("editor.screen_view.saved.newer_edit"));
}
export async function save() {
  if (state.busy || !state.document || !state.selected || !state.documentGrid) return;
  state.busy = true;
  const sent = edits, screen = state.selected, selection = selectionEpoch, submitted = pages.clone(state.document), submittedGrid = pages.clone(state.documentGrid);
  const workspace = state.workspaceDirty ? pages.clone(state.workspace) : undefined;
  const adaptation = committedGrid && !pages.sameGrid(committedGrid, submittedGrid) ? { from: committedGrid, to: submittedGrid } : undefined;
  const request = { format: "pages-v2", revision: state.documentRevision, layout: submitted, ...(workspace ? { workspace } : {}), ...(adaptation ? { adaptation } : {}) };
  try {
    const result = await send<{ saved: boolean; document: PageDocument }>(`screens/${encodeURIComponent(screen)}`, "PUT", request);
    if (state.selected === screen && selection === selectionEpoch) acceptSave(result.document, submitted, workspace, sent);
    else toast(t("editor.screen_view.saved.other", { name: state.inventory.screens.find((s) => s.id === screen)?.name || screen }));
    await refresh(false);
  } catch (error: any) {
    // A lost HTTP answer does not prove the save failed. Read the authoritative
    // revision before another attempt; edits made meanwhile remain the draft.
    try {
      const inventory = await getJson<Inventory>("inventory?light=1");
      const record = inventory.screens.find((item) => item.id === screen)?.page_document;
      if (state.selected === screen && selection === selectionEpoch && savedDraft(record, submitted, submittedGrid, workspace)) {
        acceptSave(record, submitted, workspace, sent);
        return;
      }
      if (state.selected === screen && selection === selectionEpoch && record?.format === "pages-v2" && record.revision !== state.documentRevision) state.conflict = true;
    } catch { /* Keep the draft and its expected revision until the server can be reached. */ }
    toast(error.message);
  } finally {
    state.busy = false;
    if (state.workspaceDirty) scheduleWorkspaceSave();
  }
}
const mapSaver = workspaceSaver(state, {
  epoch: () => selectionEpoch, committed: () => committedLayout,
  put: (screen, revision, workspace) => send<PageWorkspace>(`screens/${encodeURIComponent(screen)}/workspace`, 'PUT', { revision, workspace }),
  error: (error: any) => toast(error.message),
});
function scheduleWorkspaceSave() { mapSaver.schedule(); }
export async function saveWorkspace() { await mapSaver.save(); }

// ---- Identify and the test alert (app 0.2.73): a screen's own show_alert action ----
export const canAlert = (screen: Screen | undefined) =>
  Boolean(screen && screen.alert_action && versionAtLeast(firmwareVersion(screen), state.inventory.alerts?.min_firmware || "0.2.31"));
export async function identify(screen: Screen) {
  try {
    await send(`screens/${encodeURIComponent(screen.id)}/identify`, "POST");
    toast(t("editor.screen_view.identified", { name: screen.name }));
  } catch (e: any) {
    toast(e.message);
  }
}
// ---- Calibrate touch (app 0.2.117): the screen's own Calibrate touch button, pressed from here ----
// Only a screen whose panel is one you calibrate has it, and the add-on says so by the button being on its device
// in Home Assistant. It asks first: the screen goes to the crosses and stays there until someone standing in front
// of it has tapped all five, so it is not something to set off by accident from a browser.
export async function calibrateTouch(screen: Screen) {
  if (!confirm(t("editor.screen_settings.actions.calibrate.confirm", { name: screen.name }))) return;
  try {
    await send(`screens/${encodeURIComponent(screen.id)}/calibrate`, "POST");
    toast(t("editor.screen_settings.actions.calibrate.done", { name: screen.name }));
  } catch (e: any) {
    toast(e.message);
  }
}
// ---- Does this screen work as you expect (app 0.3.10) ----
// One request per choice on the feedback card; the add-on keeps the board's key, picks the revision and talks to the
// website. What comes back replaces the screen's feedback view, so the card and Settings agree at once.
export async function feedbackAction(screen: Screen, body: Record<string, unknown>): Promise<boolean> {
  try {
    const result = await send<{ feedback: Partial<FeedbackView> }>(`screens/${encodeURIComponent(screen.id)}/feedback`, "POST", body);
    const live = state.inventory.screens.find((s) => s.id === screen.id) || screen;
    if (live.feedback && result?.feedback) live.feedback = { ...live.feedback, ...result.feedback };
    return true;
  } catch (e: any) {
    toast(e.message);
    return false;
  }
}
// ---- Removing a screen (app 0.2.112): the mirror of New screen ----
// Home Assistant, the ESPHome profile and everything kept here, in one request. The sidebar says what goes
// before it asks; here only what came back is shown.
export async function removeScreen(screen: Screen) {
  if (state.removing) return false;
  state.removing = screen.id;
  try {
    const result = await send<{ name?: string; kept?: string[] }>(`screens/${encodeURIComponent(screen.id)}`, "DELETE");
    const name = result?.name || screen.name;
    // The screen that was open closes without asking about its edits: its layout went with it.
    if (state.selected === screen.id) forgetOpenScreen();
    state.updating = state.updating.filter((id) => id !== screen.id);
    state.inventory.screens = state.inventory.screens.filter((s) => s.id !== screen.id);
    toast(result?.kept?.length
      ? t("editor.sidebar.remove.kept", { name, file: result.kept[0] })
      : t("editor.sidebar.remove.done", { name }));
    await refresh(false);
    return true;
  } catch (e: any) {
    toast(e.message);
    return false;
  } finally {
    state.removing = null;
  }
}
// The open screen, without the questions `select` asks: nothing of it is left to save or to send.
function forgetOpenScreen() {
  clearTimeout(settingTimer);
  settingQueue = {};
  settingTarget = null;
  state.settingEdits = {};
  state.settingPending = false;
  state.dirty = false;
  state.selected = null;
  state.document = null;
  state.documentGrid = null;
  state.gridReview = null;
  state.selectedTile = null;
  state.inspector = null;
  state.menuOpen = false;
}

export async function sendTestAlert(target: string, data: Record<string, unknown>) {
  return (await send("alerts/test", "POST", { screen: target, data })) as { sent: number; failed: number; skipped: number; unusable?: string[] };
}

// ---- Copying and sharing a layout (app 0.2.73) ----
function adopt(record: PageDocument, message: string) {
  if (!state.documentGrid) return;
  if (!pages.sameGrid(record.sourceGrid, state.documentGrid)) return reviewGrid(record, state.documentGrid, true, message);
  try {
    const copied = pages.remapLayout(record.layout, state.documentGrid), idMap = new Map(record.layout.pages.map((page, index) => [page.id, copied.pages[index].id]));
    applyDocument(copied);
    state.workspace.positions = Object.fromEntries(Object.entries(record.workspace?.positions || {}).map(([id, point]) => [idMap.get(id)!, pages.clone(point)]));
    state.workspaceDirty = true;
    closeInspector(); loadCapabilities(state.layout!.tiles.map((tile) => tile.entity)); loadStates();
    toast(message);
  } catch (error: any) { toast(error.message); }
}
export const gridChanged = computed(() => !!state.documentGrid && !!currentScreen.value?.shape &&
  !pages.sameGrid(state.documentGrid, currentScreen.value.shape));
function reviewGrid(record: PageDocument, target: PageGrid, copy: boolean, message = '') {
  try { state.gridReview = { record: pages.clone(record), layout: pages.adaptGrid(record.layout, record.sourceGrid, target),
    target: { columns: target.columns, rows: target.rows }, copy, message }; }
  catch (error: any) { toast(error.message); }
}
export function reviewScreenGrid() {
  if (!state.document || !state.documentGrid || !currentScreen.value?.shape) return;
  reviewGrid({ format: 'pages-v2', layout: state.document, sourceGrid: state.documentGrid, revision: state.documentRevision || '' }, currentScreen.value.shape, false);
}
export function acceptGridReview() {
  const review = state.gridReview;
  if (!review) return;
  state.gridReview = null;
  if (review.copy) adopt({ ...review.record, layout: review.layout, sourceGrid: review.target }, review.message);
  else applyDocument(review.layout, true, review.target);
}
export function copyLayoutFrom(id: string) {
  const other = state.inventory.screens.find((screen) => screen.id === id);
  if (other?.page_document?.format !== "pages-v2") { toast("Connect the source screen to finish its layout migration first."); return; }
  const copy = pages.clone(other.page_document);
  copy.layout.title = state.document?.title || copy.layout.title;
  adopt(copy, t("editor.layout.copied", { name: other.name }));
}
export function layoutJson() {
  if (!state.document || !state.documentGrid) return "";
  return JSON.stringify({ esp_screens_layout: 2, sourceGrid: state.documentGrid, layout: state.document,
    editor: { positions: workspacePositions() } }, null, 2);
}
export function exportLayout() {
  const text = layoutJson();
  if (!text) return;
  const name = `${(currentScreen.value?.name || "screen").toLowerCase().replace(/[^a-z0-9]+/g, "-")}.layout.json`;
  const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
  copyText(text, undefined, "layout_json");
}
export async function importLayout(text: string) {
  let data: any;
  try { data = JSON.parse(text); } catch { toast(t("editor.layout.not_json")); return; }
  if (!state.selected || !state.documentGrid) return;
  const screen = state.selected, selection = selectionEpoch;
  if (data?.esp_screens_layout !== 2 && !confirm(t("addon.errors.pages.import_grid", { columns: state.documentGrid.columns, rows: state.documentGrid.rows }))) return;
  try {
    const record = await send<PageDocument>(`screens/${encodeURIComponent(screen)}/import`, "POST", {
      document: data, sourceGrid: data?.sourceGrid || state.documentGrid,
    });
    if (state.selected === screen && selection === selectionEpoch) adopt(record, t("editor.layout.imported"));
  } catch (error: any) { toast(error.message); }
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
  if (u.phase === "verify") return { percent: 78, text: phaseText("verify") };
  if (u.phase === "settle") return { percent: 92, text: phaseText("settle") };
  if (u.phase === "install" || !u.phase) {
    if (stage === "upload") return { percent: 66, text: t("editor.update.writing") };
    if (stage) return { percent: 40, text: t("editor.update.building") };
    return { percent: 12, text: phaseText("install") };
  }
  return { percent: 12, text: phaseText(u.phase) };
}

// ---- Top bar ----
// Without a stored top bar the screen shows what it always did: the clock of show_clock.
export const topbarItems = (page = state.barPage): HeaderItem[] => pageAt(page)?.topbar.trailing || [];
export const topbarMax = () => state.inventory.header?.max_items || 6;
export function setTopbarItems(items: HeaderItem[], page = state.barPage) {
  if (!state.document || !state.documentGrid || !state.document.pages[page]) return;
  try { applyDocument(pages.setBarItems(state.document, state.documentGrid, state.document.pages[page].id, items, !pageReady.value)); }
  catch (error: any) { toast(error.message); }
}
export function copyPageBars(source: string, targets: string[], whole: boolean) {
  if (!pageReady.value || !state.document || !state.documentGrid || !targets.length) return false;
  try { return applyDocument(pages.replaceBar(state.document, state.documentGrid, source, targets, whole)); }
  catch (error: any) { toast(error.message); return false; }
}
let topbarTimer = 0;
// Entity text as the screen will show it, for the items not previewed yet.
export function loadTopbarPreview(delay = 150) {
  clearTimeout(topbarTimer);
  topbarTimer = window.setTimeout(async () => {
    const screen = state.selected;
    const items = [...new Map((state.document?.pages.flatMap((page) => page.topbar.trailing) || []).map((item) => [itemKey(item), item])).values()];
    const entities = items.filter((item) => item.type === "entity");
    if (!entities.length) return;
    try {
      // Each request stays within the actual six-item header bound.
      for (let at = 0; at < entities.length; at += 6) {
        const batch = entities.slice(at, at + 6), data = await send("header-preview", "POST", { header: { items: batch.map(({ id: _id, ...item }) => item) } });
        if (state.selected !== screen) return;
        const stillUsed = new Set(state.document?.pages.flatMap((page) => page.topbar.trailing.map(itemKey)) || []);
        batch.forEach((item, i) => { if (stillUsed.has(itemKey(item))) state.topbarPreviews[itemKey(item)] = data.items[i]; });
      }
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
  if (item.type === "clock") return { text: clockText(clock24.value, now, screenLanguage.value), shown: true };
  if (item.type === "date") return { text: dateText(now, screenLanguage.value), shown: true };
  if (item.type === "analog") return { analog: true, shown: true };
  const p = state.topbarPreviews[itemKey(item)];
  if (!p) return { icon: item.icon === "none" ? null : iconNamed(item.icon)?.cp || automaticIcon(item.entity!), text: "…", shown: true, loading: true };
  return { icon: p.i || null, text: p.k === "ago" ? agoText(p.e, Math.floor(state.now / 1000), screenLanguage.value) : p.t, color: p.c ? `#${p.c}` : null, shown: p.shown };
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
  toast(t("editor.topbar.removed", { name: topbarLabel(item) }), {
    label: t("editor.common.undo"),
    run: () => { const back = [...topbarItems()]; back.splice(Math.min(index, back.length), 0, item); setTopbarItems(back); },
  });
}
export function addTopbarItem(item: HeaderItem) {
  const items = topbarItems();
  if (items.length >= topbarMax()) return toast(t("editor.topbar.full", topbarMax()));
  if (items.some((other) => itemKey(other) === itemKey(item))) return toast(t("editor.topbar.already"));
  // The new chip lights up briefly so the eye finds it.
  state.topbarAdded = { key: itemKey(item), time: Date.now() };
  setTopbarItems([...items, item]);
  openBar(items.length);
}

// ---- Screen settings: the same groups and rows as the settings page on the screen itself ----
// Every change applies at once, like on the screen; no Save needed. A screen with firmware 0.2.49+ owns its
// settings and ESP Screens changes them through its entities in Home Assistant. A group's title and a row's label
// are the texts editor.screen_settings.groups.<group> and editor.screen_settings.rows.<key> (app 0.2.90).
export const SETTING_GROUPS = [
  { group: "brightness", icon: "F0599", rows: [
    { key: "brightness", kind: "number", min: 5, max: 100, step: 5, unit: "%" },
    { key: "dark_mode", kind: "toggle" },
    { key: "standby_enabled", kind: "toggle" },
    { key: "standby_seconds", kind: "duration", min: 60, max: 86400, needs: "standby_enabled" },
    { key: "standby_brightness", kind: "number", min: 0, max: 100, step: 5, unit: "%", needs: "standby_enabled", cap: "brightness" },
  ] },
  { group: "night", icon: "F0594", rows: [
    { key: "night_enabled", kind: "toggle" },
    { key: "night_start", kind: "moment", needs: "night_enabled" },
    { key: "night_end", kind: "moment", needs: "night_enabled" },
    { key: "night_brightness", kind: "number", min: 0, max: 100, step: 5, unit: "%", needs: "night_enabled", cap: "brightness" },
  ] },
  { group: "screen", icon: "F0379", rows: [
    { key: "auto_home", kind: "toggle" },
    { key: "auto_home_seconds", kind: "duration", min: 30, max: 3600, needs: "auto_home" },
    { key: "home_on_standby", kind: "toggle" },
    { key: "swipe_pages", kind: "toggle" },
    { key: "page_buttons", kind: "toggle" },
    { key: "home_button", kind: "toggle" },
    { key: "rotation", kind: "choice", options: [0, 90, 180, 270] },
  ] },
] as const;
export type SettingRow = (typeof SETTING_GROUPS)[number]["rows"][number] & { min?: number; max?: number; step?: number; unit?: string; needs?: string; cap?: string; options?: readonly unknown[] };
export const settingLabel = (row: SettingRow) => t(`editor.screen_settings.rows.${row.key}`);
// A choice in the same words in every language: the rotation's angle. The clock left this page for Settings → Language
// & region, one choice for every screen (app 0.2.90).
export const choiceText = (_row: SettingRow, value: unknown) => `${value}°`;
// Device navigation settings are separate from the page document. Unknown
// settings remain permissive for warnings, avoiding a false unreachable report.
export function navigationSettings(): pages.NavigationSettings {
  const values = settingValues();
  return { pageButtons: values.page_buttons !== false, swipe: values.swipe_pages !== false,
    homeButton: supports(0, 2, 100) && values.home_button !== false };
}
export function pageReachWarning() {
  if (!state.document) return "";
  const result = pages.reachability(state.document, navigationSettings());
  const named = (ids: string[]) => t("editor.screen_settings.reach.pages", {
    list: andList(ids.map((id) => state.document!.pages.findIndex((page) => page.id === id) + 1)),
  }, ids.length);
  const messages: string[] = [];
  if (result.unreachable.length) messages.push(t("editor.pages.unreachable", { pages: named(result.unreachable) }));
  if (result.noWayHome.length) messages.push(t("editor.pages.no_way_home", { pages: named(result.noWayHome) }));
  return messages.join(" ");
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
// The house in the top bar of the mockup (app 0.2.122, firmware 0.2.100+): on every page, as on the screen, unless
// the screen's Show home button is off. A screen whose value nobody can read right now (offline) is drawn as set.
export const homeKeyShown = (page = state.barPage) => supports(0, 2, 100) && settingValues().home_button !== false && Boolean(pageAt(page)?.topbar.leading.length);
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
  if (seconds < 60) return t("editor.screen_settings.duration.seconds", { n: seconds });
  if (seconds < 3600) return t("editor.screen_settings.duration.minutes", { n: Math.floor(seconds / 60) });
  const hours = Math.floor(seconds / 3600), minutes = Math.floor((seconds % 3600) / 60);
  return minutes
    ? t("editor.screen_settings.duration.hours_minutes", { h: hours, m: String(minutes).padStart(2, "0") })
    : t("editor.screen_settings.duration.hours", { n: hours });
}
export function momentText(minutes: number, clock24: boolean) {
  const hour = Math.floor(minutes / 60), minute = String(minutes % 60).padStart(2, "0");
  if (clock24) return `${String(hour).padStart(2, "0")}:${minute}`;
  return t(hour < 12 ? "editor.screen_settings.time.am" : "editor.screen_settings.time.pm", { time: `${hour % 12 || 12}:${minute}` });
}
export function settingText(row: SettingRow, values: Record<string, any>) {
  const value = values[row.key];
  // Home Assistant has no value while the screen is offline or the entity is off.
  if (value === null || value === undefined) return "—";
  if (row.kind === "number") return `${value}${row.unit || ""}`;
  if (row.kind === "duration") return durationText(value);
  if (row.kind === "moment") return momentText(value, clock24.value);
  return "";
}
export function setSetting(key: string, value: any, delay: number) {
  // One screen's changes at a time: the ones for the screen shown before go out first.
  if (settingTarget && settingTarget !== state.selected && Object.keys(settingQueue).length) {
    flushSettings();
    toast(t("editor.screen_settings.other_screen_busy"));
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
// What a running update is doing, by its phase.
export const phaseText = (phase: string | undefined) =>
  ["install", "verify", "settle"].includes(phase || "") ? t(`editor.update.phases.${phase}`) : t("editor.update.starting");
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
    toast(t(auto ? "editor.settings.updates.auto_on" : "editor.settings.updates.auto_off"));
  } catch (e: any) {
    toast(e.message);
  }
}
export async function installClaudeSkill() {
  try {
    state.inventory.claude_skill = await send("claude-skill", "POST");
    toast(t(state.inventory.claude_skill?.restart ? "editor.settings.claude.installed_restart" : "editor.settings.claude.installed"));
  } catch (e: any) {
    toast(e.message);
  }
}

// ---- Languages (app 0.2.90) ----
// The editor speaks the language of the user's Home Assistant profile (i18n.ts). The screens have one language for all
// of them, Home Assistant's unless the setting says another; the mockup draws their words in it, and in English until
// the add-on tells which one it is.
export const screenLanguage = computed(() => pickLanguage(state.inventory.language?.effective));
watch(screenLanguage, (code) => loadLanguage(code), { immediate: true });
/** A text as the screens show it: in their language, not the editor's. */
export const screenText = (key: string, named: Record<string, unknown> = {}) => t(key, named, { locale: screenLanguage.value });
/** A language by its own name ("Nederlands"), as the add-on lists it. */
export const languageName = (code: string | null | undefined) =>
  state.inventory.language?.languages?.find((l) => l.code === code)?.name || languageMeta(code || "")?.name || code || "";
// A screen that doesn't run the chosen language yet needs its update as well.
export const needsUpdate = (screen: Screen) => Boolean(screen.update?.available || screen.update?.language);
export const newLanguageText = () => t("editor.update.new_language", { name: languageName(state.inventory.language?.effective) });
// Time and number format, for every screen at once under Settings → Language & region: a 24-hour clock and "1,234.5"
// until the add-on says otherwise. The mockup's clocks and numbers follow what the add-on sends the screens: the style,
// from how many digits a number is grouped, and the space before "%" (Home Assistant's language decides "auto").
export const clock24 = computed(() => state.inventory.language?.clock_effective !== "12");
export const numberMarks = computed<NumberMarks>(() => {
  const language = state.inventory.language;
  const marks = STYLE_MARKS[language?.numbers_effective || "point"] || STYLE_MARKS.point;
  return { ...marks, from: (language?.group_min || 1) >= 2 ? 5 : 4 };
});
/** How Automatic writes numbers: the marks of the language that decides, for the label of that choice. */
export const autoMarks = computed<NumberMarks>(() => {
  const language = state.inventory.language;
  return { ...(STYLE_MARKS[language?.numbers_auto || "point"] || STYLE_MARKS.point), from: (language?.group_min_auto || 1) >= 2 ? 5 : 4 };
});
/** What follows a number for its unit, as Home Assistant spaces it: "°", "%" or " %" by the language, " kWh". */
export function unitSuffix(unit: string | undefined | null) {
  if (!unit || unit === "°") return unit || "";
  if (unit === "%") return state.inventory.language?.percent_space ? " %" : "%";
  return ` ${unit}`;
}
/** A built-in card's name as the screens show it (Settings, Clock, Go to page 2), in their language. */
export const screenBuiltinName = (id: string) => state.inventory.builtin?.find((e) => e.id === id)?.screen_name;
/** Saves any of the screen language, the time format and the number format. */
export async function saveLanguage(changes: { setting?: string; clock?: string; numbers?: string }) {
  try {
    const answer = await send("language", "PUT", changes);
    if (answer?.language) state.inventory.language = answer.language;
    // A language is built into the firmware; the time and number format are not.
    toast(t(changes.setting === undefined ? "editor.settings.language.saved" : "editor.settings.language.saved_language"));
    // Every screen now wants an update, which the inventory reports.
    await refresh();
    return true;
  } catch (e: any) {
    toast(e.message);
    return false;
  }
}

/** Resolve against a fresh server revision; failed requests always retain the draft. */
export async function dismissMigrationNote() {
  const screen = currentScreen.value, record = screen?.page_document;
  if (!screen || record?.format !== 'pages-v2') return;
  try {
    await send(`screens/${encodeURIComponent(screen.id)}/migration/dismiss`, 'POST', { revision: record.revision });
    await refresh(false);
  } catch (error: any) { toast(error.message); }
}

export async function startFreshLayout() {
  const screen = currentScreen.value, record = screen?.page_document;
  if (!screen || record?.format !== 'legacy-v1' || !confirm(t('editor.pages.start_fresh_confirm'))) return;
  try {
    await send(`screens/${encodeURIComponent(screen.id)}/migration/reset`, 'POST', { revision: record.migrationRevision });
    await refresh(false);
  } catch (error: any) { toast(error.message); }
}

export async function resolveLayoutConflict(choice: 'reload' | 'keep') {
  await resolveConflict(choice, state, {
    epoch: () => selectionEpoch, refresh: () => refresh(false), screen: () => currentScreen.value,
    load: screen => { closeInspector(); loadDocument(screen); },
    acceptBase: record => { committedLayout = pages.clone(record.layout); committedGrid = pages.clone(record.sourceGrid); },
    save,
  });
}

function reconcileDocument() {
  const screen = currentScreen.value, record = screen?.page_document;
  if (!screen || state.busy) return;
  if (record?.format === "pages-v2" && record.revision !== state.documentRevision) {
    if (state.dirty || state.workspaceDirty) { state.conflict = true; return; }
    const selected = state.selectedPageId, focused = state.focusedPageId, tile = state.selectedTile?.id;
    loadDocument(screen);
    if (state.document?.pages.some((page) => page.id === selected)) state.selectedPageId = selected;
    if (state.document?.pages.some((page) => page.id === focused)) state.focusedPageId = focused;
    state.selectedTile = state.layout?.tiles.find((item) => item.id === tile) || null;
  } else if (record?.format === "pages-v2" && record.workspace && !state.workspaceDirty) {
    state.workspace = pages.clone(record.workspace);
  } else if (!state.documentGrid && screen.source_grid && !state.dirty) loadDocument(screen);
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
    if (state.selected) { settleSettings(); reconcileDocument(); }
  } catch {
    state.reachable = false;
  }
}
function applyLive(data: Partial<Inventory>) {
  state.inventory = { ...state.inventory, ...data } as Inventory;
  state.connected = Boolean(state.inventory.connected);
  for (const screen of state.inventory.screens) if (screen.update?.state === "running") state.updating = state.updating.filter((id) => id !== screen.id);
  if (state.selected) { settleSettings(); reconcileDocument(); }
}
let pollTimer = 0, lastFull = Date.now(), live = false, stream: EventSource | null = null;
function listen() {
  if (stream || typeof EventSource === "undefined") return;
  // An EventSource sends no headers of its own: the editor's language goes along in the address (app 0.2.90).
  stream = new EventSource(`api/events?language=${encodeURIComponent(editorLanguage())}`);
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
