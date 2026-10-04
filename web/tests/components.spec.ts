import { seedLayout, seedTiles, seedPages, seedTitles, appendTiles, screenFixture, documentFixture, current } from "./page-fixtures";
// The components that draw the state: a tile with live values, the library's filters, the ⌘K search.
import { readFileSync } from "node:fs";
import { flushPromises, mount } from "@vue/test-utils";
import { defineComponent, h, nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AppSettingsView from "../src/components/AppSettingsView.vue";
import CommandPalette from "../src/components/CommandPalette.vue";
import Library from "../src/components/Library.vue";
import ChoiceField from "../src/components/ChoiceField.vue";
import DevicePage from "../src/components/DevicePage.vue";
import InstallerView from "../src/components/InstallerView.vue";
import Sidebar from "../src/components/Sidebar.vue";
import HomeView from "../src/components/HomeView.vue";
import SettingsTab from "../src/components/SettingsTab.vue";
import TileCard from "../src/components/TileCard.vue";
import TileInspector from "../src/components/TileInspector.vue";
import TopbarInspector from "../src/components/TopbarInspector.vue";
import PageInspector from "../src/components/PageInspector.vue";
import { t } from "../src/i18n";
import { openBar, previewed, removePage, repeatable, setTileOption, state } from "../src/store";
import type { Inventory, Tile } from "../src/types";

// The add-on's boards (screen_manager/app/boards.json, written from boards.yaml and the board files): the catalog a
// screen's shape carries, and what New screen gets for each board (firmware.BOARD_CHOICES), made the same way here.
const SHAPES = JSON.parse(readFileSync("../screen_manager/app/boards.json", "utf8"));
const BOARD_CHOICES = Object.fromEntries(Object.entries(SHAPES).filter(([key, shape]: [string, any]) => shape.board === key)
  .map(([key, shape]: [string, any]) => [key, {
    square: shape.width === shape.height, orientations: shape.orientations, width: shape.width, height: shape.height, dpi: shape.dpi,
    camera: Boolean(shape.camera), dimmable: shape.dimmable ?? true, can_standby: shape.can_standby ?? true, ...shape.catalog,
  }]));

function inventory(): Inventory {
  return {
    csrf: "t", connected: true,
    screens: [{ id: "living", name: "Living room", online: true, firmware: "0.2.60", board: "guition", shape: { width: 480, height: 480, columns: 2, rows: 3, catalog: SHAPES.guition.catalog }, layout: { title: "Living room", tiles: [] }, alert_action: "esphome.living_show_alert" } as any],
    entities: [
      { id: "light.a", name: "Lamp A", state: "on", area: "Living room", device: "Hue" },
      { id: "light.b", name: "Lamp B", state: "unavailable", area: "Kitchen" },
      { id: "sensor.t", name: "Temperature", state: "21.5", area: "Living room" },
      { id: "cover.c", name: "Curtains", state: "open", area: "Living room" },
    ],
    builtin: [
      { id: "screen.clock", name: "Clock", device: "Built into the screen", area: "", state: "ok" },
      { id: "screen.page_1", name: "Go to page 1", device: "Built into the screen", area: "", state: "ok" },
    ],
    icons: { groups: [], weather: { partlycloudy: "F0595" }, sun: { below_horizon: "F0594" }, defaults: { light: "F0335", sensor: "F050F", cover: "F1846" }, fallback: "F0335", builtin: { "screen.clock": "F0150" }, controls: { minus: "F0374", plus: "F0415" } },
    backgrounds: { auto: { label: "Default" }, none: { label: "None" } },
    controls: { light: { default: "toggle", choices: [{ key: "toggle", label: "On/off" }, { key: "brightness", label: "Brightness" }, { key: "none", label: "None" }] } },
    alerts: { min_firmware: "0.2.31" },
  } as unknown as Inventory;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
  state.inventory = inventory();
  state.inventory.screens = state.inventory.screens.map(screenFixture);
  state.selected = "living";
  seedLayout({ title: "Living room", tiles: [] });
  state.liveStates = {};
  state.search = ""; state.filter = ""; state.room = ""; state.hidePlaced = false;
  state.palette = false;
  state.selectedTile = null; state.inspector = null;
  state.dirty = false; state.tab = "layout";
});

// A field's explanation (app 0.3.19): a warning stays in sight under the field, anything else is the tooltip beside its label.
function hint(field: { find: (selector: string) => any }) {
  const warn = field.find("small.warn");
  return warn.exists() ? { text: warn.text(), warn: true } : { text: field.find(".help-trigger").attributes("aria-label") || "", warn: false };
}
function inspector(tile: Tile) {
  const host = mount(defineComponent({ setup: () => () => h(TileInspector, { tile: tile.id ? current(tile) || tile : tile }) }));
  return host.findComponent(TileInspector);
}

function placed(tile: Tile) {
  appendTiles(tile);
  return mount(TileCard, { props: { tile, slot: tile.slot } });
}

