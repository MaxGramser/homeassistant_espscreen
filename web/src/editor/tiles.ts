// Editing the draft's tiles (stores/document.ts): a tile added from the library, placed, moved to another page, sized,
// given its options, its action and its name, taken off, and a bedside clock's keys moved between the clock and the grid.
// Plain functions over the stores, as the draft's pages are (editor/pages.ts): each asks for the stores when it is called.
// What a tile may become (its sizes, the handles' choices) is read here as the mockup and the drawer draw it.
import { t } from "../i18n";
import { askConfirm } from "../composables/useConfirm";
import { dimensions, effectiveControls, entriesOf, isFull, isWide, newTile, pageTarget, sizeOf, type Size } from "../model/layout";
import { memoryCrossing } from "../model/memory";
import { suggestedPageTitle } from "../model/page-naming";
import { validateCardOptions } from "../model/page-validation";
import * as pages from "../model/pages";
import { isTallSize, sizeColumns, sizesOn, spanOf, spanOffered } from "../model/sizes";
import { canonicalOptions, coupledOptions } from "../model/tile-options";
import { openTile, state as inspection } from "../store";
import { energyFits } from "../model/ui-scale";
import { useDocumentStore } from "../stores/document";
import { useEntitiesStore } from "../stores/entities";
import { useInventoryStore } from "../stores/inventory";
import { usePluginsStore } from "../stores/plugins";
import { useScreenStore } from "../stores/screen";
import { useUiStore } from "../stores/ui";
import type { ChildTile, Layout, Tile } from "../types";

const toast = (message: string) => useUiStore().toast(message);
// The tile as the draft has it now: a tile from an older drawing of the mockup is found again by its id.
const currentView = (tile: Tile, layout: Layout | null = useDocumentStore().layout) =>
  tile.id ? layout?.tiles.find((item) => item.id === tile.id) : tile;
export const liveEntries = () => { const layout = useDocumentStore().layout; return layout ? entriesOf(layout) : []; };

// Whether a new tile of this entity goes on, as a library click or drag makes it (its own action and line come later, in
// its settings). Past nine tenths of the screen's memory for tiles, and past all of it, the editor asks first. A warning,
// not a rule (app 0.4.61): a screen measured far less room than the screens it was priced on (GitHub #157), and a screen
// protects itself when it runs short, so whoever wants to try may. True at once when there is nothing to ask, else the
// answer to the question (useConfirm).
export function confirmMemory(entity: string): true | Promise<boolean> {
  const scr = useScreenStore(), doc = useDocumentStore(), memory = scr.screenMemory;
  if (!memory || scr.memoryMeasuring || !doc.layout) return true;
  const crossing = memoryCrossing(doc.layout.tiles, { entity }, memory, doc.document?.pages || [], usePluginsStore().pluginTileOf);
  if (!crossing) return true;
  return askConfirm(t(`editor.memory.confirm_${crossing.line}`, { n: Math.min(999, Math.round(crossing.share * 100)) }));
}

