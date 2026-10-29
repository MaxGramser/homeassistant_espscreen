// A light's presets (module light_presets, docs/LIGHT_PRESETS.md) in the editor: the firmware's colours, match and row
// (model/light-presets.ts, compared with module_light_presets.h by tests/test_editor_parity.py), the controls a board
// with the module offers, the keys on the mockup and the inspector's presets.
import { flushPromises, mount } from "@vue/test-utils";
import { defineComponent, h, nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { appendTiles, current, loadLayout, screenFixture } from "./helpers/fixtures";
import TileCard from "../src/components/TileCard.vue";
import TileInspector from "../src/components/TileInspector.vue";
import { canonicalOptions, controlChoices, optionsSave, presetsOffered } from "../src/model/tile-options";
import { tilePanel } from "../src/editor/tiles";
import { cleanPreset, darkInk, fromLight, hsRgb, kelvinRgb, levelShown, lightNow, luminosity, pale, presetPanel, presetSizes, presetsOf, row, shown,
  shows, startPreset } from "../src/model/light-presets";
import { tileFace } from "../src/model/tile-face";
import { resolveControls } from "../src/model/catalogue";
import { useDocumentStore } from "../src/stores/document";
import { useEntitiesStore } from "../src/stores/entities";
import { useInventoryStore } from "../src/stores/inventory";
import { useScreenStore } from "../src/stores/screen";
import type { Inventory, Tile } from "../src/types";

const SHAPES = JSON.parse(readFileSync("../screen_manager/app/boards.json", "utf8"));

describe("a preset's colour, as Home Assistant draws a favourite colour", () => {
  it("is temperature2rgb for a white and hs2rgb for a colour", () => {
    expect(kelvinRgb(6600)).toBe(0xffffff);
    expect(kelvinRgb(2700) >> 16).toBe(255);
    expect(kelvinRgb(2700) & 255).toBeLessThan(200);
    expect(hsRgb(0, 100)).toBe(0xff0000);
    expect(hsRgb(120, 100)).toBe(0x00ff00);
    expect(hsRgb(240, 50)).toBe(0x8080ff);
    expect(hsRgb(77, 0)).toBe(0xffffff);
  });
  it("gives a pale disc its hairline and dark ink, a deep one white ink, a brightness alone both", () => {
    expect(luminosity(0xffffff)).toBeCloseTo(1);
    expect(pale({ b: 50, k: 6500 })).toBe(true);
    expect(pale({ b: 50, h: 240, s: 100 })).toBe(false);
    expect(darkInk({ b: 50, h: 240, s: 100 })).toBe(false);
    expect(darkInk({ b: 50, h: 60, s: 100 })).toBe(true);
    expect(pale({ b: 30 })).toBe(true);
    expect(darkInk({ b: 30 })).toBe(true);
  });
  it("writes the brightness where the tile asks, and always on a brightness alone", () => {
    expect(levelShown({ b: 30 }, false)).toBe(true);
    expect(levelShown({ b: 30, k: 2700 }, false)).toBe(false);
    expect(levelShown({ b: 30, k: 2700 }, true)).toBe(true);
  });
});

describe("the preset the light shows", () => {
  const light = (a: Record<string, unknown>, state = "on") => lightNow({ state, a });
  it("reads the light as its tile does: a percent of 255, white while it reports a colour temperature", () => {
    expect(light({ brightness: 204, color_temp_kelvin: 2702 })).toMatchObject({ on: true, white: true, level: 80, kelvin: 2702 });
    expect(light({ brightness: 3, hs_color: [280.4, 40.6] })).toMatchObject({ white: false, level: 1, hue: 280, saturation: 41 });
    expect(light({}).level).toBe(100);
  });
  it("matches within a percent, 50 K, and 3 of hue (round the circle) and saturation", () => {
    expect(shows({ b: 80, k: 2700 }, light({ brightness: 204, color_temp_kelvin: 2750 }))).toBe(true);
    expect(shows({ b: 80, k: 2700 }, light({ brightness: 204, color_temp_kelvin: 2751 }))).toBe(false);
    expect(shows({ b: 80, k: 2700 }, light({ brightness: 230, color_temp_kelvin: 2700 }))).toBe(false);
    expect(shows({ b: 60, h: 358, s: 41 }, light({ brightness: 153, hs_color: [1, 44] }))).toBe(true);
    // A colour is not shown while the light reports a white, and nothing while it is off.
    expect(shows({ b: 60, h: 30, s: 20 }, light({ brightness: 153, hs_color: [30, 20], color_temp_kelvin: 3000 }))).toBe(false);
    expect(shows({ b: 60 }, light({ brightness: 153 }, "off"))).toBe(false);
    expect(shown([{ b: 10 }, { b: 60 }, { b: 60, k: 2000 }], light({ brightness: 153 }))).toBe(1);
  });
});

describe("the row the keys stand in (light_presets::row)", () => {
  it("takes as many as fit, each as wanted where that fits, smaller down to the least, the first first", () => {
    expect(row(200, 40, 4, 36, 30, 6)).toEqual({ count: 4, size: 36, gap: 6, length: 162 });
    expect(row(140, 40, 4, 36, 30, 6)).toEqual({ count: 4, size: 30, gap: 6, length: 138 });
    expect(row(100, 40, 4, 36, 30, 6)).toEqual({ count: 2, size: 36, gap: 6, length: 78 });
    expect(row(200, 20, 3, 36, 30, 6).size).toBe(20);
    expect(row(0, 40, 4, 36, 30, 6).count).toBe(0);
  });
  it("keeps the ring's room round the keys inside the panel", () => {
    const shape = { dpi: 170, look: "standard" }, z = presetSizes(shape), p = presetPanel(shape, 3, 400, z.tileKey);
    expect(z).toMatchObject({ tileKey: 41, least: 34, gap: 10, ringPad: 3, ringWidth: 2, ring: 5 });
    expect(p.width).toBe(3 * 41 + 2 * 10 + 2 * 5);
    expect(p.keys[0]).toEqual({ x: 5, y: 5, size: 41 });
  });
});

describe("what a preset is kept as", () => {
  it("takes what light_presets.py takes and refuses the rest", () => {
    expect(cleanPreset({ b: 80, k: 2700 })).toEqual({ b: 80, k: 2700 });
    expect(cleanPreset({ b: 60, h: 360, s: 41 })).toEqual({ b: 60, h: 0, s: 41 });
    expect(cleanPreset({ b: 0 })).toBeNull();
    expect(cleanPreset({ b: 50, k: 900 })).toBeNull();
    expect(cleanPreset({ b: 50, k: 2700, h: 3, s: 4 })).toBeNull();
    expect(presetsOf({ presets: [{ b: 1 }, { b: 2 }, { b: 3 }, { b: 4 }, { b: 5 }] })).toHaveLength(4);
  });
  it("starts a new one from what the light shows, else full brightness in its warm white", () => {
    const a = { supported_color_modes: ["color_temp", "hs"], min_color_temp_kelvin: 2200, max_color_temp_kelvin: 6500 };
    expect(fromLight({ state: "on", a: { ...a, brightness: 128, color_temp_kelvin: 3000 } })).toEqual({ b: 50, k: 3000 });
    expect(fromLight({ state: "on", a: { ...a, brightness: 255, hs_color: [200, 70] } })).toEqual({ b: 100, h: 200, s: 70 });
    expect(startPreset({ state: "off", a })).toEqual({ b: 100, k: 2700 });
    expect(startPreset({ state: "off", a: { supported_color_modes: ["brightness"] } })).toEqual({ b: 100 });
  });
  it("is stored on a light only, an empty list and the brightness off never", () => {
    expect(canonicalOptions("light.a", { presets: [], preset_levels: false })).toEqual({});
    expect(canonicalOptions("switch.a", { presets: [{ b: 30 }], preset_levels: true })).toEqual({});
    expect(canonicalOptions("light.a", { presets: [{ b: 30 }], preset_levels: true })).toEqual({ presets: [{ b: 30 }], preset_levels: true });
    expect(optionsSave({ entity: "light.a", name: "", slot: 0 }, { presets: [{ b: 30 }] })).toBe(true);
    expect(optionsSave({ entity: "light.a", name: "", slot: 0 }, { presets: [{ b: 30, k: 1 }] })).toBe(false);
  });
});

// ---- On the editor's screens ----
const LAMP = { supported_color_modes: ["color_temp", "hs"], min_color_temp_kelvin: 2200, max_color_temp_kelvin: 6500, brightness: 204, color_temp_kelvin: 2700 };
function inventory(presets: boolean): Inventory {
  return {
    csrf: "t", connected: true,
    screens: [{ id: "living", name: "Living room", online: true, firmware: "0.60.0", board: "guition", light_presets: presets,
      shape: { width: 480, height: 480, columns: 2, rows: 3, dpi: SHAPES.guition.dpi, catalog: SHAPES.guition.catalog }, layout: { title: "Living room", tiles: [] } } as any],
    entities: [{ id: "light.a", name: "Lamp A", state: "on", area: "Living room" }],
    builtin: [],
    icons: { groups: [], weather: {}, sun: {}, defaults: { light: "F0335" }, fallback: "F0335", builtin: {}, controls: {} },
    backgrounds: { auto: { label: "Default" } },
    controls: { light: { default: "toggle", choices: [{ key: "toggle", label: "On/off" }, { key: "brightness", label: "Brightness" },
      { key: "presets", label: "Presets" }, { key: "brightness_presets", label: "Brightness slider and presets" }, { key: "none", label: "None" }] } },
  } as unknown as Inventory;
}
function open(presets: boolean) {
  vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
  useInventoryStore().inventory = inventory(presets);
  useInventoryStore().inventory.screens = useInventoryStore().inventory.screens.map(screenFixture);
  useScreenStore().selected = "living";
  loadLayout({ title: "Living room", tiles: [] });
  useEntitiesStore().liveStates["light.a"] = { state: "on", word: "On", a: LAMP };
}
const tileOf = (options: Tile["options"], slot = 0): Tile => ({ entity: "light.a", name: "Lamp", slot, options });

describe("a board with the light_presets module", () => {
  it("offers presets and the slider with them only there, and on one cell the presets alone", () => {
    open(true);
    const keys = (options: Tile["options"]) => controlChoices(tileOf(options), tilePanel(tileOf(options)), "toggle").map(([key]) => key);
    expect(keys({ size: "square" })).toEqual(expect.arrayContaining(["presets", "brightness_presets"]));
    expect(keys({ size: "wide" })).toContain("presets");
    expect(keys({ size: "wide" })).not.toContain("brightness_presets");
    expect(keys({})).toEqual(["presets", "none"]);
    open(false);
    expect(keys({ size: "square" })).not.toContain("presets");
    expect(keys({ size: "square" })).not.toContain("brightness_presets");
    expect(presetsOffered(tileOf({ size: "wide", controls: "presets" }), tilePanel(tileOf({})), "presets")).toBe(false);
  });
  it("lays a light of one cell with its presets out as a heading over its keys", () => {
    const options = { controls: "presets", presets: [{ b: 30 }] };
    const face = (lightPresets: boolean) => tileFace({ entity: "light.a", options, shape: { columns: 1, rows: 1 }, full: false, wide: false,
      live: { state: "on", a: LAMP }, chosen: resolveControls({ entity: "light.a", options }), rangeReady: true, bigKeys: true, lightPresets,
      favorite: false, plugin: false, pluginRow: false, watch: false });
    expect(face(true)).toMatchObject({ kind: "tall", presetCell: true, tallControls: "presets" });
    expect(face(false).presetCell).toBe(false);
  });
});

describe("the keys on the mockup", () => {
  beforeEach(() => open(true));
  it("draws them at the right of a wide card, the ring round the one the light shows", () => {
    const tile = tileOf({ size: "wide", controls: "presets", presets: [{ b: 30, h: 30, s: 80 }, { b: 80, k: 2700 }, { b: 100, k: 6500 }] });
    appendTiles(tile);
    const card = mount(TileCard, { props: { tile: current(tile), at: 0 } });
    const discs = card.findAll(".ctl .preset-disc");
    expect(discs).toHaveLength(3);
    expect(discs.map((d) => d.classes("lit"))).toEqual([false, true, false]);
    // Without preset_levels a colour's disc writes no number.
    expect(discs[0].find(".preset-level").exists()).toBe(false);
  });
  it("draws the slider with the keys under it on a card two rows high", () => {
    const tile = tileOf({ size: "square", controls: "brightness_presets", presets: [{ b: 10 }, { b: 80, k: 2700 }], preset_levels: true });
    appendTiles(tile);
    const card = mount(TileCard, { props: { tile: current(tile), at: 0 } });
    expect(card.find(".glass-row .range").exists()).toBe(true);
    expect(card.findAll(".glass-row .preset-disc")).toHaveLength(2);
    expect(card.findAll(".glass-row .preset-level").map((n) => n.text())).toEqual(["10", "80"]);
  });
  it("draws them under the name on a card of one cell", () => {
    const tile = tileOf({ controls: "presets", presets: [{ b: 30 }] });
    appendTiles(tile);
    const card = mount(TileCard, { props: { tile: current(tile), at: 0 } });
    expect(card.findAll(".glass-row .preset-disc")).toHaveLength(1);
  });
});

const inspect = (tile: Tile) => mount(defineComponent({ setup: () => () => h(TileInspector, { tile: current(tile) }) }), { attachTo: document.body });
describe("the inspector's presets", () => {
  beforeEach(() => open(true));
  it("shows only where the control draws them, and adds one from the light's state", async () => {
    const plain = tileOf({ size: "wide", controls: "toggle" });
    appendTiles(plain);
    const first = inspect(plain);
    expect(first.find("#tile-presets").exists()).toBe(false);
    first.unmount();
    loadLayout({ title: "Living room", tiles: [] });
    const tile = tileOf({ size: "wide", controls: "presets" });
    appendTiles(tile);
    const panel = inspect(tile);
    expect(panel.find("#tile-presets .lp-add.first").exists()).toBe(true);
    await panel.find("#tile-presets .lp-add").trigger("click");
    expect(current(tile).options?.presets).toEqual([{ b: 80, k: 2700 }]);
    // One step of undo takes it off again.
    useDocumentStore().undo();
    await nextTick();
    expect(current(tile).options?.presets).toBeUndefined();
  });
  it("turns the brightness on the discs on and off", async () => {
    const tile = tileOf({ size: "wide", controls: "presets", presets: [{ b: 30, k: 3000 }] });
    appendTiles(tile);
    const panel = inspect(tile);
    await flushPromises();
    await panel.find(".lp-levels input, .lp-levels button[role='switch']").trigger("click");
    expect(current(tile).options?.preset_levels).toBe(true);
  });
});

// A light group, lamp by lamp (light_presets::group_shows): what Home Assistant 2026.9.2 made of a purple preset on a group
// of a lamp with colour and white shades, a colour lamp, one that only takes white shades and one that only dims.
import { groupShows, presetLit, type Lamp } from "../src/model/light-presets";
describe("a light group's preset, lamp by lamp", () => {
  const lamp = (over: Partial<Lamp>): Lamp => ({ on: true, unavailable: false, dims: true, color: false, temperature: false, level: 60, hue: 0, saturation: 0, kelvin: 0, ...over });
  const mixed = [lamp({ color: true, temperature: true, hue: 280, saturation: 41 }), lamp({ color: true, hue: 280, saturation: 41 }),
    lamp({ temperature: true, hue: 221, saturation: 20, kelvin: 9861 }), lamp({})];
  it("shows a colour preset the group's average does not", () => {
    expect(groupShows({ b: 60, h: 280, s: 41 }, mixed)).toBe(true);
    expect(groupShows({ b: 80, k: 2700 }, mixed)).toBe(false);
  });
  it("holds a lamp off or in another colour against it, an unavailable one not", () => {
    expect(groupShows({ b: 60, h: 280, s: 41 }, [...mixed.slice(0, 3), lamp({ on: false })])).toBe(false);
    expect(groupShows({ b: 60, h: 280, s: 41 }, [lamp({ color: true, hue: 220, saturation: 41 })])).toBe(false);
    expect(groupShows({ b: 60, h: 280, s: 41 }, [...mixed, lamp({ unavailable: true, on: false })])).toBe(true);
  });
  it("reads a group by its lamps and any other light by itself", () => {
    const states: Record<string, any> = {
      "light.a": { state: "on", a: { supported_color_modes: ["hs", "color_temp"], color_mode: "hs", brightness: 153, hs_color: [280, 41] } },
      "light.b": { state: "on", a: { supported_color_modes: ["color_temp"], color_mode: "color_temp", brightness: 153, color_temp_kelvin: 9861, hs_color: [221.7, 20.5] } },
    };
    const group = { state: "on", a: { entity_id: ["light.a", "light.b"], brightness: 153, hs_color: [261, 34] } };
    expect(presetLit([{ b: 80, k: 2700 }, { b: 60, h: 280, s: 41 }], group, (e) => states[e])).toBe(1);
    expect(presetLit([{ b: 60, h: 280, s: 41 }], states["light.a"], (e) => states[e])).toBe(0);
  });
});

// ---- An effect, the settings of the light's device, and the lamp's own preset (a WLED) ----
import { device, deviceRows, initials, neutral, numberText, presetLabel, rowStart, settingRows, settingsShow, withEffect, withoutEffect,
  type LightChoices } from "../src/model/light-presets";
const WLED: LightChoices = { effects: ["Solid", "Colorloop", "Rainbow"], rows: [
  { e: "select.desk_preset", n: "Preset", key: "preset", kind: "select", options: ["Film", "Reading"], value: "Film" },
  { e: "select.desk_color_palette", n: "Color palette", key: "color_palette", kind: "select", options: ["Default", "Party"], value: "Default" },
  { e: "number.desk_speed", n: "Speed", key: "speed", kind: "number", min: 0, max: 255, step: 1, value: 128 },
  { e: "number.desk_intensity", n: "Intensity", key: "intensity", kind: "number", min: 0, max: 255, step: 1, value: 128 },
  { e: "select.desk_playlist", n: "Playlist", key: "playlist", kind: "select", options: ["Evening"], value: "Evening" },
  { e: "select.desk_mode", n: "Preset", key: "", kind: "select", options: ["A", "B"], value: "A" }] };

describe("a preset with an effect, settings of the device, or the lamp's own", () => {
  it("is kept as light_presets.py keeps it", () => {
    const rw = { "select.desk_color_palette": "Party", "number.desk_speed": 180 };
    expect(cleanPreset({ b: 70, h: 280, s: 41, fx: "Colorloop", rw })).toEqual({ b: 70, h: 280, s: 41, fx: "Colorloop", rw });
    expect(cleanPreset({ b: 90, fx: "Rainbow" })).toEqual({ b: 90, fx: "Rainbow" });
    expect(cleanPreset({ rw: { "select.desk_preset": "Film" } })).toEqual({ rw: { "select.desk_preset": "Film" } });
    // A brightness is needed beside an effect or a colour; the settings at most four, of selects and numbers, each its kind.
    expect(cleanPreset({ fx: "Rainbow", rw })).toBeNull();
    expect(cleanPreset({ k: 2700, rw })).toBeNull();
    expect(cleanPreset({ b: 50, rw: {} })).toBeNull();
    expect(cleanPreset({ b: 50, rw: { "light.x": "a" } })).toBeNull();
    expect(cleanPreset({ b: 50, rw: { "select.x": 3 } })).toBeNull();
    expect(cleanPreset({ b: 50, rw: { "number.x": "3" } })).toBeNull();
    expect(cleanPreset({ b: 50, rw: { "number.a": 1, "number.b": 2, "number.c": 3, "number.d": 4, "number.e": 5 } })).toBeNull();
    expect(cleanPreset({ b: 50, fx: " " })).toBeNull();
    expect(device({ rw: { "select.desk_preset": "Film" } })).toBe(true);
    expect(device({ b: 50, rw })).toBe(false);
  });
  it("draws a plain key with the first two characters of its effect, else of its first setting (Presets::label)", () => {
    expect(initials("Film")).toBe("Fi");
    expect(initials("Ünïcode")).toBe("Ün");
    expect(initials("🌈x")).toBe("🌈x");
    expect(numberText(180)).toBe("180");
    expect(numberText(12.5)).toBe("12.5");
    expect(neutral({ b: 90, fx: "Rainbow" })).toBe(true);
    expect(neutral({ b: 70, h: 280, s: 41, fx: "Colorloop" })).toBe(false);
    expect(neutral({ b: 30 })).toBe(false);
    expect(presetLabel({ b: 90, fx: "Colorloop" }, true)).toBe("Co");
    expect(presetLabel({ rw: { "select.desk_preset": "Film" } }, false)).toBe("Fi");
    expect(presetLabel({ b: 90, rw: { "number.desk_speed": 180 } }, false)).toBe("18");
    expect(presetLabel({ b: 70, h: 280, s: 41, fx: "Colorloop" }, false)).toBe("");
    expect(presetLabel({ b: 70, h: 280, s: 41, fx: "Colorloop" }, true)).toBe("70");
    expect(presetLabel({ b: 30 }, false)).toBe("30");
    // The number never on a plain key, even where the tile shows brightness.
    expect(levelShown({ b: 90, fx: "Rainbow" }, true)).toBe(false);
  });
  it("shows the ring only with its effect and settings standing (light_presets::settings_show)", () => {
    const base = lightNow({ state: "on", a: { brightness: 179, hs_color: [280, 41], effect: "Colorloop" } });
    const p = { b: 70, h: 280, s: 41, fx: "Colorloop", rw: { "select.desk_color_palette": "Party", "number.desk_speed": 180 } };
    expect(shows(p, { ...base, now: { "select.desk_color_palette": "Party", "number.desk_speed": 180.4 } })).toBe(true);
    expect(shows(p, { ...base, now: { "select.desk_color_palette": "Party", "number.desk_speed": 181 } })).toBe(false);
    expect(shows(p, { ...base, now: { "select.desk_color_palette": "Default", "number.desk_speed": 180 } })).toBe(false);
    expect(shows(p, { ...base, now: { "select.desk_color_palette": "Party" } })).toBe(false);
    expect(shows(p, { ...base, effect: "Solid", now: { "select.desk_color_palette": "Party", "number.desk_speed": 180 } })).toBe(false);
    // The lamp's own preset by its select alone, whatever the light shows, off too.
    const own = { rw: { "select.desk_preset": "Film" } };
    expect(shows(own, { ...lightNow({ state: "off", a: {} }), now: { "select.desk_preset": "Film" } })).toBe(true);
    expect(settingsShow(own, { ...base, now: { "select.desk_preset": "Reading" } })).toBe(false);
  });
  it("reads the settings' states from the store and a group's effect as the group's own", () => {
    const states: Record<string, any> = {
      "select.desk_preset": { state: "Film" }, "number.desk_speed": { state: "180.0" },
      "light.a": { state: "on", a: { supported_color_modes: ["hs"], brightness: 230, hs_color: [0, 0] } },
      "light.b": { state: "on", a: { supported_color_modes: ["brightness"], brightness: 230 } },
    };
    const lamp = { state: "on", a: { brightness: 230, effect: "Rainbow" } };
    expect(presetLit([{ b: 90, fx: "Solid" }, { rw: { "select.desk_preset": "Film" } }], lamp, (e) => states[e])).toBe(1);
    expect(presetLit([{ b: 90, fx: "Rainbow", rw: { "number.desk_speed": 180 } }], lamp, (e) => states[e])).toBe(0);
    const group = { state: "on", a: { entity_id: ["light.a", "light.b"], brightness: 230, effect: "Rainbow" } };
    expect(presetLit([{ b: 90, fx: "Solid" }, { b: 90, fx: "Rainbow" }], group, (e) => states[e])).toBe(1);
    expect(presetLit([{ b: 50, fx: "Rainbow" }], group, (e) => states[e])).toBe(-1);
  });
  it("takes the light's effect and its rows as they stand, the lamp's own presets apart", () => {
    expect(deviceRows(WLED).map((r) => r.e)).toEqual(["select.desk_preset", "select.desk_playlist"]);
    // A select Home Assistant does not call a preset or playlist is an ordinary setting, whatever its name.
    expect(settingRows(WLED).map((r) => r.e)).toEqual(["select.desk_color_palette", "number.desk_speed", "number.desk_intensity", "select.desk_mode"]);
    expect(rowStart(WLED.rows[1], "Lost")).toBe("Default");
    expect(rowStart(WLED.rows[2], "300")).toBe(255);
    expect(rowStart(WLED.rows[2], null)).toBe(128);
    const on = withEffect({ b: 70, h: 280, s: 41 }, WLED, "Colorloop", (r) => (r.e === "number.desk_speed" ? "180" : r.value));
    expect(on).toEqual({ b: 70, h: 280, s: 41, fx: "Colorloop", rw: { "select.desk_color_palette": "Default", "number.desk_speed": 180,
      "number.desk_intensity": 128, "select.desk_mode": "A" } });
    expect(withEffect({ b: 70 }, WLED, "Nope", () => undefined).fx).toBe("Solid");
    expect(withoutEffect(on)).toEqual({ b: 70, h: 280, s: 41 });
  });
});

describe("the inspector's presets on a WLED", () => {
  beforeEach(() => {
    open(true);
    const entities = useEntitiesStore();
    entities.lightChoices["light.a"] = WLED;
    entities.liveStates["light.a"] = { state: "on", word: "On", a: { ...LAMP, effect: "Colorloop" } };
    entities.liveStates["number.desk_speed"] = { state: "200", a: {} };
  });
  const popover = () => document.body.querySelector(".lp-pop") as HTMLElement;
  const button = (text: string) => [...popover().querySelectorAll("button")].find((b) => b.textContent?.trim() === text) as HTMLElement;
  it("turns an effect on with the light's effect and rows, and off again", async () => {
    const tile = tileOf({ size: "wide", controls: "presets", presets: [{ b: 80, k: 2700 }] });
    appendTiles(tile);
    const panel = inspect(tile);
    await panel.find(".lp-swatch").trigger("click");
    await flushPromises();
    expect(popover()).toBeTruthy();
    (popover().querySelector(".lp-effect button[role='switch']") as HTMLElement).click();
    await flushPromises();
    expect(current(tile).options?.presets).toEqual([{ b: 80, k: 2700, fx: "Colorloop", rw: { "select.desk_color_palette": "Default",
      "number.desk_speed": 200, "number.desk_intensity": 128, "select.desk_mode": "A" } }]);
    expect(popover().querySelector(".lp-fx")?.textContent).toContain("Colorloop");
    (popover().querySelector(".lp-effect button[role='switch']") as HTMLElement).click();
    await flushPromises();
    expect(current(tile).options?.presets).toEqual([{ b: 80, k: 2700 }]);
    panel.unmount();
  });
  it("makes a preset of the lamp itself, a plain key with its name", async () => {
    const tile = tileOf({ size: "wide", controls: "presets", presets: [{ b: 80, k: 2700 }] });
    appendTiles(tile);
    const panel = inspect(tile);
    await panel.find(".lp-swatch").trigger("click");
    await flushPromises();
    button("Lamp's own preset").click();
    await flushPromises();
    expect(current(tile).options?.presets).toEqual([{ rw: { "select.desk_preset": "Film" } }]);
    button("Playlist").click();
    await flushPromises();
    expect(current(tile).options?.presets).toEqual([{ rw: { "select.desk_playlist": "Evening" } }]);
    button("Preset").click();
    await flushPromises();
    ([...popover().querySelectorAll(".lp-option")].find((o) => o.textContent?.includes("Reading")) as HTMLElement).click();
    await flushPromises();
    expect(current(tile).options?.presets).toEqual([{ rw: { "select.desk_preset": "Reading" } }]);
    expect(panel.find(".lp-swatch .preset-disc").classes()).toContain("plain");
    expect(panel.find(".lp-swatch .preset-level").text()).toBe("Re");
    button("Own setting").click();
    await flushPromises();
    expect(current(tile).options?.presets).toEqual([{ b: 80, k: 2700 }]);
    panel.unmount();
  });
  it("draws a plain key on the mockup with its initials and no number", () => {
    const tile = tileOf({ size: "wide", controls: "presets", preset_levels: true, presets: [{ b: 90, fx: "Rainbow" }, { b: 80, k: 2700 }] });
    appendTiles(tile);
    const card = mount(TileCard, { props: { tile: current(tile), at: 0 } });
    expect(card.findAll(".ctl .preset-level").map((n) => n.text())).toEqual(["Ra", "80"]);
    expect(card.findAll(".ctl .preset-disc")[0].classes()).toContain("plain");
  });
});
