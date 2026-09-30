import { describe, expect, it } from "vitest";
import { i18n, loadLanguage } from '../src/i18n';
import type { PageGrid, PageLayout, PageTile } from "../src/types";
import { arrangeTiles, changePages, clone, connections, deletePage, duplicatePage, emptyLayout, emptyPage,
  adaptGrid, initialPositions, instanceId, navigationFooter, navigationStep, navigationTarget, pagination, projectLayout, reachability, remapLayout, reorderPage, replaceBar, sequentialTarget, setBarItems, validatePages } from "../src/model/pages";

const grid: PageGrid = { columns: 2, rows: 3 };
it('renders draft validation errors in the selected editor language', async () => {
  await loadLanguage('nl');
  i18n.global.locale.value = 'nl';
  try {
    expect(() => validatePages({ ...emptyLayout('Test'), homePageId: 'missing' }, grid)).toThrow('Home moet een bestaande pagina zijn');
  } finally { i18n.global.locale.value = 'en'; }
});
function fixture() {
  const layout = emptyLayout("House");
  layout.pages.push(emptyPage(), emptyPage());
  return arrangeTiles(layout, grid, [
    { tile: { entity: "light.desk", name: "Desk", slot: 0, options: { size: "wide", inline: "slider" } }, slot: 0 },
    { tile: { entity: "screen.page_3", name: "Details", slot: 2 }, slot: 2 },
    { tile: { entity: "screen.page_1", name: "Back", slot: 12 }, slot: 12 },
  ]);
}
function homeTile(): PageTile {
  return { id: instanceId(), content: { kind: "navigation", target: { kind: "home" } },
    placement: { row: 0, column: 0, rows: 1, columns: 1 }, appearance: { label: "Home" }, interaction: {} };
}

