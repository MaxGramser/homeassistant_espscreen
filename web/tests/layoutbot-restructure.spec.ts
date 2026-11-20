// "Restructure this page" and "Restructure the whole screen" (model/layoutbot.ts applyRestructure, docs/LAYOUTBOT.md
// "Restructuring"): the person's own tiles grouped as the plan says and placed again through Auto layout's placement,
// each the richest card the page holds, lights that stay one row high with their brightness slider, the person's own
// names kept, the page's place, title and id kept, and nothing ever lost.
import { describe, expect, it } from "vitest";
import type { AutoInput, AutoScreen } from "../src/model/auto-layout";
import { applyPlan, type Plan, type PlanContext } from "../src/model/layoutbot";
import { emptyLayout, instanceId } from "../src/model/pages";
import { sectionsOf, tilesIn } from "../src/model/page-tiles";
import type { PageLayout, PageTile } from "../src/types";
import { CYD, home, MIDDLE, TEN, type Thing } from "./auto-layout.fixture";

const LAMPS = Array.from({ length: 8 }, (_, n) => `light.l${n}`), BLINDS = ["a", "b", "c", "d"].map((n) => `cover.blind_${n}`);
const MANY = Array.from({ length: 25 }, (_, n) => `light.m${n}`);
const THINGS: Thing[] = [...LAMPS.map((id, n) => ({ id, name: `Lamp ${n}` })), ...BLINDS.map((id) => ({ id, name: id.slice(6) })),
  ...MANY.map((id, n) => ({ id, name: `Spot ${n}` })),
  { id: "media_player.speaker", name: "Speaker", class: "speaker" }];
const tile = (entityId: string, row: number, column: number, extra: Partial<PageTile> = {}): PageTile => ({
  id: instanceId(), content: { kind: "entity", entityId }, placement: { row, column, columns: 1, rows: 1 }, appearance: { label: "" }, interaction: {}, ...extra });
const ctx = (screen: AutoScreen): PlanContext => ({ held: { columns: screen.grid.columns, rows: screen.grid.rows, pages: 8 }, input: { ...home(THINGS), screen } as AutoInput });
const entityIds = (tiles: PageTile[]) => tiles.map((t) => (t.content as { entityId: string }).entityId).sort();
/** A page as a person fills it: everything they want, one cell each, in the order they added it. */
function filled(columns: number, entities: string[], title = "Snel"): PageLayout {
  const layout = emptyLayout("Hall");
  layout.pages[0].topbar.title = { source: "text", text: title };
  layout.pages[0].tiles = entities.map((entity, n) => tile(entity, Math.floor(n / columns), n % columns));
  return layout;
}
const grouped = (restructure: Plan["restructure"], pages: Plan["pages"]): Plan => ({ pages, remove: [], restructure });
const page = (sections: [string, string[]][], tiles: string[] = [], title = "") =>
  ({ page: "new" as const, title, icon: null, sections: sections.map(([t, entities]) => ({ title: t, icon: null, entities })), tiles });