// ---- Placing tiles ----
// Apply an arrangement; a new tile joins the layout. True when anything changed.
// `field`: typing in one field is one step of undo (app 0.4.2), as with editDocument.
export function commitArrangement(result: { tile: Tile; slot: number }[], field?: string) {
  const doc = useDocumentStore();
  if (!doc.document || !doc.documentGrid) return false;
  try {
    // Adding a numbered destination from the library explicitly creates that page, in the same undo operation as its
    // navigation tile.
    const draft = pages.clone(doc.document);
    const count = Math.max(draft.pages.length, ...result.filter(({ tile }) => !tile.id).map(({ tile }) => pageTarget(tile.entity)));
    if (count > doc.editorLayout.grid.pages) throw new Error(t("addon.errors.pages.pages_full"));
    while (draft.pages.length < count) draft.pages.push(pages.emptyPage(draft.pages.at(-1)!.topbar));
    const arranged = pages.arrangeTiles(draft, doc.screenGridOf(doc.documentGrid), result);
    const existing = new Set(doc.document.pages.map((page) => page.id));
    for (const page of arranged.pages) if (!existing.has(page.id)) {
      const title = suggestedPageTitle(page, useInventoryStore().inventory.entities);
      page.topbar.title = title ? { source: "text", text: title } : { source: "screen" };
    }
    return doc.applyEdit(arranged, field);
  }
  catch (error: any) { toast(error.message); return false; }
}
export function placeTile(tile: Tile, target: number) {
  const doc = useDocumentStore(), entities = useEntitiesStore();
  if (!doc.layout) return false;
  entities.loadCapabilities([tile.entity]);
  const result = doc.editorLayout.arrange(doc.layout.tiles, currentView(tile) || tile, target);
  const placed = result ? commitArrangement(result) : false;
  if (placed && !entities.liveStates[tile.entity]) doc.loadStates();
  return placed;
}
/** A new tile from the picker or a drag: its default options, and for the energy card the smallest size its diagram fits
 * on this glass (app 0.4.77), since a 2 x 2 card is too low for it on some. */
export function startTile(id: string): Tile {
  const tile = newTile(id, useScreenStore().coversByDefault);
  if (id !== "screen.energy") return tile;
  const { grid } = useDocumentStore().editorLayout;
  const area = (size: Size) => { const d = dimensions(size, grid); return d.columns * d.rows; };
  const fitting = tileSizeChoices(tile).sort((a, b) => area(a) - area(b));
  return { ...tile, options: { ...tile.options, size: fitting.includes("square") ? "square" : fitting[0] ?? "full" } };
}
// A click in the picker: the marked empty cell or key place, else the selected page's first free cell. Never silently
// spill a library click onto another page.
export async function addTile(id: string) {
  const doc = useDocumentStore(), scr = useScreenStore();
  if (!doc.layout || (!scr.repeatable(id) && doc.layout.tiles.some((t) => t.entity === id)) || doc.layout.tiles.length >= doc.tileLimit) return;
  // Past the screen's memory the tile waits for the answer; otherwise it goes on at once.
  const allowed = confirmMemory(id);
  if (allowed !== true && !(await allowed)) return;
  const layout = doc.layout;
  if (!layout) return;
  if (inspection.insertKey) {
    const { holder, key } = inspection.insertKey;
    inspection.insertKey = null;
    const clock = layout.tiles.find((item) => item.id === holder);
    if (clock && placeKey(newTile(id), clock, key)) {
      // The key in the place it was put in: the same entity may stand under the clock twice (firmware 0.16.0+).
      const added = doc.layout!.tiles.find((item) => item.entity === id && item.in === clock.entity && item.key === key)
        || doc.layout!.tiles.find((item) => item.entity === id && item.in === clock.entity);
      if (added) openTile(added);
    }
    return;
  }
  const tile = startTile(id), { grid, firstFree, occupied } = doc.editorLayout;
  const page = Math.max(0, doc.document!.pages.findIndex((page) => page.id === doc.selectedPageId));
  const at = inspection.insertAt;
  const target = at >= 0 ? at : firstFree(occupied(entriesOf(layout)), sizeOf(tile), page * grid.slots);
  const slot = at >= 0 || target < (page + 1) * grid.slots ? target : -1;
  inspection.insertAt = -1;
  if (slot < 0) return toast(t("editor.pages.selected_full"));
  if (slot >= 0 && placeTile(tile, slot)) {
    const added = doc.layout!.tiles.find((item) => item.entity === id && item.slot === slot);
    if (added && useUiStore().phone) doc.markAdded(added);
    else if (added) openTile(added);
  }
}
export function removeTile(tile: Tile) {
  if (!tile.id) return;
  const doc = useDocumentStore();
  if (doc.editDocument((draft) => {
    for (const page of draft.pages) {
      page.tiles = page.tiles.filter((item) => item.id !== tile.id);
      // A key goes from under its clock; a clock takes its keys with it.
      for (const item of page.tiles) if (item.children) {
        item.children = item.children.filter((child) => child.id !== tile.id);
        if (!item.children.length) delete item.children;
      }
    }
  }))
    doc.undoToast(t("editor.layout.removed", { name: tile.name || useEntitiesStore().entityName(tile.entity) }));
}
// Moving a tile without dragging it (app 0.2.78), for a finger on a phone and for anyone who can't drag: the first free
// cell of that page, else its first cell, where the tile in the way swaps places as it does for a drop or an arrow key.
// `page` counts from 0; the page after the last one starts a new page.
export function moveTileToPage(tile: Tile, page: number) {
  const doc = useDocumentStore(), layout = doc.layout, { grid, firstFree, occupied, pageOf } = doc.editorLayout;
  tile = currentView(tile) || tile;
  if (!layout || !Number.isInteger(page) || page < 0 || page >= grid.pages || page === pageOf(tile.slot)) return false;
  const slot = firstFree(occupied(entriesOf(layout).filter((e) => e.tile !== tile)), sizeOf(tile), page * grid.slots);
  const moved = placeTile(tile, slot >= 0 && pageOf(slot) === page ? slot : page * grid.slots);
  if (!moved) toast(t("editor.layout.no_room", { page: page + 1 }));
  return moved;
}

