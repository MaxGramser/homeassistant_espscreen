// What one step of undo did, in words (model/change-label.ts): worked out from the draft before and after it, the most
// telling change first, and said in the editor's language when it is shown.
import { describe, expect, it } from "vitest";
import { i18n } from "../src/i18n";
import { describeChange, type ChangeLabel } from "../src/model/change-label";
import { clone, emptyPage } from "../src/model/pages";
import type { PageGrid, PageLayout, PageTile } from "../src/types";
import { documentFixture } from "./helpers/fixtures";

const grid: PageGrid = { columns: 2, rows: 3 };
const said = (change: ChangeLabel) => i18n.global.t(`editor.undo.what.${change.key}`, change.named || {}, change.count ?? 1);
const nameOf = (tile: { appearance: { label: string } }) => tile.appearance.label || "Unnamed";
const before = () => documentFixture({ title: "Hall", pages: 2, tiles: [
  { entity: "light.a", name: "Lamp", slot: 0 }, { entity: "switch.b", name: "Fan", slot: 1 }, { entity: "sensor.c", name: "Temp", slot: 6 },
] }, grid).layout;
const tiles = (layout: PageLayout) => layout.pages.flatMap((page) => page.tiles);
const tile = (layout: PageLayout, label: string) => tiles(layout).find((item) => item.appearance.label === label)!;
function change(edit: (layout: PageLayout) => void, from = before(), toGrid = grid) {
  const after = clone(from);
  edit(after);
  return said(describeChange(from, after, grid, toGrid, nameOf));
}

describe("the words of a change", () => {
  it("name a tile added, taken off, moved within its page or to another, and several at once", () => {
    expect(change((layout) => layout.pages[0].tiles.push({ ...clone(tile(layout, "Lamp")), id: "0123456789abcdef", appearance: { label: "Desk" }, placement: { row: 1, column: 0, columns: 1, rows: 1 } })))
      .toBe("Desk added");
    expect(change((layout) => { layout.pages[0].tiles = layout.pages[0].tiles.filter((item) => item.appearance.label !== "Fan"); })).toBe("Fan removed");
    expect(change((layout) => { layout.pages[0].tiles = []; })).toBe("2 tiles removed");
    expect(change((layout) => { tile(layout, "Lamp").placement.row = 2; })).toBe("Lamp moved");
    expect(change((layout) => { const lamp = tile(layout, "Lamp"); layout.pages[0].tiles.shift(); layout.pages[1].tiles.push(lamp); })).toBe("Lamp moved to page 2");
    // Two tiles that swap places: both moved, neither more than the other.
    expect(change((layout) => { tile(layout, "Lamp").placement.column = 1; tile(layout, "Fan").placement.column = 0; })).toBe("2 tiles moved");
  });
  it("name what changed of one tile before where it stands", () => {
    expect(change((layout) => { tile(layout, "Lamp").appearance.label = "Reading lamp"; })).toBe("Lamp renamed");
    expect(change((layout) => { tile(layout, "Lamp").appearance.icon = "lamp"; })).toBe("icon of Lamp changed");
    expect(change((layout) => { tile(layout, "Lamp").appearance.background = "blue"; })).toBe("background of Lamp changed");
    expect(change((layout) => { tile(layout, "Lamp").interaction.tap = "toggle"; })).toBe("on tap for Lamp changed");
    expect(change((layout) => { tile(layout, "Lamp").interaction.controls = "brightness"; })).toBe("settings of Lamp changed");
    // A tile grown wide pushes its neighbour along: the size is the change.
    expect(change((layout) => { Object.assign(tile(layout, "Lamp").placement, { columns: 2 }); tile(layout, "Fan").placement.row = 1; })).toBe("Lamp resized");
    // A forecast widens its tile: the face is what was chosen.
    expect(change((layout) => { const lamp = tile(layout, "Lamp"); lamp.appearance.display = "forecast"; lamp.placement.columns = 2; })).toBe("display of Lamp changed");
  });
  it("name what happened to the pages, their titles and their top bars", () => {
    expect(change((layout) => { layout.pages.push(emptyPage()); })).toBe("page 3 added");
    expect(change((layout) => { const copy = clone(layout.pages[1]); copy.id = "fedcba9876543210"; copy.tiles = copy.tiles.map((item: PageTile) => ({ ...item, id: "00112233445566aa" })); layout.pages.push(copy); }))
      .toBe("page 3 added as a copy");
    expect(change((layout) => { layout.pages.splice(1, 1); })).toBe("page 2 removed");
    expect(change((layout) => { layout.pages.reverse(); })).toBe("page moved to place 1");
    expect(change((layout) => { layout.title = "Hallway"; })).toBe("screen title changed");
    expect(change((layout) => { layout.pages[1].topbar.title = { source: "text", text: "Upstairs" }; })).toBe("title of page 2 changed");
    expect(change((layout) => { layout.homePageId = layout.pages[1].id; })).toBe("page 2 made the home page");
    expect(change((layout) => { layout.pages[1].navigation.excludeFromPagination = true; })).toBe("page buttons for page 2 changed");
    expect(change((layout) => { layout.pages[0].topbar.trailing.push({ id: "aaaaaaaaaaaaaaaa", type: "clock" }); })).toBe("top bar of page 1 changed");
    expect(change(() => {}, before(), { columns: 3, rows: 2 })).toBe("grid changed to 3 × 2");
    expect(change(() => {})).toBe("layout changed");
  });
});
