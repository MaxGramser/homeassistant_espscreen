// The draft of the open screen and what edits it: its pages and tiles, undo, saving, the map of pages, a grid or way of
// hanging chosen, copying and importing a layout; the inspector that opens beside it; and the mockup's sizes (the
// canvas). What a drag shows (stores/drag.ts), what the add-on says, the open screen, the session, the top bar and the
// screensaver are stores of their own (stores/), and so will this be: until then the functions here read those stores,
// and none of them reaches back in here but the session, the top bar and the screensaver, which are on top of the draft.
import { useEventListener, useTimeoutFn } from "@vueuse/core";
import { computed, effectScope, onScopeDispose, reactive, shallowRef, toRef, watch } from "vue";
import { isTallSize, sizeColumns, sizesOn, spanOf, spanOffered } from "./model/sizes";
import { getJson, send } from "./api";
import { andList, t } from "./i18n";
import { entriesOf, effectiveControls, isFull, isWide, newTile, pageOrder, pagePlaces, pageTarget, reorderTitles, retargetedPage, sizeOf, supportsFirmware } from "./model/layout";
import { barMetricsFor } from "./model/topbar";
import { energyFits, frameOf, pillMetrics, uiScale } from "./model/ui-scale";
import { createLayout, dimensions, type Size } from "./model/layout";
import { memoryCrossing, memoryUse } from "./model/memory";
import type { ChildTile, HeaderItem, Inventory, Layout, SaverKind, Screen, Tile, PageLayout, PageTile, PageDocument, PageGrid, PageWorkspace } from "./types";

import * as pages from "./model/pages";
import { DraftHistory, type HistoryScope } from './model/draft-history';
import { suggestedPageTitle } from './model/page-naming';
import { validateCardOptions } from './model/page-validation';
import pageRules from './model/page-rules.json';
import { canonicalOptions, coupledOptions } from './model/tile-options';
import { completePositions, workspaceSaver } from './model/page-workspace';
import { resolveConflict, savedDraft } from './model/page-conflict';
import { SMALLEST } from "./model/overview";
import { slug } from "./model/slug";
import { onReset } from "./resets";
import { renewable, usePreference } from "./composables/usePreference";
import { useClock } from "./composables/useClock";
import { askConfirm } from "./composables/useConfirm";
import { useVisibleInterval } from "./composables/useVisibleInterval";
import { useDragStore } from "./stores/drag";
import { useEntitiesStore } from "./stores/entities";
import { usePluginsStore } from "./stores/plugins";
import { useInventoryStore } from "./stores/inventory";
import { useScreenStore } from "./stores/screen";
import { useSettingsStore } from "./stores/settings";
import { useUiStore, type Toast } from "./stores/ui";

export type Inspector =
  | { kind: "tile" }
  | { kind: "bar"; index: number }
  | { kind: "bar-add" }
  | { kind: "saver-item"; index: number }
  | { kind: "saver-add" }
  | { kind: "saver"; step: SaverKind }
  | { kind: "page"; id: string }
  | { kind: "inspect"; entity?: string; slot?: number; key?: number };

// The editor's state as it starts, before the add-on has said anything: the page begins with it, and every test again
// (resetStore).
const fresh = () => ({
  document: null as PageLayout | null,
  gridReview: null as { record: PageDocument; layout: PageLayout; target: PageGrid; copy: boolean; message: string } | null,
  documentRevision: null as string | null,
  documentGrid: null as PageGrid | null,
  // Whether the draft stands the screen up (app 0.4.85, firmware 0.53.0+): true or false on glass that turns, null else.
  documentUpright: null as boolean | null,
  workspace: { revision: "", positions: {} } as PageWorkspace,
  workspaceDirty: false,
  editorMode: "simple" as "simple" | "advanced",
  focusedPageId: null as string | null,
  connectingTileId: null as string | null,
  selectedPageId: null as string | null,
  conflict: false,
  undoCount: 0,
  redoCount: 0,
  dirty: false,
  busy: false,
  saved: 0,
  tab: "layout" as "layout" | "settings" | "plugins",
  // The tile by its id, not its entity: several tiles can go to the same page (firmware 0.2.65). currentTile is the
  // tile as the draft has it now.
  selectedTileId: null as string | null,
  inspector: null as Inspector | null,
  iconPickerOpen: false,
  actionPickerOpen: false,
  actionSearch: "",
  insertAt: -1,
  // The key place a click marked under a bedside clock (app 0.4.12): the next tile added from the library goes there.
  insertKey: null as null | { holder: string; key: number },
  // On a phone (app 0.4.40) the tile just added is marked for a moment.
  justAdded: null as string | null,
  // A choice the pointer rests on in the inspector, drawn on its tile before it is picked (app 0.4.32).
  optionPreview: null as null | { tileId: string; key: string; value: unknown },
});
export const state = reactive({
  ...fresh(),
  get layout(): Layout | null { return renderedLayout.value; },
  // Index projection for older view helpers; selection itself is always an ID.
  get barPage(): number { return Math.max(0, state.document?.pages.findIndex(page => page.id === state.selectedPageId) ?? 0); },
});

// The page around the screens (stores/ui.ts): its toast, for the functions below.
const toast = (message: string, action?: Toast["action"]) => useUiStore().toast(message, action);

// This is a cached render projection of the one canonical draft. Mutations go
// through document operations below, never through this flattened view.
const renderedLayout = computed<Layout | null>(() => state.document && state.documentGrid
  ? pages.projectLayout(state.document, state.documentGrid) : null);
// The open screen and what its firmware takes are the screen store's (stores/screen.ts). This file's computeds outlive a
// test's pinia (tests/setup.ts makes one for every test), so one that reads a store is worked out again once resetStore has
// counted `generation` up; the page has one pinia and never resets.
const generation = shallowRef(0);
const storeComputed = <T>(get: () => T) => computed<T>(() => { generation.value; return get(); });
const scr = () => useScreenStore();
// What the add-on says (stores/inventory.ts).
const inv = () => useInventoryStore();
// What the screen holds and draws, as the add-on says (app 0.2.78), so a screen whose version Home Assistant can't
// report for a moment keeps its 48 tiles instead of dropping to ten, and a copied or imported layout isn't cut to ten.
export const tileLimit = storeComputed(() => {
  const limit = scr().currentScreen?.tile_limit;
  return typeof limit === "number" && Number.isInteger(limit) && limit > 0 ? limit : limitFor(scr().firmwareOf);
});
// How much of the screen's memory for its tiles the layout being edited takes (stores/screen.ts screenMemory).
export const memory = storeComputed(() => (scr().screenMemory && !scr().memoryMeasuring && state.layout
  ? memoryUse(state.layout.tiles, scr().screenMemory!, state.document?.pages || [], usePluginsStore().pluginTileOf) : null));