describe("restructuring a page", () => {
  it("groups the person's own tiles into sections, keeps every one and the page itself", () => {
    const doc = filled(5, [...BLINDS.slice(0, 2), ...LAMPS, ...BLINDS.slice(2), "media_player.speaker"]);
    doc.pages[0].tiles[2].appearance.label = "Bank";   // light.l0, named by the person
    const { layout, notes } = applyPlan(doc, grouped({ scope: "page", page: 1 }, [page([["Lampen", LAMPS], ["Zonwering", BLINDS]], ["media_player.speaker"])]), ctx(TEN));
    expect(notes).toEqual([]);
    expect(layout.pages[0].id).toBe(doc.pages[0].id);
    expect(layout.pages[0].topbar.title).toEqual({ source: "text", text: "Snel" });
    const tiles = layout.pages.flatMap((p) => p.tiles);
    expect(entityIds(tiles)).toEqual(entityIds(doc.pages[0].tiles));
    expect(sectionsOf(layout.pages[0]).map((s) => s.title)).toEqual(["Lampen", "Zonwering"]);
    expect(entityIds(tilesIn(layout.pages[0], sectionsOf(layout.pages[0])[0]))).toEqual([...LAMPS].sort());
    expect(tiles.find((t) => (t.content as { entityId: string }).entityId === "light.l0")!.appearance.label).toBe("Bank");
    // Room on a page of 5 x 5: cards grew beyond one cell.
    expect(tiles.some((t) => t.placement.columns * t.placement.rows > 1)).toBe(true);
  });

  it("gives a light that stays one row high its brightness slider, where the page is tight", () => {
    const doc = filled(3, [...LAMPS, "cover.blind_a"]);
    const { layout, notes } = applyPlan(doc, grouped({ scope: "page", page: 1 }, [page([["Lampen", LAMPS]], ["cover.blind_a"])]), ctx(MIDDLE));
    expect(notes).toEqual([]);
    const lamps = layout.pages.flatMap((p) => p.tiles).filter((t) => (t.content as { entityId: string }).entityId.startsWith("light."));
    expect(lamps).toHaveLength(8);
    for (const lamp of lamps.filter((t) => t.placement.rows === 1 && !t.interaction.controls)) expect(lamp.interaction.inline).toBe("slider");
    expect(lamps.some((t) => t.interaction.inline === "slider")).toBe(true);
  });

  it("goes on in a page after it when the groups need more room, before the pages after it", () => {
    const doc = filled(2, [...LAMPS.slice(0, 6)]);
    const after = instanceId();
    doc.pages.push({ ...emptyLayout("x").pages[0], id: after });
    doc.pages[1].tiles = [tile("cover.blind_a", 0, 0)];
    const { layout } = applyPlan(doc, grouped({ scope: "page", page: 1 }, [page([["Een", LAMPS.slice(0, 3)], ["Twee", LAMPS.slice(3, 6)]])]), ctx(CYD));
    expect(entityIds(layout.pages.flatMap((p) => p.tiles))).toEqual(entityIds(doc.pages.flatMap((p) => p.tiles)));
    expect(layout.pages.at(-1)!.id).toBe(after);
  });

  it("leaves the pages as they were when the result would lose a tile", () => {
    // A full page of 5 x 5 in two sections needs the sections' titles too: on a screen of one page a tile would be lost.
    const doc = filled(5, MANY);
    const tight = { ...ctx(TEN), held: { columns: 5, rows: 5, pages: 1 } };
    const { layout, notes } = applyPlan(doc, grouped({ scope: "page", page: 1 }, [page([["Een", MANY.slice(0, 12)], ["Twee", MANY.slice(12)]])]), tight);
    expect(layout).toBe(doc);
    expect(notes.map((n) => n.key)).toEqual(["restructure_no_room"]);
  });

  it("keeps the card the person chose for a tile of one cell (a meter stays a meter)", () => {
    const doc = filled(5, ["cover.blind_a", "light.l0"]);
    doc.pages[0].tiles[1].appearance = { label: "", display: "standard" };
    doc.pages[0].tiles[1].interaction = { inline: "slider" };
    const { layout } = applyPlan(doc, grouped({ scope: "page", page: 1 }, [page([], ["light.l0", "cover.blind_a"])]), ctx(TEN));
    const lamp = layout.pages[0].tiles.find((t) => (t.content as { entityId: string }).entityId === "light.l0")!;
    if (lamp.placement.rows === 1 && lamp.placement.columns === 1) expect(lamp.interaction.inline).toBe("slider");
  });
});

describe("restructuring the whole screen", () => {
  it("places the plan's pages for every tile of every page, the home page first", () => {
    const doc = filled(5, LAMPS.slice(0, 4));
    doc.pages.push({ ...emptyLayout("x").pages[0], id: "two", tiles: [tile("cover.blind_a", 0, 0), tile("light.l4", 0, 1)] });
    const { layout, notes } = applyPlan(doc, grouped({ scope: "screen" }, [page([["Lampen", LAMPS.slice(0, 5)]], [], "Licht"), page([], ["cover.blind_a"], "Zonwering")]), ctx(TEN));
    expect(notes).toEqual([]);
    expect(entityIds(layout.pages.flatMap((p) => p.tiles))).toEqual(entityIds(doc.pages.flatMap((p) => p.tiles)));
    expect(layout.pages.map((p) => p.topbar.title)).toEqual([{ source: "text", text: "Licht" }, { source: "text", text: "Zonwering" }]);
    expect(layout.homePageId).toBe(layout.pages[0].id);
  });
});
