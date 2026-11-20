// Layoutbot's plan placed through the editor's one placement (model/layoutbot.ts applyPlan over model/placement.ts
// placeUnits, docs/LAYOUTBOT.md). The cases the add-on's own placing once passed (tests/test_layoutbot.py before the plan
// moved here) and the wrong answers a model gives: a section it names again, a page that is full, a plan past the
// memory, a screen without sections, a page that does not exist.
import { describe, expect, it } from "vitest";
import type { AutoInput, AutoScreen } from "../src/model/auto-layout";
import { applyPlan, summaryOf, type Plan, type PlanContext } from "../src/model/layoutbot";
import { emptyLayout, instanceId } from "../src/model/pages";
import { sectionsOf, tilesIn } from "../src/model/page-tiles";
import type { PageLayout, PageTile } from "../src/types";
import { CYD, home, memory, TEN, type Thing } from "./auto-layout.fixture";

const THINGS: Thing[] = [
  { id: "light.sofa", name: "Sofa" }, { id: "light.desk", name: "Desk" },
  ...["a", "b", "c", "d"].map((n) => ({ id: `cover.blind_${n}`, name: `Blind ${n}` })),
  ...["a", "b", "c"].map((n) => ({ id: `cover.curtain_${n}`, name: `Curtain ${n}` })),
  ...Array.from({ length: 8 }, (_, n) => ({ id: `light.l${n}`, name: `Lamp ${n}` })),
  { id: "media_player.speaker", name: "Speaker", class: "speaker" },
];
const tile = (entityId: string, row: number, column: number, columns = 1, rows = 1, extra: Partial<PageTile> = {}): PageTile => ({
  id: instanceId(), content: { kind: "entity", entityId }, placement: { row, column, columns, rows },
  appearance: { label: "", ...(columns === 2 && rows === 1 ? { presentation: "wide" } : {}) }, interaction: {}, ...extra,
});
function draft(...tiles: PageTile[]): PageLayout {
  const layout = emptyLayout("Hall");
  layout.pages[0].topbar.title = { source: "text", text: "Living" };
  layout.pages[0].tiles = tiles;
  return layout;
}
const ctx = (screen: AutoScreen = TEN): PlanContext => ({
  held: { columns: screen.grid.columns, rows: screen.grid.rows, pages: 8 },
  input: { ...home(THINGS), screen } as AutoInput,
});
const plan = (pages: Plan["pages"], remove: string[] = []): Plan => ({ pages, remove });
const onPage = (page: number, extra: Partial<Plan["pages"][number]> = {}) => ({ page, title: "", icon: null, sections: [], tiles: [], ...extra });
const ids = (tiles: PageTile[]) => tiles.map((t) => (t.content as { entityId: string }).entityId);

