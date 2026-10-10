/** Compact test fixtures for the page API. This is not an application importer. */
import type { Layout, PageDocument, PageGrid, PageTile, Screen, Tile } from "../src/types";
import { childOf, clone, emptyLayout, emptyPage, instanceId } from "../src/model/pages";
import { loadDocument, state } from "../src/store";
import { useScreenStore } from "../src/stores/screen";

export const testGrid: PageGrid = { columns: 2, rows: 3 };
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

export function screenFixture(screen: Screen): Screen {
  const grid = screen.shape ? { columns: screen.shape.columns, rows: screen.shape.rows } : testGrid;
  return { ...screen, source_grid: grid, page_document: documentFixture(screen.layout, grid), page_capability: "ready" };
}
// The layout becomes the draft the way a screen's saved document does (loadDocument): what it was saved as, its undo and
// what is unsaved start from it, not from the test before. Null: a screen without a page document.
export function seedLayout(view: Layout | null) {
  const screen = useScreenStore().currentScreen || ({ id: "test", name: "Test", online: true, layout: { title: "Test", tiles: [] } } as unknown as Screen);
  if (!view) { loadDocument({ ...screen, page_document: { format: "legacy-v1" } as Screen["page_document"], source_grid: undefined }); return; }
  loadDocument({ ...screen, page_document: documentFixture(view, state.documentGrid || testGrid) });
}
export function seedTiles(tiles: Tile[]) { seedLayout({ ...state.layout!, tiles }); }
export function appendTiles(...tiles: Tile[]) { seedTiles([...state.layout!.tiles, ...tiles]); }
export function seedPages(pages: number) {
  while (state.document!.pages.length < pages) state.document!.pages.push(emptyPage());
  // Tests that only change a rendered page count keep any occupied pages valid.
  while (state.document!.pages.length > pages && !state.document!.pages.at(-1)!.tiles.length) state.document!.pages.pop();
}
export function seedTitles(titles: string[]) {
  state.document!.pages.forEach((page, index) => { page.topbar.title = titles[index] ? { source: "text", text: titles[index] } : { source: "screen" }; });
}
export function current(tile: Tile) { return state.layout!.tiles.find((item) => item.id === tile.id)!; }
