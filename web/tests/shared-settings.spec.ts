// The settings several chosen tiles share (editor/shared-settings.ts, components/inspector/SharedSettings.vue, docs/PAGES.md
// "Several tiles at once"): a setting shows when every chosen tile offers it with the same choices, with the value they
// all have or the word that they differ; a pick is written to every one of them, as one step of undo; and what belongs
// to one tile alone (its name, its entity, the action to perform) is not there.
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import SelectionInspector from "../src/components/SelectionInspector.vue";
import { setShared, sharedRows } from "../src/editor/shared-settings";
import { useDocumentStore } from "../src/stores/document";
import { useEntitiesStore } from "../src/stores/entities";
import { useInspectorStore } from "../src/stores/inspector";
import { useInventoryStore } from "../src/stores/inventory";
import type { Inventory, Screen, Tile } from "../src/types";
import { fakeApi } from "./helpers/fake-api";
import { openScreen, screenFixture } from "./helpers/fixtures";

const COVER = { controls: ["buttons", "position"], toggle: true, inline: true, displays: ["standard"] };
const LIGHT = { controls: ["toggle", "brightness"], toggle: true, inline: true, displays: ["standard"] };
function open(tiles: Tile[]) {
  fakeApi({ states: { states: {} }, capabilities: { capabilities: {} }, "POST header-preview": { items: [] }, "entity-subtitle": { values: [] } });
  const screen = screenFixture({ id: "hall", name: "Hall", online: true, firmware: "0.64.0", shape: { columns: 3, rows: 3, width: 800, height: 480 },
    layout: { title: "Hall", tiles, pages: 1 } } as unknown as Screen);
  useInventoryStore().inventory = { connected: true, screens: [screen], entities: tiles.map((tile) => ({ id: tile.entity, name: tile.entity, state: "on", area: "" })),
    icons: { groups: [], weather: {}, sun: {}, defaults: { light: "F0335", cover: "F1846" }, fallback: "F0335", builtin: {}, controls: {} },
    backgrounds: { auto: { label: "Default" }, none: { label: "None" }, orange: { label: "Orange", color: "#ffe1c6" } },
    controls: {
      cover: { default: "buttons", choices: [{ key: "buttons", label: "Open, stop, close" }, { key: "position", label: "Position" }, { key: "none", label: "None" }] },
      light: { default: "toggle", choices: [{ key: "toggle", label: "On/off" }, { key: "brightness", label: "Brightness" }, { key: "none", label: "None" }] },
    } } as unknown as Inventory;
  for (const tile of tiles) useEntitiesStore().capabilities[tile.entity] = (tile.entity.startsWith("cover.") ? COVER : LIGHT) as any;
  openScreen(screen.id);
  return { doc: useDocumentStore(), insp: useInspectorStore() };
}
// Three blinds two cells wide, one under the other on a grid of three columns.
const blinds = (): Tile[] => ["left", "middle", "right"].map((name, row) => ({ entity: `cover.${name}`, name: "", slot: row * 3, options: { size: "wide" } }));
const tileOf = (entity: string) => useDocumentStore().layout!.tiles.find((item) => item.entity === entity)!;
const all = () => useDocumentStore().layout!.tiles;
const row = (key: string) => sharedRows(useInspectorStore().selectedTiles).find((item) => item.key === key);