describe("Layoutbot's plan on a page the person has", () => {
  it("puts a tile at the first free cell and leaves the others where they stand", () => {
    const doc = draft(tile("light.sofa", 0, 0));
    const { layout, notes } = applyPlan(doc, plan([onPage(1, { tiles: ["light.desk"] })]), ctx());
    expect(notes).toEqual([]);
    expect(layout.pages[0].tiles[0]).toEqual(doc.pages[0].tiles[0]);
    expect(ids(layout.pages[0].tiles)).toEqual(["light.sofa", "light.desk"]);
    expect(layout.pages).toHaveLength(1);
  });

  it("keeps a loose tile the plan names again where it stands", () => {
    const doc = draft(tile("light.sofa", 0, 0));
    const { layout } = applyPlan(doc, plan([onPage(1, { tiles: ["light.sofa", "light.desk"] })]), ctx());
    expect(ids(layout.pages[0].tiles)).toEqual(["light.sofa", "light.desk"]);
    expect(layout.pages[0].tiles[0]).toEqual(doc.pages[0].tiles[0]);
  });

  it("keeps a section's tiles when the plan names them again, size, label and control as they were", () => {
    const wide = tile("light.desk", 1, 0, 2, 1, { appearance: { label: "Desk", presentation: "wide" }, interaction: { controls: "brightness" } });
    const doc = draft(wide);
    doc.pages[0].sections = [{ id: "s1", title: "Lights", placement: { row: 1, column: 0, columns: 3, rows: 1 } }];
    const { layout, notes } = applyPlan(doc, plan([onPage(1, { sections: [{ title: "lights", icon: null, entities: ["light.desk", "cover.blind_a"] }] })]), ctx());
    expect(notes).toEqual([]);
    const lights = tilesIn(layout.pages[0], sectionsOf(layout.pages[0])[0]);
    expect(lights.find((t) => ids([t])[0] === "light.desk")).toEqual(wide);
    // The new one in a cell the wide tile does not cover.
    const blind = lights.find((t) => ids([t])[0] === "cover.blind_a")!;
    expect([blind.placement.row, blind.placement.column]).toEqual([1, 2]);
  });

  it("moves a tile into the section the plan makes instead of showing it twice", () => {
    const doc = draft(tile("light.sofa", 0, 0));
    const { layout } = applyPlan(doc, plan([onPage(1, { sections: [{ title: "Lights", icon: "lamp", entities: ["light.sofa", "light.desk"] }] })]), ctx());
    expect(ids(layout.pages[0].tiles).sort()).toEqual(["light.desk", "light.sofa"]);
    const [section] = sectionsOf(layout.pages[0]);
    expect([section.title, section.icon]).toEqual(["Lights", "lamp"]);
    expect(ids(tilesIn(layout.pages[0], section)).sort()).toEqual(["light.desk", "light.sofa"]);
  });

  it("puts a section's tiles loose on a screen without sections", () => {
    const { layout } = applyPlan(draft(), plan([onPage(1, { sections: [{ title: "Blinds", icon: null, entities: ["cover.blind_a", "cover.blind_b"] }] })]), ctx(CYD));
    expect(layout.pages[0].sections).toBeUndefined();
    expect(ids(layout.pages[0].tiles)).toEqual(["cover.blind_a", "cover.blind_b"]);
  });

  it("leaves out what does not fit on a full page with a note, and pushes no page in after it", () => {
    const doc = draft(...Array.from({ length: 6 }, (_, n) => tile(`light.l${n}`, Math.floor(n / 2), n % 2)));
    for (const item of [onPage(1, { tiles: ["light.desk"] }), onPage(1, { sections: [{ title: "Desk", icon: null, entities: ["light.desk"] }] })]) {
      const { layout, notes } = applyPlan(doc, plan([item]), ctx(CYD));
      expect(layout).toEqual(doc);
      expect(notes).toEqual([{ key: "page_full", named: { page: 1, count: 1 } }]);
    }
  });

  it("renames a page only when renaming is all the plan does there", () => {
    const { layout } = applyPlan(draft(), plan([onPage(1, { title: "Lounge" })]), ctx());
    expect(layout.pages[0].topbar.title).toEqual({ source: "text", text: "Lounge" });
    // An add-on that forgot its own rule sends a title with the tiles it adds: the person's page keeps its name.
    const added = applyPlan(draft(), plan([onPage(1, { title: "Security", tiles: ["light.desk"] })]), ctx()).layout;
    expect(added.pages[0].topbar.title).toEqual({ source: "text", text: "Living" });
  });

  it("takes tiles off, and a section left without tiles with them", () => {
    const doc = draft(tile("light.sofa", 0, 0), tile("light.desk", 1, 0));
    doc.pages[0].sections = [{ id: "s1", title: "Desk", placement: { row: 1, column: 0, columns: 1, rows: 1 } }];
    const { layout } = applyPlan(doc, plan([], ["light.desk"]), ctx());
    expect(ids(layout.pages[0].tiles)).toEqual(["light.sofa"]);
    expect(layout.pages[0].sections).toBeUndefined();
  });

  it("notes a page number the screen does not have", () => {
    expect(applyPlan(draft(), plan([onPage(4, { tiles: ["light.sofa"] })]), ctx()).notes).toEqual([{ key: "no_page", named: { page: 4 } }]);
  });

  it("notes an entity the screen draws no tile of", () => {
    const { notes } = applyPlan(draft(), plan([onPage(1, { tiles: ["light.not_in_this_home"] })]), ctx());
    expect(notes).toEqual([{ key: "not_drawn", named: { count: 1 } }]);
  });
});