// Whether a new tile of this entity goes on, as a library click or drag makes it (its own action and line come later, in
// its settings). Past nine tenths of the screen's memory for tiles, and past all of it, the editor asks first. A warning,
// not a rule (app 0.4.61): a screen measured far less room than the screens it was priced on (GitHub #157), and a screen
// protects itself when it runs short, so whoever wants to try may. True at once when there is nothing to ask, else the
// answer to the question (useConfirm).
export function confirmMemory(entity: string): true | Promise<boolean> {
  const memory = scr().screenMemory;
  if (!memory || scr().memoryMeasuring || !state.layout) return true;
  const crossing = memoryCrossing(state.layout.tiles, { entity }, memory, state.document?.pages || [], usePluginsStore().pluginTileOf);
  if (!crossing) return true;
  return askConfirm(t(`editor.memory.confirm_${crossing.line}`, { n: Math.min(999, Math.round(crossing.share * 100)) }));
}
// What the screen being edited looks like. The manager works it out (core.shape_of): what the screen reported
// itself, else the board package its YAML builds from, else its board. The editor only draws it, and falls
// back to the smallest screen there is while it has heard nothing at all (SMALLEST).
export const screenShape = storeComputed(() => {
  const shape = scr().currentScreen?.shape;
  if (!shape || !(shape.columns > 0 && shape.rows > 0)) return SMALLEST;
  // A draft that stands the screen up or lays it down (app 0.4.85): the canvas of that way, before the screen turned.
  const upright = state.documentUpright;
  return upright !== null && (shape.height > shape.width) !== upright ? { ...shape, width: shape.height, height: shape.width } : shape;
});
// The top bar of the mockup at the screen's own width and density (topbar.ts).
export const barMetrics = storeComputed(() => barMetricsFor(screenShape.value));
// The tile grid of a page, as CSS variables: the mockup is the screen's own shape, whatever board it is.
// Every mockup has the same shorter side (MOCKUP_SIDE), so a screen keeps its size against its neighbours: a
// 800 x 480 page lying down is wider than a square 480 x 480 one, and the same glass standing up is taller, not
// narrower. Drawn the same height instead, a 480 x 800 screen came out 180 px wide, smaller than the 480 x 480
// Guition though it has more glass. Very wide glass is capped so it still fits beside a neighbour on a laptop.
const MOCKUP_SIDE = 300;
// Whether the screen keeps room for its page bar under the tiles: on every page, once the layout has more than one
// (page_protocol.h footer), so a card is lower on all of them.
export const pageBarShown = storeComputed(() => Boolean(state.document && pages.navigationFooter(state.document, useSettingsStore().navigationSettings())));
export const deviceStyle = storeComputed(() => {
  const shape = screenShape.value;
  // To a tenth of a pixel, not a whole one: on a 1280 x 800 screen the nearest whole pixel of width would make
  // the mockup a pixel taller than the rest. Every board lying down lands on a whole number anyway.
  const width = shape.width >= shape.height ? Math.min(560, (MOCKUP_SIDE * shape.width) / shape.height) : MOCKUP_SIDE;
  const rounded = Math.round(width * 10) / 10;
  // The glass in editor pixels, and the -/+ pill at the size the screen draws it (model/ui-scale.ts).
  const glass = rounded / shape.width, pill = pillMetrics(shape);
  const [watch, text] = [pill.faces[0] ?? 22, pill.faces[1] ?? pill.faces[0] ?? 14];
  // The page in the glass's proportions (app 0.4.74): the top bar from the top of the glass down to where the tile area
  // starts, the margins and gaps of the grid, and the page bar where the layout has one, so a card is as high against
  // its page as on the screen (ui-scale cardHeight). Before, the mockup's own 10 px frame, 8 px gaps and 24 px
  // page bar left a card of a 4-inch Guition with three rows and three pages 65 px high where the glass's is 117 x 0.625.
  const frame = frameOf(shape), paged = pageBarShown.value;
  const g = (n: number) => `${(n * glass).toFixed(2)}px`;
  return {
    "--glass": String(glass),
    "--frame-top": g(frame.top),
    "--frame-side": g(frame.margin),
    "--frame-bottom": g(paged ? 0 : frame.margin),
    "--frame-bar": g(frame.page_bar),
    "--frame-gap-x": g(frame.gap),
    "--frame-gap-y": g(frame.gap_y),
    "--frame-pad": g(frame.tile_pad),
    "--pill-h": `${(pill.height * glass).toFixed(2)}px`,
    "--pill-in": `${(pill.inset * glass).toFixed(2)}px`,
    "--pill-key": `${(pill.key * glass).toFixed(2)}px`,
    "--face-watch": `${(watch * glass).toFixed(2)}px`,
    "--face-text": `${(text * glass).toFixed(2)}px`,
    // A range's chip (runtime_tiles range_chip): its icon is a key's icon, beside the number with the glass's gap.
    "--chip-icon": `${((("fonts" in shape ? shape.fonts?.icon_mini : undefined) ?? (uiScale(shape).large ? 26 : 18)) * glass).toFixed(2)}px`,
    "--chip-pad": `${(uiScale(shape).px(6) * glass).toFixed(2)}px`,
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
export const isCompact = storeComputed(() =>
  screenShape.value.look ? screenShape.value.look === "compact" : Math.min(screenShape.value.width, screenShape.value.height) < 300);
// A plain card's name gets larger letters on the compact look where its cell has 30 mm of room
// (runtime_tiles::name_font): one column standing up, a 4-inch glass. The cell's width as the screen lays it out:
// its 9 px margins and 8 px gaps, then the card's padding (8 px of the look) and border.
export const roomyNames = storeComputed(() => {
  const shape = screenShape.value;
  if (!isCompact.value || !shape.dpi) return false;
  const columns = state.documentGrid?.columns ?? shape.columns;
  const pad = Math.round((8 * shape.dpi) / 143);
  const cell = (shape.width - 18 - (columns - 1) * 8) / columns - 2 * pad - 2;
  return cell >= Math.floor((shape.dpi * 30 + 12) / 25);
});
export const editorLayout = createLayout(() => state.documentGrid ?? screenShape.value, () => scr().currentScreen?.page_limit);
export const grid = editorLayout.grid;
const { arrange, cellsOf, firstFree, fits, nearestFree, normalize, occupied, pageCount, pageOf, reorderPages, rowStart, startOf, strandedPages, tileLimit: limitFor } = editorLayout;
export const currentTile = computed<Tile | undefined>(() => state.selectedTileId
  ? state.layout?.tiles.find((tile) => tile.id === state.selectedTileId) : undefined);
export const isSelected = (tile: Tile) => Boolean(tile.id) && state.selectedTileId === tile.id;
// The tile as the mockup draws it: with the choice the pointer rests on in the inspector, when that is this tile's.
export function previewed(tile: Tile): Tile {
  const hover = state.optionPreview;
  // Only while that tile's own settings are open and nothing is being dragged: the drawn copy never reaches an edit.
  if (!hover || !tile.id || hover.tileId !== tile.id || state.selectedTileId !== tile.id || useDragStore().active) return tile;
  return { ...tile, options: { ...(tile.options || {}), [hover.key]: hover.value } } as Tile;
}
const currentView = (tile: Tile, layout = state.layout) => tile.id ? layout?.tiles.find((item) => item.id === tile.id) : tile;
export const pageAt = (index: number) => state.document?.pages[useDragStore().page?.order[index] ?? index];

// ---- What Home Assistant says of the open layout's entities (stores/entities.ts) ----
// An answer asked for one screen is dropped once another is open, or this one was read again (selectionEpoch).
export function stillSelected() {
  const epoch = selectionEpoch;
  return () => epoch === selectionEpoch;
}
const entityName = (id: string) => useEntitiesStore().entityName(id);
const loadCapabilities = (entities: string[]) => useEntitiesStore().loadCapabilities(entities);
// The states of the open layout's entities, for the mockup.
function loadStates() {
  return useEntitiesStore().loadStates((state.layout?.tiles || []).map((tile) => tile.entity), stillSelected());
}
// ---- Selecting a screen and editing its layout ----
// Every edit counts, so a save only clears the edits it sent (app 0.2.78).
let edits = 0;
let committedLayout: PageLayout | null = null;
let committedGrid: PageGrid | null = null;
let committedUpright: boolean | null = null;
let selectionEpoch = 0;
export function markDirty() {
  state.dirty = !pages.sameValue(state.document, committedLayout) || !pages.sameValue(state.documentGrid, committedGrid) || state.documentUpright !== committedUpright;
  state.saved = 0;
  edits++;
}
type DraftSnapshot = { layout: PageLayout; grid: PageGrid; upright: boolean | null; positions: PageWorkspace["positions"]; page: string | null; tile: string | null };
const draftHistory = new DraftHistory<DraftSnapshot>();
const snapshot = (): DraftSnapshot => ({ layout: pages.clone(state.document!), grid: pages.clone(state.documentGrid!), upright: state.documentUpright, positions: pages.clone(state.workspace.positions),
  page: state.selectedPageId, tile: state.selectedTileId });
function historyCounts() {
  // A removal toast only belongs to the latest history entry. Once another
  // edit, map move, undo or screen selection changes history, retire it.
  const ui = useUiStore();
  if (ui.notice?.action?.run === undo) ui.dismissToast();
  const counts = draftHistory.counts(state.editorMode === 'advanced');
  state.undoCount = counts.undo; state.redoCount = counts.redo;
}
// A document's grid with the pages this screen takes (page_limit): what every edit is held to, where a stored document is
// held to the most any board takes (model/pages.ts pageLimit). Plugin tiles and items are taken where the add-on serves
// plugins (stores/plugins.ts pluginsEnabled), on the grid of every change (heldTo) as on the screen's.
export const heldTo = (grid: PageGrid): PageGrid => ({ ...grid, plugins: usePluginsStore().pluginsEnabled });
const screenGridOf = (grid: PageGrid): PageGrid => heldTo({ columns: grid.columns, rows: grid.rows, pages: editorLayout.grid.pages, barItems: scr().topbarMax });
// The draft becomes `next` (and its grid `nextGrid`), checked against what the screen takes, remembered for undo unless
// `remember` is false. True when anything changed. A change of a page's top bar is the top bar store's (stores/topbar.ts).
export function applyDocument(next: PageLayout, remember = true, nextGrid = state.documentGrid) {
  if (!state.document || !state.documentGrid) return false;
  if (!nextGrid) return false;
  pages.validatePages(next, screenGridOf(nextGrid));
  if (pages.sameValue(next, state.document) && pages.sameGrid(nextGrid, state.documentGrid)) return false;
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
  // A key under a bedside clock is a child of its clock: a change to it keeps it open like any tile.
  const selected = state.selectedTileId;
  if (selected && !next.pages.some((page) => page.tiles.some((tile) => tile.id === selected || tile.children?.some((child) => child.id === selected))))
    closeInspector();
  markDirty();
  return true;
}
let focusedField: string | null = null, groupedEdit = -1;
export function beginFieldEdit(key: string) { focusedField = key; groupedEdit = -1; }
export function endFieldEdit() { focusedField = null; groupedEdit = -1; }
export function editDocument(apply: (draft: PageLayout) => void, field?: string) {
  if (!state.document || !state.documentGrid) return false;
  try {
    const grouped = field !== undefined && focusedField === field;
    const changed = applyDocument(pages.changePages(state.document, heldTo(state.documentGrid), apply), !(grouped && groupedEdit === edits));
    if (changed) groupedEdit = grouped ? edits : -1;
    return changed;
  }
  catch (error: any) { toast(error.message); return false; }
}
function restoreSnapshot(value: DraftSnapshot, scope: HistoryScope) {
  endFieldEdit();
  if (scope === 'document') {
    const positions = pages.clone(state.workspace.positions);
    state.documentUpright = value.upright;
    applyDocument(value.layout, false, value.grid);
    markDirty();
    // Keep current positions; recover a deleted page's position from its snapshot.
    state.workspace.positions = Object.fromEntries(value.layout.pages.flatMap((page) => {
      const point = positions[page.id] || value.positions[page.id];
      return point ? [[page.id, point]] : [];
    }));
    state.selectedPageId = value.page;
    state.selectedTileId = state.layout?.tiles.some((tile) => tile.id === value.tile) ? value.tile : null;
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
// The simple or the advanced editor, remembered in this browser per screen: the preference of the open screen.
const screenPreferences = renewable(() => ({
  mode: usePreference<"simple" | "advanced">(() => `esp-screens-mode:${scr().selected ?? ""}`, "simple",
    { serializer: { read: (raw) => (raw === "advanced" ? "advanced" : "simple"), write: (mode) => mode } }),
}));
// Made when first asked, since its name reads the open screen (stores/screen.ts), which a module cannot ask while it loads.
let screenKept: ReturnType<typeof screenPreferences> | null = null;
const kept = () => (screenKept ??= screenPreferences());
export function setEditorMode(mode: "simple" | "advanced") {
  state.editorMode = mode;
  historyCounts();
  state.focusedPageId = null;
  state.connectingTileId = null;
  useDragStore().clear();
  if (mode === "advanced") initializeWorkspace();
  if (scr().selected) kept().mode.value = mode;
}
// A screen's saved document becomes the draft, with nothing to undo and nothing unsaved: when a screen is chosen, when it
// is read again, and for the tests' fixtures (tests/page-fixtures.ts), which so start from what the editor starts from.
export function loadDocument(screen: Screen) {
  endFieldEdit();
  selectionEpoch++;
  const record = screen.page_document;
  state.document = record?.format === "legacy-v1" ? null : record?.format === "pages-v2"
    ? pages.clone(record.layout) : pages.emptyLayout(screen.layout.title || screen.name);
  state.documentGrid = record?.format === "pages-v2" ? pages.clone(record.sourceGrid)
    : screen.source_grid ? pages.clone(screen.source_grid) : null;
  committedLayout = pages.clone(state.document);
  committedGrid = pages.clone(state.documentGrid);
  state.documentUpright = committedUpright = screen.hang ? screen.hang === 'portrait' : null;
  state.gridReview = null;
  state.documentRevision = record?.format === "pages-v2" ? record.revision : null;
  state.workspace = record?.format === "pages-v2" && record.workspace ? pages.clone(record.workspace) : { revision: "", positions: {} };
  state.workspaceDirty = false;
  state.selectedPageId = state.document?.homePageId || null;
  state.focusedPageId = null;
  state.conflict = false;
  draftHistory.clear(); historyCounts();
}
// The draft of the screen the session opens (stores/session.ts select), or none: what the editor shows of the screen
// before starts again. True when there is a screen.
export function openDocument(screen: Screen | undefined) {
  state.selectedTileId = null; state.inspector = null;
  state.tab = "layout";
  // Nothing chosen (the overview, app 0.4.0): the draft that was confirmed away is gone, so nothing is unsaved.
  if (!screen) { state.document = null; state.documentGrid = null; state.dirty = false; return false; }
  loadDocument(screen);
  state.editorMode = kept().mode.value;
  if (state.editorMode === "advanced") initializeWorkspace();
  state.insertAt = -1; state.dirty = false; state.saved = 0;
  loadCapabilities(state.layout?.tiles.map((tile) => tile.entity) || []);
  loadStates();
  return true;
}
// The open screen's draft gone without a question (stores/session.ts forgetOpenScreen): nothing of it is left to save.
export function closeDocument() {
  state.dirty = false;
  state.document = null;
  state.documentGrid = null;
  state.documentUpright = null;
  state.gridReview = null;
  state.selectedTileId = null;
  state.inspector = null;
}
export const liveEntries = () => (state.layout ? entriesOf(state.layout) : []);
// Apply an arrangement; a new tile joins the layout. True when anything changed.
// `field`: typing in one field is one step of undo (app 0.4.2), as with editDocument.
export function commitArrangement(result: { tile: Tile; slot: number }[], field?: string) {
  if (!state.document || !state.documentGrid) return false;
  try {
    // Adding a numbered destination from the library explicitly creates that
    // page, in the same undo operation as its navigation tile.
    const draft = pages.clone(state.document);
    const count = Math.max(draft.pages.length, ...result.filter(({ tile }) => !tile.id).map(({ tile }) => pageTarget(tile.entity)));
    if (count > editorLayout.grid.pages) throw new Error(t("addon.errors.pages.pages_full"));
    while (draft.pages.length < count) draft.pages.push(pages.emptyPage(draft.pages.at(-1)!.topbar));
    const arranged = pages.arrangeTiles(draft, screenGridOf(state.documentGrid), result);
    const existing = new Set(state.document.pages.map(page => page.id));
    for (const page of arranged.pages) if (!existing.has(page.id)) {
      const title = suggestedPageTitle(page, inv().inventory.entities);
      page.topbar.title = title ? { source: 'text', text: title } : { source: 'screen' };
    }
    const grouped = field !== undefined && focusedField === field;
    const changed = applyDocument(arranged, !(grouped && groupedEdit === edits));
    if (changed) groupedEdit = grouped ? edits : -1;
    return changed;
  }
  catch (error: any) { toast(error.message); return false; }
}
export function placeTile(tile: Tile, target: number) {
  if (!state.layout) return false;
  loadCapabilities([tile.entity]);
  const result = arrange(state.layout.tiles, currentView(tile) || tile, target);
  const placed = result ? commitArrangement(result) : false;
  if (placed && !useEntitiesStore().liveStates[tile.entity]) loadStates();
  return placed;
}
// A click in the picker: the marked empty cell, else the selected page's first
// free cell. Never silently spill a library click onto another page.
/** A new tile from the picker or a drag: its default options, and for the energy card the smallest size its diagram fits
 * on this glass (app 0.4.77), since a 2 x 2 card is too low for it on some. */
export function startTile(id: string): Tile {
  const tile = newTile(id, scr().coversByDefault);
  if (id !== "screen.energy") return tile;
  const area = (size: Size) => { const d = dimensions(size, grid); return d.columns * d.rows; };
  const fitting = tileSizeChoices(tile).sort((a, b) => area(a) - area(b));
  return { ...tile, options: { ...tile.options, size: fitting.includes("square") ? "square" : fitting[0] ?? "full" } };
}
export async function addTile(id: string) {
  if (!state.layout || (!scr().repeatable(id) && state.layout.tiles.some((t) => t.entity === id)) || state.layout.tiles.length >= tileLimit.value) return;
  // Past the screen's memory the tile waits for the answer; otherwise it goes on at once.
  const allowed = confirmMemory(id);
  if (allowed !== true && !(await allowed)) return;
  const layout = state.layout;
  if (!layout) return;
  if (state.insertKey) {
    const { holder, key } = state.insertKey;
    state.insertKey = null;
    const clock = layout.tiles.find((item) => item.id === holder);
    if (clock && placeKey(newTile(id), clock, key)) {
      // The key in the place it was put in: the same entity may stand under the clock twice (firmware 0.16.0+).
      const added = state.layout!.tiles.find((item) => item.entity === id && item.in === clock.entity && item.key === key)
        || state.layout!.tiles.find((item) => item.entity === id && item.in === clock.entity);
      if (added) openTile(added);
    }
    return;
  }
  const tile = startTile(id);
  const page = Math.max(0, state.document!.pages.findIndex((page) => page.id === state.selectedPageId));
  const target = state.insertAt >= 0 ? state.insertAt : firstFree(occupied(entriesOf(layout)), sizeOf(tile), page * grid.slots);
  const slot = state.insertAt >= 0 || target < (page + 1) * grid.slots ? target : -1;
  state.insertAt = -1;
  if (slot < 0) return toast(t('editor.pages.selected_full'));
  if (slot >= 0 && placeTile(tile, slot)) {
    const added = state.layout!.tiles.find((item) => item.entity === id && item.slot === slot);
    if (added && useUiStore().phone) markAdded(added);
    else if (added) openTile(added);
  }
}
// On a phone the sheet goes and the screen shows the new tile, lit for a moment, with Undo at hand: one tile is the
// usual errand there, and its settings are one tap away.
const addedExpiry = useTimeoutFn(() => { state.justAdded = null; }, 2400, { immediate: false });
function markAdded(tile: Tile) {
  useUiStore().addSheet = false;
  state.justAdded = tile.id || null;
  addedExpiry.start();
  toast(t("editor.phone.added", { name: tile.name || entityName(tile.entity) }), { label: t("editor.common.undo"), run: undo });
}
export function removeTile(tile: Tile) {
  if (!tile.id) return;
  if (editDocument((draft) => {
    for (const page of draft.pages) {
      page.tiles = page.tiles.filter((item) => item.id !== tile.id);
      // A key goes from under its clock; a clock takes its keys with it.
      for (const item of page.tiles) if (item.children) {
        item.children = item.children.filter((child) => child.id !== tile.id);
        if (!item.children.length) delete item.children;
      }
    }
  }))
    toast(t("editor.layout.removed", { name: tile.name || entityName(tile.entity) }), { label: t("editor.common.undo"), run: undo });
}
export function addPage(bar?: PageLayout["pages"][number]["topbar"]) {
  if (state.document && state.document.pages.length >= editorLayout.grid.pages) { toast(t("addon.errors.pages.pages_full")); return false; }
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
  // Older firmware knows no home page of its own: it starts on the first page, so there the home page stays first
  // (app 0.4.1). Before, the move was taken and the save refused it later with no clue why.
  if (!scr().pageReady && (from === 0 || to === 0)) { toast(t("editor.pages.update_notice")); return false; }
  try { return applyDocument(pages.reorderPage(state.document, heldTo(state.documentGrid), state.document.pages[from]?.id, to)); }
  catch (error: any) { toast(error.message); return false; }
}
export function removePage(page: number) {
  if (!state.document || !state.documentGrid || !state.document.pages[page] || state.document.pages.length === 1) return;
  const id = state.document.pages[page].id;
  try {
    const next = pages.deletePage(state.document, heldTo(state.documentGrid), id);
    const removed = state.layout!.tiles.length - pages.projectLayout(next, state.documentGrid).tiles.length;
    if (applyDocument(next)) toast(removed ? t("editor.layout.page_removed_tiles", { page: page + 1 }, removed)
      : t("editor.layout.page_removed", { page: page + 1 }), { label: t("editor.common.undo"), run: undo });
  } catch (error: any) { toast(error.message); }
}
export function setHomePage(id: string) { return editDocument((draft) => { draft.homePageId = id; }); }
export function openPage(id: string) {
  state.selectedPageId = id; state.selectedTileId = null;
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
// A full copy of a page puts its tiles on the screen twice: a page tile when the firmware takes that (0.2.65), any
// other entity from 0.16.0, but never a clock with keys, which is on a screen once.
export function pageCopyable(page: PageTile[] | undefined) {
  return Boolean(page?.every((tile) => tile.content.kind === "navigation" ? scr().pageTilesRepeat :
    scr().entityTilesRepeat && !(tile.content.kind === "builtin" && `screen.${tile.content.name}` in pageRules.keyHolders)));
}
export function duplicateEditorPage(id: string, empty: boolean) {
  if (!state.document || !state.documentGrid) return false;
  if (state.document.pages.length >= editorLayout.grid.pages) { toast(t("addon.errors.pages.pages_full")); return false; }
  const copied = empty ? 0 : (state.document.pages.find((page) => page.id === id)?.tiles.length || 0);
  if ((state.layout?.tiles.length || 0) + copied > tileLimit.value) { toast(t("addon.errors.layout.tiles_max", tileLimit.value)); return false; }
  try { return applyDocument(pages.duplicatePage(state.document, screenGridOf(state.documentGrid), id, empty)); }
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
  const layout = state.layout, dragging = useDragStore();
  if (!layout) return 1;
  const entries = dragging.preview || entriesOf(layout);
  const pages = pageCount(entries, layout.pages);
  // While a tile is being dragged, one more page waits after the last one. A page on the move is looking for a place
  // in the row it is already in, so the row stays as long as it is.
  return dragging.active && !dragging.page && pages < grid.pages ? pages + 1 : pages;
}
/** The sizes the screen takes on the draft's grid: one given its grid with the layout (firmware 0.53.0+) every size of
 * that grid, an older one those it named for the grid it was built with. */
function screenSizes(): string[] {
  return scr().currentScreen?.grids ? sizesOn(grid) : scr().currentScreen?.tile_sizes || [];
}
export function tileSizeChoices(tile: Tile): Size[] {
  const choices: Size[] = ['single', 'wide'];
  const said = screenSizes();
  // A forecast or the sun's path needs width: nothing one column wide and taller than a row.
  const narrow = ['forecast', 'sunpath'].includes(String(tile.options?.display));
  if (inv().tallerTilesEnabled) for (const size of ['tall', 'square'] as const) {
    if (!said.includes(size) || grid.rows < 2 || (size === 'square' && grid.columns < 2)) continue;
    if (size === 'tall' && narrow) continue;
    choices.push(size);
  }
  // Every other rectangle the screen said its grid takes (firmware 0.19.0, app 0.4.32): 3 x 2, 2 x 3 and the rest.
  for (const size of said) {
    const span = spanOf(size);
    if (!span || !spanOffered(span.columns, span.rows, grid) || (span.rows > 1 && !inv().tallerTilesEnabled) || (span.columns === 1 && narrow)) continue;
    choices.push(size as Size);
  }
  // A plugin's tile takes the sizes between its manifest's smallest and largest (design, docs: the plugins proposal).
  const plugin = usePluginsStore().pluginTileOf(tile.entity);
  if (!pageTarget(tile.entity) && !plugin) choices.push('full');
  if (plugin) {
    const least = dimensions(plugin.tile.min as Size, grid), most = dimensions(plugin.tile.max as Size, grid);
    return choices.filter((size) => { const d = dimensions(size, grid);
      return d.columns >= least.columns && d.rows >= least.rows && d.columns <= most.columns && d.rows <= most.rows; });
  }
  // The energy card's diagram takes a size it fits (app 0.4.77): on a small glass a page of its own, never a single cell.
  if (tile.entity === "screen.energy") return choices.filter((size) => {
    const { columns, rows } = dimensions(size, grid);
    return energyFits(screenShape.value, grid.columns, grid.rows, columns, rows);
  });
  return choices;
}
/** Edge resizing keeps the anchor and every neighbouring tile in place. */
export function resizeChoices(tile: Tile, axis: 'columns' | 'rows'): Size[] {
  const current = currentView(tile);
  if (!current || !state.layout || (axis === 'rows' && !inv().tallerTilesEnabled)) return [];
  const before = dimensions(sizeOf(current), grid), other = axis === 'columns' ? 'rows' : 'columns';
  const taken = occupied(entriesOf(state.layout).filter(entry => entry.tile.id !== current.id));
  const owned = state.document?.pages.flatMap(page => page.tiles).find(item => item.id === current.id);
  return tileSizeChoices(current).filter(size => {
    // The handles are the only way to size a tile (app 0.4.32), the whole page too: it keeps its top left corner, so
    // a tile there grows into the page and a page shrinks back into a tile.
    const start = size === 'full' ? current.slot - (current.slot % grid.slots) : current.slot;
    if (!owned || dimensions(size, grid)[other] !== before[other] || start !== current.slot || !fits(taken, current.slot, size)) return false;
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
    // A Go to page tile has no controls at all (app 0.4.1): writing 'none' there made the add-on refuse the resize.
    if (owned.placement.rows === 1 && dimensions(size, grid).rows > 1 && owned.interaction.controls === undefined && owned.content.kind !== "navigation")
      owned.interaction.controls = effectiveControls(current, inv().inventory) || 'none';
    Object.assign(owned.placement, dimensions(size, grid));
    if (size === 'single') delete owned.appearance.presentation;
    else owned.appearance.presentation = size;
  });
}
// Inspector resizing may find the nearest fitting rectangle. Edge handles above
// keep the anchor fixed so that dragging an edge never moves the tile.
export function setTileOption(tile: Tile, key: string, value: unknown, field?: string) {
  if (!state.layout) return;
  const layout = pages.clone(state.layout);
  tile = currentView(tile, layout) || tile;
  const domain = tile.entity.split(".")[0], caps = useEntitiesStore().capabilities[tile.entity], wasSize = sizeOf(tile);
  // Beyond single, wide and the whole page, a size is one the screen said it takes (tall and square 0.3.1, spans 0.19.0).
  if (key === "size" && !["single", "wide", "full"].includes(String(value)) && ((isTallSize(value) && !inv().tallerTilesEnabled) || !screenSizes().includes(String(value)))) return;
  if (key === "size" && isTallSize(value) && sizeColumns(value) === 1 && ["forecast", "sunpath"].includes(String(tile.options?.display))) return;
  // Perform action is a choice with a second step (app 0.4.0, GitHub #47): nothing is stored until an action is
  // chosen, which comes here as `action` and brings the tap choice with it.
  if (key === "tap" && value === "action" && !tile.options?.action) return;
  const previousControls = effectiveControls(tile, inv().inventory);
  // Direct controls need the standard layout without a mini slider, and vice versa (tile-options.ts).
  tile.options = coupledOptions(tile.options, key, value, Boolean(inv().inventory.controls?.[domain]));
  if (key === 'size' && isTallSize(value) && dimensions(wasSize, grid).rows === 1 && !('controls' in tile.options))
    tile.options.controls = previousControls || 'none';
  if (key === "display" && ["forecast", "sunpath"].includes(value as string) && !isWide(tile)) tile.options.size = "wide";
  // A card that becomes wide gets the first direct control Home Assistant offers when the usual one isn't there.
  const catalogue = inv().inventory.controls?.[domain];
  if (key === "size" && value !== "full" && sizeColumns(value) > 1 && caps && catalogue && !("controls" in tile.options) && !caps.controls.includes(catalogue.default))
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
  // What the add-on would still change is never stored (its canonical form): a default, a stale action or picture setting.
  tile.options = canonicalOptions(tile.entity, tile.options, tile.in !== undefined);
  normalize(layout);
  commitArrangement(layout.tiles.map((item) => ({ tile: item, slot: item.slot })), field);
}
// A navigation tile goes to another page: its entity changes (screen.page_<n>). One tile per page it goes to, unless
// the firmware takes several (0.2.65). The page after the last one becomes a new, empty page to fill (app 0.2.78).
export function retargetPageTile(tile: Tile, page: number) {
  if (!tile.id || !Number.isInteger(page) || page < 1 || page > grid.pages) return false;
  if (!scr().pageTilesRepeat && state.layout?.tiles.some((other) => other.id !== tile.id && pageTarget(other.entity) === page)) {
    toast(t("editor.layout.page_taken", { page })); return false;
  }
  return editDocument((draft) => {
    while (draft.pages.length < page) draft.pages.push(pages.emptyPage(draft.pages.at(-1)!.topbar));
    const source = draft.pages.flatMap((item) => item.tiles).find((item) => item.id === tile.id);
    if (!source || source.content.kind !== "navigation") throw new Error(t("addon.errors.pages.tile_missing"));
    // A link that follows Home stays one when the page it is sent to is the home page (app 0.4.2): it keeps following
    // Home when another page becomes it, instead of turning into a fixed link to this page.
    if (source.content.target.kind === "home" && draft.pages[page - 1].id === draft.homePageId) return;
    source.content.target = { kind: "page", pageId: draft.pages[page - 1].id };
  });
}
// Perform action with its action (app 0.4.0, GitHub #47): the tap choice and the action go into the document together,
// and typing in one of the action's fields is one step of undo, as typing a name is.
export function setTileAction(tile: Tile, action: { action: string; data?: Record<string, unknown> }, field?: string) {
  return editDocument((draft) => {
    const found = draft.pages.flatMap((page) => page.tiles).find((item) => item.id === tile.id);
    if (!found) throw new Error(t("addon.errors.pages.tile_missing"));
    found.interaction.tap = "action";
    found.interaction.action = pages.clone(action);
  }, field);
}
export function setTileName(tile: Tile, value: string) {
  editDocument((draft) => {
    const tiles = draft.pages.flatMap((page) => page.tiles);
    const found = tiles.find((item) => item.id === tile.id) || tiles.flatMap((item) => item.children || []).find((child) => child.id === tile.id);
    if (found) found.appearance.label = value;
  }, `tile:${tile.id}`);
}
/** A key dragged onto an empty cell becomes a tile there, the same tile: its id, name, icon and tap go along. */
export function keyToCell(tile: Tile, slot: number) {
  if (!tile.id || !state.documentGrid) return false;
  const cells = state.documentGrid.columns * state.documentGrid.rows, columns = state.documentGrid.columns;
  return editDocument((draft) => {
    let child: ChildTile | undefined;
    for (const page of draft.pages) for (const item of page.tiles) if (item.children) {
      const found = item.children.find((c) => c.id === tile.id);
      if (found) { child = found; item.children = item.children.filter((c) => c !== found); if (!item.children.length) delete item.children; }
    }
    const page = draft.pages[Math.floor(slot / cells)];
    if (!child || !page) return;
    page.tiles.push({ id: child.id, content: child.content, appearance: { ...child.appearance }, interaction: { ...child.interaction },
      placement: { row: Math.floor((slot % cells) / columns), column: slot % columns, columns: 1, rows: 1 } });
  });
}
/** Put a tile on a key place under a bedside clock (app 0.4.12): a new entity takes the place, a key from another place
 * trades places with what stands there, and a tile from the grid moves off its cell to become that key. Only what a
 * key keeps of a tile goes along: its name, icon and tap. */
export function placeKey(tile: Tile, holder: Tile, key: number) {
  return editDocument((draft) => {
    const tiles = draft.pages.flatMap((page) => page.tiles), clock = tiles.find((item) => item.id === holder.id);
    if (!clock) return;
    const children = clock.children || [];
    const from = tile.id ? children.findIndex((child) => child.id === tile.id) : -1;
    if (from >= 0) {
      const to = Math.min(key, children.length - 1);
      [children[from], children[to]] = [children[to], children[from]];
    } else {
      if (tile.id) for (const page of draft.pages) {
        page.tiles = page.tiles.filter((item) => item.id !== tile.id);
        for (const item of page.tiles) if (item !== clock && item.children) item.children = item.children.filter((child) => child.id !== tile.id);
      }
      const child = pages.childOf(tile, tile.id || pages.instanceId());
      if (key < children.length) children[key] = child; else children.push(child);
    }
    clock.children = children;
  });
}

// ---- Inspector (the drawer) ----
export function openTile(tile: Tile) {
  if (!isSelected(tile)) { state.iconPickerOpen = false; state.actionPickerOpen = false; state.actionSearch = ""; }
  state.selectedTileId = tile.id || null;
  state.selectedPageId = state.document?.pages.find((page) => page.tiles.some((item) => item.id === tile.id ||
    item.children?.some((child) => child.id === tile.id)))?.id || state.selectedPageId;
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
  const order = useDragStore().page?.order;
  return pageTitle(order ? order[page] ?? page : page) || state.layout?.title || "";
};
export function setPageTitle(page: number, value: string) {
  editDocument((draft) => { if (draft.pages[page]) draft.pages[page].topbar.title = value.trim() ? { source: "text", text: value } : { source: "screen" }; }, `page:${state.document?.pages[page]?.id}`);
}
// `page` is the page whose bar was clicked (app 0.2.105): the inspector changes that page's own title there,
// which is where you look for it after clicking the bar.
export function openBar(index: number, page = state.barPage) {
  if (!(state.inspector?.kind === "bar" && state.inspector.index === index)) state.iconPickerOpen = false;
  state.selectedTileId = null;
  state.selectedPageId = state.document?.pages[page]?.id || null;
  state.inspector = { kind: "bar", index };
}
export function openBarAdd() {
  state.selectedTileId = null;
  state.inspector = { kind: "bar-add" };
}
// The drawer of one entity of the screensaver clock's row (app 0.4.81, stores/screensaver.ts).
export function openSaverItem(index: number) {
  if (!(state.inspector?.kind === "saver-item" && state.inspector.index === index)) state.iconPickerOpen = false;
  state.selectedTileId = null;
  state.inspector = { kind: "saver-item", index };
}
// One step of the screensaver in the drawer: its players, its camera or its clock.
export function openSaverStep(step: SaverKind) {
  state.iconPickerOpen = false;
  state.selectedTileId = null;
  state.inspector = { kind: "saver", step };
}
export function openSaverAdd() {
  state.selectedTileId = null;
  state.inspector = { kind: "saver-add" };
}
export function closeInspector() {
  state.inspector = null;
  state.selectedTileId = null;
  state.optionPreview = null;
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
  state.dirty = !pages.sameValue(state.document, committedLayout) || !pages.sameValue(state.documentGrid, committedGrid) || state.documentUpright !== committedUpright;
  state.conflict = false;
  if (edits === sent) { state.saved = Date.now(); toast(t("editor.screen_view.saved.current")); }
  else toast(t("editor.screen_view.saved.newer_edit"));
}
export async function save() {
  const screen = scr().selected, open = scr().currentScreen;
  if (state.busy || !state.document || !screen || !state.documentGrid) return;
  if (open?.virtual) {
    try {
      const layout = pages.clone(pages.validatePages(state.document, screenGridOf(state.documentGrid)));
      const record: PageDocument = { format: 'pages-v2', revision: pages.instanceId(), layout,
        sourceGrid: pages.clone(state.documentGrid), workspace: { ...pages.clone(state.workspace), revision: pages.instanceId() } };
      const updated = { ...open, page_document: record, source_grid: record.sourceGrid,
        layout: pages.projectLayout(layout, record.sourceGrid) };
      inv().persistVirtualScreens(inv().inventory.screens.map(item => item.id === open.id ? updated : item));
      Object.assign(open, updated);
      acceptSave(record, layout, record.workspace, edits);
      toast(t('editor.preview.saved'));
    } catch (error: any) { toast(error.message); }
    return;
  }
  state.busy = true;
  const sent = edits, selection = selectionEpoch, submitted = pages.clone(state.document), submittedGrid = pages.clone(state.documentGrid);
  const workspace = state.workspaceDirty ? pages.clone(state.workspace) : undefined;
  // Another grid, or the screen stood up or laid down (app 0.4.85): the add-on takes it as a reviewed adaptation.
  const submittedUpright = state.documentUpright, turned = submittedUpright !== null && submittedUpright !== committedUpright;
  const adaptation = committedGrid && (turned || !pages.sameGrid(committedGrid, submittedGrid))
    ? { from: committedGrid, to: submittedGrid, ...(turned ? { upright: submittedUpright } : {}) } : undefined;
  const request = { format: "pages-v2", revision: state.documentRevision, layout: submitted, ...(workspace ? { workspace } : {}), ...(adaptation ? { adaptation } : {}) };
  try {
    const result = await send<{ saved: boolean; document: PageDocument }>(`screens/${encodeURIComponent(screen)}`, "PUT", request);
    if (scr().selected === screen && selection === selectionEpoch) { committedUpright = submittedUpright; acceptSave(result.document, submitted, workspace, sent); }
    else toast(t("editor.screen_view.saved.other", { name: inv().inventory.screens.find((s) => s.id === screen)?.name || screen }));
    await inv().refresh(false);
  } catch (error: any) {
    // A lost HTTP answer does not prove the save failed. Read the authoritative
    // revision before another attempt; edits made meanwhile remain the draft.
    try {
      const inventory = await getJson<Inventory>("inventory?light=1");
      const record = inventory.screens.find((item) => item.id === screen)?.page_document;
      if (scr().selected === screen && selection === selectionEpoch && savedDraft(record, submitted, submittedGrid, workspace)) {
        acceptSave(record, submitted, workspace, sent);
        return;
      }
      if (scr().selected === screen && selection === selectionEpoch && record?.format === "pages-v2" && record.revision !== state.documentRevision) state.conflict = true;
    } catch { /* Keep the draft and its expected revision until the server can be reached. */ }
    toast(error.message);
  } finally {
    state.busy = false;
    if (state.workspaceDirty) scheduleWorkspaceSave();
  }
}
const mapSaver = workspaceSaver(state, {
  epoch: () => selectionEpoch, selected: () => scr().selected, committed: () => committedLayout,
  put: async (id, revision, workspace) => {
    const screen = inv().inventory.screens.find(item => item.id === id);
    if (screen?.virtual && screen.page_document?.format === 'pages-v2') {
      const saved = { ...pages.clone(workspace), revision: pages.instanceId() };
      const updated = { ...screen, page_document: { ...screen.page_document, workspace: saved } };
      inv().persistVirtualScreens(inv().inventory.screens.map(item => item.id === id ? updated : item));
      Object.assign(screen, updated);
      return saved;
    }
    return send<PageWorkspace>(`screens/${encodeURIComponent(id)}/workspace`, 'PUT', { revision, workspace });
  },
  error: (error: any) => toast(error.message),
});
function scheduleWorkspaceSave() { mapSaver.schedule(); }
export async function saveWorkspace() { await mapSaver.save(); }

// ---- Copying and sharing a layout (app 0.2.73) ----
function adopt(record: PageDocument, message: string) {
  if (!state.documentGrid) return;
  if (!pages.sameGrid(record.sourceGrid, state.documentGrid)) return reviewGrid(record, state.documentGrid, true, message);
  try {
    const copied = pages.remapLayout(record.layout, heldTo(state.documentGrid)), idMap = new Map(record.layout.pages.map((page, index) => [page.id, copied.pages[index].id]));
    applyDocument(copied);
    state.workspace.positions = Object.fromEntries(Object.entries(record.workspace?.positions || {}).map(([id, point]) => [idMap.get(id)!, pages.clone(point)]));
    state.workspaceDirty = true;
    closeInspector(); loadCapabilities(state.layout!.tiles.map((tile) => tile.entity)); loadStates();
    toast(message);
  } catch (error: any) { toast(error.message); }
}
// The grids the open screen takes the way its glass hangs now (firmware 0.53.0+), null for a screen that keeps the grid
// it was built with.
// The way of the draft: standing up or lying down as the draft says on glass that turns, else as the screen hangs.
export const gridWay = storeComputed(() => {
  const grids = scr().currentScreen?.grids;
  if (!grids) return null;
  const upright = state.documentUpright ?? grids.upright;
  return grids[upright ? 'portrait' : 'landscape'];
});
export const takesGrid = (grid: PageGrid) => {
  const way = gridWay.value;
  return !!way && grid.columns >= way.min[0] && grid.columns <= way.max[0] && grid.rows >= way.min[1] && grid.rows <= way.max[1];
};
// A screen that takes the draft's grid is given it with the layout: only a grid it cannot take asks for a review.
export const gridChanged = storeComputed(() => {
  const shape = scr().currentScreen?.shape;
  return !!state.documentGrid && !!shape && !pages.sameGrid(state.documentGrid, shape) && !takesGrid(state.documentGrid);
});
// Stand the open screen up or lay it down (app 0.4.85, on glass that turns): the draft goes on the grid the screen keeps
// for that way, or where its tiles need more pages than the screen takes there, on the grid of that way nearest to it that
// holds them; laid out on it at once as for any other grid. The screen turns and starts again with the next save.
export function chooseHang(upright: boolean) {
  const grids = scr().currentScreen?.grids;
  if (!state.document || !state.documentGrid || !grids || state.documentUpright === null || state.documentUpright === upright) return;
  const way = grids[upright ? 'portrait' : 'landscape'], kept = way.columns * way.rows;
  const candidates: PageGrid[] = [];
  for (let columns = way.min[0]; columns <= way.max[0]; columns++)
    for (let rows = way.min[1]; rows <= way.max[1]; rows++) candidates.push({ columns, rows });
  candidates.sort((a, b) => Number(!pages.sameGrid(a, way)) - Number(!pages.sameGrid(b, way))
    || Math.abs(a.columns * a.rows - kept) - Math.abs(b.columns * b.rows - kept) || Math.abs(a.columns - way.columns) - Math.abs(b.columns - way.columns));
  let first: Error | null = null;
  for (const target of candidates) {
    try {
      pages.adaptGrid(state.document, heldTo(state.documentGrid), screenGridOf(target));
      return hangOn(upright, target);
    } catch (error: any) { first ??= error; }
  }
  if (first) toast(first.message);
}
function hangOn(upright: boolean, target: PageGrid) {
  if (!state.document || !state.documentGrid) return;
  try {
    const adapted = pages.adaptGrid(state.document, heldTo(state.documentGrid), screenGridOf(target));
    const added = adapted.pages.length - state.document.pages.length;
    const before = snapshot();
    if (!applyDocument(adapted, true, target)) { draftHistory.remember(before); historyCounts(); }
    state.documentUpright = upright;
    markDirty();
    if (added > 0) toast(t('editor.grid.pages_added', { n: added }, added));
  } catch (error: any) { toast(error.message); }
}
// Another grid for the open screen, chosen beside the mockup (app 0.4.85): the draft is laid out on it at once (adaptGrid:
// what no longer fits moves on to a new page after its own) and goes to the screen with the next save. Undo takes it back.
export function chooseGrid(columns: number, rows: number) {
  if (!state.document || !state.documentGrid) return;
  const target = { columns, rows };
  if (pages.sameGrid(target, state.documentGrid) || !takesGrid(target)) return;
  try {
    const adapted = pages.adaptGrid(state.document, heldTo(state.documentGrid), screenGridOf(target));
    const added = adapted.pages.length - state.document.pages.length;
    applyDocument(adapted, true, target);
    if (added > 0) toast(t('editor.grid.pages_added', { n: added }, added));
  } catch (error: any) { toast(error.message); }
}
function reviewGrid(record: PageDocument, target: PageGrid, copy: boolean, message = '') {
  try {
    if (record.layout.pages.length > editorLayout.grid.pages) throw new Error(t("addon.errors.pages.adapt_pages"));
    state.gridReview = { record: pages.clone(record), layout: pages.adaptGrid(record.layout, heldTo(record.sourceGrid), screenGridOf(target)),
    target: { columns: target.columns, rows: target.rows }, copy, message }; }
  catch (error: any) { toast(error.message); }
}
export function reviewScreenGrid() {
  const shape = scr().currentScreen?.shape;
  if (!state.document || !state.documentGrid || !shape) return;
  reviewGrid({ format: 'pages-v2', layout: state.document, sourceGrid: state.documentGrid, revision: state.documentRevision || '' }, shape, false);
}
export function acceptGridReview() {
  const review = state.gridReview;
  if (!review) return;
  state.gridReview = null;
  if (review.copy) adopt({ ...review.record, layout: review.layout, sourceGrid: review.target }, review.message);
  else applyDocument(review.layout, true, review.target);
}
export function copyLayoutFrom(id: string) {
  const other = inv().inventory.screens.find((screen) => screen.id === id);
  if (other?.page_document?.format !== "pages-v2") { toast(t("editor.layout.copy_needs_migration")); return; }
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
  const name = `${slug(scr().currentScreen?.name || "screen", { trim: false })}.layout.json`;
  const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
  void useUiStore().copyText(text, undefined, "layout_json");
}
export async function importLayout(text: string) {
  let data: any;
  try { data = JSON.parse(text); } catch { toast(t("editor.layout.not_json")); return; }
  const screen = scr().selected, selection = selectionEpoch;
  if (!screen || !state.documentGrid) return;
  if (data?.esp_screens_layout !== 2 && !(await askConfirm(t("addon.errors.pages.import_grid", { columns: state.documentGrid.columns, rows: state.documentGrid.rows })))) return;
  try {
    const path = scr().currentScreen?.virtual ? 'firmware-preview/import' : `screens/${encodeURIComponent(screen)}/import`;
    const record = await send<PageDocument>(path, "POST", {
      document: data, sourceGrid: data?.sourceGrid || state.documentGrid,
    });
    if (scr().selected === screen && selection === selectionEpoch) adopt(record, t("editor.layout.imported"));
  } catch (error: any) { toast(error.message); }
}

// ---- What the screen's settings mean for its pages (stores/settings.ts) ----
export function pageReachWarning() {
  if (!state.document) return "";
  const result = pages.reachability(state.document, useSettingsStore().navigationSettings());
  const named = (ids: string[]) => t("editor.screen_settings.reach.pages", {
    list: andList(ids.map((id) => state.document!.pages.findIndex((page) => page.id === id) + 1)),
  }, ids.length);
  const messages: string[] = [];
  if (result.unreachable.length) messages.push(t("editor.pages.unreachable", { pages: named(result.unreachable) }));
  if (result.noWayHome.length) messages.push(t("editor.pages.no_way_home", { pages: named(result.noWayHome) }));
  return messages.join(" ");
}
// ---- The Tessera skill for Claude Code in Home Assistant (Settings), which the add-on writes ----
export async function installClaudeSkill() {
  try {
    inv().inventory.claude_skill = await send("claude-skill", "POST");
    toast(t(inv().inventory.claude_skill?.restart ? "editor.settings.claude.installed_restart" : "editor.settings.claude.installed"));
  } catch (e: any) {
    toast(e.message);
  }
}

/** Resolve against a fresh server revision; failed requests always retain the draft. */
export async function dismissMigrationNote() {
  const screen = scr().currentScreen, record = screen?.page_document;
  if (!screen || record?.format !== 'pages-v2') return;
  try {
    await send(`screens/${encodeURIComponent(screen.id)}/migration/dismiss`, 'POST', { revision: record.revision });
    await inv().refresh(false);
  } catch (error: any) { toast(error.message); }
}

export async function startFreshLayout() {
  const screen = scr().currentScreen, record = screen?.page_document;
  if (!screen || record?.format !== 'legacy-v1' || !(await askConfirm(t('editor.pages.start_fresh_confirm')))) return;
  try {
    await send(`screens/${encodeURIComponent(screen.id)}/migration/reset`, 'POST', { revision: record.migrationRevision });
    await inv().refresh(false);
  } catch (error: any) { toast(error.message); }
}

export async function resolveLayoutConflict(choice: 'reload' | 'keep') {
  await resolveConflict(choice, state, {
    epoch: () => selectionEpoch, selected: () => scr().selected, reachable: () => inv().reachable, refresh: () => inv().refresh(false),
    screen: () => scr().currentScreen,
    load: screen => { closeInspector(); loadDocument(screen); },
    acceptBase: record => { committedLayout = pages.clone(record.layout); committedGrid = pages.clone(record.sourceGrid); },
    save,
  });
}

// A new inventory for the open screen (stores/session.ts arrived): its draft read again when the add-on has a newer one, a
// conflict said when this page has unsaved changes.
export function reconcileDocument() {
  const screen = scr().currentScreen, record = screen?.page_document;
  if (!screen || state.busy) return;
  if (record?.format === "pages-v2" && record.revision !== state.documentRevision) {
    if (state.dirty || state.workspaceDirty) { state.conflict = true; return; }
    const selected = state.selectedPageId, focused = state.focusedPageId, tile = state.selectedTileId;
    loadDocument(screen);
    if (state.document?.pages.some((page) => page.id === selected)) state.selectedPageId = selected;
    if (state.document?.pages.some((page) => page.id === focused)) state.focusedPageId = focused;
    state.selectedTileId = tile && state.layout?.tiles.some((item) => item.id === tile) ? tile : null;
  } else if (record?.format === "pages-v2" && record.workspace && !state.workspaceDirty) {
    state.workspace = pages.clone(record.workspace);
  } else if (!state.documentGrid && screen.source_grid && !state.dirty) loadDocument(screen);
}

// ---- Started once the page is on the screen (stores/session.ts start, from boot.ts) ----
// What the draft does by itself while the page is open: the clocks of the mockup, the live values of its entities, the
// reactions to a change elsewhere, and what the page does when it is closed. Nothing of it starts
// when the module loads, so a test imports the store and starts only what it tests. All of it lives in one scope, and
// the returned function stops it.
let started: (() => void) | null = null;
export function startStore() {
  if (started) return started;
  const scope = effectScope(true);
  scope.run(() => {
    // The screensaver's drawers belong to the settings: they close when the layout comes back.
    watch(() => state.tab, (tab) => { if (tab !== "settings" && state.inspector?.kind.startsWith("saver")) closeInspector(); });
    const ui = useUiStore(), dragging = useDragStore();
    // The mockup's clocks tick while a screen is open and the page in sight, and hold still while a tile is dragged; the
    // entity values in its top bar follow Home Assistant as they tick.
    const editing = () => Boolean(state.layout) && !dragging.active;
    useClock(30000, { now: toRef(ui, "now"), when: editing });
    // The mockup follows Home Assistant while it is on screen.
    useVisibleInterval(loadStates, 8000, { when: () => Boolean(state.layout) && state.tab === "layout" && ui.route === "" });
    useEventListener(window, "beforeunload", (e: BeforeUnloadEvent) => {
      if (state.dirty) { e.preventDefault(); e.returnValue = ""; }
    });
  });
  started = () => { started = null; scope.stop(); };
  return started;
}
// ---- A fresh start (tests/setup.ts, between tests) ----
// Every field back to how it starts, and what the module keeps outside the state forgotten: the committed draft and its
// undo, the timers still waiting. A request still on its way finds another
// selection and keeps its answer to itself. What the stores keep (stores/) goes with each test's pinia.
function resetStore() {
  started?.();
  Object.assign(state, fresh());
  screenKept = null;
  generation.value++;
  addedExpiry.stop();
  mapSaver.cancel();
  edits = 0; selectionEpoch++;
  committedLayout = null; committedGrid = null; committedUpright = null;
  draftHistory.clear();
  focusedField = null; groupedEdit = -1;
}
onReset(resetStore);
