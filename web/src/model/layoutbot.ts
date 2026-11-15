// Layoutbot's plan placed in a draft (docs/LAYOUTBOT.md): the editor's part. The add-on asks the AI and checks the plan
// (screen_manager/app/layoutbot.py checked: only this home's entities, page numbers that exist, each entity once); this
// places it with what the editor places by, never another way:
// - on a page the person has, as their own edits place: a tile from the library at the first free cell outside the
//   sections (model/layout.ts firstFree), a section made as "Add a section" makes one (model/sections.ts emptySection)
//   and filled as a drop fills one (insertIntoSection, the section growing as a drop grows it), each through
//   arrangeTiles, which checks it as any edit; nothing of theirs moves, and what has no room is a note;
// - new pages through the one placement Auto layout uses (model/placement.ts placeUnits): each section, and a page's
//   loose tiles, a unit; each tile the cards Auto layout gives the same entity (model/auto-layout.ts placeTileFor: the
//   catalogue and what the entity can do), grown while the page still holds everything (`grow`).
// The screen's tile ceiling, pages and memory hold as they hold an add from the library (proposalHolds, the draft priced
// with what is added). Pure: the draft and the plan in, the next draft and what was left out (notes, keys of
// editor.layoutbot.notes) out. The caller takes it as one step of undo (stores/layoutbot.ts). tests:
// web/tests/layoutbot-plan.spec.ts.
import type { Page, PageGrid, PageLayout, PageTile, Tile } from "../types";
import { placeTarget, placeTileFor, type AutoInput } from "./auto-layout";
import { createLayout, newTile } from "./layout";
import { memoryUse, proposalHolds } from "./memory";
import * as pages from "./pages";
import { keepTiles, sectionsOf, tilesIn } from "./page-tiles";
import { placeUnits, type PlaceTile, type PlaceUnit } from "./placement";
import * as sections from "./sections";

export type PlanSection = { title: string; icon: string | null; entities: string[] };
/** One page of a checked plan: a new one, or the number (from 1) of one the screen has. */
export type PlanPage = { page: "new" | number; title: string; icon: string | null; sections: PlanSection[]; tiles: string[] };
export type Plan = { pages: PlanPage[]; remove: string[] };
/** A note of what was left out: a key of editor.layoutbot.notes and its values. */
export type PlanNote = { key: string; named?: Record<string, string | number> };
export type PlanContext = {
  /** The home and the screen as Auto layout takes them: the screen's pages and tiles still free after the draft, its
   * memory with the draft priced beside what is added (`existing`). */
  input: AutoInput;
  /** The grid the draft is held to (its page limit, plugins), as the document store holds it. */
  held: PageGrid;
  /** Players start with their album cover, as a tile from the library does (the screen store's coversByDefault). */
  covers?: boolean;
};

const entityOf = (tile: PageTile) => (tile.content.kind === "entity" ? tile.content.entityId : tile.content.kind === "plugin" ? tile.content.entityId : undefined);
const lower = (text: string) => text.trim().toLocaleLowerCase();