describe("TileCard", () => {
  it("draws a bedside clock's keys round, each with the tile's own remove key (app 0.4.12)", async () => {
    seedLayout({ title: "Bedroom", tiles: [
      { entity: "screen.nightstand", name: "", slot: 0, options: { size: "full", background: "none" } },
      { entity: "light.bedside", name: "Lamp", slot: -1, in: "screen.nightstand", key: 0 },
      { entity: "lock.front", name: "Front door", slot: -1, in: "screen.nightstand", key: 1 }] });
    const clock = state.layout!.tiles[0];
    const card = mount(TileCard, { props: { tile: clock, slot: 0 } });
    expect(card.findAll(".round-tile")).toHaveLength(2);
    expect(card.findAll(".key-empty")).toHaveLength(1);
    await card.findAll(".round-tile .remove")[0].trigger("click");
    expect(state.layout!.tiles.map((tile) => tile.entity)).toEqual(["screen.nightstand", "lock.front"]);
    expect(state.document!.pages[0].tiles[0].children?.map((child) => child.content.entityId)).toEqual(["lock.front"]);
  });
  it('keeps the cover primary control when slats are selected or the tile shrinks', async () => {
    state.inventory.controls!.cover = { default: 'buttons', choices: [
      { key: 'buttons', label: 'Open, stop, close' }, { key: 'position', label: 'Position' },
      { key: 'tilt', label: 'Tilt' }, { key: 'position_tilt', label: 'Position and tilt' }, { key: 'none', label: 'None' },
    ] };
    state.capabilities['cover.c'] = { controls: ['buttons', 'position', 'tilt', 'position_tilt', 'buttons_tilt'], toggle: true, inline: true, displays: ['standard'] };
    state.liveStates['cover.c'] = { state: 'open', word: 'Open', a: { supported_features: 255, current_position: 45, current_tilt_position: 65 } };
    const tile: Tile = { entity: 'cover.c', name: '', slot: 0, options: { size: 'square', controls: 'position' } };
    appendTiles(tile);
    const settings = inspector(tile);
    expect(settings.find('.tilt-choice [role=switch]').exists()).toBe(true);
    await settings.find('.tilt-choice [role=switch]').trigger('click');
    expect(current(tile)?.options?.controls ?? tile.options?.controls).toBe('position_tilt');
    await settings.find('.tilt-choice [role=switch]').trigger('click');
    expect(current(tile)?.options?.controls ?? tile.options?.controls).toBe('position');
    const card = mount(TileCard, { props: { tile: { ...tile, options: { size: 'tall', controls: 'position_tilt' } }, slot: 0 } });
    expect(card.findComponent({ name: 'CoverTilePreview' }).exists()).toBe(true);
    await card.setProps({ tile: { ...tile, options: { size: 'wide', controls: 'position_tilt' } } });
    expect(card.find('.cover-preview').exists()).toBe(false);
    expect(card.find('.ctl .range').exists()).toBe(true);
    for (const controls of ['none', 'tilt']) {
      await card.setProps({ tile: { ...tile, options: { size: 'wide', controls } } });
      expect(card.find('.ctl').exists()).toBe(false);
    }
  });

  it("extends only taller tiles and waits for actual artwork before using white text", async () => {
    state.inventory.controls!.media_player = { default: 'playback', choices: [] };
    state.liveStates['media_player.a'] = { state: 'playing', word: 'Playing', a: { media_title: 'A track', media_artist: 'An artist', artwork_mark: 'first', supported_features: 49 } };
    // A screen that draws pictures (app 0.4.42: a CYD's mockup draws no cover it will never show).
    Object.assign(state.inventory.screens[0], { pictures: true });
    const card = placed({ entity: 'media_player.a', name: 'Music', slot: 0, options: { size: 'tall', display: 'cover', controls: 'playback' } });
    expect(card.classes()).toContain('tall');
    expect(card.find('.track-title').text()).toBe('A track');
    expect(card.findAll('.ctl .key')).toHaveLength(3);
    state.liveStates['media_player.a'].a.supported_features = 1;
    await nextTick();
    expect(card.findAll('.ctl .key')).toHaveLength(1);
    expect(card.find('.ctl .key').classes()).toContain('primary');
    expect(card.find('img').attributes('src')).toBe('api/media-art?entity=media_player.a&v=first');
    expect(card.classes()).not.toContain('photo');
    await card.find('img').trigger('load');
    expect(card.classes()).toContain('photo');
    state.liveStates['media_player.a'].a.artwork_mark = 'second';
    await nextTick();
    expect(card.classes()).not.toContain('photo');
    await card.find('img').trigger('error');
    expect(card.classes()).not.toContain('photo');
    await card.setProps({ tile: { entity: 'media_player.a', name: 'Music', slot: 0, options: { size: 'wide', display: 'cover', controls: 'playback' } } });
    expect(card.classes()).not.toContain('tall');
    expect(card.find('.tall-body').exists()).toBe(false);
    expect(card.find('img').exists()).toBe(false);
    Object.assign(state.inventory.screens[0], { pictures: false });
    await card.setProps({ tile: { entity: 'media_player.a', name: 'Music', slot: 0, options: { size: 'tall', display: 'cover', controls: 'playback' } } });
    expect(card.find('img').exists()).toBe(false);
  });
  it("shows the selected climate target or modes, and adds no controls to an unconfigured tall tile", () => {
    state.inventory.controls!.climate = { default: 'setpoint', choices: [] };
    state.liveStates['climate.a'] = { state: 'cool', word: 'Cooling', a: { supported_features: 1, current_temperature: 24, temperature: 21, hvac_modes: ['off', 'cool'] } };
    const plain = placed({ entity: 'climate.a', name: 'Climate', slot: 0, options: { size: 'tall' } });
    expect(plain.find('.ctl').exists()).toBe(false);
    expect(plain.find('.tall-setpoint').exists()).toBe(false);
    const target = placed({ entity: 'climate.a', name: 'Climate', slot: 0, options: { size: 'tall', controls: 'setpoint' } });
    expect(target.find('.target b').text()).toBe('21°');
    expect(target.find('.tall-setpoint .st').text()).toBe('Now 24°');
    state.liveStates['climate.a'].a.hvac_modes = ['off', 'heat', 'cool', 'dry'];
    const modes = placed({ entity: 'climate.a', name: 'Climate', slot: 0, options: { size: 'square', controls: 'mode' } });
    // "Mode" on a taller card is the same bar as under the -/+ of "Temperature and mode".
    expect(modes.findAll('.ctl .mode-bar .seg').map((s) => s.classes('on'))).toEqual([false, true, false]);
    const both = placed({ entity: 'climate.a', name: 'Climate', slot: 0, options: { size: 'square', controls: 'setpoint_mode' } });
    expect(both.findAll('.mode-bar .seg')).toHaveLength(3);
  });

  it("draws a humidifier as a thermostat in percent, with its action, its own modes in blue and its slider (firmware 0.42.0)", () => {
    state.inventory.controls!.humidifier = { default: 'setpoint', choices: [] };
    const a = { supported_features: 1, current_humidity: 68, humidity: 55, min_humidity: 30, max_humidity: 80, action: 'drying',
      device_class: 'dehumidifier', available_modes: ['normal', 'eco', 'boost'], mode: 'eco' };
    state.liveStates['humidifier.h'] = { state: 'on', word: 'On', a };
    // Home Assistant's word for what it is doing and the humidity now; Off while it is off; On without an action.
    expect(placed({ entity: 'humidifier.h', name: 'Dryer', slot: 0 }).find('.st').text()).toBe('Drying · 68%');
    state.liveStates['humidifier.h'] = { state: 'on', word: 'On', a: { ...a, action: 'humidifying', current_humidity: 38 } };
    expect(placed({ entity: 'humidifier.h', name: 'Dryer', slot: 0 }).find('.st').text()).toBe('Humidifying · 38%');
    state.liveStates['humidifier.h'] = { state: 'off', word: 'Off', a: { ...a, action: 'off', current_humidity: 52 } };
    const off = placed({ entity: 'humidifier.h', name: 'Dryer', slot: 0 });
    expect(off.find('.st').text()).toBe('Off · 52%');
    expect(off.attributes('style')).toContain('--tile-accent: #9e9e9e');
    state.liveStates['humidifier.h'] = { state: 'on', word: 'On', a: { ...a, action: undefined, current_humidity: undefined } };
    expect(placed({ entity: 'humidifier.h', name: 'Dryer', slot: 0 }).find('.st').text()).toBe('On');
    state.liveStates['humidifier.h'] = { state: 'on', word: 'On', a: { ...a, current_humidity: 45.5 } };
    expect(placed({ entity: 'humidifier.h', name: 'Dryer', slot: 0 }).find('.st').text()).toBe('Drying · 45.5%');
    state.liveStates['humidifier.h'] = { state: 'on', word: 'On', a };
    // On it is Home Assistant's blue.
    expect(placed({ entity: 'humidifier.h', name: 'Dryer', slot: 0 }).attributes('style')).toContain('--tile-accent: #2196f3');
    // The humidity it is set to between - and +, on a wide card and a tall one with the humidity now under it.
    expect(placed({ entity: 'humidifier.h', name: 'Dryer', slot: 0, options: { size: 'wide', controls: 'setpoint' } }).find('.stp b').text()).toBe('55%');
    const tall = placed({ entity: 'humidifier.h', name: 'Dryer', slot: 0, options: { size: 'tall', controls: 'setpoint' } });
    expect(tall.find('.target b').text()).toBe('55%');
    expect(tall.find('.tall-setpoint .st').text()).toBe('Now 68%');
    // Its modes as the mode bar with Home Assistant's icons, the one it is in filled blue.
    const modes = placed({ entity: 'humidifier.h', name: 'Dryer', slot: 0, options: { size: 'wide', controls: 'mode' } });
    const segs = modes.findAll('.ctl .mode-bar .seg');
    expect(segs.map((s) => s.find('.mdi').text())).toEqual([String.fromCodePoint(0xF058E), String.fromCodePoint(0xF032A), String.fromCodePoint(0xF14DE)]);
    expect(segs.map((s) => s.classes('on'))).toEqual([false, true, false]);
    expect(segs[1].attributes('style')).toContain('#2196f3');
    const both = placed({ entity: 'humidifier.h', name: 'Dryer', slot: 0, options: { size: 'square', controls: 'setpoint_mode' } });
    expect(both.find('.tall-setpoint .target b').text()).toBe('55%');
    expect(both.findAll('.mode-bar .seg')).toHaveLength(3);
    // The slider fills to the humidity it is set to over its own range: 55 of 30 to 80 is half.
    const slider = placed({ entity: 'humidifier.h', name: 'Dryer', slot: 0, options: { size: 'wide', controls: 'slider' } });
    expect(slider.find('.ctl .range').attributes('style')).toContain('50%');
  });

  it("writes a thermostat set to a range as Home Assistant does, with the chip for its end between - and + (firmware 0.19.0)", () => {
    state.inventory.controls!.climate = { default: 'setpoint', choices: [] };
    state.liveStates['climate.r'] = { state: 'heat_cool', word: 'Heat/Cool', a: { supported_features: 442, current_temperature: 73, target_temp_low: 70, target_temp_high: 75, target_temp_step: 1 } };
    expect(placed({ entity: 'climate.r', name: 'Range', slot: 0 }).find('.st').text()).toBe('Heat/Cool · 73°');
    // The wide tile's -/+ with the chip between them: the low end, heat, first.
    const wide = placed({ entity: 'climate.r', name: 'Range', slot: 0, options: { size: 'wide', controls: 'setpoint' } });
    expect(wide.find('.stp .range-chip b').text()).toBe('70°');
    expect(wide.findAll('.stp > .mdi')).toHaveLength(2);
    // Both features: the range only while it reports no single temperature.
    state.liveStates['climate.b'] = { state: 'heat_cool', word: 'Heat/Cool', a: { supported_features: 3, current_temperature: 21, target_temp_low: 19, target_temp_high: 23.5, temperature: null } };
    expect(placed({ entity: 'climate.b', name: 'Both', slot: 0, options: { size: 'tall', controls: 'setpoint' } }).find('.range-chip b').text()).toBe('19.0°');
    state.liveStates['climate.b'].a.temperature = 20;
    const single = placed({ entity: 'climate.b', name: 'Both', slot: 0, options: { size: 'tall', controls: 'setpoint' } });
    expect(single.find('.range-chip').exists()).toBe(false);
    expect(single.find('.target b').text()).toBe('20°');
    // One set to a single temperature says it as Home Assistant sends it: 68°, 21.5°, never 68.0°.
    state.liveStates['climate.s'] = { state: 'heat', word: 'Heat', a: { supported_features: 385, temperature: 68, current_temperature: 77 } };
    expect(placed({ entity: 'climate.s', name: 'Single', slot: 0 }).find('.st').text()).toBe('68°');
    state.liveStates['climate.s'].a.temperature = 21.5;
    expect(placed({ entity: 'climate.s', name: 'Single', slot: 0 }).find('.st').text()).toBe('21.5°');
    state.liveStates['climate.d'] = { state: 'dry', word: 'Dry', a: { supported_features: 1, current_temperature: 21.5 } };
    expect(placed({ entity: 'climate.d', name: 'Dry', slot: 0 }).find('.st').text()).toBe('Dry · 21.5°');
  });
  it("draws a range thermostat without its -/+ for a screen before firmware 0.19.0, as that screen gets it", () => {
    state.inventory.controls!.climate = { default: 'setpoint', choices: [] };
    state.liveStates['climate.r'] = { state: 'heat_cool', word: 'Heat/Cool', a: { supported_features: 442, current_temperature: 73, target_temp_low: 70, target_temp_high: 75 } };
    const screen = state.inventory.screens[0];
    const before = screen.climate_range;
    screen.climate_range = false;
    try {
      const wide = placed({ entity: 'climate.r', name: 'Range', slot: 0, options: { size: 'wide', controls: 'setpoint' } });
      expect(wide.find('.stp').exists()).toBe(false);
      expect(wide.find('.range-chip').exists()).toBe(false);
    } finally { screen.climate_range = before; }
  });

  it("draws a wide card's keys as the screen does for that entity, not a fixed set (app 0.4.32)", () => {
    state.inventory.controls!.climate = { default: 'setpoint', choices: [] };
    state.liveStates['climate.m'] = { state: 'heat', word: 'Heat', a: { supported_features: 1, hvac_modes: ['off', 'heat', 'cool'], temperature: 20 } };
    const modes = placed({ entity: 'climate.m', name: 'Modes', slot: 0, options: { size: 'wide', controls: 'mode' } });
    // Its mode bar, as the screen draws it: heat and cool, its own modes; off is the tile's circle.
    expect(modes.findAll('.ctl .mode-bar .seg')).toHaveLength(2);
    expect(modes.find('.mode-bar .seg.on').exists()).toBe(true);
    state.liveStates['climate.m'].a.hvac_modes = ['off', 'heat'];
    // One mode besides off makes no bar.
    expect(placed({ entity: 'climate.m', name: 'Modes', slot: 0, options: { size: 'wide', controls: 'mode' } }).findAll('.mode-bar .seg')).toHaveLength(0);
    state.inventory.controls!.vacuum = { default: 'buttons', choices: [] };
    state.liveStates['vacuum.v'] = { state: 'docked', word: 'Docked', a: { supported_features: 8192 | 8 } };
    const vacuum = placed({ entity: 'vacuum.v', name: 'Robot', slot: 0, options: { size: 'wide', controls: 'buttons' } });
    expect(vacuum.findAll('.ctl .key')).toHaveLength(2);   // start and stop: it cannot go back to its base
  });

  it("shows a sensor's value with its unit and a light that is on as lit", () => {
    state.liveStates["sensor.t"] = { state: "21.4", word: null, a: { unit_of_measurement: "°C" } };
    state.liveStates["light.a"] = { state: "on", word: "On", a: { brightness: 128 } };
    const sensor = placed({ entity: "sensor.t", name: "Temp", slot: 0 });
    expect(sensor.text()).toContain("21.4 °C");
    const lamp = placed({ entity: "light.a", name: "", slot: 1, options: { inline: "slider" } });
    expect(lamp.text()).toContain("Lamp A");
    expect(lamp.find(".ic").classes()).toContain("lit");
    expect(lamp.find(".mini-slider").attributes("style")).toContain("50%");
  });
  it("fills a blind's bar with its closed part, like the screen and its card", () => {
    state.liveStates["cover.c"] = { state: "open", word: "Open", a: { current_position: 30 } };
    const blind = placed({ entity: "cover.c", name: "", slot: 2, options: { inline: "slider" } });
    expect(blind.find(".mini-slider").attributes("style")).toContain("70%");
  });
  it("draws the large value, the wide card's toggle and an unavailable entity in grey", () => {
    state.liveStates["sensor.t"] = { state: "1249", word: null, a: { unit_of_measurement: "W" } };
    const big = placed({ entity: "sensor.t", name: "Power", slot: 0, options: { display: "watch" } });
    // Numbers as the screens write them (app 0.2.90): "1,234.5" until the add-on names another format.
    expect(big.find(".big").text()).toBe("1,249W");
    state.liveStates["light.a"] = { state: "off", word: "Off", a: {} };
    const wide = placed({ entity: "light.a", name: "", slot: 2, options: { size: "wide" } });
    expect(wide.classes()).toContain("wide");
    expect(wide.find(".tog").classes()).toContain("off");
    expect(wide.find(".ic").classes()).not.toContain("lit");
    const gone = placed({ entity: "light.b", name: "", slot: 4 });
    expect(gone.find(".st").text()).toBe("Unavailable");
    expect(gone.find(".st").classes()).toContain("off");
  });
  it("draws a single tile as the screen does: the icon left, the name and value beside it", () => {
    state.liveStates["sensor.t"] = { state: "1249", word: null, a: { unit_of_measurement: "W" } };
    const plain = placed({ entity: "sensor.t", name: "Power", slot: 0 });
    expect(plain.find(".head > .ic").exists()).toBe(true);
    expect(plain.find(".head > .tx > .nm").text()).toBe("Power");
    expect(plain.find(".head > .tx > .st").text()).toBe("1,249 W");
    // A watch card keeps the name next to the icon and puts the big value underneath.
    const watch = placed({ entity: "sensor.t", name: "Power", slot: 1, options: { display: "watch" } });
    expect(watch.find(".head").classes()).toContain("top");
    expect(watch.find(".head .big").exists()).toBe(false);
    expect(watch.find(".head + .big").text()).toBe("1,249W");
    state.liveStates["light.a"] = { state: "on", word: "On", a: { brightness: 255 } };
    const lamp = placed({ entity: "light.a", name: "", slot: 2, options: { inline: "slider" } });
    expect(lamp.find(".head + .mini-slider").exists()).toBe(true);
  });
  it("shows the display name when Home Assistant has no value, and nothing for a scene", () => {
    const graph = placed({ entity: "sensor.x", name: "Unknown sensor", slot: 0, options: { display: "graph" } });
    expect(graph.find(".st").text()).toBe("graph");
    state.liveStates["scene.movie"] = { state: "2026-09-14T19:15:00+00:00", word: null, a: {} };
    const scene = placed({ entity: "scene.movie", name: "Movie", slot: 1 });
    expect(scene.find(".st").exists()).toBe(false);
  });
  it("opens the tile's settings on a click", async () => {
    const lamp = placed({ entity: "light.a", name: "", slot: 0 });
    await lamp.trigger("click");
    expect(state.selectedTile?.entity).toBe("light.a");
    expect(state.inspector).toEqual({ kind: "tile" });
    expect(lamp.classes()).toContain("chosen");
  });
});