// ---- Sizes ----
/** The sizes the screen takes on the draft's grid: one given its grid with the layout (firmware 0.53.0+) every size of
 * that grid, an older one those it named for the grid it was built with. */
function screenSizes(): string[] {
  const screen = useScreenStore().currentScreen;
  return screen?.grids ? sizesOn(useDocumentStore().editorLayout.grid) : screen?.tile_sizes || [];
}
export function tileSizeChoices(tile: Tile): Size[] {
  const doc = useDocumentStore(), { grid } = doc.editorLayout, taller = useInventoryStore().tallerTilesEnabled;
  const choices: Size[] = ["single", "wide"];
  const said = screenSizes();
  // A forecast or the sun's path needs width: nothing one column wide and taller than a row.
  const narrow = ["forecast", "sunpath"].includes(String(tile.options?.display));
  if (taller) for (const size of ["tall", "square"] as const) {
    if (!said.includes(size) || grid.rows < 2 || (size === "square" && grid.columns < 2)) continue;
    if (size === "tall" && narrow) continue;
    choices.push(size);
  }
  // Every other rectangle the screen said its grid takes (firmware 0.19.0, app 0.4.32): 3 x 2, 2 x 3 and the rest.
  for (const size of said) {
    const span = spanOf(size);
    if (!span || !spanOffered(span.columns, span.rows, grid) || (span.rows > 1 && !taller) || (span.columns === 1 && narrow)) continue;
    choices.push(size as Size);
  }
  // A plugin's tile takes the sizes between its manifest's smallest and largest (design, docs: the plugins proposal).
  const plugin = usePluginsStore().pluginTileOf(tile.entity);
  if (!pageTarget(tile.entity) && !plugin) choices.push("full");
  if (plugin) {
    const least = dimensions(plugin.tile.min as Size, grid), most = dimensions(plugin.tile.max as Size, grid);
    return choices.filter((size) => { const d = dimensions(size, grid);
      return d.columns >= least.columns && d.rows >= least.rows && d.columns <= most.columns && d.rows <= most.rows; });
  }
  // The energy card's diagram takes a size it fits (app 0.4.77): on a small glass a page of its own, never a single cell.
  if (tile.entity === "screen.energy") return choices.filter((size) => {
    const { columns, rows } = dimensions(size, grid);
    return energyFits(doc.screenShape, grid.columns, grid.rows, columns, rows);
  });
  return choices;
}
/** Edge resizing keeps the anchor and every neighbouring tile in place. */
export function resizeChoices(tile: Tile, axis: "columns" | "rows"): Size[] {
  const doc = useDocumentStore(), current = currentView(tile), { grid, fits, occupied } = doc.editorLayout;
  if (!current || !doc.layout || (axis === "rows" && !useInventoryStore().tallerTilesEnabled)) return [];
  const before = dimensions(sizeOf(current), grid), other = axis === "columns" ? "rows" : "columns";
  const taken = occupied(entriesOf(doc.layout).filter((entry) => entry.tile.id !== current.id));
  const owned = doc.document?.pages.flatMap((page) => page.tiles).find((item) => item.id === current.id);
  return tileSizeChoices(current).filter((size) => {
    // The handles are the only way to size a tile (app 0.4.32), the whole page too: it keeps its top left corner, so a
    // tile there grows into the page and a page shrinks back into a tile.
    const start = size === "full" ? current.slot - (current.slot % grid.slots) : current.slot;
    if (!owned || dimensions(size, grid)[other] !== before[other] || start !== current.slot || !fits(taken, current.slot, size)) return false;
    try { validateCardOptions(owned, current.entity, size); return true; }
    catch { return false; }
  });
}
export function resizeTile(tile: Tile, size: Size, axis: "columns" | "rows") {
  const current = currentView(tile);
  if (!current || size === sizeOf(current) || !resizeChoices(current, axis).includes(size)) return false;
  const doc = useDocumentStore(), { grid } = doc.editorLayout, inventory = useInventoryStore().inventory;
  return doc.editDocument((draft) => {
    const owned = draft.pages.flatMap((page) => page.tiles).find((item) => item.id === current.id)!;
    // Gaining height exposes choices, it never opts into a default control.
    // A Go to page tile has no controls at all (app 0.4.1): writing 'none' there made the add-on refuse the resize.
    if (owned.placement.rows === 1 && dimensions(size, grid).rows > 1 && owned.interaction.controls === undefined && owned.content.kind !== "navigation")
      owned.interaction.controls = effectiveControls(current, inventory) || "none";
    Object.assign(owned.placement, dimensions(size, grid));
    if (size === "single") delete owned.appearance.presentation;
    else owned.appearance.presentation = size;
  });
}

