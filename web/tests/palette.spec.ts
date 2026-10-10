// ⌘K's rows (model/palette.ts): every screen and the editor's actions, the open screen's first, the entities to add once
// something is typed, what the search finds, and the groups the rows stand in.
import { describe, expect, it, vi } from "vitest";
import { t } from "../src/i18n";
import { paletteGroups, paletteItems, rememberChoice, type PaletteActions, type PaletteFacts } from "../src/model/palette";
import type { Screen } from "../src/types";

const hall = { id: "hall", name: "Hall", online: true, firmware: "0.53.0" } as Screen, attic = { id: "attic", name: "Attic", online: false } as Screen;
const facts = (more: Partial<PaletteFacts> = {}): PaletteFacts => ({ query: "", screens: [hall, attic], open: null, dirty: false, alerts: true,
  entities: [{ id: "light.kitchen", name: "Kitchen light", area: "Kitchen" }, { id: "light.hall", name: "Hall light" }, { id: "sensor.x", name: "Kitchen x", tile: false }],
  placed: new Set(), repeatable: () => false, full: false, ...more });
const actions = (): PaletteActions => ({ openScreen: vi.fn(), go: vi.fn(), showTab: vi.fn(), save: vi.fn(), identify: vi.fn(), exportLayout: vi.fn(), addTile: vi.fn() });

describe("the search's rows", () => {
  it("lists every screen and the actions, the open screen's first, and nothing to add until something is typed", () => {
    const rows = paletteItems(facts(), actions());
    expect(rows.map((row) => row.label)).toEqual(["Hall", "Attic", t("editor.nav.new_screen"), t("editor.nav.firmware"), t("editor.nav.alerts"), t("editor.nav.settings")]);
    expect(rows[1].detail).toBe(`${t("editor.common.offline")} · ${t("editor.common.unknown")}`);
    const open = paletteItems(facts({ open: hall, dirty: true }), actions());
    expect(open.slice(2, 7).map((row) => row.label)).toEqual([t("editor.common.save_send"), t("editor.screen_view.tabs.layout"), t("editor.screen_view.tabs.settings"),
      t("editor.palette.identify"), t("editor.palette.export")]);
    expect(open[2].detail).toBe(t("editor.common.unsaved"));
  });

  it("does what a row says", () => {
    const does = actions(), rows = paletteItems(facts({ open: hall, query: "" }), does);
    rows.find((row) => row.label === "Attic")!.run();
    rows.find((row) => row.label === t("editor.nav.alerts"))!.run();
    rows.find((row) => row.label === t("editor.screen_view.tabs.settings"))!.run();
    rows.find((row) => row.label === t("editor.palette.identify"))!.run();
    expect(does.openScreen).toHaveBeenCalledWith(attic);
    expect(does.go).toHaveBeenCalledWith("#alerts");
    expect(does.showTab).toHaveBeenCalledWith("settings");
    expect(does.identify).toHaveBeenCalledWith(hall);
    const cannot = actions();
    paletteItems(facts({ open: hall, alerts: false }), cannot).find((row) => row.label === t("editor.palette.identify"))!.run();
    expect(cannot.identify).not.toHaveBeenCalled();
  });

  it("offers the entities the open screen can take for what is typed, and finds rows by their words", () => {
    const does = actions(), rows = paletteItems(facts({ open: hall, query: "kitchen", icon: () => "F0335" }), does);
    const add = rows.filter((row) => row.group === t("editor.palette.groups.add"));
    expect(add.map((row) => [row.label, row.icon])).toEqual([["Kitchen light", "F0335"]]);
    add[0].run();
    expect(does.addTile).toHaveBeenCalledWith("light.kitchen");
    expect(paletteItems(facts({ open: hall, query: "kitchen", placed: new Set(["light.kitchen"]) }), actions()).some((row) => row.label === "Kitchen light")).toBe(false);
    expect(paletteItems(facts({ open: hall, query: "kitchen", placed: new Set(["light.kitchen"]), repeatable: () => true }), actions()).some((row) => row.label === "Kitchen light")).toBe(true);
    const full = actions();
    paletteItems(facts({ open: hall, query: "kitchen", full: true }), full).find((row) => row.label === "Kitchen light")!.run();
    expect(full.addTile).not.toHaveBeenCalled();
    expect(paletteItems(facts({ query: "kitchen" }), actions()).some((row) => row.label === "Kitchen light")).toBe(false);
    expect(paletteItems(facts({ query: "att" }), actions()).map((row) => row.label)).toEqual(["Attic"]);
  });

  it("stands the rows in their groups, each with its place in the list", () => {
    const groups = paletteGroups(paletteItems(facts(), actions()));
    expect(groups.map((g) => [g.group, g.items.map((i) => i.index)])).toEqual([[t("editor.palette.groups.screens"), [0, 1]], [t("editor.palette.groups.actions"), [2, 3, 4, 5]]]);
  });
});