describe("Library", () => {
  beforeEach(() => { state.libraryOpen = true; });
  const room = (library: ReturnType<typeof mount>, name: string) => library.findAll("#room button").find((b) => b.find(".dn").text() === name)!;
  it("groups by room, filters by room and hides what is placed, and tints the avatars by state", async () => {
    appendTiles({ entity: "light.a", name: "", slot: 0 });
    const library = mount(Library);
    const names = () => library.findAll(".ent .tx b").map((b) => b.text());
    // Browsing, each room under its name and the screen's own cards last (app 0.4.32).
    expect(library.findAll(".lib-group-title").map((h) => h.text())).toEqual(["Kitchen 1", "Living room 3", "Screen 2"]);
    expect(names()).toEqual(["Lamp B", "Lamp A", "Temperature", "Curtains", "Clock", "Go to page 1"]);
    expect(library.find('.ent[title="light.a"]').attributes("disabled")).toBeDefined();
    expect(library.find('.ent[title="light.a"] .av').classes()).toContain("on");
    expect(library.find('.ent[title="light.b"] .av').classes()).toContain("gone");
    expect(library.findAll("#room button .dn").map((o) => o.text())).toEqual(["Kitchen", "Living room"]);
    await room(library, "Kitchen").trigger("click");
    expect(names()).toEqual(["Lamp B"]);
    expect(library.find(".lib-group-title").exists()).toBe(false);
    // The chosen room again is all rooms.
    await room(library, "Kitchen").trigger("click");
    expect(state.room).toBe("");
    await library.find("#hide-placed").trigger("click");
    expect(names()).toEqual(["Lamp B", "Temperature", "Curtains", "Clock", "Go to page 1"]);
    state.filter = "light";
    await library.vm.$nextTick();
    expect(names()).toEqual(["Lamp B"]);
  });
});

// The domains were a strip of chips: first on a sideways scroller a mouse could not reach (app 0.2.74), then wrapped
// with the tail behind "More" (app 0.2.116). In the drawer along the bottom they are one column, every one in reach,
// following the results the way the list does (app 0.4.32).
describe("Library: the drawer along the bottom, with every domain in one column (app 0.4.32)", () => {
  const label = (b: { find: (s: string) => { text: () => string } }) => b.find(".dn").text();
  const domains = (library: ReturnType<typeof mount>) => library.findAll("#filters button").map(label);
  const counts = (library: ReturnType<typeof mount>) => library.findAll("#filters button").map((b) => `${label(b)} ${b.find("small").text()}`);
  const chip = (library: ReturnType<typeof mount>, name: string) =>
    library.findAll("#filters button").find((b) => label(b) === name)!;
  // One entity in each of nine domains, more than the old strip of chips could hold.
  const manyDomains = () => state.inventory.entities.push(
    { id: "climate.c", name: "Heating", state: "heat" }, { id: "switch.s", name: "Plug", state: "on" },
    { id: "binary_sensor.b", name: "Door", state: "off" }, { id: "script.r", name: "Run", state: "off" },
    { id: "fan.f", name: "Fan", state: "off" }, { id: "scene.n", name: "Night", state: "on" },
    { id: "media_player.m", name: "Sonos", state: "idle" }, { id: "person.p", name: "Sam", state: "home" },
  ) as unknown as void;
  beforeEach(() => { state.libraryOpen = true; });

  it("offers the domains the results hold, each with its count, and narrows them as the search narrows the list", async () => {
    const library = mount(Library);
    // Four domains in this home, plus All. A domain with nothing behind it would filter to an empty list.
    expect(domains(library)).toEqual(["All", "Lights", "Covers", "Sensors", "Screen"]);
    expect(counts(library).slice(0, 2)).toEqual([`All ${library.findAll(".ent").length}`, "Lights 2"]);

    state.search = "lamp";
    await library.vm.$nextTick();
    expect(domains(library)).toEqual(["All", "Lights"]);
    state.search = "temp";
    await library.vm.$nextTick();
    expect(domains(library)).toEqual(["All", "Sensors"]);
  });

  it("keeps every other domain once one is chosen, so a domain is never a dead end", async () => {
    const library = mount(Library);
    await chip(library, "Lights").trigger("click");
    expect(state.filter).toBe("light");
    expect(library.findAll(".ent .tx b").map((b) => b.text())).toEqual(["Lamp B", "Lamp A"]);
    // Read off the domain filter itself and picking Lights would have taken Sensors and Covers away with it.
    expect(domains(library)).toEqual(["All", "Lights", "Covers", "Sensors", "Screen"]);
    expect(chip(library, "Lights").attributes("aria-pressed")).toBe("true");
  });

  it("keeps the chosen domain in sight when the search leaves nothing of it", async () => {
    const library = mount(Library);
    await chip(library, "Lights").trigger("click");
    state.search = "temp";
    await library.vm.$nextTick();
    expect(library.findAll(".ent").length).toBe(0);
    // An empty list needs the domain that empties it on show, or there is nothing to explain it and nothing to undo.
    expect(domains(library)).toContain("Lights");
    expect(chip(library, "Lights").attributes("aria-pressed")).toBe("true");
  });

  it("lists every domain at once, however many there are", () => {
    manyDomains();
    const library = mount(Library);
    expect(domains(library)).toEqual([
      "All", "Lights", "Climate", "Switches", "Status", "Scripts", "Fans", "Covers", "Scenes", "Sensors",
      "Media", "People", "Screen",
    ]);
    expect(library.find("#more-filters").exists()).toBe(false);
  });

  it("folds to its head, keeps the search there, and opens again on typing", async () => {
    const library = mount(Library);
    await library.find("#library-toggle").trigger("click");
    expect(state.libraryOpen).toBe(false);
    expect(library.find("#library-body").attributes("inert")).toBeDefined();
    expect(library.find("#search").exists()).toBe(true);
    await library.find("#search").setValue("lamp");
    expect(state.libraryOpen).toBe(true);
    expect(library.findAll(".ent .tx b").map((b) => b.text())).toEqual(["Lamp A", "Lamp B"]);
  });

  it("starts a search from a key typed anywhere, and leaves a field's keys to the field", async () => {
    const library = mount(Library, { attachTo: document.body });
    state.libraryOpen = false;
    state.tab = "layout";
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "l", bubbles: true, cancelable: true }));
    await nextTick();
    expect(state.search).toBe("l");
    expect(state.libraryOpen).toBe(true);
    const field = document.createElement("input");
    document.body.append(field);
    field.dispatchEvent(new KeyboardEvent("keydown", { key: "x", bubbles: true, cancelable: true }));
    expect(state.search).toBe("l");
    // A shortcut is not a letter to search for.
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "z", metaKey: true, bubbles: true, cancelable: true }));
    expect(state.search).toBe("l");
    field.remove();
    library.unmount();
  });

  it("selects nothing on the page while its edge is dragged", async () => {
    const library = mount(Library, { attachTo: document.body });
    const grip = library.find(".lib-grip").element as HTMLElement;
    grip.setPointerCapture = () => {};
    const down = Object.assign(new Event("pointerdown", { bubbles: true, cancelable: true }), { clientY: 400, pointerId: 1 });
    grip.dispatchEvent(down);
    expect(down.defaultPrevented).toBe(true);
    expect(document.body.style.userSelect).toBe("none");
    grip.dispatchEvent(new Event("pointerup", { bubbles: true }));
    expect(document.body.style.userSelect).toBe("");
    library.unmount();
  });

  it("walks the results with the arrows, adds with Enter, and clears then folds with Escape", async () => {
    const library = mount(Library);
    const search = library.find("#search");
    await search.setValue("lamp");
    expect(library.find(".ent.active .tx b").text()).toBe("Lamp A");
    await search.trigger("keydown", { key: "ArrowDown" });
    expect(library.find(".ent.active .tx b").text()).toBe("Lamp B");
    await search.trigger("keydown", { key: "Enter" });
    expect(state.layout!.tiles.map((tile) => tile.entity)).toContain("light.b");
    await search.trigger("keydown", { key: "Escape" });
    expect(state.search).toBe("");
    expect(state.libraryOpen).toBe(true);
    await search.trigger("keydown", { key: "Escape" });
    expect(state.libraryOpen).toBe(false);
  });

  it("names an entity without its device's name in front, and puts the device under it", async () => {
    state.inventory.entities.push({ id: "switch.n", name: "Bedroom screen night mode", state: "off", area: "Bedroom", device: "Bedroom screen" } as any);
    const library = mount(Library);
    const row = library.find('.ent[title="switch.n"]');
    expect(row.find(".tx b").text()).toBe("Night mode");
    expect(row.find(".tx small").text()).toBe("Bedroom screen");
  });

  it("opens when an empty cell is marked for the next entity", async () => {
    const library = mount(Library);
    state.libraryOpen = false;
    await library.vm.$nextTick();
    state.insertAt = 3;
    await library.vm.$nextTick();
    expect(state.libraryOpen).toBe(true);
  });
});

describe("CommandPalette", () => {
  it("lists screens and actions, finds an entity to add, and runs the chosen row", async () => {
    state.palette = true;
    const palette = mount(CommandPalette);
    await palette.vm.$nextTick();
    const labels = () => palette.findAll(".palette-item .tx > span").map((s) => s.text());
    expect(labels()).toContain("Living room");
    expect(labels()).toContain("Save & send");
    expect(labels()).toContain("Identify this screen");
    await palette.find("#palette-input").setValue("curt");
    expect(labels()).toEqual(["Curtains"]);
    await palette.find("#palette-input").trigger("keydown", { key: "Enter" });
    expect(state.layout!.tiles.map((t) => t.entity)).toEqual(["cover.c"]);
    expect(state.palette).toBe(false);
  });
});

describe("full-page and navigation tiles on the mockup", () => {
  it("draws a full tile as one big card and a navigation tile with its page", () => {
    state.liveStates["light.a"] = { state: "on", word: "On", a: {} };
    const full = placed({ entity: "light.a", name: "", slot: 0, options: { size: "full" } });
    expect(full.classes()).toContain("full");
    expect(full.classes()).not.toContain("wide");
    expect(full.find(".ic").classes()).toContain("lit");
    expect(full.find(".tog").exists()).toBe(false);
    const nav = placed({ entity: "screen.page_3", name: "Go to page 3", slot: 6 });
    expect(nav.find(".goto").text()).toBe("Page 3 ›");
  });
});

