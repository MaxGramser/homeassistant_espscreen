// Screens and drafts for the editor's tests, made the way the editor makes them: a screen's saved page document is in the
// add-on's inventory, and the draft is read from it by the document store's own load (stores/document.ts loadDocument),
// the one the session runs when a screen is opened and when a newer save arrives. So a test starts from what the editor
// starts from: nothing unsaved, nothing to undo, the home page chosen, and the inventory holding what the draft came from.
// openScreen opens one as a person does (the session's select). Compact fixtures of the page API, not an importer.
import { childOf, clone, emptyLayout, emptyPage, instanceId } from "../../src/model/pages";
import { useDocumentStore } from "../../src/stores/document";
import { useInventoryStore } from "../../src/stores/inventory";
import { useScreenStore } from "../../src/stores/screen";
import { useSessionStore } from "../../src/stores/session";
import type { Layout, PageDocument, PageGrid, PageLayout, PageTile, Screen, Tile } from "../../src/types";

export const testGrid: PageGrid = { columns: 2, rows: 3 };

/** A layout as the editor once drew it (tiles in slots), as the page document the add-on keeps. */
export function documentFixture(view: Layout, grid = testGrid): PageDocument {
  const cells = grid.columns * grid.rows;
  const count = Math.max(1, view.pages || 1, ...view.tiles.map((tile) => Math.floor(tile.slot / cells) + 1),
    ...view.tiles.map((tile) => Number(/^screen\.page_(\d+)$/.exec(tile.entity)?.[1] || 1)));
  const layout = emptyLayout(view.title);
  while (layout.pages.length < count) layout.pages.push(emptyPage());
  layout.pages.forEach((page, i) => {
    const text = view.page_titles?.[i];
    if (text) page.topbar.title = { source: "text", text };
    if (view.header) page.topbar.trailing = view.header.items.map((item) => ({ ...clone(item), id: instanceId() }));
  });
  for (const tile of view.tiles) {
    // Give renderer fixtures an ID too, so selection has the same contract as the API.
    tile.id ||= instanceId();
    if (tile.in !== undefined) continue;  // a bedside clock's key goes under its clock below
    const o = tile.options || {}, destination = /^screen\.page_(\d+)$/.exec(tile.entity);
    const content: PageTile["content"] = destination
      ? { kind: "navigation", target: { kind: "page", pageId: layout.pages[Number(destination[1]) - 1].id } }
      : tile.entity === "screen.clock" || tile.entity === "screen.settings" || tile.entity === "screen.nightstand"
        ? { kind: "builtin", name: tile.entity.slice(7) as "clock" | "nightstand" | "settings" }
        : { kind: "entity", entityId: tile.entity };
    const appearance: PageTile["appearance"] = { label: tile.name }, interaction: PageTile["interaction"] = {};
    if (o.size === "wide" || o.size === "full") appearance.presentation = o.size;
    for (const [key, option] of Object.entries({ display: "display", icon: "icon", background: "background", historyHours: "history_hours", refresh: "refresh", subtitle: "sub" }))
      if (o[option] !== undefined) Object.assign(appearance, { [key]: clone(o[option]) });
    for (const key of ["tap", "inline", "controls", "action"] as const) if (o[key] !== undefined) Object.assign(interaction, { [key]: clone(o[key]) });
    layout.pages[Math.floor(tile.slot / cells)].tiles.push({ id: tile.id, content, appearance, interaction,
      placement: { row: Math.floor(tile.slot % cells / grid.columns), column: tile.slot % grid.columns,
        columns: o.size === "full" ? grid.columns : ["wide", "square"].includes(o.size || "") ? Math.min(2, grid.columns) : 1,
        rows: o.size === "full" ? grid.rows : ["tall", "square"].includes(o.size || "") ? 2 : 1 } });
  }
  // Keys under the clock they name, in their order, as the page document keeps them.
  for (const key of view.tiles.filter((tile) => tile.in !== undefined).sort((a, b) => (a.key ?? 0) - (b.key ?? 0))) {
    const holder = layout.pages.flatMap((page) => page.tiles).find((tile) => tile.content.kind === "builtin" && `screen.${tile.content.name}` === key.in);
    if (holder) (holder.children ||= []).push(childOf(key, key.id!));
  }
  return { format: "pages-v2", revision: instanceId(), sourceGrid: clone(grid), layout,
    workspace: { revision: instanceId(), positions: {} } };
}

