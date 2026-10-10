// The draft of the open screen: its page document as the editor changes it (with its grid and the way it hangs), the
// revision it started from and what was saved of it last (so what is unsaved is worked out, not kept), undo, saving it and
// the map of pages beside it, a conflict with a newer save and its resolution, another grid or way of hanging chosen,
// copying, importing and exporting a layout, which page, map page and tile are chosen (they are part of every undo step),
// and what the screen's own shape and memory mean for this draft. The big edits of tiles and pages are plain functions
// over this store (editor/tiles.ts, editor/pages.ts); the drawer beside the mockup is the inspector's (stores/inspector.ts),
// which follows the draft and is told when it is replaced as a whole (onReplaced): nothing here reaches into it.
import { useEventListener, useTimeoutFn } from "@vueuse/core";
import { defineStore } from "pinia";
import { computed, effectScope, markRaw, onScopeDispose, ref, shallowRef, toRef } from "vue";
import { getJson, send } from "../api";
import { t } from "../i18n";
import { useClock } from "../composables/useClock";
import { askConfirm } from "../composables/useConfirm";
import { usePreference } from "../composables/usePreference";
import { useVisibleInterval } from "../composables/useVisibleInterval";
import { describeChange, label, type ChangeLabel } from "../model/change-label";
import { DraftHistory, type HistoryScope } from "../model/draft-history";
import { createLayout } from "../model/layout";
import { memoryUse } from "../model/memory";
import { SMALLEST } from "../model/overview";
import { savedDraft } from "../model/page-conflict";
import { completePositions } from "../model/page-workspace";
import * as pages from "../model/pages";
import { slug } from "../model/slug";
import type { ChildTile, Inventory, Layout, PageDocument, PageGrid, PageLayout, PageTile, PageWorkspace, Screen, Tile } from "../types";
import { useDragStore } from "./drag";
import { useEntitiesStore } from "./entities";
import { useInventoryStore } from "./inventory";
import { lookups } from "./lookup";
import { usePluginsStore } from "./plugins";
import { useScreenStore } from "./screen";
import { useUiStore } from "./ui";

export type EditorMode = "simple" | "advanced";
// A layout copied, imported or put on another grid, shown on the new grid before it is taken (GridReview.vue).
export type GridReview = { record: PageDocument; layout: PageLayout; target: PageGrid; copy: boolean; message: string; said?: ChangeLabel };
// One step of undo: the draft, its grid and way, the map, and what was chosen.
type DraftSnapshot = { layout: PageLayout; grid: PageGrid; upright: boolean | null; positions: PageWorkspace["positions"]; page: string | null; tile: string | null };
// Whoever shows something of the draft (the inspector) is told when it is replaced as a whole: `opened` when a screen was
// opened or closed, not when the same screen's draft was replaced (a copy, an import, the saved one read again).
export type Replaced = (opened: boolean) => void;