describe("several tiles of one entity in the library (firmware 0.2.65 for a page tile, 0.16.0 for any)", () => {
  it("keeps offering a placed navigation tile when the screen takes several, and adds another copy", async () => {
    Object.assign(state.inventory.screens[0], { firmware: "0.2.65", page_tiles_repeat: true, entity_tiles_repeat: false });
    appendTiles({ entity: "screen.page_1", name: "", slot: 0 }, { entity: "light.a", name: "", slot: 1 });
    const library = mount(Library);
    const row = () => library.find('.ent[title^="screen.page_1 "]');
    expect(row().attributes("disabled")).toBeUndefined();
    expect(row().attributes("title")).toContain("add it again");
    expect(row().find(".add").text()).toBe("✓");
    expect(library.find('.ent[title="light.a"]').attributes("disabled")).toBeDefined();
    await row().trigger("click");
    expect(state.layout!.tiles.filter((t) => t.entity === "screen.page_1")).toHaveLength(2);
    expect(row().find(".add").text()).toBe("×2");
    // Hide placed hides what is on the screen, a copy it could take again too.
    await library.find("#hide-placed").trigger("click");
    expect(row().exists()).toBe(false);
  });
  it("offers any placed entity again from firmware 0.16.0 and says how often it is there, but one bedside clock", async () => {
    Object.assign(state.inventory.screens[0], { firmware: "0.16.0", page_tiles_repeat: true, entity_tiles_repeat: true });
    appendTiles({ entity: "light.a", name: "", slot: 0 });
    const library = mount(Library);
    const row = () => library.find('.ent[title^="light.a "]');
    expect(row().attributes("disabled")).toBeUndefined();
    expect(row().find(".add").text()).toBe("✓");
    await row().trigger("click");
    expect(state.layout!.tiles.filter((t) => t.entity === "light.a")).toHaveLength(2);
    expect(row().find(".add").text()).toBe("×2");
    expect(repeatable("screen.nightstand")).toBe(false);
    expect(repeatable("light.b")).toBe(true);
  });
  it("marks it placed when the screen takes one per page", () => {
    Object.assign(state.inventory.screens[0], { page_tiles_repeat: false });
    appendTiles({ entity: "screen.page_1", name: "", slot: 0 });
    const library = mount(Library);
    expect(library.find('.ent[title="screen.page_1"]').attributes("disabled")).toBeDefined();
    expect(library.find('.ent[title="screen.page_1"] .add').text()).toBe("✓");
  });
});