describe("the settings chosen tiles share", () => {
  it("are those every tile offers with the same choices, with the value they all have", () => {
    const { insp } = open(blinds());
    expect(sharedRows([tileOf("cover.left")])).toEqual([]);
    insp.selectTiles(all().map((tile) => tile.id!));
    const keys = sharedRows(insp.selectedTiles).map((item) => item.key);
    // What a blind is set to, in the order of its own inspector; never a name, an entity or an action.
    expect(keys).toEqual(["display", "sub", "tap", "controls", "slider", "icon", "background"]);
    expect(row("slider")).toMatchObject({ kind: "switch", value: false });
    expect(row("controls")).toMatchObject({ section: "controls", kind: "choice", value: "buttons", text: "Open, stop, close" });
    expect(row("controls")!.choices.map(([key]) => key)).toEqual(["buttons", "position", "none"]);
    expect(row("tap")!.choices.map(([key]) => key)).not.toContain("action");
    expect(row("sub")!.choices.map(([key]) => key)).toEqual(["auto", "none"]);
    expect(row("background")).toMatchObject({ kind: "background", value: "auto", text: "Default" });
  });

  it("say nothing of a value the tiles differ in, and name one that is none of the choices", () => {
    const tiles = blinds();
    tiles[1].options = { size: "wide", background: "orange", sub: "text:Bedroom" };
    const { insp } = open(tiles);
    insp.selectTiles(all().map((tile) => tile.id!));
    expect(row("background")).toMatchObject({ value: null, text: undefined });
    expect(row("sub")!.value).toBeNull();
    // Words of one's own on all three: no choice of the row, and said as what it is.
    setShared(insp.selectedTiles, "sub", "text:Bedroom");
    expect(row("sub")).toMatchObject({ value: "text:Bedroom", text: "Own text" });
  });

  it("write a pick to every tile as one step of undo", () => {
    const { doc, insp } = open(blinds());
    insp.selectTiles(all().map((tile) => tile.id!));
    setShared(insp.selectedTiles, "controls", "position");
    expect(all().map((tile) => tile.options?.controls)).toEqual(["position", "position", "position"]);
    setShared(insp.selectedTiles, "background", "orange");
    expect(all().map((tile) => tile.options?.background)).toEqual(["orange", "orange", "orange"]);
    // The tiles stay chosen, and the rows show what they now all have.
    expect(insp.selectedTiles).toHaveLength(3);
    expect([row("controls")!.value, row("background")!.value]).toEqual(["position", "orange"]);
    doc.undo();
    expect(all().map((tile) => [tile.options?.controls, tile.options?.background])).toEqual([["position", undefined], ["position", undefined], ["position", undefined]]);
    doc.undo();
    expect(all().map((tile) => tile.options?.controls)).toEqual([undefined, undefined, undefined]);
    doc.redo();
    expect(all().map((tile) => tile.options?.controls)).toEqual(["position", "position", "position"]);
  });

  it("are fewer for tiles of another kind: what any tile has, not what a blind has", () => {
    const { insp } = open([...blinds().slice(0, 2), { entity: "light.desk", name: "", slot: 6, options: { size: "wide" } }]);
    insp.selectTiles(all().map((tile) => tile.id!));
    const keys = sharedRows(insp.selectedTiles).map((item) => item.key);
    expect(keys).toContain("background");
    expect(keys).not.toContain("controls");
    setShared(insp.selectedTiles, "background", "none");
    expect(all().map((tile) => tile.options?.background)).toEqual(["none", "none", "none"]);
  });
});

describe("the inspector of several tiles", () => {
  it("shows the shared settings under the tiles, the word for a value that differs, and sets all at a tap", async () => {
    const tiles = blinds();
    tiles[2].options = { size: "wide", controls: "position" };
    const { insp } = open(tiles);
    insp.selectTiles(all().map((tile) => tile.id!));
    // The field itself, not the tests' stand-in for it (tests/setup.ts): it is the field that says the tiles differ.
    const view = mount(SelectionInspector, { attachTo: document.body, global: { stubs: { ChoiceField: false } } });
    await flushPromises();
    expect(view.find("#shared-hint").text()).toBe("A change here is for all 3 tiles.");
    expect(view.findAll("[data-shared]").map((item) => item.attributes("data-shared"))).toEqual(["display", "sub", "tap", "controls", "slider", "icon", "background"]);
    // Two blinds have their keys and one its position: the field says they differ, and no choice is the chosen one.
    expect(view.find("[data-shared=controls] .choice-field .choice-text").text()).toBe("Mixed");
    // What is one tile's own is not here.
    expect(view.find("#tile-name").exists()).toBe(false);
    expect(view.find(".selection-list").findAll(".item")).toHaveLength(3);
    await view.find("[data-shared=background] button[title=Orange]").trigger("click");
    await flushPromises();
    expect(all().map((tile) => tile.options?.background)).toEqual(["orange", "orange", "orange"]);
    expect(view.find("[data-shared=background] button[title=Orange]").attributes("aria-pressed")).toBe("true");
    expect(view.find("[data-shared=background] .prop-aside").text()).toBe("Orange");
    view.unmount();
  });
});