// ---- A tile's options, action and name ----
// Inspector resizing may find the nearest fitting rectangle. Edge handles above keep the anchor fixed so that dragging an
// edge never moves the tile.
export function setTileOption(tile: Tile, key: string, value: unknown, field?: string) {
  const doc = useDocumentStore(), inv = useInventoryStore();
  if (!doc.layout) return;
  const { grid, cellsOf, firstFree, fits, nearestFree, normalize, occupied, pageOf, startOf } = doc.editorLayout;
  const layout = pages.clone(doc.layout);
  tile = currentView(tile, layout) || tile;
  const domain = tile.entity.split(".")[0], caps = useEntitiesStore().capabilities[tile.entity], wasSize = sizeOf(tile);
  // Beyond single, wide and the whole page, a size is one the screen said it takes (tall and square 0.3.1, spans 0.19.0).
  if (key === "size" && !["single", "wide", "full"].includes(String(value)) && ((isTallSize(value) && !inv.tallerTilesEnabled) || !screenSizes().includes(String(value)))) return;
  if (key === "size" && isTallSize(value) && sizeColumns(value) === 1 && ["forecast", "sunpath"].includes(String(tile.options?.display))) return;
  // Perform action is a choice with a second step (app 0.4.0, GitHub #47): nothing is stored until an action is chosen,
  // which comes here as `action` and brings the tap choice with it.
  if (key === "tap" && value === "action" && !tile.options?.action) return;
  const previousControls = effectiveControls(tile, inv.inventory);
  // Direct controls need the standard layout without a mini slider, and vice versa (tile-options.ts).
  tile.options = coupledOptions(tile.options, key, value, Boolean(inv.inventory.controls?.[domain]));
  if (key === "size" && isTallSize(value) && dimensions(wasSize, grid).rows === 1 && !("controls" in tile.options))
    tile.options.controls = previousControls || "none";
  if (key === "display" && ["forecast", "sunpath"].includes(value as string) && !isWide(tile)) tile.options.size = "wide";
  // A card that becomes wide gets the first direct control Home Assistant offers when the usual one isn't there.
  const catalogue = inv.inventory.controls?.[domain];
  if (key === "size" && value !== "full" && sizeColumns(value) > 1 && caps && catalogue && !("controls" in tile.options) && !caps.controls.includes(catalogue.default))
    tile.options.controls = catalogue.choices.find((c) => c.key !== "none" && caps.controls.includes(c.key))?.key || "none";
  // A card that grows to the whole page keeps its page: the other tiles there move to the first free cells after it. With
  // no room for them it takes the first empty page, or stays as it was.
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
// A navigation tile goes to another page: its entity changes (screen.page_<n>). One tile per page it goes to, unless the
// firmware takes several (0.2.65). The page after the last one becomes a new, empty page to fill (app 0.2.78).
export function retargetPageTile(tile: Tile, page: number) {
  const doc = useDocumentStore();
  if (!tile.id || !Number.isInteger(page) || page < 1 || page > doc.editorLayout.grid.pages) return false;
  if (!useScreenStore().pageTilesRepeat && doc.layout?.tiles.some((other) => other.id !== tile.id && pageTarget(other.entity) === page)) {
    toast(t("editor.layout.page_taken", { page })); return false;
  }
  return doc.editDocument((draft) => {
    while (draft.pages.length < page) draft.pages.push(pages.emptyPage(draft.pages.at(-1)!.topbar));
    const source = draft.pages.flatMap((item) => item.tiles).find((item) => item.id === tile.id);
    if (!source || source.content.kind !== "navigation") throw new Error(t("addon.errors.pages.tile_missing"));
    // A link that follows Home stays one when the page it is sent to is the home page (app 0.4.2): it keeps following Home
    // when another page becomes it, instead of turning into a fixed link to this page.
    if (source.content.target.kind === "home" && draft.pages[page - 1].id === draft.homePageId) return;
    source.content.target = { kind: "page", pageId: draft.pages[page - 1].id };
  });
}
// Perform action with its action (app 0.4.0, GitHub #47): the tap choice and the action go into the document together, and
// typing in one of the action's fields is one step of undo, as typing a name is.
export function setTileAction(tile: Tile, action: { action: string; data?: Record<string, unknown> }, field?: string) {
  return useDocumentStore().editDocument((draft) => {
    const found = draft.pages.flatMap((page) => page.tiles).find((item) => item.id === tile.id);
    if (!found) throw new Error(t("addon.errors.pages.tile_missing"));
    found.interaction.tap = "action";
    found.interaction.action = pages.clone(action);
  }, field);
}
export function setTileName(tile: Tile, value: string) {
  useDocumentStore().editDocument((draft) => {
    const tiles = draft.pages.flatMap((page) => page.tiles);
    const found = tiles.find((item) => item.id === tile.id) || tiles.flatMap((item) => item.children || []).find((child) => child.id === tile.id);
    if (found) found.appearance.label = value;
  }, `tile:${tile.id}`);
}

// ---- A bedside clock's keys (app 0.4.12) ----
/** A key dragged onto an empty cell becomes a tile there, the same tile: its id, name, icon and tap go along. */
export function keyToCell(tile: Tile, slot: number) {
  const doc = useDocumentStore(), grid = doc.documentGrid;
  if (!tile.id || !grid) return false;
  const cells = grid.columns * grid.rows, columns = grid.columns;
  return doc.editDocument((draft) => {
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
/** Put a tile on a key place under a bedside clock: a new entity takes the place, a key from another place trades places
 * with what stands there, and a tile from the grid moves off its cell to become that key. Only what a key keeps of a tile
 * goes along: its name, icon and tap. */
export function placeKey(tile: Tile, holder: Tile, key: number) {
  return useDocumentStore().editDocument((draft) => {
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