describe("TileInspector: a live picture on a camera tile (app 0.2.91)", () => {
  const row = (wrapper: ReturnType<typeof mount>, label: string) =>
    wrapper.findAll(".prop").find((f) => f.find(".prop-label").text().replace(/^[^\p{L}\d]+/u, "").trim() === label)!;
  const choices = (wrapper: ReturnType<typeof mount>, label: string) => row(wrapper, label).findAll(".seg button").map((b) => b.text());
  it("offers the live picture for a camera, with its pace once chosen, and says which firmware it needs", async () => {
    state.inventory.entities.push({ id: "camera.front", name: "Front", state: "idle", area: "Hall" } as any);
    const tile: Tile = { entity: "camera.front", name: "", slot: 0 };
    appendTiles(tile);
    const drawer = inspector(tile);
    // The add-on's own choices: a camera has no large value to show, and saving one was refused (GitHub #4).
    expect(choices(drawer, "Display")).toEqual(["Name and status", "Live picture"]);
    expect(row(drawer, "Refresh")).toBeUndefined();
    await row(drawer, "Display").findAll(".seg button")[1].trigger("click");
    expect(current(tile).options).toEqual({ display: "live" });
    expect(choices(drawer, "Refresh")).toEqual(["Every 5 s", "Every 10 s", "Every 15 s", "Every 30 s"]);
    expect(row(drawer, "Refresh").find('[aria-pressed="true"]').text()).toBe("Every 15 s");
    expect(hint(row(drawer, "Display")).text).toMatch(/firmware 0\.2\.77/);
    expect(hint(row(drawer, "Display")).warn).toBe(true);
    await row(drawer, "Refresh").findAll(".seg button")[3].trigger("click");
    expect(current(tile).options).toEqual({ display: "live", refresh: 30 });
    await row(drawer, "Refresh").findAll(".seg button")[1].trigger("click");
    expect(current(tile).options).toEqual({ display: "live", refresh: 10 });
    // Firmware that draws the small square in the icon's place is told what fills the tile (app 0.3.13).
    Object.assign(state.inventory.screens[0], { firmware: "0.2.77" });
    await drawer.vm.$nextTick();
    expect(hint(row(drawer, "Display")).text).toMatch(/firmware 0\.3\.7/);
    expect(hint(row(drawer, "Display")).warn).toBe(true);
    Object.assign(state.inventory.screens[0], { firmware: "0.3.7" });
    await drawer.vm.$nextTick();
    expect(hint(row(drawer, "Display")).text).toMatch(/fills the tile/);
    expect(hint(row(drawer, "Display")).warn).toBe(false);
    // A light has no such choice.
    const lamp = mount(TileInspector, { props: { tile: { entity: "light.a", name: "", slot: 1 } } });
    expect(choices(lamp, "Display")).not.toContain("Live picture");
    // The mockup draws the add-on's picture over the whole card, one cell high too.
    const card = mount(TileCard, { props: { tile: current(tile), slot: 0 } });
    expect(card.find("img.camera-art").attributes("src")).toBe("api/camera-preview?entity=camera.front");
  });
  it("lets a live camera fill its tile, whole or cut, with its name or without, and keeps no defaults (app 0.3.8, every size 0.3.13)", async () => {
    Object.assign(state.inventory, { editor_features: { tall_tiles: true } });
    Object.assign(state.inventory.screens[0], { firmware: "0.3.1", tile_sizes: ["single", "wide", "tall", "square", "full"] });
    state.inventory.entities.push({ id: "camera.garden", name: "Garden", state: "idle", area: "Garden" } as any);
    const tile: Tile = { entity: "camera.garden", name: "", slot: 0, options: { display: "live" } };
    appendTiles(tile);
    const drawer = inspector(tile);
    // One cell high it fills the card as well, from firmware 0.3.7.
    expect(choices(drawer, "Picture")).toEqual(["Fill the tile", "Whole picture"]);
    expect(hint(row(drawer, "Display")).text).toMatch(/firmware 0\.3\.7/);
    setTileOption(current(tile), "size", "tall");
    await drawer.vm.$nextTick();
    expect(choices(drawer, "Picture")).toEqual(["Fill the tile", "Whole picture"]);
    expect(choices(drawer, "On the picture")).toEqual(["Name", "Nothing"]);
    expect(hint(row(drawer, "Display")).text).toMatch(/firmware 0\.3\.7/);
    expect(hint(row(drawer, "Display")).warn).toBe(true);
    await row(drawer, "Picture").findAll(".seg button")[1].trigger("click");
    await row(drawer, "On the picture").findAll(".seg button")[1].trigger("click");
    expect(current(tile).options).toMatchObject({ display: "live", size: "tall", fit: "contain", overlay: "none" });
    // Back to the defaults stores nothing, and another display takes the picture's own settings with it.
    await row(drawer, "Picture").findAll(".seg button")[0].trigger("click");
    expect(current(tile).options).not.toHaveProperty("fit");
    setTileOption(current(tile), "display", "standard");
    expect(current(tile).options).not.toHaveProperty("overlay");
    expect(current(tile).options).not.toHaveProperty("refresh");
    Object.assign(state.inventory.screens[0], { firmware: "0.3.3" });
    setTileOption(current(tile), "display", "live");
    await drawer.vm.$nextTick();
    // Firmware 0.3.3 fills a 1x2 or 2x2 tile, but a single one only from 0.3.7.
    expect(hint(row(drawer, "Display")).warn).toBe(false);
    setTileOption(current(tile), "size", "single");
    await drawer.vm.$nextTick();
    expect(hint(row(drawer, "Display")).warn).toBe(true);
    setTileOption(current(tile), "size", "tall");
    // The mockup draws the add-on's picture over the whole card, cut as the tile asks.
    setTileOption(current(tile), "fit", "contain");
    const card = mount(TileCard, { props: { tile: current(tile), slot: 0 } });
    const picture = card.find("img.camera-art");
    expect(picture.attributes("src")).toBe("api/camera-preview?entity=camera.garden");
    expect(picture.classes()).toContain("contain");
    await picture.trigger("load");
    expect(card.find(".camera-name").text()).toBe("Garden");
  });
  it("offers the album cover for a media player on a Guition, not on a full-page tile, and keeps its controls", async () => {
    Object.assign(state.inventory.screens[0], { firmware: "0.2.78", pictures: true });  // as the add-on says of a Guition
    state.inventory.entities.push({ id: "media_player.sonos", name: "Sonos", state: "playing", area: "Hall" } as any);
    (state.inventory as any).controls.media_player = { default: "volume", choices: [{ key: "volume", label: "Volume" }, { key: "none", label: "None" }] };
    const tile: Tile = { entity: "media_player.sonos", name: "", slot: 0, options: { size: "wide" } };
    appendTiles(tile);
    const drawer = inspector(tile);
    expect(choices(drawer, "Display")).toEqual(["Name and status", "Large value", "Album cover", "Favourite"]);
    await row(drawer, "Display").findAll(".seg button")[2].trigger("click");
    expect(current(tile).options).toEqual({ size: "wide", display: "cover" });
    expect(hint(row(drawer, "Display")).text).toMatch(/icon's place/);
    expect(row(drawer, "Refresh")).toBeUndefined();
    expect(row(drawer, "Direct control on the tile")).toBeDefined();
    const card = mount(TileCard, { props: { tile: current(tile), slot: 0 } });
    expect(card.find(".ic").classes()).toContain("thumb");
    expect(card.find(".range").exists()).toBe(true);
    // A board without memory for pictures (a CYD) gets no such choice; a tile over the whole page keeps the card's big cover.
    Object.assign(state.inventory.screens[0], { board: "cyd", pictures: false });
    seedTiles([{ ...current(tile), options: { size: "single" } }]);
    await drawer.vm.$nextTick();
    // A favourite plays there all the same, as an ordinary tile.
    expect(choices(inspector(tile), "Display")).toEqual(["Name and status", "Large value", "Favourite"]);
    Object.assign(state.inventory.screens[0], { board: "guition", pictures: true });
    seedTiles([{ ...current(tile), options: { size: "full" } }]);
    expect(choices(inspector(tile), "Display")).toEqual(["Name and status", "Large value"]);
  });
});

describe("TileInspector: pages (app 0.2.78)", () => {
  const row = (wrapper: ReturnType<typeof mount>, label: string) =>
    wrapper.findAll(".prop").find((f) => f.find(".prop-label").text().replace(/^[^\p{L}\d]+/u, "").trim() === label)!;
  const choices = (wrapper: ReturnType<typeof mount>, label: string) => row(wrapper, label).findAll(".seg button").map((b) => b.text());
  function open(tiles: any[], index: number) {
    appendTiles(...tiles);
    seedPages(1);
    const tile = state.layout!.tiles[index];
    return { tile, drawer: inspector(tile) };
  }
  it("offers existing page destinations and creates the next empty page as one edit", async () => {
    Object.assign(state.inventory.screens[0], { firmware: "0.2.63", full_page: true });
    const { tile, drawer } = open([
      { entity: "light.a", name: "", slot: 0 }, { entity: "screen.page_2", name: "", slot: 1 }, { entity: "sensor.t", name: "", slot: 6 },
    ], 1);
    expect(choices(drawer, "Goes to page")).toEqual(["1", "2", "3 (empty)"]);
    expect(row(drawer, "Goes to page").find('[aria-pressed="true"]').text()).toBe("2");
    await row(drawer, "Goes to page").findAll(".seg button")[2].trigger("click");
    expect(current(tile).entity).toBe("screen.page_3");
    expect(state.layout!.pages).toBe(3);
    expect(choices(drawer, "Goes to page")).toEqual(["1", "2", "3 (empty)", "4 (empty)"]);
    expect(row(drawer, "Goes to page").find(".warn").exists()).toBe(false);
  });

});

describe("Sidebar", () => {
  it("marks the open screen with unsaved edits and keeps them when it is chosen again", async () => {
    state.dirty = true;
    const layout = state.layout;
    state.tab = "settings";
    const sidebar = mount(Sidebar);
    const item = sidebar.find("#screens .nav-item");
    expect(item.find(".unsaved").exists()).toBe(true);
    await item.trigger("click");
    expect(state.layout).toBe(layout);
    expect(state.dirty).toBe(true);
    expect(state.tab).toBe("layout");
  });
  it("shows a screen's name alone on one line, and its details behind the chevron (app 0.4.32)", async () => {
    state.selected = null;
    const sidebar = mount(Sidebar);
    const item = sidebar.find("#screens .screen-item");
    expect(item.find(".led").exists()).toBe(false);
    expect(item.find(".sub").exists()).toBe(false);
    expect(item.find(".screen-details").exists()).toBe(false);
    // Chosen, a healthy screen keeps its details folded: the chevron at its right opens them.
    await item.find(".nav-item").trigger("click");
    expect(item.classes()).not.toContain("open");
    expect(item.find(".details-toggle").attributes("aria-expanded")).toBe("false");
    await item.find(".details-toggle").trigger("click");
    expect(item.classes()).toContain("open");
    expect(item.findAll(".facts dt").map((dt) => dt.text())).toEqual(["Firmware", "Board"]);
    expect(item.findAll(".facts dd").map((dd) => dd.text())).toEqual(["0.2.60", "Guition · 4 inch"]);
    await item.find(".details-toggle").trigger("click");
    expect(item.classes()).not.toContain("open");
    // A screen that is off says so on its row, and keeps its details folded: there is nothing more to say there.
    Object.assign(state.inventory.screens[0], { online: false });
    state.selected = null;
    await nextTick();
    expect(item.classes()).toContain("down");
    expect(item.find(".sub").text()).toBe("Offline");
    await item.find(".nav-item").trigger("click");
    expect(item.classes()).not.toContain("open");
  });
  it("downloads a screen's files, to build it with ESPHome on your own computer", async () => {
    Object.assign(state.inventory.screens[0], { update: { profile: "living room.yaml" } });
    state.inventory.pending = [{ file: "hall.yaml", friendly: "Hall", api_key: "key" } as any];
    const sidebar = mount(Sidebar);
    const item = sidebar.find("#screens .screen-item");
    await item.find(".nav-item").trigger("click");
    if (!item.classes().includes("open")) await item.find(".details-toggle").trigger("click");
    const own = item.find("a.screen-files");
    expect(own.attributes("href")).toBe("api/firmware/profiles/living%20room.yaml/files");
    expect(own.attributes("download")).toBeDefined();
    // A screen that isn't in Home Assistant yet has it in sight, not behind its API key.
    const pending = sidebar.find("#pending a.screen-files");
    expect(pending.attributes("href")).toBe("api/firmware/profiles/hall.yaml/files");
    expect(pending.element.closest("details")).toBeNull();
    // Without a profile the add-on has no files to give.
    Object.assign(state.inventory.screens[0], { update: { profile: null } });
    await nextTick();
    expect(item.find("a.screen-files").exists()).toBe(false);
    state.inventory.pending = [];
  });
  it("puts the update's one button on the row, and keeps the details folded (app 0.4.32)", async () => {
    Object.assign(state.inventory.screens[0], { update: { available: true, target: "0.4.0", profile: "living.yaml" } });
    const sidebar = mount(Sidebar);
    const item = sidebar.find("#screens .screen-item");
    expect(item.classes()).not.toContain("open");
    expect(item.find(".update-pill").attributes("aria-label")).toBe("Update: Living room");
    expect(item.find(".update-pill").attributes("title")).toContain("0.4.0");
    // Without a profile nothing here can build it: the row says Update, the details say why.
    Object.assign(state.inventory.screens[0], { update: { available: true, target: "0.4.0", profile: null } });
    await nextTick();
    expect(item.find(".update-pill").exists()).toBe(false);
    expect(item.find(".sub").text()).toBe("Update");
  });
  it("goes home from the logo: the overview, nothing chosen (app 0.4.0)", async () => {
    const sidebar = mount(Sidebar);
    await sidebar.find(".brand").trigger("click");
    expect(state.selected).toBeNull();
    expect(state.layout).toBeNull();
  });
  it("removes a screen that never got its firmware, after asking (GitHub #114)", async () => {
    state.inventory.pending = [{ file: "hall.yaml", friendly: "Hall", node: "hall" } as any];
    const calls: [string, RequestInit][] = [];
    vi.stubGlobal("fetch", vi.fn((path: string, options: RequestInit) => {
      calls.push([path, options]);
      return Promise.resolve(new Response(JSON.stringify({ removed: ["hall.yaml"] }), { status: 200 }));
    }));
    const sidebar = mount(Sidebar);
    await sidebar.find("#pending .remove-pending").trigger("click");
    expect(sidebar.find("#pending .screen-remove").text()).toContain("hall.yaml");
    expect(calls).toEqual([]);
    await sidebar.find("#pending .forget-pending").trigger("click");
    await flushPromises();
    expect(calls.some(([path, options]) => path.endsWith("api/firmware/profiles/hall.yaml") && options.method === "DELETE")).toBe(true);
    expect(state.inventory.pending).toEqual([]);
    expect(sidebar.find("#pending .pending").exists()).toBe(false);
  });
  it("asks what goes before it removes a screen, and then removes it (app 0.2.112)", async () => {
    Object.assign(state.inventory.screens[0], { online: false, update: { profile: "living.yaml" } });
    const calls: [string, RequestInit][] = [];
    vi.stubGlobal("fetch", vi.fn((path: string, options: RequestInit) => {
      calls.push([path, options]);
      return Promise.resolve(new Response(JSON.stringify({ removed: true, name: "Living room", kept: [] }), { status: 200 }));
    }));
    const sidebar = mount(Sidebar);
    const item = sidebar.find("#screens .screen-item");
    await item.find(".nav-item").trigger("click");
    await item.find(".details-toggle").trigger("click");
    await item.find(".remove-screen").trigger("click");
    // What goes, before anything is asked of Home Assistant: the device, the profile and what is kept here.
    const said = item.find(".screen-remove").text();
    expect(said).toContain("Remove Living room?");
    expect(said).toContain("living.yaml");
    expect(calls).toEqual([]);
    await item.find(".btn.danger").trigger("click");
    await flushPromises();
    expect(calls.map(([path, options]) => [path, options.method])).toEqual([
      ["api/screens/living", "DELETE"], ["api/inventory?light=1", undefined]]);
    expect(state.selected).toBeNull();
    expect(state.layout).toBeNull();
    expect(state.toast?.message).toBe("Living room is removed.");
  });
  it("warns that a screen that is still connected comes back (app 0.2.112)", async () => {
    const sidebar = mount(Sidebar);
    const item = sidebar.find("#screens .screen-item");
    await item.find(".nav-item").trigger("click");
    await item.find(".details-toggle").trigger("click");
    await item.find(".remove-screen").trigger("click");
    expect(item.find(".screen-remove small.warn").text()).toContain("still connected");
    // Nothing goes until it is confirmed: Cancel puts the details back.
    await item.findAll(".screen-remove .btn")[1].trigger("click");
    expect(item.find(".screen-remove").exists()).toBe(false);
    expect(item.find(".facts").exists()).toBe(true);
  });
});

describe("HomeView: every screen with its home page (app 0.4.0)", () => {
  it("draws each screen's home page on its own grid, and opens a screen on a click", async () => {
    state.inventory.screens = [
      screenFixture({ ...state.inventory.screens[0], layout: { title: "Living room", tiles: [
        { entity: "light.a", name: "Reading", slot: 0 }, { entity: "sensor.t", name: "", slot: 7 }] } }),
      screenFixture({ id: "hall", name: "Hall", online: false, firmware: "0.3.9", board: "waveshare43",
        shape: { width: 800, height: 480, columns: 3, rows: 3 }, layout: { title: "Hall", tiles: [{ entity: "cover.c", name: "", slot: 4 }] } } as any),
    ];
    state.selected = null;
    seedLayout(null);
    const home = mount(HomeView);
    const cards = home.findAll(".home-card:not(.home-new)");
    expect(cards.map((card) => card.find(".home-name strong").text())).toEqual(["Living room", "Hall"]);
    // Only the tiles of the home page, on the screen's own grid: the sensor stands on page 2.
    expect(cards[0].findAll(".tile").map((tile) => tile.text())).toEqual([expect.stringContaining("Reading")]);
    expect(cards[1].find(".tile").attributes("style")).toContain("grid-column: 2 / span 1");
    expect(cards[1].find(".home-page").attributes("style")).toContain("--screen-columns: 3");
    // A tile of the overview is only drawn: not a button, not focusable.
    expect(cards[0].find(".tile").attributes("tabindex")).toBe("-1");
    expect(cards[1].classes()).toContain("away");
    expect(cards[1].find(".home-name small").text()).toBe("Offline");
    expect(home.find(".home-head p").text()).toBe("1 of 2 online");
    await cards[1].trigger("click");
    expect(state.selected).toBe("hall");
    // The next test starts on the fixture's own grid again.
    state.documentGrid = null;
  });
});

describe("Screen settings: Calibrate touch (app 0.2.117)", () => {
  const view = (extra: Record<string, unknown> = {}) => {
    Object.assign(state.inventory.screens[0], {
      settings: { owner: "screen", keys: [], values: {}, unavailable: [], rotations: [0, 180], switches: [], ...extra },
    });
    return mount(SettingsTab);
  };
  it("stays away from a screen whose panel has nothing to calibrate", () => {
    expect(view({ calibrate: false }).find("#settings-this-screen").exists()).toBe(false);
  });
  it("asks first, and then starts the wizard on the screen", async () => {
    const calls: [string, RequestInit][] = [];
    vi.stubGlobal("fetch", vi.fn((path: string, options: RequestInit) => {
      calls.push([path, options]);
      return Promise.resolve(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    }));
    const panel = view({ calibrate: true });
    expect(panel.find("#settings-this-screen").text()).toContain("five crosses");
    // Cancel sends nothing.
    vi.stubGlobal("confirm", vi.fn(() => false));
    await panel.find("#setting-calibrate").trigger("click");
    await flushPromises();
    expect(calls).toEqual([]);
    vi.stubGlobal("confirm", vi.fn(() => true));
    await panel.find("#setting-calibrate").trigger("click");
    await flushPromises();
    expect(calls.map(([path, options]) => [path, options.method])).toEqual([["api/screens/living/calibrate", "POST"]]);
    expect(state.toast?.message).toBe("Living room is showing the crosses.");
  });
  it("waits for a screen that is off: the crosses need glass that is on", () => {
    state.inventory.screens[0].online = false;
    expect(view({ calibrate: true }).find<HTMLButtonElement>("#setting-calibrate").element.disabled).toBe(true);
  });
});

describe("AppSettingsView", () => {
  it("shows what the current firmware brings from the changelog of the full inventory (app 0.2.78)", () => {
    state.inventory.updates = { target: "0.2.65", pending: 0 };
    state.inventory.changelog = [
      { app: "0.2.78", firmware: "0.2.65", lines: ["Several tiles go to the same page."] },
      { app: "0.2.76", firmware: "0.2.63", lines: ["Older."] },
    ];
    const view = mount(AppSettingsView);
    expect(view.find(".whatsnew summary").text()).toBe("What's new in firmware 0.2.65");
    expect(view.findAll(".whatsnew li").map((li) => li.text())).toEqual(["Several tiles go to the same page."]);
    delete state.inventory.changelog;
    expect(mount(AppSettingsView).find(".whatsnew").exists()).toBe(false);
  });
  it("names one firmware only when the screens share it (app 0.3.20, a firmware per board)", () => {
    const [living] = state.inventory.screens;
    const kitchen = { ...living, id: "kitchen", name: "Kitchen", board: "waveshare4b" } as any;
    const hint = () => mount(AppSettingsView).find("#updates-hint").text();
    state.inventory.updates = { target: "0.4.0", pending: 1 };
    state.inventory.screens = [{ ...living, update: { available: true, target: "0.4.0" } }, { ...kitchen, update: { available: false, target: "0.4.1" } }];
    expect(hint()).toBe("Firmware 0.4.0 is available for 1 screen.");
    state.inventory.screens[1].update = { available: true, target: "0.4.1" };
    expect(hint()).toBe("An update is available for 2 screens.");
    state.inventory.screens.forEach((s) => (s.update!.available = false));
    expect(hint()).toBe("All screens are up to date.");
    state.inventory.screens[1].update!.target = "0.4.0";
    expect(hint()).toBe("All screens have firmware 0.4.0.");
    // A running update names the firmware of the screen it is updating.
    state.inventory.updates = { target: "0.4.0", pending: 1, busy: "kitchen" };
    state.inventory.screens[1].update = { available: true, target: "0.4.1", state: "running" };
    expect(hint()).toBe("Updating to firmware 0.4.1…");
  });
});

describe("the title above a page (app 0.2.105, in the page's settings since 0.3.19)", () => {
  // A title belongs to its page: you set it in that page's settings, and the top bar's panel only says where.
  const settings = (page: number) => mount(PageInspector, { props: { id: state.document!.pages[page].id } });
  it("asks each page for its own title", async () => {
    seedLayout({ title: "Living room", tiles: [], pages: 3 });
    const drawer = settings(1);
    const field = drawer.find("#owned-page-title");
    expect(drawer.find("label[for='owned-page-title']").text()).toBe("Page title");
    // Empty says the screen's title, so a page that follows page 1 looks like it does.
    expect((field.element as HTMLInputElement).value).toBe("");
    expect(field.attributes("placeholder")).toBe("Living room");
    expect(drawer.find(".f-label .help-trigger").attributes("aria-label")).toBe("Leave empty to use the screen title.");
    await field.setValue("Music");
    expect(state.layout!.page_titles).toEqual(["", "Music"]);
    // Clearing it hands the page back and leaves nothing behind.
    await field.setValue("");
    expect(state.layout!.page_titles).toBeUndefined();
  });
  it("keeps the screen's own title one click under the page's", async () => {
    seedLayout({ title: "Living room", tiles: [], pages: 2, page_titles: ["", "Music"] });
    const drawer = settings(0);
    expect(drawer.find("#screen-title").exists()).toBe(false);
    await drawer.find(".disclosure").trigger("click");
    const screen = drawer.find("#screen-title");
    expect(drawer.find("label[for='screen-title']").text()).toBe("Screen title");
    expect((screen.element as HTMLInputElement).value).toBe("Living room");
    expect(drawer.find("#screen-title-hint button").attributes("aria-label")).toBe("Every page without a title of its own says this.");
    await screen.setValue("Downstairs");
    expect(state.layout!.title).toBe("Downstairs");
    expect(state.layout!.page_titles).toEqual(["", "Music"]);
    // Page 1 carries one of its own like any other page (app 0.2.123), and falls back to the screen's.
    const own = drawer.find("#owned-page-title");
    expect(own.attributes("placeholder")).toBe("Downstairs");
    await own.setValue("Hall");
    expect(state.layout!.page_titles).toEqual(["Hall", "Music"]);
    expect(state.layout!.title).toBe("Downstairs");
  });
  it("asks a screen with one page for one title only", () => {
    seedLayout({ title: "Living room", tiles: [] });
    const one = settings(0);
    expect(one.findAll("#screen-title")).toHaveLength(1);
    expect(one.find("label[for='screen-title']").text()).toBe("Title above the page");
    // One page and the screen's title are the same thing, so there is no second field to fill.
    expect(one.find("#owned-page-title").exists()).toBe(false);
    // A title that page kept from a longer row does get its field back: nothing is set that nobody can see.
    seedLayout({ title: "Living room", tiles: [], page_titles: ["Hall"] });
    expect(settings(0).find("#owned-page-title").exists()).toBe(true);
  });
  it("leaves the title out of the top bar's panel and leads to the page instead", async () => {
    seedLayout({ title: "Living room", tiles: [], pages: 2, page_titles: ["", "Music"] });
    openBar(0, 1);
    const drawer = mount(TopbarInspector, { props: { index: 0 } });
    expect(drawer.find("#screen-title").exists()).toBe(false);
    expect(drawer.find("#page-title").exists()).toBe(false);
    expect(drawer.find(".nav-row").text()).toContain("Music");
    await drawer.find(".nav-row").trigger("click");
    expect(state.inspector).toEqual({ kind: "page", id: state.document!.pages[1].id });
  });
  it("shows the page's own title in that page's mockup bar, and opens that page's field", async () => {
    seedLayout({ title: "Living room", tiles: [], pages: 2, page_titles: ["", "Music"] });
    const props = { entries: [], pages: 2, moving: null };
    const second = mount(DevicePage, { props: { page: 1, ...props } });
    expect(second.find(".bar-wrap").text()).toContain("Music");
    expect(mount(DevicePage, { props: { page: 0, ...props } }).find(".bar-wrap").text()).toContain("Living room");
    await second.find(".bar-wrap").trigger("click");
    expect(state.barPage).toBe(1);
  });
});

// New screen: which way the screen will hang (app 0.2.107). The choice is a build choice, so it is made here and
// nowhere else; the numbers beside each way come from the board files through the add-on, never from this page.
// A screen may not take a name another screen already carries (app 0.2.123): Home Assistant cannot tell two
// devices of one name apart, so New screen says it while the name is typed and the add-on refuses it as well.
// A screen that does not reach its Wi-Fi (app 0.4.32): another network before the build, and after the build the page
// follows Home Assistant finding it on the network, or after three minutes says what fixes it.
describe("New screen and the Wi-Fi", () => {
  const flush = async () => { for (let i = 0; i < 4; i++) await Promise.resolve(); await new Promise((done) => setTimeout(done, 0)); };
  function addon(job: any) {
    const calls: { url: string; method: string; body?: any }[] = [];
    const inventory = { screens: [] as any[], pending: [{ file: "hall.yaml", friendly: "Hall", node: "hall", installed: true, seen: false }] };
    vi.stubGlobal("fetch", vi.fn((url: string, options: any = {}) => {
      const method = options.method || "GET";
      calls.push({ url: String(url), method, body: options.body ? JSON.parse(options.body) : undefined });
      if (String(url).endsWith("api/firmware")) return Promise.resolve({ ok: true, json: () => Promise.resolve({ available: true, ports: ["/dev/ttyUSB0"], profiles: [], logs: [], wifi: { state: "ready", missing: [] }, boards: BOARD_CHOICES, taken: { nodes: [], prefixes: [] }, job: calls.some((c) => c.url.endsWith("firmware/profiles")) ? job : null }) });
      if (String(url).includes("inventory")) return Promise.resolve({ ok: true, json: () => Promise.resolve({ ...state.inventory, ...inventory }) });
      const answer = String(url).endsWith("firmware/profiles") ? { file: "hall.yaml", api_key: "k", job } : String(url).endsWith("firmware/jobs") ? job : { state: "ready" };
      return Promise.resolve({ ok: true, text: () => Promise.resolve(JSON.stringify(answer)), json: () => Promise.resolve(answer) });
    }));
    return { calls, inventory };
  }
  async function toDone(view: ReturnType<typeof mount>) {
    await view.find('input[value="guition"]').setValue();
    await view.find("#setup-next").trigger("click");
    await view.find("#friendly_name").setValue("Hall");
  }
  it("writes another network before it makes the profile", async () => {
    const { calls } = addon({ file: "hall.yaml", action: "install", state: "success", stage: "upload" });
    const view = mount(InstallerView);
    await flush();
    await toDone(view);
    await view.find("#wifi-other").trigger("click");
    await view.find("#wifi_ssid").setValue("Home");
    await view.find("#wifi_password").setValue("secret");
    await view.find("#install-form").trigger("submit");
    await flush();
    const writes = calls.filter((c) => c.method !== "GET");
    expect(writes.map((c) => [c.url, c.method])).toEqual([["api/firmware/wifi", "PUT"], ["api/firmware/profiles", "POST"]]);
    expect(writes[0].body).toEqual({ wifi_ssid: "Home", wifi_password: "secret" });
    expect(writes[1].body.wifi_password).toBeUndefined();
  });
  it("follows the screen onto the network, and after three minutes without it offers the fix", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const { calls, inventory } = addon({ file: "hall.yaml", action: "install", state: "success", stage: "upload" });
      const view = mount(InstallerView);
      await flush();
      await toDone(view);
      await view.find("#install-form").trigger("submit");
      await flush();
      expect(view.find("#arrive").classes()).toContain("waiting");
      // Home Assistant found it: the page says so.
      state.inventory.pending = [{ ...inventory.pending[0], seen: true }];
      await flush();
      expect(view.find("#arrive").classes()).toContain("seen");
      // Not found for three minutes: what fixes it, with the right network and the installation again.
      state.inventory.pending = [{ ...inventory.pending[0], seen: false }];
      await vi.advanceTimersByTimeAsync(181000);
      await flush();
      expect(view.find("#arrive").classes()).toContain("missing");
      // It says what Another network says: every screen builds with this Wi-Fi, so the others take it too.
      expect(view.find("#arrive").text()).toContain(t("editor.installer.wifi.other_note"));
      await view.find("#fix_ssid").setValue("Right");
      await view.find("#fix_password").setValue("pw");
      await view.find("#arrive-wifi").trigger("submit");
      await flush();
      const writes = calls.filter((c) => c.method !== "GET").map((c) => c.url);
      expect(writes.slice(-2)).toEqual(["api/firmware/wifi", "api/firmware/jobs"]);
      // Paired: nothing left to wait for.
      state.inventory.screens = [{ ...state.inventory.screens[0], node: "hall" } as any];
      await flush();
    } finally { vi.useRealTimers(); }
  });
});