export const useDocumentStore = defineStore("document", () => {
  const inv = useInventoryStore();
  const ui = useUiStore();
  const scr = useScreenStore();
  const entities = useEntitiesStore();
  const plugins = usePluginsStore();
  const dragging = useDragStore();

  // ---- The draft ----
  const document = ref<PageLayout | null>(null);
  const documentGrid = ref<PageGrid | null>(null);
  // Whether the draft stands the screen up (app 0.4.85, firmware 0.53.0+): true or false on glass that turns, null else.
  const documentUpright = ref<boolean | null>(null);
  const documentRevision = ref<string | null>(null);
  const workspace = ref<PageWorkspace>({ revision: "", positions: {} });
  const workspaceDirty = ref(false);
  const gridReview = ref<GridReview | null>(null);
  const conflict = ref(false);
  const busy = ref(false);
  // When the last save of every edit went through (the "Sent" note), 0 once there is another edit.
  const saved = ref(0);
  const editorMode = ref<EditorMode>("simple");
  // What is chosen, by id: the page, the page of the map opened to be edited on its own, the tile (several tiles can go to
  // the same page, firmware 0.2.65), and the Go to page tile whose link is being drawn on the map.
  const selectedPageId = ref<string | null>(null);
  const focusedPageId = ref<string | null>(null);
  const selectedTileId = ref<string | null>(null);
  const connectingTileId = ref<string | null>(null);
  // On a phone (app 0.4.40) the tile just added is marked for a moment.
  const justAdded = ref<string | null>(null);

  // The draft as the mockup draws it: a projection worked out again when the draft changes, never edited itself.
  const layout = computed<Layout | null>(() => document.value && documentGrid.value ? pages.projectLayout(document.value, documentGrid.value) : null);
  // The chosen page by its place in the row, for the parts that still count pages.
  const barPage = computed(() => Math.max(0, document.value?.pages.findIndex((page) => page.id === selectedPageId.value) ?? 0));
  // The tile chosen, as the draft has it now.
  const currentTile = computed<Tile | undefined>(() => selectedTileId.value
    ? layout.value?.tiles.find((tile) => tile.id === selectedTileId.value) : undefined);
  const isSelected = (tile: Tile) => Boolean(tile.id) && selectedTileId.value === tile.id;
  // The page drawn at a place in the row: while a page is being moved, not always the page that started there.
  const pageAt = (index: number) => document.value?.pages[dragging.page?.order[index] ?? index];

  // ---- What was saved, and so what is unsaved ----
  // What the add-on holds of this draft: what it was read as, or what the last save sent. Unsaved is the difference.
  const committedLayout = shallowRef<PageLayout | null>(null);
  const committedGrid = shallowRef<PageGrid | null>(null);
  const committedUpright = shallowRef<boolean | null>(null);
  const dirty = computed(() => !pages.sameValue(document.value, committedLayout.value) ||
    !pages.sameValue(documentGrid.value, committedGrid.value) || documentUpright.value !== committedUpright.value);
  // Every edit counts, so a save only clears the edits it sent (app 0.2.78). When the draft last changed, for what this
  // browser keeps of it (stores/drafts.ts): 0 for a draft as it was read.
  let edits = 0;
  const editedAt = ref(0);
  function markEdited() { saved.value = 0; edits++; editedAt.value = Date.now(); }
  // An answer asked for one screen is dropped once another is open, or this one was read again.
  let selectionEpoch = 0;
  function stillSelected() {
    const epoch = selectionEpoch;
    return () => epoch === selectionEpoch;
  }

  // ---- What the screen's shape and firmware mean for this draft ----
  // What the screen being edited looks like. The manager works it out (core.shape_of): what the screen reported itself,
  // else the board package its YAML builds from, else its board. The editor only draws it, and falls back to the smallest
  // screen there is while it has heard nothing at all (SMALLEST).
  const screenShape = computed(() => {
    const shape = scr.currentScreen?.shape;
    if (!shape || !(shape.columns > 0 && shape.rows > 0)) return SMALLEST;
    // A draft that stands the screen up or lays it down (app 0.4.85): the canvas of that way, before the screen turned.
    const upright = documentUpright.value;
    return upright !== null && (shape.height > shape.width) !== upright ? { ...shape, width: shape.height, height: shape.width } : shape;
  });
  // The cells, pages and arrangements of the draft's grid (model/layout.ts), read through it as it changes.
  const editorLayout = markRaw(createLayout(() => documentGrid.value ?? screenShape.value, () => scr.currentScreen?.page_limit));
  // What the screen holds and draws, as the add-on says (app 0.2.78), so a screen whose version Home Assistant can't
  // report for a moment keeps its 48 tiles instead of dropping to ten, and a copied or imported layout isn't cut to ten.
  const tileLimit = computed(() => {
    const limit = scr.currentScreen?.tile_limit;
    return typeof limit === "number" && Number.isInteger(limit) && limit > 0 ? limit : editorLayout.tileLimit(scr.firmwareOf);
  });
  // How much of the screen's memory for its tiles the draft takes (stores/screen.ts screenMemory).
  const memory = computed(() => (scr.screenMemory && !scr.memoryMeasuring && layout.value
    ? memoryUse(layout.value.tiles, scr.screenMemory, document.value?.pages || [], plugins.pluginTileOf) : null));
  // A document's grid with the pages this screen takes (page_limit): what every edit is held to, where a stored document is
  // held to the most any board takes (model/pages.ts pageLimit). Plugin tiles and items are taken where the add-on serves
  // plugins (stores/plugins.ts pluginsEnabled), on the grid of every change (heldTo) as on the screen's.
  const heldTo = (grid: PageGrid): PageGrid => ({ ...grid, plugins: plugins.pluginsEnabled });
  const screenGridOf = (grid: PageGrid): PageGrid => heldTo({ columns: grid.columns, rows: grid.rows, pages: editorLayout.grid.pages, barItems: scr.topbarMax });
  // The grids the open screen takes the way the draft hangs (firmware 0.53.0+): standing up or lying down as the draft says
  // on glass that turns, else as the screen hangs; null for a screen that keeps the grid it was built with.
  const gridWay = computed(() => {
    const grids = scr.currentScreen?.grids;
    if (!grids) return null;
    return grids[(documentUpright.value ?? grids.upright) ? "portrait" : "landscape"];
  });
  const takesGrid = (grid: PageGrid) => {
    const way = gridWay.value;
    return !!way && grid.columns >= way.min[0] && grid.columns <= way.max[0] && grid.rows >= way.min[1] && grid.rows <= way.max[1];
  };
  // A screen that takes the draft's grid is given it with the layout: only a grid it cannot take asks for a review.
  const gridChanged = computed(() => {
    const shape = scr.currentScreen?.shape;
    return !!documentGrid.value && !!shape && !pages.sameGrid(documentGrid.value, shape) && !takesGrid(documentGrid.value);
  });

  // ---- Undo ----
  const history = new DraftHistory<DraftSnapshot>();
  // The history is no reactive object (its steps are whole drafts): every change of it counts this up, and the counts follow.
  const historyVersion = shallowRef(0);
  const counts = computed(() => { historyVersion.value; return history.counts(editorMode.value === "advanced"); });
  const undoCount = computed(() => counts.value.undo);
  const redoCount = computed(() => counts.value.redo);
  // What the next undo and redo do, in words in the editor's language ("Kitchen light moved to page 2"), for the buttons'
  // tooltips and the toast after them; empty when there is nothing to do.
  const said = (change: ChangeLabel | undefined) => change ? (change.count === undefined
    ? t(`editor.undo.what.${change.key}`, change.named || {}) : t(`editor.undo.what.${change.key}`, change.named || {}, change.count)) : "";
  const undoWhat = computed(() => { historyVersion.value; return counts.value.undo ? said(history.peek("undo", editorMode.value === "advanced") || label("changed")) : ""; });
  const redoWhat = computed(() => { historyVersion.value; return counts.value.redo ? said(history.peek("redo", editorMode.value === "advanced") || label("changed")) : ""; });
  // A removal toast, and the one after an undo or redo, only belong to the latest history entry. Once another edit, map
  // move, undo or screen selection changes history, retire it.
  function historyChanged() {
    if (ui.notice?.action?.run === undo || ui.notice?.action?.run === redo) ui.dismissToast();
    historyVersion.value++;
  }
  // A tile's name as the mockup shows it, for the words of a change.
  const nameOf = (tile: PageTile | ChildTile, layout: PageLayout) => {
    if (tile.appearance.label) return tile.appearance.label;
    try { return entities.entityName(tile.content.kind === "entity" ? tile.content.entityId : pages.entityOf(layout, tile as PageTile)); }
    catch { return t("editor.undo.a_tile"); }
  };
  const snapshot = (): DraftSnapshot => ({ layout: pages.clone(document.value!), grid: pages.clone(documentGrid.value!), upright: documentUpright.value,
    positions: pages.clone(workspace.value.positions), page: selectedPageId.value, tile: selectedTileId.value });
  /** A toast that offers to take back what was just done. */
  function undoToast(message: string) {
    ui.toast(message, { label: t("editor.common.undo"), run: undo });
  }

  // ---- Editing ----
  // The draft becomes `next` (and its grid `nextGrid`), checked against what the screen takes, remembered for undo unless
  // `remember` is false, with what it did in words: `said`, or worked out from the change (model/change-label.ts). True
  // when anything changed. A change of a page's top bar is the top bar store's (stores/topbar.ts).
  function applyDocument(next: PageLayout, remember = true, nextGrid = documentGrid.value, said?: ChangeLabel) {
    if (!document.value || !documentGrid.value || !nextGrid) return false;
    pages.validatePages(next, screenGridOf(nextGrid));
    if (pages.sameValue(next, document.value) && pages.sameGrid(nextGrid, documentGrid.value)) return false;
    if (remember) {
      history.remember(snapshot(), "document", said ?? describeChange(document.value, next, documentGrid.value, nextGrid, nameOf));
      historyChanged();
    }
    documentGrid.value = pages.clone(nextGrid);
    document.value = next;
    const ids = new Set(next.pages.map((page) => page.id));
    const positions = Object.fromEntries(Object.entries(workspace.value.positions).filter(([id]) => ids.has(id)));
    if (Object.keys(positions).length !== Object.keys(workspace.value.positions).length) {
      workspace.value.positions = positions; workspaceDirty.value = true;
    }
    if (editorMode.value === "advanced" || Object.keys(positions).length) initializeWorkspace();
    if (selectedPageId.value && !ids.has(selectedPageId.value)) selectedPageId.value = next.homePageId;
    if (focusedPageId.value && !ids.has(focusedPageId.value)) focusedPageId.value = null;
    // A key under a bedside clock is a child of its clock: a change to it keeps it chosen like any tile. A tile that went
    // is no longer chosen, and its drawer closes (stores/inspector.ts follows the chosen tile).
    const selected = selectedTileId.value;
    if (selected && !next.pages.some((page) => page.tiles.some((tile) => tile.id === selected || tile.children?.some((child) => child.id === selected))))
      selectedTileId.value = null;
    markEdited();
    return true;
  }
  // Typing in one field is one step of undo (app 0.4.2): an edit of the field focused (beginFieldEdit) right after the last
  // one of it joins that step.
  let focusedField: string | null = null, groupedEdit = -1;
  function beginFieldEdit(key: string) { focusedField = key; groupedEdit = -1; }
  function endFieldEdit() { focusedField = null; groupedEdit = -1; }
  /** The draft becomes `next` as an edit of `field`, if one is given. True when anything changed. */
  function applyEdit(next: PageLayout, field?: string) {
    const grouped = field !== undefined && focusedField === field;
    const changed = applyDocument(next, !(grouped && groupedEdit === edits));
    if (changed) groupedEdit = grouped ? edits : -1;
    return changed;
  }
  /** An edit of the draft in place (model/pages.ts changePages); a refused one is said, and changes nothing. */
  function editDocument(apply: (draft: PageLayout) => void, field?: string) {
    if (!document.value || !documentGrid.value) return false;
    try { return applyEdit(pages.changePages(document.value, heldTo(documentGrid.value), apply), field); }
    catch (error: any) { ui.toast(error.message); return false; }
  }
  function restoreSnapshot(value: DraftSnapshot, scope: HistoryScope) {
    endFieldEdit();
    if (scope === "document") {
      const positions = pages.clone(workspace.value.positions);
      documentUpright.value = value.upright;
      applyDocument(value.layout, false, value.grid);
      markEdited();
      // Keep current positions; recover a deleted page's position from its snapshot.
      workspace.value.positions = Object.fromEntries(value.layout.pages.flatMap((page) => {
        const point = positions[page.id] || value.positions[page.id];
        return point ? [[page.id, point]] : [];
      }));
      selectedPageId.value = value.page;
      selectedTileId.value = layout.value?.tiles.some((tile) => tile.id === value.tile) ? value.tile : null;
    } else {
      const ids = new Set(document.value!.pages.map((page) => page.id));
      workspace.value.positions = Object.fromEntries(Object.entries(value.positions).filter(([id]) => ids.has(id)));
    }
    if (editorMode.value === "advanced") initializeWorkspace();
    workspaceDirty.value = true;
    historyChanged();
    scheduleWorkspaceSave();
  }
  // An undo or a redo says what it took back or did again ("Undone: Kitchen light moved to page 2"), with the way back at
  // hand: the change may be on a page out of sight, or on the map.
  function historyStep(direction: "undo" | "redo") {
    if (!document.value || !documentGrid.value) return;
    const entry = history.step(direction, snapshot(), editorMode.value === "advanced");
    if (!entry) return;
    restoreSnapshot(entry.value, entry.scope);
    const what = said(entry.label || label("changed"));
    if (direction === "undo") ui.toast(t("editor.undo.undone", { what }), { label: t("editor.pages.redo"), run: redo });
    else ui.toast(t("editor.undo.redone", { what }), { label: t("editor.common.undo"), run: undo });
  }
  function undo() { historyStep("undo"); }
  function redo() { historyStep("redo"); }

  // The simple or the advanced editor, remembered in this browser per screen: the preference of the open screen.
  const keptMode = usePreference<EditorMode>(() => `esp-screens-mode:${scr.selected ?? ""}`, "simple",
    { serializer: { read: (raw) => (raw === "advanced" ? "advanced" : "simple"), write: (mode) => mode } });
  function setEditorMode(mode: EditorMode) {
    editorMode.value = mode;
    historyChanged();
    focusedPageId.value = null;
    connectingTileId.value = null;
    dragging.clear();
    if (mode === "advanced") initializeWorkspace();
    if (scr.selected) keptMode.value = mode;
  }

  // On a phone the sheet goes and the screen shows the new tile, lit for a moment, with Undo at hand: one tile is the
  // usual errand there, and its settings are one tap away.
  const addedExpiry = useTimeoutFn(() => { justAdded.value = null; }, 2400, { immediate: false });
  function markAdded(tile: Tile) {
    ui.addSheet = false;
    justAdded.value = tile.id || null;
    addedExpiry.start();
    undoToast(t("editor.phone.added", { name: tile.name || entities.entityName(tile.entity) }));
  }

  // ---- Opening and closing a screen's draft ----
  const followers = new Set<Replaced>();
  /** Told when the draft is replaced as a whole; the returned function stops it. */
  function onReplaced(follower: Replaced) {
    followers.add(follower);
    return () => { followers.delete(follower); };
  }
  const replaced = (opened: boolean) => { for (const follower of followers) follower(opened); };
  // The states of the open layout's entities, for the mockup.
  function loadStates() {
    return entities.loadStates((layout.value?.tiles || []).map((tile) => tile.entity), stillSelected());
  }
  // A screen's saved document becomes the draft, with nothing to undo and nothing unsaved: when a screen is opened, when it
  // is read again, and for the tests' fixtures (tests/helpers/fixtures.ts), which so start from what the editor starts from.
  function loadDocument(screen: Screen) {
    endFieldEdit();
    selectionEpoch++;
    const record = screen.page_document;
    document.value = record?.format === "legacy-v1" ? null : record?.format === "pages-v2"
      ? pages.clone(record.layout) : pages.emptyLayout(screen.layout.title || screen.name);
    documentGrid.value = record?.format === "pages-v2" ? pages.clone(record.sourceGrid)
      : screen.source_grid ? pages.clone(screen.source_grid) : null;
    committedLayout.value = pages.clone(document.value);
    committedGrid.value = pages.clone(documentGrid.value);
    documentUpright.value = committedUpright.value = screen.hang ? screen.hang === "portrait" : null;
    gridReview.value = null;
    documentRevision.value = record?.format === "pages-v2" ? record.revision : null;
    workspace.value = record?.format === "pages-v2" && record.workspace ? pages.clone(record.workspace) : { revision: "", positions: {} };
    workspaceDirty.value = false;
    selectedPageId.value = document.value?.homePageId || null;
    focusedPageId.value = null;
    conflict.value = false;
    editedAt.value = 0;
    history.clear(); historyChanged();
  }
  // No draft at all: nothing shown, and nothing unsaved.
  function forgetDraft() {
    document.value = null; documentGrid.value = null; documentUpright.value = null; gridReview.value = null;
    committedLayout.value = null; committedGrid.value = null; committedUpright.value = null;
  }
  // The draft of the screen the session opens (stores/session.ts select), or none: what the editor shows of the screen
  // before starts again. True when there is a screen.
  function openDocument(screen: Screen | undefined) {
    selectedTileId.value = null;
    ui.tab = "layout";
    replaced(true);
    // Nothing chosen (the overview, app 0.4.0): the draft that was confirmed away is gone, so nothing is unsaved.
    if (!screen) { forgetDraft(); return false; }
    loadDocument(screen);
    editorMode.value = keptMode.value;
    if (editorMode.value === "advanced") initializeWorkspace();
    saved.value = 0;
    entities.loadCapabilities(layout.value?.tiles.map((tile) => tile.entity) || []);
    loadStates();
    return true;
  }
  // The open screen's draft gone without a question (stores/session.ts forgetOpenScreen): nothing of it is left to save.
  function closeDocument() {
    selectedTileId.value = null;
    replaced(true);
    forgetDraft();
  }
  // A new inventory for the open screen (stores/session.ts arrived): its draft read again when the add-on has a newer one, a
  // conflict said when this page has unsaved changes.
  function reconcile() {
    const screen = scr.currentScreen, record = screen?.page_document;
    if (!screen || busy.value) return;
    if (record?.format === "pages-v2" && record.revision !== documentRevision.value) {
      if (dirty.value || workspaceDirty.value) { conflict.value = true; return; }
      const page = selectedPageId.value, focused = focusedPageId.value, tile = selectedTileId.value;
      loadDocument(screen);
      if (document.value?.pages.some((item) => item.id === page)) selectedPageId.value = page;
      if (document.value?.pages.some((item) => item.id === focused)) focusedPageId.value = focused;
      selectedTileId.value = tile && layout.value?.tiles.some((item) => item.id === tile) ? tile : null;
    } else if (record?.format === "pages-v2" && record.workspace && !workspaceDirty.value) {
      workspace.value = pages.clone(record.workspace);
    } else if (!documentGrid.value && screen.source_grid && !dirty.value) loadDocument(screen);
  }

  // ---- The map of pages (the advanced editor): positions kept beside the draft, saved on their own ----
  const workspacePositions = () => completePositions(document.value, workspace.value.positions);
  function initializeWorkspace() {
    const positions = workspacePositions();
    if (JSON.stringify(positions) === JSON.stringify(workspace.value.positions)) return;
    workspace.value.positions = positions;
    workspaceDirty.value = true;
    scheduleWorkspaceSave();
  }
  function moveWorkspacePage(id: string, x: number, y: number) {
    endFieldEdit();
    if (!document.value?.pages.some((page) => page.id === id)) return;
    const positions = workspacePositions();
    if (![x, y].every(Number.isInteger) || x < 0 || y < 0 || x > 100 || y > 100) return;
    if (Object.entries(positions).some(([key, point]) => key !== id && point.x === x && point.y === y)) {
      ui.toast(t("editor.pages.position_occupied")); return;
    }
    if (positions[id]?.x === x && positions[id]?.y === y) return;
    history.remember(snapshot(), "workspace", label("map_moved", { page: document.value.pages.findIndex((page) => page.id === id) + 1 })); historyChanged();
    workspace.value.positions = { ...positions, [id]: { x, y } };
    workspaceDirty.value = true; scheduleWorkspaceSave();
  }
  function arrangeFromHome() {
    if (!document.value) return;
    history.remember(snapshot(), "workspace", label("map_arranged")); historyChanged();
    workspace.value.positions = pages.initialPositions(document.value);
    workspaceDirty.value = true; scheduleWorkspaceSave();
  }
  // The map goes to the add-on after a short pause, checked against the draft's revision, one request at a time; a preview
  // screen's stays in this browser. A save that comes back for a screen no longer open changes nothing here, and a map
  // moved while a request was on its way is saved after it.
  let mapTimer = 0, mapFlight = false;
  function scheduleWorkspaceSave() {
    clearTimeout(mapTimer);
    mapTimer = window.setTimeout(saveWorkspace, 400);
  }
  async function putWorkspace(id: string, revision: string, positions: PageWorkspace): Promise<PageWorkspace> {
    const screen = inv.inventory.screens.find((item) => item.id === id);
    if (screen?.virtual && screen.page_document?.format === "pages-v2") {
      const kept = { ...pages.clone(positions), revision: pages.instanceId() };
      const updated = { ...screen, page_document: { ...screen.page_document, workspace: kept } };
      inv.persistVirtualScreens(inv.inventory.screens.map((item) => item.id === id ? updated : item));
      Object.assign(screen, updated);
      return kept;
    }
    return send<PageWorkspace>(`screens/${encodeURIComponent(id)}/workspace`, "PUT", { revision, workspace: positions });
  }
  async function saveWorkspace() {
    const committed = committedLayout.value, screen = scr.selected;
    if (mapFlight || busy.value || conflict.value || !workspaceDirty.value || !screen || !documentRevision.value || !committed) return;
    const ids = new Set(committed.pages.map((page) => page.id));
    if (Object.keys(workspace.value.positions).some((id) => !ids.has(id))) return;
    const epoch = selectionEpoch, sent = pages.clone(workspace.value), revision = documentRevision.value;
    mapFlight = true;
    try {
      const answer = await putWorkspace(screen, revision, sent);
      if (scr.selected === screen && selectionEpoch === epoch) {
        workspace.value.revision = answer.revision;
        workspaceDirty.value = JSON.stringify(workspace.value.positions) !== JSON.stringify(answer.positions);
        if (workspaceDirty.value) scheduleWorkspaceSave();
      }
    } catch (error: any) { ui.toast(error.message); }
    finally {
      mapFlight = false;
      // A timer for a newly selected screen may have fired while the old request was pending. It still deserves its own
      // save afterwards.
      if (selectionEpoch !== epoch && workspaceDirty.value) scheduleWorkspaceSave();
    }
  }

  // ---- Saving ----
  function acceptSave(record: PageDocument, submitted: PageLayout, submittedWorkspace: PageWorkspace | undefined, sent: number) {
    documentRevision.value = record.revision;
    committedLayout.value = pages.clone(submitted);
    committedGrid.value = pages.clone(record.sourceGrid);
    if (record.workspace) {
      workspace.value.revision = record.workspace.revision;
      if (!submittedWorkspace || JSON.stringify(workspace.value.positions) === JSON.stringify(submittedWorkspace.positions)) {
        workspace.value.positions = pages.clone(record.workspace.positions); workspaceDirty.value = false;
      }
    }
    conflict.value = false;
    if (edits === sent) { saved.value = Date.now(); ui.toast(t("editor.screen_view.saved.current")); }
    else ui.toast(t("editor.screen_view.saved.newer_edit"));
  }
  async function save() {
    const screen = scr.selected, open = scr.currentScreen;
    if (busy.value || !document.value || !screen || !documentGrid.value) return;
    if (open?.virtual) {
      try {
        const kept = pages.clone(pages.validatePages(document.value, screenGridOf(documentGrid.value)));
        const record: PageDocument = { format: "pages-v2", revision: pages.instanceId(), layout: kept,
          sourceGrid: pages.clone(documentGrid.value), workspace: { ...pages.clone(workspace.value), revision: pages.instanceId() } };
        const updated = { ...open, page_document: record, source_grid: record.sourceGrid,
          layout: pages.projectLayout(kept, record.sourceGrid) };
        inv.persistVirtualScreens(inv.inventory.screens.map((item) => item.id === open.id ? updated : item));
        Object.assign(open, updated);
        acceptSave(record, kept, record.workspace, edits);
        ui.toast(t("editor.preview.saved"));
      } catch (error: any) { ui.toast(error.message); }
      return;
    }
    busy.value = true;
    const sent = edits, selection = selectionEpoch, submitted = pages.clone(document.value), submittedGrid = pages.clone(documentGrid.value);
    const positions = workspaceDirty.value ? pages.clone(workspace.value) : undefined;
    // Another grid, or the screen stood up or laid down (app 0.4.85): the add-on takes it as a reviewed adaptation.
    const submittedUpright = documentUpright.value, turned = submittedUpright !== null && submittedUpright !== committedUpright.value;
    const from = committedGrid.value;
    const adaptation = from && (turned || !pages.sameGrid(from, submittedGrid))
      ? { from, to: submittedGrid, ...(turned ? { upright: submittedUpright } : {}) } : undefined;
    const request = { format: "pages-v2", revision: documentRevision.value, layout: submitted, ...(positions ? { workspace: positions } : {}), ...(adaptation ? { adaptation } : {}) };
    try {
      const result = await send<{ saved: boolean; document: PageDocument }>(`screens/${encodeURIComponent(screen)}`, "PUT", request);
      if (scr.selected === screen && selection === selectionEpoch) { committedUpright.value = submittedUpright; acceptSave(result.document, submitted, positions, sent); }
      else ui.toast(t("editor.screen_view.saved.other", { name: inv.inventory.screens.find((s) => s.id === screen)?.name || screen }));
      await inv.refresh(false);
    } catch (error: any) {
      // A lost HTTP answer does not prove the save failed. Read the authoritative revision before another attempt; edits
      // made meanwhile remain the draft.
      try {
        const inventory = await getJson<Inventory>("inventory?light=1");
        const record = inventory.screens.find((item) => item.id === screen)?.page_document;
        if (scr.selected === screen && selection === selectionEpoch && savedDraft(record, submitted, submittedGrid, positions)) {
          acceptSave(record, submitted, positions, sent);
          return;
        }
        if (scr.selected === screen && selection === selectionEpoch && record?.format === "pages-v2" && record.revision !== documentRevision.value) conflict.value = true;
      } catch { /* Keep the draft and its expected revision until the server can be reached. */ }
      ui.toast(error.message);
    } finally {
      busy.value = false;
      if (workspaceDirty.value) scheduleWorkspaceSave();
    }
  }
  // A newer save than the one this draft started from (another tab, another browser): the saved one read again, or this
  // draft kept and sent over it. Nothing changes the draft before the add-on has answered; a failed request keeps it.
  async function resolveLayoutConflict(choice: "reload" | "keep") {
    if (busy.value || !conflict.value) return;
    const selected = scr.selected, epoch = selectionEpoch;
    await inv.refresh(false);
    if (!inv.reachable || scr.selected !== selected || selectionEpoch !== epoch) return;
    const screen = scr.currentScreen, record = screen?.page_document;
    if (!screen || record?.format !== "pages-v2") return;
    if (choice === "reload") {
      selectedTileId.value = null;
      replaced(false);
      loadDocument(screen);
      return;
    }
    // Keep mine authorizes only this observed revision. A subsequent concurrent save still fails the server's revision check.
    documentRevision.value = record.revision;
    workspace.value.revision = record.workspace?.revision || "";
    committedLayout.value = pages.clone(record.layout);
    committedGrid.value = pages.clone(record.sourceGrid);
    await save();
  }

  // ---- A draft from elsewhere: kept in this browser, or another tab's (stores/drafts.ts) ----
  // It becomes the draft as one step of undo, said in `said`. One that started from another saved revision than the one
  // read here goes through the conflict: the add-on refuses a save of it until Reload saved or Keep mine is chosen, so a
  // newer save is never written over without a question.
  function takeDraft(draft: { layout: PageLayout; grid: PageGrid; upright: boolean | null; revision: string | null }, said: ChangeLabel) {
    if (!document.value || !documentGrid.value) return false;
    try {
      const before = snapshot();
      const changed = applyDocument(pages.clone(draft.layout), true, { columns: draft.grid.columns, rows: draft.grid.rows }, said);
      if (draft.upright !== documentUpright.value) {
        if (!changed) { history.remember(before, "document", said); historyChanged(); }
        documentUpright.value = draft.upright;
        markEdited();
      }
    } catch (error: any) { ui.toast(error.message); return false; }
    if (draft.revision !== documentRevision.value) { documentRevision.value = draft.revision; conflict.value = true; }
    return true;
  }

  // ---- Another grid, or another way of hanging (app 0.4.85) ----
  // Stand the open screen up or lay it down (on glass that turns): the draft goes on the grid the screen keeps for that way,
  // or where its tiles need more pages than the screen takes there, on the grid of that way nearest to it that holds them;
  // laid out on it at once as for any other grid. The screen turns and starts again with the next save.
  function chooseHang(upright: boolean) {
    const grids = scr.currentScreen?.grids;
    if (!document.value || !documentGrid.value || !grids || documentUpright.value === null || documentUpright.value === upright) return;
    const way = grids[upright ? "portrait" : "landscape"], kept = way.columns * way.rows;
    const candidates: PageGrid[] = [];
    for (let columns = way.min[0]; columns <= way.max[0]; columns++)
      for (let rows = way.min[1]; rows <= way.max[1]; rows++) candidates.push({ columns, rows });
    candidates.sort((a, b) => Number(!pages.sameGrid(a, way)) - Number(!pages.sameGrid(b, way))
      || Math.abs(a.columns * a.rows - kept) - Math.abs(b.columns * b.rows - kept) || Math.abs(a.columns - way.columns) - Math.abs(b.columns - way.columns));
    let first: Error | null = null;
    for (const target of candidates) {
      try {
        pages.adaptGrid(document.value, heldTo(documentGrid.value), screenGridOf(target));
        return hangOn(upright, target);
      } catch (error: any) { first ??= error; }
    }
    if (first) ui.toast(first.message);
  }
  function hangOn(upright: boolean, target: PageGrid) {
    if (!document.value || !documentGrid.value) return;
    try {
      const adapted = pages.adaptGrid(document.value, heldTo(documentGrid.value), screenGridOf(target));
      const added = adapted.pages.length - document.value.pages.length;
      const before = snapshot(), turned = label(upright ? "stood_up" : "laid_down");
      if (!applyDocument(adapted, true, target, turned)) { history.remember(before, "document", turned); historyChanged(); }
      documentUpright.value = upright;
      markEdited();
      if (added > 0) ui.toast(t("editor.grid.pages_added", { n: added }, added));
    } catch (error: any) { ui.toast(error.message); }
  }
  // Another grid for the open screen, chosen beside the mockup (app 0.4.85): the draft is laid out on it at once (adaptGrid:
  // what no longer fits moves on to a new page after its own) and goes to the screen with the next save. Undo takes it back.
  function chooseGrid(columns: number, rows: number) {
    if (!document.value || !documentGrid.value) return;
    const target = { columns, rows };
    if (pages.sameGrid(target, documentGrid.value) || !takesGrid(target)) return;
    try {
      const adapted = pages.adaptGrid(document.value, heldTo(documentGrid.value), screenGridOf(target));
      const added = adapted.pages.length - document.value.pages.length;
      applyDocument(adapted, true, target);
      if (added > 0) ui.toast(t("editor.grid.pages_added", { n: added }, added));
    } catch (error: any) { ui.toast(error.message); }
  }
  function reviewGrid(record: PageDocument, target: PageGrid, copy: boolean, message = "", said?: ChangeLabel) {
    try {
      if (record.layout.pages.length > editorLayout.grid.pages) throw new Error(t("addon.errors.pages.adapt_pages"));
      gridReview.value = { record: pages.clone(record), layout: pages.adaptGrid(record.layout, heldTo(record.sourceGrid), screenGridOf(target)),
        target: { columns: target.columns, rows: target.rows }, copy, message, said };
    } catch (error: any) { ui.toast(error.message); }
  }
  function reviewScreenGrid() {
    const shape = scr.currentScreen?.shape;
    if (!document.value || !documentGrid.value || !shape) return;
    reviewGrid({ format: "pages-v2", layout: document.value, sourceGrid: documentGrid.value, revision: documentRevision.value || "" }, shape, false);
  }
  function acceptGridReview() {
    const review = gridReview.value;
    if (!review) return;
    gridReview.value = null;
    if (review.copy) adopt({ ...review.record, layout: review.layout, sourceGrid: review.target }, review.message, review.said);
    else applyDocument(review.layout, true, review.target);
  }

  // ---- Copying and sharing a layout (app 0.2.73) ----
  // Another layout becomes the draft, with new ids for its pages, as one step of undo; on another grid it is shown first.
  function adopt(record: PageDocument, message: string, said?: ChangeLabel) {
    if (!documentGrid.value) return;
    if (!pages.sameGrid(record.sourceGrid, documentGrid.value)) return reviewGrid(record, documentGrid.value, true, message, said);
    try {
      const copied = pages.remapLayout(record.layout, heldTo(documentGrid.value)), idMap = new Map(record.layout.pages.map((page, index) => [page.id, copied.pages[index].id]));
      applyDocument(copied, true, documentGrid.value, said);
      workspace.value.positions = Object.fromEntries(Object.entries(record.workspace?.positions || {}).map(([id, point]) => [idMap.get(id)!, pages.clone(point)]));
      workspaceDirty.value = true;
      selectedTileId.value = null;
      replaced(false);
      entities.loadCapabilities(layout.value!.tiles.map((tile) => tile.entity)); loadStates();
      ui.toast(message);
    } catch (error: any) { ui.toast(error.message); }
  }
  function copyLayoutFrom(id: string) {
    const other = inv.inventory.screens.find((screen) => screen.id === id);
    if (other?.page_document?.format !== "pages-v2") { ui.toast(t("editor.layout.copy_needs_migration")); return; }
    const copy = pages.clone(other.page_document);
    copy.layout.title = document.value?.title || copy.layout.title;
    adopt(copy, t("editor.layout.copied", { name: other.name }), label("layout_copied", { name: other.name }));
  }
  const layoutJson = () => {
    if (!document.value || !documentGrid.value) return "";
    return JSON.stringify({ esp_screens_layout: 2, sourceGrid: documentGrid.value, layout: document.value,
      editor: { positions: workspacePositions() } }, null, 2);
  };
  function exportLayout() {
    const text = layoutJson();
    if (!text) return;
    const name = `${slug(scr.currentScreen?.name || "screen", { trim: false })}.layout.json`;
    const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
    const a = window.document.createElement("a");
    a.href = url; a.download = name; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
    void ui.copyText(text, undefined, "layout_json");
  }
  async function importLayout(text: string) {
    let data: any;
    try { data = JSON.parse(text); } catch { ui.toast(t("editor.layout.not_json")); return; }
    const screen = scr.selected, selection = selectionEpoch;
    if (!screen || !documentGrid.value) return;
    if (data?.esp_screens_layout !== 2 && !(await askConfirm(t("addon.errors.pages.import_grid", { columns: documentGrid.value.columns, rows: documentGrid.value.rows }),
      { confirm: t("editor.confirm.import") }))) return;
    try {
      const path = scr.currentScreen?.virtual ? "firmware-preview/import" : `screens/${encodeURIComponent(screen)}/import`;
      const record = await send<PageDocument>(path, "POST", {
        document: data, sourceGrid: data?.sourceGrid || documentGrid.value,
      });
      if (scr.selected === screen && selection === selectionEpoch) adopt(record, t("editor.layout.imported"), label("layout_imported"));
    } catch (error: any) { ui.toast(error.message); }
  }

  // ---- A screen saved before page documents (app 0.3.1): its note, or a fresh start ----
  // Resolved against a fresh server revision; failed requests always retain the draft.
  async function dismissMigrationNote() {
    const screen = scr.currentScreen, record = screen?.page_document;
    if (!screen || record?.format !== "pages-v2") return;
    try {
      await send(`screens/${encodeURIComponent(screen.id)}/migration/dismiss`, "POST", { revision: record.revision });
      await inv.refresh(false);
    } catch (error: any) { ui.toast(error.message); }
  }
  async function startFreshLayout() {
    const screen = scr.currentScreen, record = screen?.page_document;
    if (!screen || record?.format !== "legacy-v1" || !(await askConfirm(t("editor.pages.start_fresh_confirm"), { confirm: t("editor.confirm.start_fresh"), danger: true }))) return;
    try {
      await send(`screens/${encodeURIComponent(screen.id)}/migration/reset`, "POST", { revision: record.migrationRevision });
      await inv.refresh(false);
    } catch (error: any) { ui.toast(error.message); }
  }

  // ---- Started once the page is on the screen (stores/session.ts start); the returned function stops it ----
  // What the draft does by itself while the page is open: the clocks of the mockup, the live values of its entities, and
  // the question the browser asks before a page with unsaved changes closes.
  let running: (() => void) | null = null;
  function start() {
    if (running) return running;
    const scope = effectScope(true);
    scope.run(() => {
      // The mockup's clocks tick while a screen is open and the page in sight, and hold still while a tile is dragged; the
      // entity values in its top bar follow Home Assistant as they tick.
      const editing = () => Boolean(layout.value) && !dragging.active;
      useClock(30000, { now: toRef(ui, "now"), when: editing });
      // The mockup follows Home Assistant while it is on screen.
      useVisibleInterval(loadStates, 8000, { when: () => Boolean(layout.value) && ui.tab === "layout" && ui.route === "" });
      useEventListener(window, "beforeunload", (e: BeforeUnloadEvent) => {
        if (dirty.value) { e.preventDefault(); e.returnValue = ""; }
      });
    });
    running = () => { running = null; scope.stop(); };
    return running;
  }
  onScopeDispose(() => { running?.(); clearTimeout(mapTimer); });

  return {
    document, documentGrid, documentUpright, documentRevision, workspace, workspaceDirty, gridReview, conflict, busy, saved, editedAt, editorMode,
    selectedPageId, focusedPageId, selectedTileId, connectingTileId, justAdded,
    layout, barPage, currentTile, dirty, undoCount, redoCount, undoWhat, redoWhat, screenShape, editorLayout, tileLimit, memory, gridWay, gridChanged,
    // What the mockup, the map and the edits read as they go (stores/lookup.ts).
    ...lookups({ isSelected, pageAt, stillSelected, heldTo, screenGridOf, takesGrid, workspacePositions, layoutJson }),
    applyDocument, applyEdit, editDocument, beginFieldEdit, endFieldEdit, undo, redo, undoToast, setEditorMode, markAdded,
    onReplaced, loadStates, loadDocument, openDocument, closeDocument, reconcile,
    moveWorkspacePage, arrangeFromHome, saveWorkspace, save, resolveLayoutConflict, takeDraft,
    chooseHang, chooseGrid, reviewScreenGrid, acceptGridReview, copyLayoutFrom, exportLayout, importLayout,
    dismissMigrationNote, startFreshLayout, start,
  };
});