/** The plan placed in `document`: the next draft (checked as any edit) and what was left out. */
export function applyPlan(document: PageLayout, plan: Plan, ctx: PlanContext): { layout: PageLayout; notes: PlanNote[] } {
  const grid = ctx.held, notes: PlanNote[] = [];
  const note = (key: string, named: Record<string, string | number> = {}) => {
    const same = notes.find((n) => n.key === key && n.named?.page === named.page);
    if (same && named.count !== undefined) same.named!.count = Number(same.named!.count ?? 0) + Number(named.count);
    else if (!same) notes.push({ key, ...(Object.keys(named).length ? { named } : {}) });
  };
  let doc = pages.clone(document);
  const edit = (apply: (draft: PageLayout) => void) => { doc = pages.changePages(doc, grid, apply); };
  // Taking tiles off: only this screen's, and a section left without tiles goes with them.
  const gone = new Set(plan.remove);
  if (gone.size) edit((draft) => draft.pages.forEach((page) => takeOff(page, gone)));

  // The memory an add from the library is held to: the draft as it was, priced against it with each tile added.
  const memory = ctx.input.screen.memory ?? null, plugins = ctx.input.plugins;
  const start = memory ? memoryUse(pages.projectLayout(document, grid).tiles, memory, document.pages, plugins) : null;
  const holds = (entity: string) => {
    if (!memory || !start) return true;
    const view = pages.projectLayout(doc, grid);
    return proposalHolds(start, memoryUse([...view.tiles, { entity }], memory, doc.pages, plugins));
  };

  for (const item of plan.pages) {
    if (item.page === "new") continue;
    const index = item.page - 1;
    if (!doc.pages[index]) { note("no_page", { page: item.page }); continue; }
    if (item.title) edit((draft) => { draft.pages[index].topbar.title = { source: "text", text: item.title }; });
    // A section the plan names again keeps the tiles already in it (models restate a section's tiles); one standing
    // elsewhere on the page moves into it. A loose tile named again stays where it stands.
    const page = doc.pages[index];
    const standing = new Map(sectionsOf(page).map((s) => [lower(s.title), new Set(tilesIn(page, s).map(entityOf))]));
    const wanted = item.sections.map((s) => ({ ...s, entities: s.entities.filter((e) => !standing.get(lower(s.title))?.has(e)) }));
    const moving = new Set(wanted.flatMap((s) => s.entities));
    if (moving.size) edit((draft) => takeOff(draft.pages[index], moving, false));
    const onPage = () => new Set(doc.pages[index].tiles.map(entityOf));
    const place = (entity: string, into?: string) => {
      if (!ctx.input.entities.some((e) => e.id === entity)) { note("not_drawn", { count: 1 }); return; }
      if (!holds(entity)) { note("memory_full", { count: 1 }); return; }
      const tile = newTile(entity, ctx.covers);
      const placed = into ? intoSection(doc, grid, tile, into) : loose(doc, grid, index, tile);
      if (placed) doc = placed; else note("page_full", { page: item.page, count: 1 });
    };
    for (const section of wanted) {
      if (!ctx.input.screen.sections) { section.entities.filter((e) => !onPage().has(e)).forEach((e) => place(e)); continue; }
      let id = sectionsOf(doc.pages[index]).find((s) => lower(s.title) === lower(section.title))?.id;
      if (!id && section.entities.length) {
        const made = newSection(doc, grid, index, section);
        if (!made) { note("page_full", { page: item.page, count: section.entities.length }); continue; }
        ({ doc, id } = made);
      }
      section.entities.forEach((e) => place(e, id));
    }
    item.tiles.filter((e) => !onPage().has(e)).forEach((e) => place(e));
  }

  // New pages, all at once, through the placement Auto layout uses: each section a unit, a page's loose tiles one.
  const units: PlaceUnit[] = [];
  plan.pages.forEach((item, n) => {
    if (item.page !== "new") return;
    const page = { title: item.title, ...(item.icon ? { icon: item.icon } : {}) }, share = `${n}`;
    item.sections.forEach((s, k) => units.push({ key: `${n}:${k}`, title: s.title, ...(s.icon ? { icon: s.icon } : {}),
      tiles: tilesOf(s.entities, s.title, `${n}:${k}`, ctx, note), page, share, run: share, ...(ctx.input.screen.sections ? {} : { loose: true }) }));
    if (item.tiles.length) units.push({ key: `${n}:loose`, title: "", tiles: tilesOf(item.tiles, "", `${n}:loose`, ctx, note), loose: true, page, share, run: share });
  });
  const placing = units.filter((unit) => unit.tiles.length);
  if (placing.length) {
    const screen = ctx.input.screen, view = pages.projectLayout(doc, grid);
    const placed = placeUnits(placing, {
      ...placeTarget({ ...ctx.input, existing: { tiles: view.tiles, pages: doc.pages } }),
      // The person asked for these tiles: the screen's own ceilings, no room kept back, every cell of a page, and the
      // cards grown while a page still holds everything.
      pages: Math.max(0, Math.min(screen.pages, pages.pageLimit(grid) - doc.pages.length)), tiles: Math.max(0, screen.tiles), fill: 1, grow: true,
    });
    for (const left of placed.left) note(left.why === "memory" ? "memory_full" : "left_out", { count: 1 });
    if (placed.pages.length) doc = pages.validatePages({ ...doc, pages: [...doc.pages, ...placed.pages] }, grid, doc);
  }
  return { layout: doc, notes };
}