describe("a name another screen already carries", () => {
  const flush = async () => { await Promise.resolve(); await Promise.resolve(); await new Promise((done) => setTimeout(done, 0)); };
  async function installer(taken: any) {
    vi.stubGlobal("fetch", vi.fn((url: string) => (String(url).endsWith("api/firmware")
      ? Promise.resolve({ ok: true, json: () => Promise.resolve({ available: true, ports: ["/dev/ttyUSB0"], profiles: [], logs: [], wifi: { state: "ready" }, boards: BOARD_CHOICES, taken }) })
      : Promise.resolve({ ok: true, text: () => Promise.resolve("{}") }))));
    const view = mount(InstallerView);
    await flush();
    return view;
  }
  it("says so under the name and holds the step until the name is the screen's own", async () => {
    const view = await installer({ nodes: ["hall"], prefixes: ["living_room"] });
    await view.find("#setup-next").trigger("click");
    await view.find("#friendly_name").setValue("Living room");
    expect(view.find("#name-taken").exists()).toBe(true);
    expect(view.find("#setup-next").attributes("disabled")).toBeDefined();
    await view.find("#friendly_name").setValue("Kitchen");
    expect(view.find("#name-taken").exists()).toBe(false);
    expect(view.find("#node-taken").exists()).toBe(false);
    expect(view.find("#setup-next").attributes("disabled")).toBeUndefined();
    // The device name follows the name, and can be the one that clashes.
    await view.find("#friendly_name").setValue("Hall");
    expect(view.find("#name-taken").exists()).toBe(false);
    expect(view.find("#node-taken").exists()).toBe(true);
    expect(view.find("#setup-next").attributes("disabled")).toBeDefined();
  });
});