describe("the search can do everything", () => {
  const every = (): PaletteActions => ({ ...actions(), update: vi.fn(), updateAll: vi.fn(), installSetAside: vi.fn(), showTile: vi.fn(), openSetting: vi.fn(),
    openPlugin: vi.fn(), addPlugin: vi.fn() });
  const kitchen = { id: "kitchen", name: "Kitchen", online: true, firmware: "0.50.0" } as Screen;
  const more = (extra: Partial<PaletteFacts> = {}) => facts({ screens: [hall, attic, kitchen], canIdentify: (s) => s.online, updateTo: (s) => s.id === "kitchen" ? "0.53.0" : null,
    updatesWaiting: 1, setAside: 2, entityName: (id) => ({ "light.kitchen": "Kitchen light", "sensor.t": "Temperature" } as Record<string, string>)[id] || id,
    tiles: [{ screen: hall, tileId: "t1", entity: "light.kitchen", label: "", page: 1, pageTitle: "" }, { screen: kitchen, tileId: "t2", entity: "sensor.t", label: "Inside", page: 0, pageTitle: "Home" }],
    settings: [{ screen: hall, key: "brightness", label: "Brightness", value: "80%" }, { screen: kitchen, key: "brightness", label: "Brightness", value: "40%" },
      { screen: kitchen, key: "dark_mode", label: "Dark mode", value: "On" }],
    plugins: [{ id: "bus", name: "Bus departures", summary: "The next buses", addable: true }, { id: "rain", name: "Rain radar", summary: "Rain soon", addable: false }], ...extra });

  it("with nothing typed: the screens and the actions, updating every screen and installing what is set aside among them, nothing found by name", () => {
    const rows = paletteItems(more(), every());
    expect(rows.some((row) => row.id === "action:update-all" && row.detail === t("editor.search.update_all_detail", 1))).toBe(true);
    expect(rows.some((row) => row.id === "action:install-set-aside" && row.detail === t("editor.search.install_detail", 2))).toBe(true);
    // Each screen's own actions, the settings, the tiles and the plugins come for what is typed.
    expect(rows.some((row) => /^(identify|update|setting|tile|plugin|add):/.test(row.id))).toBe(false);
  });

  it("finds a setting on every screen with its value, and opens it there", () => {
    const does = every(), rows = paletteItems(more({ query: "brightness" }), does);
    const settings = rows.filter((row) => row.group === t("editor.search.groups.settings"));
    expect(settings.map((row) => row.detail)).toEqual(["Hall · 80%", "Kitchen · 40%"]);
    // Words in any order and field: "kitchen bright" is the kitchen's.
    const one = paletteItems(more({ query: "kitchen bright" }), does).filter((row) => row.id.startsWith("setting:"));
    expect(one.map((row) => row.id)).toEqual(["setting:kitchen:brightness"]);
    one[0].run();
    expect(does.openSetting).toHaveBeenCalledWith(kitchen, "brightness");
  });

  it("does not bring a screen's every setting and tile along with its name alone, and names a setting's group where its label does not", () => {
    const rows = paletteItems(more({ query: "kitchen" }), every());
    expect(rows.filter((row) => row.id.startsWith("setting:") || row.id.startsWith("tile:")).map((row) => row.id)).toEqual(["tile:hall:t1"]);
    const night = paletteItems(more({ query: "starts", settings: [{ screen: kitchen, key: "night_start", label: "Starts", group: "Night", value: "22:00" },
      { screen: kitchen, key: "night_brightness", label: "Night brightness", group: "Night", value: "10%" }] }), every());
    expect(night.map((row) => row.detail)).toEqual(["Kitchen · Night · 22:00"]);
    expect(paletteItems(more({ query: "night", settings: [{ screen: kitchen, key: "night_brightness", label: "Night brightness", group: "Night", value: "10%" }] }), every())
      .find((row) => row.id === "setting:kitchen:night_brightness")!.detail).toBe("Kitchen · 10%");
  });

  it("finds the tiles that show an entity, on whichever screen, by its name, its id or the tile's own name", () => {
    const does = every();
    const found = paletteItems(more({ query: "kitchen light" }), does).filter((row) => row.id.startsWith("tile:"));
    expect(found.map((row) => [row.label, row.detail])).toEqual([["Kitchen light", "Hall · Page 2"]]);
    found[0].run();
    expect(does.showTile).toHaveBeenCalledWith(hall, "t1");
    expect(paletteItems(more({ query: "sensor.t" }), does).find((row) => row.id === "tile:kitchen:t2")?.detail).toBe("Kitchen · Home");
    expect(paletteItems(more({ query: "inside" }), does).some((row) => row.id === "tile:kitchen:t2")).toBe(true);
  });

  it("identifies and updates a screen by its name, and updates every screen", () => {
    const does = every();
    const rows = paletteItems(more({ query: "kitchen" }), does);
    rows.find((row) => row.id === "identify:kitchen")!.run();
    rows.find((row) => row.id === "update:kitchen")!.run();
    expect(does.identify).toHaveBeenCalledWith(kitchen);
    expect(does.update).toHaveBeenCalledWith(kitchen);
    expect(rows.find((row) => row.id === "update:kitchen")!.detail).toBe(t("editor.search.update_detail", { version: "0.53.0" }));
    // A screen that is away cannot show its card.
    expect(paletteItems(more({ query: "identify" }), does).map((row) => row.id)).not.toContain("identify:attic");
    paletteItems(more({ query: "update all" }), does).find((row) => row.id === "action:update-all")!.run();
    expect(does.updateAll).toHaveBeenCalled();
  });

  it("opens a plugin, and adds one the open screen can take to it", () => {
    const does = every();
    expect(paletteItems(more({ query: "bus" }), does).map((row) => row.id)).toEqual(["plugin:bus"]);
    const rows = paletteItems(more({ query: "bus", open: hall }), does);
    expect(rows.map((row) => row.id)).toEqual(["plugin:bus", "plugin-add:hall:bus"]);
    expect(rows[1].label).toBe(t("editor.search.add_plugin", { plugin: "Bus departures", screen: "Hall" }));
    rows[0].run(); rows[1].run();
    expect(does.openPlugin).toHaveBeenCalledWith("bus");
    expect(does.addPlugin).toHaveBeenCalledWith("bus");
    expect(paletteItems(more({ query: "rain", open: hall }), does).map((row) => row.id)).toEqual(["plugin:rain"]);
  });

  it("puts what was chosen last first, under Recent with nothing typed and at the top of its group for what is typed", () => {
    const recent = rememberChoice(rememberChoice([], "setting:kitchen:brightness"), "screen:attic");
    expect(recent).toEqual(["screen:attic", "setting:kitchen:brightness"]);
    expect(rememberChoice(recent, "setting:kitchen:brightness")).toEqual(["setting:kitchen:brightness", "screen:attic"]);
    const rows = paletteItems(more({ recent }), every());
    expect(rows.slice(0, 2).map((row) => [row.group, row.id])).toEqual([[t("editor.search.groups.recent"), "screen:attic"], [t("editor.search.groups.recent"), "setting:kitchen:brightness"]]);
    // Each once: Attic is no longer among the screens below.
    expect(rows.filter((row) => row.id === "screen:attic")).toHaveLength(1);
    const typed = paletteItems(more({ query: "brightness", recent }), every()).filter((row) => row.id.startsWith("setting:"));
    expect(typed.map((row) => row.id)).toEqual(["setting:kitchen:brightness", "setting:hall:brightness"]);
  });

  it("shows the best few of a long group, and every row walks in the order the groups stand", () => {
    const many = Array.from({ length: 30 }, (_, i) => ({ id: `light.l${i}`, name: `Lamp ${i}` }));
    const rows = paletteItems(more({ query: "lamp", open: hall, entities: many }), every());
    expect(rows.filter((row) => row.id.startsWith("add:"))).toHaveLength(8);
    const groups = paletteGroups(rows);
    expect(groups.flatMap((group) => group.items.map(({ index }) => index))).toEqual(rows.map((_, index) => index));
  });
});