/** The cards of the entities of a unit, as Auto layout dresses its own: the first of a kind in it the larger one. */
function tilesOf(entities: string[], context: string, unit: string, ctx: PlanContext, note: (key: string, named: Record<string, number>) => void): PlaceTile[] {
  const firsts = new Set<string>();
  return entities.flatMap((entity) => {
    const kind = placeTileFor(entity, ctx.input, { context })?.alike;
    const tile = kind === undefined ? null : placeTileFor(entity, ctx.input, { first: !firsts.has(kind), context });
    if (!tile) { note("not_drawn", { count: 1 }); return []; }
    firsts.add(kind!);
    // Alike tiles of one section grow together (every light of it as large as the others), not those of another.
    return [{ ...tile, alike: `${unit}:${tile.alike}` }];
  });
}

/** Tiles of these entities off a page; a section left without tiles goes too (`sectionsGo`), as Remove section does. */
function takeOff(page: Page, gone: Set<string>, sectionsGo = true) {
  const before = new Map(sectionsOf(page).map((s) => [s.id, tilesIn(page, s).length]));
  keepTiles(page, (tile) => !gone.has(entityOf(tile) ?? ""));
  if (sectionsGo && page.sections) {
    page.sections = page.sections.filter((s) => !(before.get(s.id) && !tilesIn(page, s).length));
    if (!page.sections.length) delete page.sections;
  }
}

/** A tile at the first free cell of a page, outside its sections; null when the page has none. */
function loose(doc: PageLayout, grid: PageGrid, index: number, tile: Tile): PageLayout | null {
  const view = pages.projectLayout(doc, grid), blocks = view.sections ?? [], cells = grid.columns * grid.rows;
  const layout = createLayout(() => grid, () => pages.pageLimit(grid), () => blocks);
  const taken = layout.occupied(view.tiles.filter((t) => t.in === undefined).map((t) => ({ tile: t, slot: t.slot })));
  for (const b of blocks) if (b.page === index)
    for (let r = b.row; r < b.row + b.rows; r++) for (let c = b.column; c < b.column + b.columns; c++) taken.add(index * cells + r * grid.columns + c);
  const slot = layout.firstFree(taken, "single", index * cells);
  if (slot < 0 || slot >= (index + 1) * cells) return null;
  return pages.arrangeTiles(doc, grid, [...view.tiles.map((t) => ({ tile: t, slot: t.slot })), { tile, slot }], blocks);
}

/** A tile at the end of a section, the section growing as a drop makes it grow; null when the page has no room. */
function intoSection(doc: PageLayout, grid: PageGrid, tile: Tile, id: string): PageLayout | null {
  const done = sections.insertIntoSection(pages.projectLayout(doc, grid), grid, tile, id, Number.MAX_SAFE_INTEGER);
  return "refused" in done ? null : pages.arrangeTiles(doc, grid, done.entries, done.blocks);
}

/** A new section on a page the person has, as "Add a section" makes one: on free cells, nothing moved. */
function newSection(doc: PageLayout, grid: PageGrid, index: number, section: PlanSection) {
  const view = pages.projectLayout(doc, grid);
  const made = sections.emptySection(view, grid, index, null, section.title);
  if ("refused" in made) return null;
  const block = made.blocks.find((b) => b.page === index && !(view.sections ?? []).some((old) => old.id === b.id))!;
  if (section.icon) block.icon = section.icon;
  return { doc: pages.arrangeTiles(doc, grid, made.entries, made.blocks), id: block.id };
}

/** What a plan changes on a screen, in numbers the chat puts in words: pages added, tiles added and taken off, and the
 * numbers of the pages the person has that it changed. */
export type Summary = { pages: number; added: number; removed: number; changed: number[] };
export function summaryOf(before: PageLayout, after: PageLayout): Summary {
  const ids = (layout: PageLayout) => new Set(layout.pages.flatMap((page) => page.tiles.map((tile) => tile.id)));
  const was = ids(before), now = ids(after), old = new Map(before.pages.map((page) => [page.id, JSON.stringify(page)]));
  return {
    pages: after.pages.filter((page) => !old.has(page.id)).length,
    added: [...now].filter((id) => !was.has(id)).length,
    removed: [...was].filter((id) => !now.has(id)).length,
    changed: after.pages.flatMap((page, n) => (old.has(page.id) && old.get(page.id) !== JSON.stringify(page) ? [n + 1] : [])),
  };
}