describe("the orientation of a new screen", () => {
  const boards = BOARD_CHOICES;
  const answers: any[] = [];
  async function installer() {
    vi.stubGlobal("fetch", vi.fn((url: string, options: any) => {
      if (String(url).endsWith("api/firmware")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ available: true, ports: [], profiles: [], logs: [], wifi: { state: "ready" }, boards }) });
      }
      answers.push(JSON.parse(options.body));
      return Promise.resolve({ ok: true, text: () => Promise.resolve(JSON.stringify({ file: "hall.yaml", api_key: "k" })) });
    }));
    const view = mount(InstallerView);
    await flush();
    return view;
  }
  const flush = async () => { await Promise.resolve(); await Promise.resolve(); await new Promise((done) => setTimeout(done, 0)); };

  it("offers the two ways glass that is not square can hang, with the cells each way gives", async () => {
    const view = await installer();
    const options = view.findAll("#orientation-fields .orient");
    expect(options).toHaveLength(2);
    expect(options.map((option) => option.find("b").text())).toEqual(["Lying down", "Standing up"]);
    expect(options.map((option) => option.find("small").text())).toEqual(["6 tiles a page", "4 tiles a page"]);
    // A picture of the glass each way, with a cell per tile of that page.
    expect(options[0].findAll(".orient-cells i")).toHaveLength(6);
    expect(options[1].findAll(".orient-cells i")).toHaveLength(4);
    expect(options[1].find(".orient-glass").attributes("style")).toContain("240 / 320");
    // Lying down to begin with, and saying so plainly that this is chosen now and not later.
    expect((options[0].find("input").element as HTMLInputElement).checked).toBe(true);
    expect(view.find("#orientation-hint").text()).toContain("build the screen again");
  });

  it("asks nothing about square glass, and asks again about the next board", async () => {
    const view = await installer();
    await view.find('input[value="guition"]').setValue("guition");
    expect(view.find("#orientation-fields").exists()).toBe(false);
    await view.find('input[value="waveshare43"]').setValue("waveshare43");
    const options = view.findAll("#orientation-fields .orient");
    expect(options.map((option) => option.find("small").text())).toEqual(["9 tiles a page", "4 tiles a page"]);
  });

  it("lists every board of the catalog in its order, named and described from its data alone", async () => {
    const view = await installer();
    const rows = view.findAll(".board");
    // One card per screen: the models of one brand and size share it, in the catalog's order (app 0.4.32).
    const ordered = Object.entries(boards).sort(([, a]: any, [, b]: any) => a.order - b.order);
    const firsts = ordered.filter(([, board]: any, index) => ordered.findIndex(([, other]: any) => other.name === board.name && other.inch === board.inch) === index).map(([key]) => key);
    expect(rows.map((row) => row.find("input").attributes("value"))).toEqual(firsts);
    expect(rows[0].find("b").text()).toBe("CYD · 2.8 inch");
    expect(rows[0].findAll("small").map((line) => line.text())).toEqual(["320 × 240 · XPT2046", "2 models"]);
    expect(view.find('input[value="guition"]').element.closest("label")!.textContent).toContain("480 × 480 · GT911");
    expect(view.find('input[value="jc8012p4a1"]').element.closest("label")?.textContent).toContain("Guition · 10.1 inch");
    // Each board drawn in its own proportions with the tiles of one page lying down, and to scale by its size (app 0.4.32).
    const art = (key: string) => view.find(`input[value="${key}"]`).element.closest("label")!.querySelector(".board-art") as HTMLElement;
    expect(art("jc8012p4a1").querySelector("svg")!.getAttribute("viewBox")).toBe("-7 -7 174 114");
    expect(art("jc8012p4a1").querySelectorAll(".da-tile")).toHaveLength(25);
    expect(art("guition").querySelector("svg")!.getAttribute("viewBox")).toBe("-7 -7 114 114");
    expect(art("jc8012p4a1").getAttribute("style")).toContain("--inch: 10.1");
    // The first board is chosen to begin with, with what it can do; the CYD asks for a touch calibration first.
    expect((rows[0].find("input").element as HTMLInputElement).checked).toBe(true);
    expect(view.findAll("#board-abilities li").map((li) => li.text())).toEqual(
      ["No camera pictures", "Dimmable backlight", "Standby and night", "Touch calibration on first start"]);
    expect(view.find("#board-status").exists()).toBe(false);
  });

  it("finds a board by brand, size or what is printed on it, and narrows by size (app 0.4.32)", async () => {
    const view = await installer();
    const names = () => view.findAll(".board b").map((b) => b.text());
    await view.find("#board-search").setValue("guition 4");
    expect(names()).toContain("Guition · 4 inch");
    expect(names().every((name) => name.startsWith("Guition"))).toBe(true);
    await view.find("#board-search").setValue("2432S028");
    expect(names()).toEqual(expect.arrayContaining(["CYD · 2.8 inch"]));
    await view.find("#board-search").setValue("nothing like it");
    expect(view.find(".pick-none").text()).toContain("nothing like it");
    await view.find("#board-search").setValue("");
    await view.findAll(".pick-sizes button").find((b) => b.text().startsWith("7 inch"))!.trigger("click");
    expect(names().length).toBeGreaterThan(0);
    expect(view.findAll(".board").every((row) => Number(row.find(".board-art").attributes("style")!.match(/--inch: ([\d.]+)/)![1]) >= 6)).toBe(true);
  });

  it("asks which model a screen of several models is, in sight in the second step (app 0.4.32)", async () => {
    const view = await installer();
    await view.find('input[value="jc8012p4a1"]').setValue();
    await view.find("#setup-next").trigger("click");
    const models = view.findAll("#board-model .model");
    expect(models.map((row) => row.find("b").text())).toEqual(["JC8012P4A1", "JC8012P4A1 V3", "JC8012P4A1 V2"]);
    await models[1].find("input").setValue();
    await view.find("#friendly_name").setValue("Hall");
    await view.find("#install-form").trigger("submit");
    await flush();
    expect(answers.at(-1).board).toBe("jc8012p4a1v3");
    // A board with one model asks nothing.
    const other = await installer();
    await other.find('input[value="guition"]').setValue();
    await other.find("#setup-next").trigger("click");
    expect(other.find("#board-model").exists()).toBe(false);
  });

  it("walks the three steps: Next only with a board, and on only with a name (app 0.4.32)", async () => {
    const view = await installer();
    const shown = () => view.findAll(".setup-step").filter((step) => (step.element as HTMLElement).style.display !== "none").map((step) => step.classes()[1]);
    expect(shown()).toEqual(["pick"]);
    await view.find("#setup-next").trigger("click");
    expect(shown()).toEqual(["make"]);
    await view.find("#setup-next").trigger("click");
    // No name yet: the step stays.
    expect(shown()).toEqual(["make"]);
    await view.find("#friendly_name").setValue("Hall");
    await view.find("#setup-next").trigger("click");
    expect(shown()).toEqual(["ways"]);
    expect(view.find("#install-go").exists()).toBe(true);
    await view.find("#setup-back").trigger("click");
    expect(shown()).toEqual(["make"]);
    // The name shows in the drawing of the screen as it is typed.
    expect(view.find(".make-art .da-name").text()).toBe("Hall");
  });

  it("explains an experimental board by what it can do and submits its selected orientation", async () => {
    const view = await installer();
    await view.find('input[value="waveshare7"]').setValue("waveshare7");
    expect(view.find('input[value="waveshare7"]').element.closest("label")?.textContent).toContain("Experimental");
    expect(view.find("#board-status").text()).toContain("not yet tried on this hardware");
    expect(view.findAll("#board-abilities li.off").map((li) => li.text())).toEqual(["Backlight always on", "No standby"]);
    const options = view.findAll("#orientation-fields .orient");
    expect(options.map((option) => option.find("small").text())).toEqual(["16 tiles a page", "14 tiles a page"]);
    await options[1].find("input").setValue("portrait");
    await view.find("#friendly_name").setValue("Hall");
    await view.find("#install-form").trigger("submit");
    await flush();
    expect(answers.pop()).toMatchObject({ board: "waveshare7", orientation: "portrait", name: "hall" });
  });

  it("asks nothing about the square glass of an experimental board", async () => {
    const view = await installer();
    await view.find('input[value="waveshare4b"]').setValue("waveshare4b");
    expect(view.find("#board-status").text()).toContain("Experimental");
    expect(view.findAll("#board-abilities li.off")).toHaveLength(0);
    expect(view.find("#orientation-fields").exists()).toBe(false);
    await view.find("#friendly_name").setValue("Hall");
    await view.find("#install-form").trigger("submit");
    await flush();
    expect(answers.pop()).toMatchObject({ board: "waveshare4b", name: "hall" });
  });

  it("offers a board's own choices, starting at the board file's value, and sends only one that differs", async () => {
    const view = await installer();
    const options = view.findAll("#choice-DISPLAY_MODEL .choice");
    expect(view.find("#choice-DISPLAY_MODEL legend").text()).toBe("Display controller");
    expect(options.map((option) => option.find("b").text())).toEqual(["ILI9341", "ST7789V"]);
    expect((options[0].find("input").element as HTMLInputElement).checked).toBe(true);
    await view.find("#friendly_name").setValue("Hall");
    await view.find("#install-form").trigger("submit");
    await flush();
    expect(answers.pop().choices).toBeUndefined();
    const other = await installer();
    await other.findAll("#choice-DISPLAY_MODEL .choice input")[1].setValue("ST7789V");
    await other.find("#friendly_name").setValue("Hall");
    await other.find("#install-form").trigger("submit");
    await flush();
    expect(answers.pop()).toMatchObject({ board: "cyd", choices: { DISPLAY_MODEL: "ST7789V" } });
    // Another board has other choices, or none.
    const third = await installer();
    await third.find('input[value="guition"]').setValue("guition");
    expect(third.find("#choice-DISPLAY_MODEL").exists()).toBe(false);
    // The Guition's rows (app 0.4.31): said in words, the usual size first, and four rows sent only when chosen.
    const rows = third.findAll("#choice-GRID_ROWS .choice");
    expect(third.find("#choice-GRID_ROWS legend").text()).toBe("Tiles on a page");
    expect(rows.map((option) => option.find("b").text())).toEqual(["3 rows", "4 rows, smaller tiles"]);
    expect(rows[0].find("small").text()).toBe("the usual size");
    await rows[1].find("input").setValue("4");
    await third.find("#friendly_name").setValue("Hall");
    await third.find("#install-form").trigger("submit");
    await flush();
    expect(answers.pop()).toMatchObject({ board: "guition", choices: { GRID_ROWS: "4" } });
  });

  it("sends the chosen way with the new screen", async () => {
    const view = await installer();
    await view.findAll("#orientation-fields .orient input")[1].setValue("portrait");
    await view.find("#friendly_name").setValue("Hall");
    await view.find("#install-form").trigger("submit");
    await flush();
    expect(answers.pop()).toMatchObject({ board: "cyd", orientation: "portrait", name: "hall" });
  });
});