describe("page-owned document operations", () => {
  it('refuses an arrangement that accidentally omits an existing tile', () => {
    const layout = fixture(), original = clone(layout);
    const entries = projectLayout(layout, grid).tiles.map(tile => ({ tile, slot: tile.slot! }));
    expect(() => arrangeTiles(layout, grid, entries.slice(1))).toThrow('retain every existing tile');
    expect(layout).toEqual(original);
    expect(arrangeTiles(layout, grid, entries).pages.flatMap(page => page.tiles)).toHaveLength(entries.length);
  });
  it('proposes another grid without changing page identity, navigation, or the source', () => {
    const source = fixture(), before = clone(source), target = { columns: 1, rows: 4 };
    source.pages[1].navigation.excludeFromPagination = true;
    const adapted = adaptGrid(source, grid, target);
    expect(adapted.pages.map((page) => page.id)).toEqual(source.pages.map((page) => page.id));
    expect(adapted.homePageId).toBe(source.homePageId);
    expect(connections(adapted)).toEqual(connections(source));
    expect(adapted.pages[0].tiles[0].appearance.presentation).toBe('wide');
    expect(adapted.pages[0].tiles[0].placement.columns).toBe(1);
    expect(source.pages[0]).toEqual(before.pages[0]);
    expect(adapted.pages[1].navigation.excludeFromPagination).toBe(true);
  });
  it('refuses a grid adaptation that would lose tiles, and keeps every page on any grid', () => {
    const layout = emptyLayout('Full page');
    const full = arrangeTiles(layout, grid, Array.from({ length: 6 }, (_, slot) => ({ tile: { entity: `sensor.a${slot}`, name: '', slot }, slot })));
    expect(() => adaptGrid(full, grid, { columns: 1, rows: 4 })).toThrow('No tiles were removed');
    // Every grid has eight pages (firmware 0.18.0+), so a grid of nine cells keeps all eight.
    const eight = fixture(); while (eight.pages.length < 8) eight.pages.push(emptyPage());
    expect(adaptGrid(eight, grid, { columns: 3, rows: 3 }).pages).toHaveLength(8);
  });
  it('copies items without renaming pages, and whole bars only when explicitly chosen', () => {
    const layout = fixture(), [first, second, third] = layout.pages;
    first.topbar.title = { source: 'text', text: 'Kitchen' };
    first.topbar.leading = [];
    second.topbar.title = { source: 'text', text: 'Bedroom' };
    const copied = replaceBar(layout, grid, first.id, [second.id, third.id], false);
    expect(copied.pages[1].topbar.title).toEqual(second.topbar.title);
    expect(copied.pages[1].topbar.leading).toEqual(second.topbar.leading);
    expect(copied.pages[1].topbar.trailing[0].id).not.toBe(first.topbar.trailing[0].id);
    expect(copied.pages[1].topbar.trailing[0].id).not.toBe(copied.pages[2].topbar.trailing[0].id);
    const whole = replaceBar(layout, grid, first.id, [second.id], true);
    expect(whole.pages[1].topbar.title).toEqual(first.topbar.title);
    expect(whole.pages[1].topbar.leading).toEqual([]);
    expect(layout.pages[1].topbar.title).toEqual({ source: 'text', text: 'Bedroom' });
  });
  it('simulates explicit links independently of opt-outs and honors both sequential controls', () => {
    const layout = fixture(), settings = { pageButtons: false, swipe: false, homeButton: false };
    const [first, second, third] = layout.pages;
    third.navigation.excludeFromPagination = true;
    expect(navigationTarget(layout, first.id, { kind: 'next' }, settings)).toBe(first.id);
    expect(navigationTarget(layout, first.id, { kind: 'swipe-next' }, { ...settings, swipe: true })).toBe(second.id);
    expect(navigationTarget(layout, first.id, { kind: 'tile', tileId: first.tiles[1].id }, settings)).toBe(third.id);
    expect(navigationTarget(layout, third.id, { kind: 'previous' }, { ...settings, pageButtons: true })).toBe(third.id);
    expect(navigationTarget(layout, third.id, { kind: 'swipe-previous' }, { ...settings, swipe: true })).toBe(third.id);
    expect(navigationTarget(layout, third.id, { kind: 'home' }, settings)).toBe(third.id);
    expect(navigationTarget(layout, third.id, { kind: 'home' }, { ...settings, homeButton: true })).toBe(first.id);
    expect(reachability(layout, settings)).toEqual({ unreachable: [second.id], noWayHome: [] });
    third.tiles = [];
    expect(reachability(layout, settings)).toEqual({ unreachable: [second.id], noWayHome: [] });
    layout.homePageId = second.id;
    second.navigation.excludeFromPagination = true;
    expect(reachability(layout, { pageButtons: true, swipe: true, homeButton: true }).unreachable).toEqual([first.id, third.id]);
  });
  it('returns along the actual route, tolerates reorder/deletion, and bounds the history', () => {
    const layout = fixture(), settings = { pageButtons: true, swipe: true, homeButton: true };
    const [first, second, third] = layout.pages;
    third.navigation.excludeFromPagination = true;
    let step = navigationStep(layout, first.id, [], { kind: 'tile', tileId: first.tiles[1].id }, settings);
    expect(step).toEqual({ current: third.id, history: [first.id] });
    layout.pages.reverse();
    expect(navigationStep(layout, step.current, step.history, { kind: 'back' }, settings)).toEqual({ current: first.id, history: [] });
    expect(navigationStep(layout, third.id, [second.id, 'deleted'], { kind: 'back' }, settings)).toEqual({ current: second.id, history: [] });
    expect(navigationStep(layout, third.id, ['deleted'], { kind: 'back' }, settings).current).toBe(first.id);
    expect(navigationStep(layout, third.id, [second.id], { kind: 'home' }, settings).history).toEqual([]);
    step = navigationStep(layout, first.id, Array(8).fill(second.id), { kind: 'tile', tileId: first.tiles[1].id }, settings);
    expect(step.history).toHaveLength(8);
    expect(step.history.at(-1)).toBe(first.id);
    expect(navigationFooter(layout, settings)).toBe(true);
    expect(navigationFooter(layout, { ...settings, pageButtons: false })).toBe(false);
  });
  it("preserves a wide card's controls on a one-column portrait screen", () => {
    const portrait = { columns: 1, rows: 4 };
    const layout = arrangeTiles(emptyLayout("Portrait"), portrait, [
      { tile: { entity: "light.single", name: "", slot: 0 }, slot: 0 },
      { tile: { entity: "light.wide", name: "", slot: 1, options: { size: "wide", controls: "brightness" } }, slot: 1 },
    ]);
    expect(layout.pages[0].tiles[1].placement).toEqual({ row: 1, column: 0, rows: 1, columns: 1 });
    expect(projectLayout(layout, portrait).tiles[1].options).toEqual({ size: "wide", controls: "brightness" });
    const updated = arrangeTiles(layout, portrait, projectLayout(layout, portrait).tiles.map((tile) => ({ tile, slot: tile.slot })));
    expect(updated).toEqual(layout);
  });
  it("rejects a footprint that disagrees with its presentation without changing the draft", () => {
    const layout = fixture(), before = clone(layout);
    expect(layout.pages[0].tiles[0].placement).toEqual({ row: 0, column: 0, rows: 1, columns: 2 });
    expect(() => changePages(layout, grid, (draft) => { draft.pages[0].tiles[0].placement.rows = 2; })).toThrow("future screen capability");
    expect(layout).toEqual(before);
    expect(projectLayout(layout, grid).tiles[0].options).toEqual({ size: "wide", inline: "slider" });
  });
  it("roundtrips tall and square presentations and preserves their rectangles on grid adaptation", () => {
    const layout = arrangeTiles(emptyLayout('Rectangles'), grid, [
      { tile: { entity: 'light.tall', name: '', slot: 0, options: { size: 'tall' } }, slot: 0 },
      { tile: { entity: 'sensor.neighbor', name: '', slot: 1 }, slot: 1 },
      { tile: { entity: 'climate.square', name: '', slot: 6, options: { size: 'square' } }, slot: 6 },
    ]);
    expect(layout.pages[0].tiles[0].placement).toEqual({ row: 0, column: 0, rows: 2, columns: 1 });
    expect(layout.pages[1].tiles[0].placement).toEqual({ row: 0, column: 0, rows: 2, columns: 2 });
    const projection = projectLayout(layout, grid);
    expect(arrangeTiles(layout, grid, projection.tiles.map((tile) => ({ tile, slot: tile.slot })))).toEqual(layout);
    const adapted = adaptGrid(layout, grid, { columns: 3, rows: 3 });
    expect(adapted.pages[1].tiles[0].placement).toEqual(layout.pages[1].tiles[0].placement);
    expect(() => adaptGrid(layout, grid, { columns: 1, rows: 3 })).toThrow();
  });

  it("keeps page IDs, bars, Home and destinations when reordering", () => {
    const layout = fixture(), first = layout.pages[0].id, target = layout.pages[2].id;
    const moved = reorderPage(layout, grid, target, 0);
    expect(moved.homePageId).toBe(first);
    expect(moved.pages[0]).toEqual(layout.pages[2]);
    expect(connections(moved)).toEqual(expect.arrayContaining([{ tileId: layout.pages[0].tiles[1].id, from: first, to: target, home: false }]));
    expect(projectLayout(moved, grid).tiles.find((tile) => tile.name === "Details")?.entity).toBe("screen.page_1");
    expect(layout.pages[2].id).toBe(target);
  });

  it("filters only sequential navigation, including all-excluded and excluded Home", () => {
    const layout = fixture();
    for (let mask = 0; mask < 8; mask++) {
      const draft = changePages(layout, grid, (next) => next.pages.forEach((page, index) => { page.navigation.excludeFromPagination = Boolean(mask & (1 << index)); }));
      const included = pagination(draft);
      expect(projectLayout(draft, grid).tiles).toEqual(projectLayout(layout, grid).tiles);
      for (const page of draft.pages) for (const direction of [-1, 1] as const) {
        const index = included.indexOf(page.id);
        expect(sequentialTarget(draft, page.id, direction)).toBe(index < 0 ? page.id : included[index + direction] ?? page.id);
      }
    }
  });

  it("deletes incoming fixed links atomically while Home links follow the new Home", () => {
    const layout = fixture();
    layout.pages[1].tiles.push(homeTile());
    const removed = deletePage(layout, grid, layout.homePageId);
    expect(removed.pages).toHaveLength(2);
    expect(removed.homePageId).toBe(layout.pages[1].id);
    expect(connections(removed)).toHaveLength(1);
    expect(connections(removed)[0].home).toBe(true);
    expect(() => deletePage(emptyLayout("Only"), grid, "missing")).toThrow();
  });

  it("preserves a Home target when a tile moves, without turning it into a fixed link", () => {
    const layout = fixture();
    layout.pages[1].tiles.push(homeTile());
    const view = projectLayout(layout, grid), home = view.tiles.find((tile) => tile.name === "Home")!;
    const moved = arrangeTiles(layout, grid, view.tiles.map((tile) => ({ tile, slot: tile.id === home.id ? 14 : tile.slot })));
    expect(moved.pages[2].tiles.find((tile) => tile.id === home.id)?.content).toEqual({ kind: "navigation", target: { kind: "home" } });
    expect(moved.pages.map((page) => page.id)).toEqual(layout.pages.map((page) => page.id));
  });

  it("copies a page with its entities as new tiles (firmware 0.16.0+) and offers a separate empty copy", () => {
    const layout = fixture(), first = layout.pages[0];
    const full = duplicatePage(layout, grid, first.id), copied = full.pages[1];
    expect(copied.tiles.map((tile) => tile.content)).toEqual(first.tiles.map((tile) => tile.content));
    expect(copied.tiles.every((tile) => !first.tiles.some((other) => other.id === tile.id))).toBe(true);
    first.navigation.excludeFromPagination = true;
    const result = duplicatePage(layout, grid, first.id, true), copy = result.pages[1];
    expect(copy.tiles).toEqual([]);
    expect(copy.navigation.excludeFromPagination).toBe(false);
    expect(copy.topbar.title).toEqual(first.topbar.title);
    expect(copy.topbar.trailing[0].id).not.toBe(first.topbar.trailing[0].id);
  });

  it("copies self-links to the copied page while other destinations remain stable", () => {
    const layout = fixture(), page = layout.pages[2];
    page.tiles[0].content = { kind: "navigation", target: { kind: "page", pageId: page.id } };
    const copy = duplicatePage(layout, grid, page.id).pages[3];
    expect(copy.tiles[0].content).toEqual({ kind: "navigation", target: { kind: "page", pageId: copy.id } });
  });

  it("refuses overlap and preserves each board's capacity", () => {
    const layout = fixture(), view = projectLayout(layout, grid);
    expect(() => arrangeTiles(layout, grid, view.tiles.map((tile) => ({ tile, slot: 0 })))).toThrow("same spot");
    for (const board of [grid, { columns: 3, rows: 3 }]) {
      const full = emptyLayout("Capacity"), limit = 8;
      while (full.pages.length < limit) full.pages.push(emptyPage());
      expect(validatePages(full, board)).toBe(full);
      expect(() => duplicatePage(full, board, full.homePageId, true)).toThrow("no room");
    }
  });

  it("gives all copied instances new IDs and preserves references and opt-outs", () => {
    const original = fixture();
    original.pages[1].navigation.excludeFromPagination = true;
    const copy = remapLayout(original, grid);
    const ids = (doc: PageLayout) => doc.pages.flatMap((p) => [p.id, ...p.tiles.map((t) => t.id), ...p.topbar.leading.map((i) => i.id), ...p.topbar.trailing.map((i) => i.id)]);
    expect(ids(copy).some((id) => ids(original).includes(id))).toBe(false);
    expect(copy.pages[1].navigation.excludeFromPagination).toBe(true);
    const stripIds = (doc: PageLayout) => projectLayout(doc, grid).tiles.map(({ id: _id, ...tile }) => tile);
    expect(stripIds(copy)).toEqual(stripIds(original));
  });

  it("edits one page's items or explicitly creates independent copies on all pages", () => {
    const layout = fixture(), id = layout.pages[1].id;
    const one = setBarItems(layout, grid, id, [{ type: "entity", entity: "sensor.temperature" }]);
    expect(one.pages[0]).toEqual(layout.pages[0]);
    expect(one.pages[1].topbar.trailing[0].entity).toBe("sensor.temperature");
    const all = setBarItems(one, grid, id, one.pages[1].topbar.trailing, true);
    expect(new Set(all.pages.map((p) => p.topbar.trailing[0].id)).size).toBe(3);
  });

  it("derives a finite initial map with cycles, Home outside position one and orphan pages", () => {
    const layout = fixture();
    layout.homePageId = layout.pages[2].id;
    const before = clone(layout), positions = initialPositions(layout);
    expect(positions[layout.homePageId]).toEqual({ x: 0, y: 0 });
    expect(Object.keys(positions)).toHaveLength(3);
    expect(new Set(Object.values(positions).map((p) => `${p.x}:${p.y}`)).size).toBe(3);
    expect(layout).toEqual(before);
  });
});