/** A screen with its layout saved as a page document, on the grid of its shape. */
export function screenFixture(screen: Screen): Screen {
  const grid = screen.shape ? { columns: screen.shape.columns, rows: screen.shape.rows } : testGrid;
  return { ...screen, source_grid: grid, page_document: documentFixture(screen.layout, grid), page_capability: "ready" };
}

// The screen a test edits when it opened none of its own.
const TEST_SCREEN = { id: "test", name: "Test", online: true, layout: { title: "Test", tiles: [] } } as unknown as Screen;

/** Opens a screen as a person does: it is in the add-on's inventory (added when it is not), and the session chooses it. */
export function openScreen(screen: Screen | string) {
  if (typeof screen !== "string") keep(screen);
  return useSessionStore().select(typeof screen === "string" ? screen : screen.id);
}
// The add-on's record of a screen, in the inventory in place of the one it had.
function keep(screen: Screen) {
  const inv = useInventoryStore(), at = inv.inventory.screens.findIndex((item) => item.id === screen.id);
  if (at >= 0) inv.inventory.screens.splice(at, 1, screen); else inv.inventory.screens.push(screen);
}
/** The open screen's saved document becomes `record` (on `grid`), and the draft is read from it, as when a newer save
 * arrives. A test that opened no screen edits a test screen of its own. */
function loadSaved(record: Screen["page_document"], grid?: PageGrid) {
  const scr = useScreenStore(), open = scr.currentScreen || TEST_SCREEN;
  const screen = { ...open, page_document: record, source_grid: grid } as Screen;
  keep(screen);
  scr.selected = screen.id;
  useDocumentStore().loadDocument(screen);
}
const LEGACY = { format: "legacy-v1" } as Screen["page_document"];

/** The open screen's layout becomes `view`, saved, and the draft is read from it; null for a screen saved before page
 * documents (no draft until it is brought over), or for no draft at all when no screen is open. */
export function loadLayout(view: Layout | null) {
  if (!view && !useScreenStore().currentScreen) return useDocumentStore().loadDocument({ ...TEST_SCREEN, page_document: LEGACY });
  if (!view) return loadSaved(LEGACY);
  const record = documentFixture(view, useDocumentStore().documentGrid || testGrid);
  loadSaved(record, record.sourceGrid);
}
/** The open screen's tiles become `tiles`, the rest of its layout as it is. */
export function loadTiles(tiles: Tile[]) { loadLayout({ ...useDocumentStore().layout!, tiles }); }
/** Tiles added to the open screen's saved layout. */
export function appendTiles(...tiles: Tile[]) { loadTiles([...useDocumentStore().layout!.tiles, ...tiles]); }
// The draft changed as a saved document and read again: what it says is what the add-on holds.
function loadDraft(change: (layout: PageLayout) => void) {
  const doc = useDocumentStore(), layout = clone(doc.document!);
  change(layout);
  loadSaved({ format: "pages-v2", revision: instanceId(), layout, sourceGrid: clone(doc.documentGrid!), workspace: { revision: instanceId(), positions: {} } },
    clone(doc.documentGrid!));
}
/** The open screen with `pages` pages: empty ones added, or empty ones at the end taken off (pages with tiles stay). */
export function loadPages(pages: number) {
  loadDraft((layout) => {
    while (layout.pages.length < pages) layout.pages.push(emptyPage());
    while (layout.pages.length > pages && !layout.pages.at(-1)!.tiles.length) layout.pages.pop();
  });
}
/** Each page's own title, in order; empty for the screen's own title. */
export function loadTitles(titles: string[]) {
  loadDraft((layout) => {
    layout.pages.forEach((page, index) => { page.topbar.title = titles[index] ? { source: "text", text: titles[index] } : { source: "screen" }; });
  });
}
/** The tile as the draft has it now. */
export function current(tile: Tile) { return useDocumentStore().layout!.tiles.find((item) => item.id === tile.id)!; }