// A whole page to another place in the row (app 0.2.121, GitHub #24): the label is its handle.
describe("a page that moves as a whole", () => {
  const props = (page: number, pages: number) => ({ page, pages, entries: state.layout!.tiles.map((t) => ({ tile: t, slot: t.slot })), moving: null });
  beforeEach(() => {
    seedLayout({ title: "Living room", pages: 3, tiles: [{ entity: "light.a", name: "", slot: 6 }] });
    state.drag = { active: false, moving: null, preview: null, page: null };
  });
  it("gives every page a handle, but not a screen with one page", () => {
    const second = mount(DevicePage, { props: props(1, 3) });
    const grab = second.find(".grab");
    expect(grab.exists()).toBe(true);
    // The grip of the top bar's rows, so anything you drag by hand looks the same.
    expect(grab.text()).toContain("Page 2");
    expect(grab.find(".grip").attributes("aria-hidden")).toBe("true");
    expect(grab.attributes("aria-label")).toBe("Move page 2");
    expect(grab.attributes("title")).toBe("Drag this page to another place in the row, or use ← and →");
    seedPages(1);
    expect(mount(DevicePage, { props: props(0, 1) }).find(".grab").exists()).toBe(false);
    // The page a tile can start behind the last one is not a page yet.
    expect(mount(DevicePage, { props: props(3, 3) }).find(".grab").exists()).toBe(false);
  });
  it("moves a page with the arrow keys and keeps the handle under the finger", async () => {
    const row = mount(DevicePage, { props: props(1, 3) });
    await row.find(".grab").trigger("keydown", { key: "ArrowLeft" });
    // Page 2 and page 1 changed places: the tile that stood on page 2 now stands on page 1.
    expect(state.layout!.tiles[0].slot).toBe(0);
    expect(state.dirty).toBe(true);
    await mount(DevicePage, { props: props(0, 3) }).find(".grab").trigger("keydown", { key: "ArrowRight" });
    expect(state.layout!.tiles[0].slot).toBe(6);
    // Another key is not a move.
    await row.find(".grab").trigger("keydown", { key: "Enter" });
    expect(state.layout!.tiles[0].slot).toBe(6);
  });
  it("gives every page one menu, and Remove page takes the page with its tiles", async () => {
    // A page leaves whether it is empty or not (app 0.2.123); since 0.3.19 the way out is in the page's ··· menu.
    // jsdom cannot place Reka's popover, so opening it is checked in the browser; here the menu's key and its action.
    const second = mount(DevicePage, { props: props(1, 3) });
    expect(second.find(".page-menu").attributes("aria-label")).toBe("Page 2: more");
    expect(second.find(".page-side").text()).toContain("1/6");
    // The page a tile can start behind the last one is not a page yet, so it has no menu.
    expect(mount(DevicePage, { props: props(3, 3) }).find(".page-menu").exists()).toBe(false);
    removePage(1);
    expect(state.layout!.tiles).toEqual([]);
    expect(state.toast?.message).toBe("Page 2 and one tile are gone.");
  });
  it("draws the page on the move where it would land, with the title that belongs there", () => {
    seedTitles(["", "Music", "Hall"]);
    // Page 3 is being carried to the middle: the row shows Hall there and Music after it.
    state.drag = { active: true, moving: null, preview: [], page: { from: 2, to: 1, order: [0, 2, 1] } };
    const middle = mount(DevicePage, { props: props(1, 3) });
    expect(middle.find(".page").classes()).toContain("carried");
    expect(middle.find(".bar-wrap").text()).toContain("Hall");
    const last = mount(DevicePage, { props: props(2, 3) });
    expect(last.find(".page").classes()).not.toContain("carried");
    expect(last.find(".bar-wrap").text()).toContain("Music");
    // Page 1 says the screen's own title, whatever lands there.
    expect(mount(DevicePage, { props: props(0, 3) }).find(".bar-wrap").text()).toContain("Living room");
  });
});

// The home key in the top bar (app 0.2.122, firmware 0.2.100+), the Tessera mark since firmware 0.10.0: the mockup
// draws what the screen draws.
describe("the home key on the mockup", () => {
  const mark = 'fill="#FFC107"';
  const props = (page: number) => ({ page, pages: 3, entries: [], moving: null });
  const bar = (page: number) => mount(DevicePage, { props: props(page) }).find(".bar-wrap").html();
  beforeEach(() => {
    seedLayout({ title: "Living room", pages: 3, tiles: [] });
    (state.inventory.screens[0] as any).firmware = "0.2.100";
    (state.inventory.screens[0] as any).firmware_known = "0.2.100";
    (state.inventory.screens[0] as any).settings = { owner: "screen", keys: ["home_button"], values: { home_button: true }, unavailable: [] };
  });
  it("draws it on every page, as the screens do", () => {
    expect(bar(0)).toContain(mark);
    expect(bar(1)).toContain(mark);
    expect(bar(2)).toContain(mark);
  });
  it("leaves it out when the screen's setting is off, and on firmware that has no key", () => {
    (state.inventory.screens[0] as any).settings.values.home_button = false;
    expect(bar(1)).not.toContain(mark);
    (state.inventory.screens[0] as any).settings.values.home_button = true;
    (state.inventory.screens[0] as any).firmware_known = "0.2.99";
    expect(bar(1)).not.toContain(mark);
  });
  it("gives the name the room the key takes, with the margin of the glass between them", () => {
    const withKey = mount(DevicePage, { props: props(1) }).findComponent({ name: "TopbarSvg" }).vm as any;
    (state.inventory.screens[0] as any).settings.values.home_button = false;
    const without = mount(DevicePage, { props: props(1) }).findComponent({ name: "TopbarSvg" }).vm as any;
    expect(without.lay.homeShift).toBe(0);
    // The key is the Tessera mark (firmware 0.10.0+), with the same air as between the edge of the glass and the key.
    expect(withKey.lay.key.mark).toBe(true);
    expect(withKey.lay.homeShift).toBe(withKey.lay.metrics.mark + withKey.lay.metrics.inset);
    expect(withKey.lay.nameRoom).toBe(without.lay.nameRoom - withKey.lay.homeShift);
  });
});

describe("Alerts: one screen through the event (app 0.2.133)", () => {
  function alertsInventory() {
    const inv = state.inventory as any;
    inv.screens = [
      { ...inv.screens[0], node: "living-screen", area: "Living room", pictures: true },
      { id: "desk", name: "Desk CYD", online: true, firmware: "0.2.60", board: "cyd", node: "desk", pictures: false,
        layout: { title: "Desk", tiles: [] }, alert_action: "esphome.desk_show_alert" },
    ];
    inv.alerts = {
      min_firmware: "0.2.31", broadcast: { show: "esp_screens_show_alert", dismiss: "esp_screens_dismiss_alert" },
      fields: [{ name: "title", type: "string", label: "Title", help: "", example: "Someone is at the door" }],
      camera: { name: "camera", label: "Camera", help: "", example: "camera.front_door" },
      screen: { name: "screen", label: "Screen", help: "Which screen gets the alert.", example: "kitchen-screen" },
      colors: [], suggested_icons: [], extra_icons: [], endings: [], limits: {}, limit_boards: {},
    };
  }
  it("lists what goes after screen: for every screen and copies it", async () => {
    alertsInventory();
    const { default: AlertsView } = await import("../src/components/AlertsView.vue");
    const page = mount(AlertsView);
    const rows = page.findAll("#alerts-one-table tr").slice(1);
    expect(rows.map((row) => row.findAll("td").map((td) => td.text().replace("Copy", "").trim()))).toEqual([
      ["living-screen", "Living room", "Living room", "Yes"],
      ["desk", "Desk CYD", "—", "No, the alert comes without it"],
    ]);
    const write = vi.fn(() => Promise.resolve());
    vi.stubGlobal("navigator", { clipboard: { writeText: write } });
    vi.stubGlobal("isSecureContext", true);
    await rows[1].find("button").trigger("click");
    expect(write).toHaveBeenCalledWith("desk");
    // Your screens shows the same value next to the actions.
    expect(page.findAll(".alert-screen-value code").map((code) => code.text())).toEqual(["living-screen", "desk"]);
    vi.unstubAllGlobals();
    page.unmount();
  });
  it("writes the example for the chosen screen, with a camera only where the board draws it", async () => {
    alertsInventory();
    const { default: AlertsView } = await import("../src/components/AlertsView.vue");
    const page = mount(AlertsView);
    expect(page.find("#alerts-one-example").text()).toBe(
      "event: esp_screens_show_alert\nevent_data:\n  screen: living-screen\n  title: \"Someone is at the door\"\n  camera: camera.front_door");
    await page.find("#alerts-one-screen").setValue("desk");
    expect(page.find("#alerts-one-example").text()).toBe(
      "event: esp_screens_show_alert\nevent_data:\n  screen: desk\n  title: \"Someone is at the door\"");
    expect(page.find("[data-jump='alerts-one']").text()).toBe("One screen");
    expect(page.text()).toContain("screen: [living-screen, desk]");
    page.unmount();
  });
});

describe("ChoiceField: the choice under the pointer is drawn on its tile first (app 0.4.32)", () => {
  const choices = [["standard", "Name"], ["big", "Big"]] as const;
  const tile: Tile = { id: "t1", entity: "sensor.t", name: "", slot: 0, options: { display: "standard" } };
  it("shows a choice on the tile while the pointer rests on it, and nothing once it leaves or picks", async () => {
    Object.assign(state.drag, { active: false, moving: null, preview: null, page: null });
    appendTiles({ entity: "sensor.t", name: "", slot: 0, options: { display: "standard" } });
    const placed = state.layout!.tiles.find((item) => item.entity === "sensor.t")!;
    const field = mount(ChoiceField, { props: { choices, value: "standard", tile: placed, previewKey: "display" } });
    const [, big] = field.findAll("button");
    await big.trigger("pointerenter");
    expect(state.optionPreview).toEqual({ tileId: placed.id, key: "display", value: "big" });
    // The preview is drawn only while that tile's own settings are open, and never during a drag.
    expect(previewed(placed)).toBe(placed);
    state.selectedTile = placed;
    expect(previewed(placed).options?.display).toBe("big");
    state.drag.active = true;
    expect(previewed(placed)).toBe(placed);
    state.drag.active = false;
    // Only that tile: another is drawn as it is.
    expect(previewed({ ...placed, id: "other" }).options?.display).toBe("standard");
    await field.find(".seg").trigger("pointerleave");
    expect(state.optionPreview).toBeNull();
    expect(previewed(placed)).toBe(placed);
    await big.trigger("pointerenter");
    await big.trigger("click");
    expect(state.optionPreview).toBeNull();
    expect(field.emitted("pick")).toEqual([["big"]]);
  });
  it("previews nothing for the choice already made", async () => {
    const field = mount(ChoiceField, { props: { choices, value: "standard", tile, previewKey: "display" } });
    await field.findAll("button")[0].trigger("pointerenter");
    expect(state.optionPreview).toBeNull();
  });
  it("folds a longer list into one field with the current choice", () => {
    const long = [["a", "Automatic"], ["b", "Nothing"], ["c", "A value"], ["d", "Own text"]] as const;
    const field = mount(ChoiceField, { props: { choices: long, value: "c" } });
    expect(field.find(".seg").exists()).toBe(false);
    expect(field.find(".choice-field .choice-text").text()).toBe("A value");
  });
});
