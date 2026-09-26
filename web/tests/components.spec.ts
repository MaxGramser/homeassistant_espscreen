import { seedLayout, seedTiles, seedPages, seedTitles, appendTiles, screenFixture, documentFixture, current } from "./page-fixtures";
// The components that draw the state: a tile with live values, the library's filters, the ⌘K search.
import { readFileSync } from "node:fs";
import { flushPromises, mount } from "@vue/test-utils";
import { defineComponent, h, nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AppSettingsView from "../src/components/AppSettingsView.vue";
import CommandPalette from "../src/components/CommandPalette.vue";
import Library from "../src/components/Library.vue";
import DevicePage from "../src/components/DevicePage.vue";
import InstallerView from "../src/components/InstallerView.vue";
import Sidebar from "../src/components/Sidebar.vue";
import SettingsTab from "../src/components/SettingsTab.vue";
import TileCard from "../src/components/TileCard.vue";
import TileInspector from "../src/components/TileInspector.vue";
import TopbarInspector from "../src/components/TopbarInspector.vue";
import { openBar, setTileOption, state } from "../src/store";
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

function inspector(tile: Tile) {
  const host = mount(defineComponent({ setup: () => () => h(TileInspector, { tile: tile.id ? current(tile) || tile : tile }) }));
  return host.findComponent(TileInspector);
}

function placed(tile: Tile) {
  appendTiles(tile);
  return mount(TileCard, { props: { tile, slot: tile.slot } });
}

describe("TileCard", () => {
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
    expect(settings.find('.tilt-choice input').exists()).toBe(true);
    await settings.find('.tilt-choice input').setValue(true);
    expect(current(tile)?.options?.controls ?? tile.options?.controls).toBe('position_tilt');
    await settings.find('.tilt-choice input').setValue(false);
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
    const modes = placed({ entity: 'climate.a', name: 'Climate', slot: 0, options: { size: 'square', controls: 'mode' } });
    expect(modes.findAll('.ctl .key')).toHaveLength(2);
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
  it("filters by room and hides what is placed, and tints the avatars by state", async () => {
    appendTiles({ entity: "light.a", name: "", slot: 0 });
    const library = mount(Library);
    const names = () => library.findAll(".ent .tx b").map((b) => b.text());
    expect(names()).toEqual(["Clock", "Go to page 1", "Lamp A", "Lamp B", "Temperature", "Curtains"]);
    expect(library.find('.ent[title="light.a"]').attributes("disabled")).toBeDefined();
    expect(library.find('.ent[title="light.a"] .av').classes()).toContain("on");
    expect(library.find('.ent[title="light.b"] .av').classes()).toContain("gone");
    expect(library.findAll("#room option").map((o) => o.text())).toEqual(["All rooms", "Kitchen", "Living room"]);
    await library.find("#room").setValue("Kitchen");
    expect(names()).toEqual(["Lamp B"]);
    await library.find("#room").setValue("");
    await library.find("#hide-placed").trigger("click");
    expect(names()).toEqual(["Clock", "Go to page 1", "Lamp B", "Temperature", "Curtains"]);
    state.filter = "light";
    await library.vm.$nextTick();
    expect(names()).toEqual(["Lamp B"]);
  });
});

// The nineteen domain chips used to sit on one sideways scroller with its scrollbar hidden (app 0.2.74). A trackpad
// swipes such a strip, but an ordinary mouse has no bar to grab and no drag to start, so fifteen of the nineteen could
// not be reached at all. They wrap now, they follow the results the way the list does, and the tail of a long one
// folds behind "More" (app 0.2.116).
describe("Library: every domain chip is reachable without a trackpad", () => {
  // Every chip but All and the More/Fewer one carries its domain's glyph in front of the label.
  const label = (b: { text: () => string }) => b.text().replace(/^[^\p{L}]+/u, "");
  const chips = (library: ReturnType<typeof mount>) => library.findAll("#filters button").map(label);
  const domains = (library: ReturnType<typeof mount>) => chips(library).filter((c) => !/^(More|Fewer)/.test(c));
  const chip = (library: ReturnType<typeof mount>, name: string) =>
    library.findAll("#filters button").find((b) => label(b) === name)!;
  // One entity in each of nine domains, so the strip is longer than the head can hold.
  const manyDomains = () => state.inventory.entities.push(
    { id: "climate.c", name: "Heating", state: "heat" }, { id: "switch.s", name: "Plug", state: "on" },
    { id: "binary_sensor.b", name: "Door", state: "off" }, { id: "script.r", name: "Run", state: "off" },
    { id: "fan.f", name: "Fan", state: "off" }, { id: "scene.n", name: "Night", state: "on" },
    { id: "media_player.m", name: "Sonos", state: "idle" }, { id: "person.p", name: "Sam", state: "home" },
  ) as unknown as void;

  it("offers the domains the results hold, and narrows them as the search narrows the list", async () => {
    const library = mount(Library);
    // Four domains in this home, plus All. A chip for a domain with nothing behind it would filter to an empty list.
    expect(domains(library)).toEqual(["All", "Lights", "Covers", "Sensors", "Screen"]);
    expect(library.find("#more-filters").exists()).toBe(false);

    state.search = "lamp";
    await library.vm.$nextTick();
    expect(domains(library)).toEqual(["All", "Lights"]);
    state.search = "temp";
    await library.vm.$nextTick();
    expect(domains(library)).toEqual(["All", "Sensors"]);
  });

  it("keeps every other chip once one is chosen, so a domain is never a dead end", async () => {
    const library = mount(Library);
    await chip(library, "Lights").trigger("click");
    expect(state.filter).toBe("light");
    expect(library.findAll(".ent .tx b").map((b) => b.text())).toEqual(["Lamp A", "Lamp B"]);
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
    // An empty list needs the chip that empties it on show, or there is nothing to explain it and nothing to undo.
    expect(domains(library)).toContain("Lights");
    expect(chip(library, "Lights").attributes("aria-pressed")).toBe("true");
  });

  it("folds a long strip behind More and opens the rest in place", async () => {
    manyDomains();
    const library = mount(Library);
    expect(domains(library)).toHaveLength(7);
    expect(chips(library).at(-1)).toBe("More (6)");
    expect(library.find("#more-filters").attributes("aria-expanded")).toBe("false");

    await library.find("#more-filters").trigger("click");
    expect(library.find("#more-filters").attributes("aria-expanded")).toBe("true");
    expect(domains(library)).toEqual([
      "All", "Lights", "Climate", "Switches", "Status", "Scripts", "Fans", "Covers", "Scenes", "Sensors",
      "Media", "People", "Screen",
    ]);
    expect(chips(library).at(-1)).toBe("Fewer");

    await library.find("#more-filters").trigger("click");
    expect(domains(library)).toHaveLength(7);
  });

  it("carries a folded-away chip into the head once it is the chosen one", async () => {
    manyDomains();
    const library = mount(Library);
    await library.find("#more-filters").trigger("click");
    await chip(library, "People").trigger("click");
    await library.find("#more-filters").trigger("click");
    expect(domains(library)).toContain("People");
    expect(chips(library).at(-1)).toBe("More (5)");
    const pressed = library.findAll("#filters button").filter((b) => b.attributes("aria-pressed") === "true");
    expect(pressed.map(label)).toEqual(["People"]);
  });

  it("never hides the strip behind a scrollbar a mouse cannot reach", () => {
    const css = readFileSync("src/styles/app.css", "utf8");
    const rule = css.split("\n").find((line) => line.startsWith(".filters {"))!;
    expect(rule).toContain("flex-wrap: wrap");
    expect(rule).not.toContain("overflow");
    expect(rule).not.toContain("scrollbar-width");
    expect(css).not.toContain(".filters::-webkit-scrollbar");
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

describe("several tiles that go to the same page in the library (firmware 0.2.65)", () => {
  it("keeps offering a placed navigation tile when the screen takes several, and adds another copy", async () => {
    Object.assign(state.inventory.screens[0], { firmware: "0.2.65", page_tiles_repeat: true });
    appendTiles({ entity: "screen.page_1", name: "", slot: 0 }, { entity: "light.a", name: "", slot: 1 });
    const library = mount(Library);
    const row = () => library.find('.ent[title="screen.page_1"]');
    expect(row().attributes("disabled")).toBeUndefined();
    expect(row().find(".add").text()).toBe("+");
    expect(library.find('.ent[title="light.a"]').attributes("disabled")).toBeDefined();
    await library.find("#hide-placed").trigger("click");
    expect(row().exists()).toBe(true);
    await row().trigger("click");
    expect(state.layout!.tiles.filter((t) => t.entity === "screen.page_1")).toHaveLength(2);
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
    wrapper.findAll(".f").find((f) => f.find(".f-label").exists() && f.find(".f-label").text() === label)!;
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
    expect(choices(drawer, "Refresh")).toEqual(["Every 15 s", "Every 30 s"]);
    expect(row(drawer, "Refresh").find('[aria-pressed="true"]').text()).toBe("Every 15 s");
    expect(row(drawer, "Display").find("small").text()).toMatch(/firmware 0\.2\.77/);
    expect(row(drawer, "Display").find("small").classes()).toContain("warn");
    await row(drawer, "Refresh").findAll(".seg button")[1].trigger("click");
    expect(current(tile).options).toEqual({ display: "live", refresh: 30 });
    Object.assign(state.inventory.screens[0], { firmware: "0.2.77" });
    await drawer.vm.$nextTick();
    expect(row(drawer, "Display").find("small").text()).toMatch(/icon's place/);
    expect(row(drawer, "Display").find("small").classes()).not.toContain("warn");
    // A light has no such choice.
    const lamp = mount(TileInspector, { props: { tile: { entity: "light.a", name: "", slot: 1 } } });
    expect(choices(lamp, "Display")).not.toContain("Live picture");
    // The mockup draws the picture's rounded square instead of the icon.
    const card = mount(TileCard, { props: { tile: current(tile), slot: 0 } });
    expect(card.find(".ic").classes()).toContain("thumb");
  });
  it("lets a live camera on a taller tile fill it, whole or cut, with its name or without, and keeps no defaults (app 0.3.8)", async () => {
    Object.assign(state.inventory, { editor_features: { tall_tiles: true } });
    Object.assign(state.inventory.screens[0], { firmware: "0.3.1", tile_sizes: ["single", "wide", "tall", "square", "full"] });
    state.inventory.entities.push({ id: "camera.garden", name: "Garden", state: "idle", area: "Garden" } as any);
    const tile: Tile = { entity: "camera.garden", name: "", slot: 0, options: { display: "live" } };
    appendTiles(tile);
    const drawer = inspector(tile);
    // One cell high the picture stays in the icon's place: nothing to fill.
    expect(row(drawer, "Picture")).toBeUndefined();
    setTileOption(current(tile), "size", "tall");
    await drawer.vm.$nextTick();
    expect(choices(drawer, "Picture")).toEqual(["Fill the tile", "Whole picture"]);
    expect(choices(drawer, "On the picture")).toEqual(["Name", "Nothing"]);
    expect(row(drawer, "Display").find("small").text()).toMatch(/firmware 0\.3\.3/);
    expect(row(drawer, "Display").find("small").classes()).toContain("warn");
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
    expect(row(drawer, "Display").find("small").classes()).not.toContain("warn");
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
    expect(choices(drawer, "Display")).toEqual(["Name and status", "Large value", "Album cover"]);
    await row(drawer, "Display").findAll(".seg button")[2].trigger("click");
    expect(current(tile).options).toEqual({ size: "wide", display: "cover" });
    expect(row(drawer, "Display").find("small").text()).toMatch(/icon's place/);
    expect(row(drawer, "Refresh")).toBeUndefined();
    expect(row(drawer, "Direct control on the tile")).toBeDefined();
    const card = mount(TileCard, { props: { tile: current(tile), slot: 0 } });
    expect(card.find(".ic").classes()).toContain("thumb");
    expect(card.find(".range").exists()).toBe(true);
    // A board without memory for pictures (a CYD) gets no such choice; a tile over the whole page keeps the card's big cover.
    Object.assign(state.inventory.screens[0], { board: "cyd", pictures: false });
    seedTiles([{ ...current(tile), options: { size: "single" } }]);
    await drawer.vm.$nextTick();
    expect(choices(inspector(tile), "Display")).toEqual(["Name and status", "Large value"]);
    Object.assign(state.inventory.screens[0], { board: "guition", pictures: true });
    seedTiles([{ ...current(tile), options: { size: "full" } }]);
    expect(choices(inspector(tile), "Display")).toEqual(["Name and status", "Large value"]);
  });
});

describe("TileInspector: pages (app 0.2.78)", () => {
  const row = (wrapper: ReturnType<typeof mount>, label: string) =>
    wrapper.findAll(".f").find((f) => f.find(".f-label").exists() && f.find(".f-label").text() === label)!;
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
  it("moves the tile to another page or a new one with a tap", async () => {
    const { tile, drawer } = open([{ entity: "light.a", name: "", slot: 0 }, { entity: "sensor.t", name: "", slot: 6 }], 0);
    expect(choices(drawer, "Page")).toEqual(["1", "2", "New page"]);
    expect(row(drawer, "Page").find('[aria-pressed="true"]').text()).toBe("1");
    await row(drawer, "Page").findAll(".seg button")[1].trigger("click");
    expect(current(tile).slot).toBe(7);
    expect(state.dirty).toBe(true);
    // Alone on the last page now: a new page would only leave this one empty.
    const sensor = state.layout!.tiles.find((t) => t.entity === "sensor.t")!;
    await row(drawer, "Page").findAll(".seg button")[0].trigger("click");
    expect(current(tile).slot).toBe(0);
    expect(current(sensor).slot).toBe(6);
    const other = inspector(sensor);
    expect(choices(other, "Page")).toEqual(["1", "2"]);
    await row(other, "Page").findAll(".seg button")[0].trigger("click");
    expect(current(sensor).slot).toBe(1);
    // One tile on one page: nowhere to go, so no row.
    seedTiles([]);
    const only = open([{ entity: "light.b", name: "", slot: 0 }], 0).drawer;
    expect(row(only, "Page")).toBeUndefined();
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
  it("shows a screen's name and light alone, and its details once it is chosen (app 0.2.108)", async () => {
    const sidebar = mount(Sidebar);
    const item = sidebar.find("#screens .screen-item");
    expect(item.find(".led").classes()).toContain("ok");
    expect(item.find(".sub").exists()).toBe(false);
    expect(item.find(".screen-details").exists()).toBe(false);
    await item.find(".nav-item").trigger("click");
    expect(item.classes()).toContain("open");
    expect(item.findAll(".facts dt").map((dt) => dt.text())).toEqual(["Firmware", "Board"]);
    expect(item.findAll(".facts dd").map((dd) => dd.text())).toEqual(["0.2.60", "Guition · 4 inch"]);
    // Chosen again, the details fold away; a screen that is off shows why in red.
    await item.find(".nav-item").trigger("click");
    expect(item.classes()).not.toContain("open");
    Object.assign(state.inventory.screens[0], { online: false });
    await nextTick();
    expect(item.find(".led").classes()).toContain("down");
    expect(item.find(".sub").text()).toBe("Offline");
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
    await item.find(".remove-screen").trigger("click");
    expect(item.find(".screen-remove small.warn").text()).toContain("still connected");
    // Nothing goes until it is confirmed: Cancel puts the details back.
    await item.findAll(".screen-remove .btn")[1].trigger("click");
    expect(item.find(".screen-remove").exists()).toBe(false);
    expect(item.find(".facts").exists()).toBe(true);
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
});

describe("the title above a page (app 0.2.105)", () => {
  // You click a page's bar and answer one question: what stands above this page.
  it("asks it for the page whose bar was clicked", async () => {
    seedLayout({ title: "Living room", tiles: [], pages: 3 });
    openBar(0, 1);
    const drawer = mount(TopbarInspector, { props: { index: 0 } });
    const field = drawer.find("#page-title");
    expect(drawer.find("label[for='page-title']").text()).toBe("Title above page 2");
    // Empty says what page 1 says, so a page that follows it looks like it does.
    expect((field.element as HTMLInputElement).value).toBe("");
    expect(field.attributes("placeholder")).toBe("Living room");
    expect(drawer.find("#page-title-hint button").attributes("aria-label")).toBe("Leave empty and this page says the screen's title.");
    await field.setValue("Music");
    expect(state.layout!.page_titles).toEqual(["", "Music"]);
    // Clearing it hands the page back and leaves nothing behind.
    await field.setValue("");
    expect(state.layout!.page_titles).toBeUndefined();
  });
  it("asks page 1 for the screen's title and for a title of its own", async () => {
    seedLayout({ title: "Living room", tiles: [], pages: 2, page_titles: ["", "Music"] });
    openBar(0, 0);
    const drawer = mount(TopbarInspector, { props: { index: 0 } });
    const screen = drawer.find("#screen-title");
    expect(drawer.find("label[for='screen-title']").text()).toBe("Screen title");
    expect((screen.element as HTMLInputElement).value).toBe("Living room");
    expect(drawer.find("#screen-title-hint button").attributes("aria-label")).toBe("Every page without a title of its own says this.");
    await screen.setValue("Downstairs");
    expect(state.layout!.title).toBe("Downstairs");
    expect(state.layout!.page_titles).toEqual(["", "Music"]);
    // Page 1 carries one of its own like any other page (app 0.2.123), and falls back to the screen's.
    const own = drawer.find("#page-title");
    expect(drawer.find("label[for='page-title']").text()).toBe("Title above page 1");
    expect((own.element as HTMLInputElement).value).toBe("");
    expect(own.attributes("placeholder")).toBe("Downstairs");
    await own.setValue("Hall");
    expect(state.layout!.page_titles).toEqual(["Hall", "Music"]);
    expect(state.layout!.title).toBe("Downstairs");
  });
  it("asks a screen with one page for one title only", () => {
    seedLayout({ title: "Living room", tiles: [] });
    openBar(0, 0);
    const one = mount(TopbarInspector, { props: { index: 0 } });
    expect(one.findAll("#screen-title")).toHaveLength(1);
    expect(one.find("label[for='screen-title']").text()).toBe("Title above the page");
    // One page and the screen's title are the same thing, so there is no second field to fill.
    expect(one.find("#page-title").exists()).toBe(false);
    // A title that page kept from a longer row does get its field back: nothing is set that nobody can see.
    seedLayout({ title: "Living room", tiles: [], page_titles: ["Hall"] });
    expect(mount(TopbarInspector, { props: { index: 0 } }).find("#page-title").exists()).toBe(true);
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
describe("a name another screen already carries", () => {
  const flush = async () => { await Promise.resolve(); await Promise.resolve(); await new Promise((done) => setTimeout(done, 0)); };
  async function installer(taken: any) {
    vi.stubGlobal("fetch", vi.fn((url: string) => (String(url).endsWith("api/firmware")
      ? Promise.resolve({ ok: true, json: () => Promise.resolve({ available: true, ports: ["/dev/ttyUSB0"], profiles: [], logs: [], wifi: { state: "ready" }, boards: {}, taken }) })
      : Promise.resolve({ ok: true, text: () => Promise.resolve("{}") }))));
    const view = mount(InstallerView);
    await flush();
    return view;
  }
  it("says so under the name and holds the button until the name is the screen's own", async () => {
    const view = await installer({ nodes: ["hall"], prefixes: ["living_room"] });
    await view.find("#friendly_name").setValue("Living room");
    expect(view.find("#name-taken").exists()).toBe(true);
    expect(view.find("#install-go").attributes("disabled")).toBeDefined();
    await view.find("#friendly_name").setValue("Kitchen");
    expect(view.find("#name-taken").exists()).toBe(false);
    expect(view.find("#node-taken").exists()).toBe(false);
    expect(view.find("#install-go").attributes("disabled")).toBeUndefined();
    // The device name follows the name, and can be the one that clashes.
    await view.find("#friendly_name").setValue("Hall");
    expect(view.find("#name-taken").exists()).toBe(false);
    expect(view.find("#node-taken").exists()).toBe(true);
    expect(view.find("#install-go").attributes("disabled")).toBeDefined();
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
    expect(rows.map((row) => row.find("input").attributes("value"))).toEqual(
      Object.values(boards).sort((a: any, b: any) => a.order - b.order).map((board: any) => Object.keys(boards).find((key) => boards[key] === board)));
    expect(rows[0].find("b").text()).toBe("CYD · 2.8 inch");
    expect(rows[0].findAll("small").map((line) => line.text())).toEqual(["ESP32-2432S028", "320 × 240 · XPT2046"]);
    expect(view.find('input[value="jc8012p4a1"]').element.closest("label")?.textContent).toContain("Guition · 10.1 inch");
    // Each glass in its own proportions with the cells of one page lying down.
    const glass = (key: string) => view.find(`input[value="${key}"]`).element.closest("label")!.querySelector(".orient-glass") as HTMLElement;
    expect(glass("jc8012p4a1").getAttribute("style")).toContain("1280 / 800");
    expect(glass("jc8012p4a1").querySelectorAll(".orient-cells i")).toHaveLength(20);
    expect(glass("guition").getAttribute("style")).toContain("480 / 480");
    // The first board is chosen to begin with, with what it can do; the CYD asks for a touch calibration first.
    expect((rows[0].find("input").element as HTMLInputElement).checked).toBe(true);
    expect(view.findAll("#board-abilities li").map((li) => li.text())).toEqual(
      ["No camera pictures", "Dimmable backlight", "Standby and night", "Touch calibration on first start"]);
    expect(view.find("#board-status").exists()).toBe(false);
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
    expect(grab.text()).toBe("⋮⋮Page 2");
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
  it("offers Remove page on every page of the row, filled or not", async () => {
    // A page leaves whether it is empty or not (app 0.2.123): the way out stands beside the cells in use.
    const second = mount(DevicePage, { props: props(1, 3) });
    const remove = second.find(".page-remove");
    expect(remove.exists()).toBe(true);
    expect(remove.attributes("aria-label")).toBe("Remove page 2");
    expect(second.find(".page-side").text()).toContain("1 / 6");
    // The only page cannot leave, and neither can the page a tile can start behind the last one.
    expect(mount(DevicePage, { props: props(3, 3) }).find(".page-remove").exists()).toBe(false);
    seedPages(1);
    expect(mount(DevicePage, { props: props(0, 1) }).find(".page-remove").exists()).toBe(false);
    seedPages(3);
    await remove.trigger("click");
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

// The house in the top bar (app 0.2.122, firmware 0.2.100+): the mockup draws what the screen draws.
describe("the home key on the mockup", () => {
  const house = String.fromCodePoint(0xf02dc);
  const props = (page: number) => ({ page, pages: 3, entries: [], moving: null });
  const bar = (page: number) => mount(DevicePage, { props: props(page) }).find(".bar-wrap").text();
  beforeEach(() => {
    seedLayout({ title: "Living room", pages: 3, tiles: [] });
    (state.inventory.screens[0] as any).firmware = "0.2.100";
    (state.inventory.screens[0] as any).firmware_known = "0.2.100";
    (state.inventory.screens[0] as any).settings = { owner: "screen", keys: ["home_button"], values: { home_button: true }, unavailable: [] };
  });
  it("draws it on every page, as the screens do", () => {
    expect(bar(0)).toContain(house);
    expect(bar(1)).toContain(house);
    expect(bar(2)).toContain(house);
  });
  it("leaves it out when the screen's setting is off, and on firmware that has no key", () => {
    (state.inventory.screens[0] as any).settings.values.home_button = false;
    expect(bar(1)).not.toContain(house);
    (state.inventory.screens[0] as any).settings.values.home_button = true;
    (state.inventory.screens[0] as any).firmware_known = "0.2.99";
    expect(bar(1)).not.toContain(house);
  });
  it("gives the name the room the key takes, with the margin of the glass between them", () => {
    const withKey = mount(DevicePage, { props: props(1) }).findComponent({ name: "TopbarSvg" }).vm as any;
    (state.inventory.screens[0] as any).settings.values.home_button = false;
    const without = mount(DevicePage, { props: props(1) }).findComponent({ name: "TopbarSvg" }).vm as any;
    expect(without.lay.homeShift).toBe(0);
    // The same air as between the edge of the glass and the key itself.
    expect(withKey.lay.homeShift).toBe(Math.round(withKey.lay.key.ink.right - withKey.lay.key.ink.left) + withKey.lay.metrics.inset);
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