describe("Layoutbot's new pages", () => {
  it("makes the example: a new page with a section of blinds and one of curtains, after the person's pages", () => {
    const doc = draft(tile("light.sofa", 0, 0));
    const { layout, notes } = applyPlan(doc, plan([{ page: "new", title: "Zonwering", icon: "blinds", tiles: [], sections: [
      { title: "Rolgordijnen", icon: "blinds", entities: ["cover.blind_a", "cover.blind_b", "cover.blind_c", "cover.blind_d"] },
      { title: "Gordijnen", icon: "curtains", entities: ["cover.curtain_a", "cover.curtain_b", "cover.curtain_c"] }] }]), ctx());
    expect(notes).toEqual([]);
    expect(layout.pages[0]).toEqual(doc.pages[0]);
    const page = layout.pages[1];
    expect([page.topbar.title, page.icon]).toEqual([{ source: "text", text: "Zonwering" }, "blinds"]);
    expect(sectionsOf(page).map((s) => [s.title, s.icon, ids(tilesIn(page, s))])).toEqual([
      ["Rolgordijnen", "blinds", ["cover.blind_a", "cover.blind_b", "cover.blind_c", "cover.blind_d"]],
      ["Gordijnen", "curtains", ["cover.curtain_a", "cover.curtain_b", "cover.curtain_c"]]]);
    expect(layout.homePageId).toBe(doc.homePageId);
  });

  it("gives each tile the card Auto layout gives the same entity", () => {
    const { layout } = applyPlan(draft(), plan([{ page: "new", title: "Music", icon: null, tiles: ["media_player.speaker"], sections: [] }]), ctx());
    const [speaker] = layout.pages[1].tiles;
    // The album cover behind the first player where the screen draws pictures, on a larger card (auto-layout facesFor).
    expect(speaker.appearance.display).toBe("cover");
    expect(speaker.placement.columns * speaker.placement.rows).toBeGreaterThan(1);
  });

  it("puts no section on a screen without them, and runs over onto a page of the same name when a page is full", () => {
    const lamps = Array.from({ length: 8 }, (_, n) => `light.l${n}`);
    const { layout } = applyPlan(draft(), plan([{ page: "new", title: "Lamps", icon: null, tiles: [], sections: [{ title: "All", icon: null, entities: lamps }] }]), ctx(CYD));
    expect(layout.pages.slice(1).map((p) => [p.topbar.title, p.sections])).toEqual([
      [{ source: "text", text: "Lamps" }, undefined], [{ source: "text", text: "Lamps" }, undefined]]);
    expect(layout.pages.slice(1).flatMap((p) => ids(p.tiles))).toEqual(lamps);
  });

  it("holds a plan to the screen's memory, as the library holds an add", () => {
    const lamps = Array.from({ length: 8 }, (_, n) => `light.l${n}`);
    const tight: AutoScreen = { ...TEN, memory: memory(300) };
    const { layout, notes } = applyPlan(draft(), plan([{ page: "new", title: "Lamps", icon: null, tiles: lamps, sections: [] }]), ctx(tight));
    const kept = layout.pages.slice(1).flatMap((p) => p.tiles).length;
    expect(kept).toBeLessThan(8);
    expect(notes).toEqual([{ key: "memory_full", named: { count: 8 - kept } }]);
  });

  it("says what the screen's pages left out", () => {
    const { notes } = applyPlan(draft(), plan([{ page: "new", title: "More", icon: null, tiles: ["light.sofa"], sections: [] }]), ctx({ ...TEN, pages: 0 }));
    expect(notes).toEqual([{ key: "left_out", named: { count: 1 } }]);
  });

  it("counts what a plan changes for the chat", () => {
    const doc = draft(tile("light.sofa", 0, 0));
    const { layout } = applyPlan(doc, plan([onPage(1, { tiles: ["light.desk"] }), { page: "new", title: "N", icon: null, tiles: ["cover.blind_a"], sections: [] }]), ctx());
    expect(summaryOf(doc, layout)).toEqual({ pages: 1, added: 2, removed: 0, changed: [1] });
  });
});
