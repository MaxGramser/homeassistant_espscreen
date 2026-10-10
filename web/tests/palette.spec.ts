// ⌘K's rows (model/palette.ts): every screen and the editor's actions, the open screen's first, the entities to add once
// something is typed, what the search finds, and the groups the rows stand in.
import { describe, expect, it, vi } from "vitest";
import { t } from "../src/i18n";
import { paletteGroups, paletteItems, type PaletteActions, type PaletteFacts } from "../src/model/palette";
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
