// A first layout for a screen (model/auto-layout.ts, docs/AUTO_LAYOUT.md), made from fake homes as Home Assistant reports
// them: one with areas and floors and one without any, on a large screen with sections (10.1-inch, 5 x 5), a middle
// one (3 x 3) and the CYD (2 x 3, no sections, little memory). Every layout must pass the editor's own validation.
import { describe, expect, it } from "vitest";
import type { PageLayout, PageTile } from "../src/types";
import { autoLayout, appendPages, candidates, facesFor, placeTileFor, clusters, cutBytes, GROUP_ICONS, ICONS, labelOf, strip, type AutoInput, type AutoScreen } from "../src/model/auto-layout";
import { allTiles, emptyLayout, projectLayout, tilesIn, validatePages } from "../src/model/pages";
import { memoryLine, memoryUse, NEARLY_FULL } from "../src/model/memory";

import { AREAS, BUSY, CYD, FLOORS, HOUSE, MIDDLE, NOISE, TEN, home } from "./auto-layout.fixture";

const make = (screen: AutoScreen, things = HOUSE, areas = AREAS) => {
  const input: AutoInput = { ...home(things, areas, FLOORS), screen };
  const result = autoLayout(input);
  return { input, result, layout: validatePages(result.layout, { ...screen.grid, pages: screen.pages }) };
};
const tilesOf = (layout: PageLayout) => layout.pages.flatMap(allTiles);
const entityIds = (layout: PageLayout) => tilesOf(layout).map((tile) => (tile.content as { entityId: string }).entityId);
const tileFor = (layout: PageLayout, id: string) => tilesOf(layout).find((tile) => (tile.content as { entityId?: string }).entityId === id);
const sizeOf = (tile: PageTile | undefined) => tile && `${tile.placement.columns}x${tile.placement.rows}`;

describe("which entities a first layout takes", () => {
  it("leaves out what Home Assistant's own dashboards leave out, and what no wall wants", () => {
    const ids = candidates({ ...home(HOUSE, AREAS, FLOORS), screen: TEN }).map((c) => c.id);
    for (const id of ["sensor.lamp_signal", "switch.lamp_led", "light.hidden_one", "light.broken", "switch.hall_screen_backlight",
      "automation.morning", "script.bedtime", "button.restart", "input_number.target", "sensor.phone_battery", "binary_sensor.motion"]) expect(ids).not.toContain(id);
    expect(ids).toContain("light.living_room_ceiling");
  });
  it("leaves out the screen's lists and cameras where its board draws none", () => {
    const ids = candidates({ ...home(HOUSE, AREAS, FLOORS), screen: CYD }).map((c) => c.id);
    expect(ids).not.toContain("todo.shopping_list");
    expect(ids).not.toContain("camera.garden");
  });
  it("names a tile without its room", () => {
    expect(strip("Living room Ceiling", "Living room")).toBe("Ceiling");
    expect(strip("Bedroom Sonos", "Bedroom")).toBe("Sonos");
    expect(strip("Sonos Living room", "Living room")).toBe("Sonos");
    expect(strip("Kitchen", "Kitchen")).toBe("Kitchen");
    expect(strip("Keukenblad", "Keuken")).toBe("Keukenblad");
    expect(strip("Één lamp", "een")).toBe("Lamp");
    expect(cutBytes("ééééé", 4)).toBe("éé");
  });
  it("names a tile by its device where it is the device's one, else by its own part", () => {
    const named = (name: string, deviceName = "", context = "", alone = true, extra: { maker?: string; members?: string[]; domain?: string } = {}) =>
      labelOf({ name, deviceName, maker: extra.maker ?? "", domain: extra.domain ?? "light", fact: { id: "x", members: extra.members } }, context, alone);
    expect(named("Spot 1 Light", "Spot 1", "Living room")).toBe("Spot 1");
    expect(named("Bathroom Mirror", "Bathroom Switch", "Bathroom", false)).toBe("Mirror");
    expect(named("bathroom 1", "bathroom 1", "Bathroom")).toBe("Bathroom 1");
    expect(named("hall 2 Light", "hall 2", "Hall")).toBe("Hall 2");
    expect(named("Bedroom Light", "Bedroom", "Bedroom")).toBe("Light");
    expect(named("Bedroom", "Bedroom", "Bedroom", true, { maker: "Sonos", domain: "media_player" })).toBe("Sonos");
    expect(named("Kitchen", "", "Kitchen", true, { members: ["light.a"] })).toBe("All lights");
    expect(named("Robbie", "S8", "Living room", true, { domain: "vacuum" })).toBe("Robbie");
    expect(named("cupboard Light", "cupboard", "Kitchen")).toBe("Cupboard");
  });
  it("finds the room of what has none: its group's members, or a room its name holds", () => {
    const found = new Map(candidates({ ...home(BUSY, AREAS, FLOORS), screen: TEN }).map((c) => [c.id, c]));
    expect(found.get("light.lounge_group")!.area).toBe("living");
    expect(found.get("scene.evening")!.area).toBe("living");
    expect(found.get("media_player.lg_oled")!.area).toBe("living");
    expect(found.get("camera.front")!.area).toBe("living");
    // A device's own switches stay without a room; a screen's own camera and a rain radar are no cameras of the house.
    expect(found.get("switch.cam_privacy")!.area).toBe("");
    expect(found.has("camera.hall_screen_video")).toBe(false);
    expect(found.has("camera.rain_radar")).toBe(false);
  });
  it("gives every group an icon of the fixed set a section takes", () => {
    for (const icon of Object.values(GROUP_ICONS)) expect(ICONS.has(icon)).toBe(true);
  });
});

describe("a large screen with sections (10.1-inch, 5 x 5)", () => {
  const { result, layout } = make(TEN);
  it("passes the editor's validation, within the screen's pages and tiles", () => {
    expect(layout.pages.length).toBeLessThanOrEqual(8);
    expect(result.tiles).toBe(tilesOf(layout).length);
    expect(result.tiles).toBeLessThanOrEqual(64);
    expect(layout.pages.every((page) => (page.sections?.length ?? 0) + page.tiles.length > 0)).toBe(true);
    expect(layout.pages.some((page) => (page.sections?.length ?? 0) > 1)).toBe(true);
  });
  it("starts with the screen's own room, its groups as sections, and makes it Home", () => {
    const first = layout.pages[0];
    expect(layout.homePageId).toBe(first.id);
    expect(first.topbar.title).toEqual({ source: "text", text: "Living room" });
    const titles = first.sections!.map((s) => s.title);
    expect(titles[0]).toBe("Lights");
    expect(titles).toContain("Media");
    // The thermostat alone is a card of its own, not a section; the room's temperature goes on its first section.
    expect(first.tiles.map((tile) => (tile.content as { entityId: string }).entityId)).toContain("climate.airco");
    expect(first.sections![0].summary).toBe("sensor.living_room_temperature");
    expect(first.icon).toBe("sofa");
  });
  it("chooses larger tiles with more controls where they pay off", () => {
    const group = tileFor(layout, "light.living_room")!;
    expect(sizeOf(group)).toBe("2x2");
    expect(group.interaction.controls).toBe("brightness_presets");
    expect(group.appearance.label).toBe("All lights");
    expect(tileFor(layout, "climate.airco")!.interaction.controls).toBe("setpoint_mode");
    const sonos = tileFor(layout, "media_player.sonos_living")!;
    expect([sizeOf(sonos), sonos.appearance.display]).toEqual(["2x2", "cover"]);
    expect([sizeOf(tileFor(layout, "media_player.apple_tv")), tileFor(layout, "media_player.apple_tv")!.interaction.controls]).toEqual(["2x1", "playback"]);
    const weather = tileFor(layout, "weather.home")!;
    expect([sizeOf(weather), weather.appearance.display]).toEqual(["2x2", "forecast"]);
    const vacuum = tileFor(layout, "vacuum.robot")!;
    expect([sizeOf(vacuum), vacuum.interaction.controls]).toEqual(["3x2", "map_rooms"]);
    expect(tileFor(layout, "camera.garden")!.appearance.display).toBe("live");
    // One calendar card for the house, the other calendar in it.
    const calendars = tilesOf(layout).filter((tile) => (tile.content as { entityId: string }).entityId.startsWith("calendar."));
    expect(calendars).toHaveLength(1);
    expect(calendars[0].appearance.label).toBe("Calendar");
    expect(calendars[0].appearance.calendarEntities).toHaveLength(1);
    expect(tileFor(layout, "light.living_room_ceiling")!.appearance.label).toBe("Ceiling");
    expect(sizeOf(tileFor(layout, "light.spot_1"))).toBe("1x1");
  });
  it("shows a room's temperature once: in its section's summary, not as a tile beside a thermostat", () => {
    expect(entityIds(layout)).not.toContain("sensor.living_room_temperature");
    expect(entityIds(layout)).not.toContain("sensor.kitchen_temperature");
    const kitchen = layout.pages.flatMap((p) => p.sections ?? []).find((s) => s.title === "Kitchen")!;
    expect(kitchen.summary).toBe("sensor.kitchen_temperature");
    expect(kitchen.icon).toBe("silverware-fork-knife");
  });
  it("keeps the house's own things together, one weather and one meter", () => {
    const house = layout.pages.find((page) => allTiles(page).some((tile) => (tile.content as { entityId: string }).entityId === "weather.home"))!;
    expect(house.sections!.map((s) => s.title)).toContain("Who is home");
    expect(allTiles(house).map((tile) => (tile.content as { entityId: string }).entityId)).toContain("alarm_control_panel.house");
    for (const id of NOISE) expect(entityIds(layout)).not.toContain(id);
    expect(entityIds(layout)).toContain("sensor.power_consumption");
    expect(tileFor(layout, "camera.garden")!.appearance.label).toBe("Garden");
  });
  it("fills a page with several rooms before it starts the next", () => {
    const shared = layout.pages.find((page) => (page.sections ?? []).some((s) => s.title === "Bedroom"))!;
    expect(shared.sections!.length).toBeGreaterThan(1);
    expect(layout.pages.length).toBeLessThanOrEqual(4);
  });
  it("places every room and the house, nothing twice", () => {
    expect(result.rooms).toBe(5);
    expect(new Set(entityIds(layout)).size).toBe(entityIds(layout).length);
    expect(result.leftOut).toBe(0);
  });
});

describe("a middle screen (3 x 3)", () => {
  const { layout } = make(MIDDLE);
  it("makes sections that fit its grid, with its own tile sizes", () => {
    expect(layout.pages.length).toBeGreaterThan(2);
    for (const tile of tilesOf(layout)) expect(tile.placement.columns).toBeLessThanOrEqual(3);
    // No live picture on a screen that streams none.
    expect(tileFor(layout, "camera.garden")?.appearance.display).toBeUndefined();
  });
});

describe("the CYD (2 x 3, no sections, 4 MB)", () => {
  const { result, layout } = make(CYD);
  it("spreads rooms over pages, one room or theme to a page, plain tiles", () => {
    expect(layout.pages.every((page) => !page.sections)).toBe(true);
    expect(layout.pages.length).toBeLessThanOrEqual(8);
    const titles = layout.pages.map((page) => page.topbar.title.source === "text" ? page.topbar.title.text : "");
    expect(titles[0]).toBe("Home");
    expect(titles).toContain("Living room");
    for (const tile of tilesOf(layout)) {
      const id = (tile.content as { entityId: string }).entityId;
      expect(sizeOf(tile)).toBe(id.startsWith("weather.") ? "2x1" : "1x1");
      expect(tile.interaction.controls).toBeUndefined();
    }
  });
  it("stays within the screen's memory, the least wanted left out first", () => {
    expect(result.leftOut).toBeGreaterThan(0);
    expect(result.tiles).toBeLessThan(25);
    expect(entityIds(layout)).toContain("climate.airco");
    expect(entityIds(layout)).toContain("alarm_control_panel.house");
    expect(entityIds(layout)).not.toContain("binary_sensor.balcony_door");
  });
});

describe("a home without areas", () => {
  const flat = HOUSE.map(({ area: _area, ...rest }) => rest);
  flat.push({ id: "light.keuken_spot", name: "Keuken spot" }, { id: "light.keuken_werkblad", name: "Keuken werkblad" },
    { id: "switch.keuken_afzuigkap", name: "Keuken afzuigkap" }, { id: "light.desk_1", name: "Desk", device: "d-study_lamp" },
    { id: "switch.desk_2", name: "Desk socket", device: "d-study_lamp" });
  it("groups by the word names share, then by device, then by kind", () => {
    const found = clusters(candidates({ ...home(flat, [], []), screen: TEN }).filter((c) => !c.house));
    const byTitle = Object.fromEntries(found.map((c) => [c.title, c.members.map((m) => m.id)]));
    expect(byTitle.Keuken).toEqual(expect.arrayContaining(["light.keuken_spot", "light.keuken_werkblad", "switch.keuken_afzuigkap"]));
    expect(byTitle["Living"]).toEqual(expect.arrayContaining(["light.living_room_ceiling", "light.living_room_table", "climate.airco"]));
    expect(byTitle["study lamp"]).toEqual(["light.desk_1", "switch.desk_2"]);
    expect(Object.keys(byTitle)).toContain("Lights");
  });
  it("makes a valid layout on the large screen and on the CYD", () => {
    for (const screen of [TEN, CYD]) {
      const { layout, result } = make({ ...screen, area: undefined }, flat, []);
      expect(result.tiles).toBeGreaterThan(5);
      expect(entityIds(layout)).toContain("light.keuken_spot");
      expect(tileFor(layout, "light.keuken_spot")!.appearance.label).toBe("Spot");
    }
  });
});

describe("a section groups", () => {
  it("never holds a single card: a lone card stands loose on its page", () => {
    for (const screen of [TEN, MIDDLE]) for (const things of [HOUSE, BUSY]) {
      const { layout } = make(screen, things);
      for (const page of layout.pages) for (const section of page.sections ?? []) expect(tilesIn(page, section).length, section.title).toBeGreaterThan(1);
    }
    // The house's one weather and one alarm are cards of their own on the large screen.
    const { layout } = make(TEN);
    expect(layout.pages.some((page) => page.tiles.some((tile) => (tile.content as { entityId: string }).entityId === "weather.home"))).toBe(true);
  });
});

describe("a busier home", () => {
  for (const screen of [TEN, MIDDLE, CYD]) {
    const { layout, result } = make(screen, BUSY);
    it(`places nothing twice and stays within the ${screen.grid.columns} x ${screen.grid.rows} screen`, () => {
      expect(new Set(entityIds(layout)).size).toBe(entityIds(layout).length);
      expect(result.tiles).toBeLessThanOrEqual(screen.tiles);
      expect(layout.pages.length).toBeLessThanOrEqual(screen.pages);
    });
  }
  const { layout } = make(TEN, BUSY);
  it("leaves a device's own switches without a room to the library, and keeps a thermostat without one", () => {
    expect(entityIds(layout)).not.toContain("switch.cam_privacy");
    expect(entityIds(layout)).toContain("climate.attic");
    const home = layout.pages.find((page) => allTiles(page).some((t) => (t.content as { entityId: string }).entityId === "climate.attic"))!;
    expect(home.topbar.title).toEqual({ source: "text", text: "Home" });
  });
  it("names people by their first name and a room's light group as all its lights", () => {
    expect(tileFor(layout, "person.cleo")!.appearance.label).toBe("Cleo");
    expect(tileFor(layout, "light.spot_3")!.appearance.label).toBe("Spot 3");
    expect(tileFor(layout, "switch.boiler")!.appearance.label).toBe("Boiler");
    expect(entityIds(layout)).not.toContain("sensor.boiler_power");
  });
  it("streams one camera live, the screen's number of live tiles", () => {
    const live = tilesOf(layout).filter((tile) => tile.appearance.display === "live");
    expect(live).toHaveLength(1);
  });
});

describe("adding the pages after the ones a screen has", () => {
  it("keeps the screen's pages and Home, and leaves out what is already there", () => {
    const current = emptyLayout("Hall");
    current.pages[0].tiles = [{ id: "own", content: { kind: "entity", entityId: "light.hall" }, placement: { row: 0, column: 0, columns: 1, rows: 1 }, appearance: { label: "Hall" }, interaction: {} }];
    const input: AutoInput = { ...home(HOUSE, AREAS, FLOORS), screen: { ...TEN, pages: 7, tiles: 63 }, exclude: new Set(["light.hall"]) };
    const made = autoLayout(input).layout;
    const both = validatePages(appendPages(current, made), { columns: 5, rows: 5, pages: 8 });
    expect(both.homePageId).toBe(current.homePageId);
    expect(both.pages[0].tiles[0].id).toBe("own");
    expect(entityIds(both).filter((id) => id === "light.hall")).toHaveLength(1);
  });
});

describe("the add-on takes every first layout", () => {
  // The documents of every home on every screen, their ids numbered in order, for tests/test_auto_layout.py to check with
  // the add-on's own validate_document: the two document boundaries take the same layouts.
  it("writes them where the add-on's test reads them", async () => {
    let n = 0;
    const ids = new Map<string, string>();
    const numbered = (value: unknown): unknown => JSON.parse(JSON.stringify(value, (key, item) =>
      (key === "id" || key === "homePageId") && typeof item === "string"
        ? ids.get(item) ?? (ids.set(item, (++n).toString(16).padStart(16, "0")), ids.get(item)) : item));
    const documents = [TEN, MIDDLE, CYD].flatMap((screen) => [HOUSE, BUSY].map((things) => ({
      grid: screen.grid, layout: numbered(make(screen, things).layout) })));
    await expect(JSON.stringify(documents, null, 1) + "\n").toMatchFileSnapshot("../../tests/fixtures/auto-layout-documents.json");
  });
});

describe("the screen's memory, as Library holds an add", () => {
  const use = (layout: PageLayout, screen: AutoScreen) => memoryUse(projectLayout(layout, { ...screen.grid, pages: screen.pages }).tiles, screen.memory!, layout.pages);
  const nothing = (screen: AutoScreen) => memoryUse([], screen.memory!, []);
  it("never takes a new screen past a line the editor would ask about", () => {
    for (const screen of [CYD, { ...CYD, memory: { ...CYD.memory!, room: 6000 } }, TEN]) for (const things of [HOUSE, BUSY]) {
      const { layout } = make(screen, things);
      expect(memoryLine(nothing(screen), use(layout, screen))).toBeNull();
      expect(use(layout, screen).share).toBeLessThan(NEARLY_FULL);
    }
  });
  it("counts the new pages' top bars", () => {
    const bar = emptyLayout("CYD").pages[0].topbar;
    bar.trailing = ["sensor.a", "sensor.b", "sensor.c", "sensor.d"].map((entity, i) => ({ id: `b${i}`, type: "entity", entity, content: "state", icon: "auto", show: "always" }));
    const plain = make(CYD).result.tiles, barred = make({ ...CYD, topbar: bar }).result.tiles;
    expect(barred).toBeLessThan(plain);
  });
  it("adds nothing that costs memory after a draft that is past its room, and stays within it after one past nine tenths", () => {
    const current = emptyLayout("CYD"), room = 6000;
    current.pages[0].tiles = Array.from({ length: 6 }, (_, i): PageTile => ({ id: `own${i}`, content: { kind: "entity", entityId: "media_player.apple_tv" },
      placement: { row: Math.floor(i / 2), column: i % 2, columns: 1, rows: 1 }, appearance: { label: "TV" }, interaction: {} }));
    const existing = { tiles: projectLayout(current, { ...CYD.grid, pages: 8 }).tiles, pages: current.pages };
    const screen = (share: number): AutoScreen => {
      const need = memoryUse(existing.tiles, { ...CYD.memory!, room }, existing.pages).need;
      return { ...CYD, pages: 7, memory: { ...CYD.memory!, room: Math.round(need / share), used: 0 } };
    };
    const past = autoLayout({ ...home(HOUSE, AREAS, FLOORS), screen: screen(1.1), existing });
    expect(past.tiles).toBe(0);
    const close = autoLayout({ ...home(HOUSE, AREAS, FLOORS), screen: screen(0.93), existing });
    const after = memoryUse([...existing.tiles, ...projectLayout(close.layout, { ...CYD.grid, pages: 8 }).tiles], screen(0.93).memory!, [...existing.pages, ...close.layout.pages]);
    expect(after.level).not.toBe("over");
  });
  it("prices the pages that stay beside the new ones when they go after them", () => {
    const current = emptyLayout("CYD");
    current.pages[0].tiles = Array.from({ length: 6 }, (_, i): PageTile => ({ id: `own${i}`, content: { kind: "entity", entityId: "media_player.apple_tv" },
      placement: { row: Math.floor(i / 2), column: i % 2, columns: 1, rows: 1 }, appearance: { label: "TV" }, interaction: {} }));
    const existing = { tiles: projectLayout(current, { ...CYD.grid, pages: 8 }).tiles, pages: current.pages };
    const alone = autoLayout({ ...home(HOUSE, AREAS, FLOORS), screen: { ...CYD, pages: 7 } }).tiles;
    const beside = autoLayout({ ...home(HOUSE, AREAS, FLOORS), screen: { ...CYD, pages: 7 }, existing }).tiles;
    expect(beside).toBeLessThan(alone);
  });
});

describe("the cards an entity can take, for a caller that was given it", () => {
  it("are the first layout's own: plainest first, the one it gives wanted", () => {
    const input = (screen: AutoScreen): AutoInput => ({ ...home(HOUSE, AREAS, FLOORS), screen });
    const group = facesFor("light.living_room", input(TEN), { context: "Living room" })!;
    expect(group.faces.map((f) => `${f.columns}x${f.rows}`)).toEqual(["1x1", "2x1", "2x2"]);
    expect(group.want).toBe(2);
    expect(group.faces[2].tile.interaction.controls).toBe("brightness_presets");
    expect(group.faces[2].tile.appearance.label).toBe("All lights");
    expect(group.alike).toBe("light:group");
    expect(facesFor("media_player.sonos_living", input(TEN))!.faces.at(-1)!.tile.appearance.display).toBe("cover");
    const tile = placeTileFor("light.living_room", input(TEN), { context: "Living room" })!;
    expect([tile.columns, tile.rows, tile.face, tile.faces!.length, tile.alike]).toEqual([1, 1, 0, 3, "light:group"]);
    const cyd = facesFor("light.living_room", input(CYD))!;
    expect([cyd.faces.length, cyd.want]).toEqual([1, 0]);
    // A kind the first layout leaves out is a plain tile when asked for; one the screen draws no tile of is null.
    expect(facesFor("script.bedtime", input(TEN))!.faces).toHaveLength(1);
    expect(facesFor("camera.garden", input(CYD))).toBeNull();
    expect(facesFor("light.nowhere", input(TEN))).toBeNull();
  });
});

describe("an empty home", () => {
  it("makes one empty page", () => {
    const result = autoLayout({ ...home([], [], []), screen: TEN });
    expect(result.tiles).toBe(0);
    expect(result.layout.pages).toHaveLength(1);
  });
});

describe("a room's sensors", () => {
  it("start as the meter that suits them where the screen draws meters, as an added sensor does (model/sensor-look.ts)", () => {
    const things = [...HOUSE,
      { id: "sensor.kitchen_temperature", name: "Kitchen Temperature", area: "kitchen", class: "temperature", unit: "°C", stateClass: "measurement", state: "21.4" },
      { id: "sensor.kitchen_co2", name: "Kitchen CO2", area: "kitchen", class: "carbon_dioxide", unit: "ppm", stateClass: "measurement", state: "640" },
      { id: "sensor.kitchen_energy", name: "Kitchen Energy", area: "kitchen", class: "energy", unit: "kWh", stateClass: "total_increasing", state: "120.5" }];
    const { layout } = make(MIDDLE, things);
    // The temperature is the kitchen's summary; its CO2 a bar over a round range around its value now, its energy a value.
    expect(tileFor(layout, "sensor.kitchen_co2")?.appearance).toMatchObject({ display: "meter", meterStyle: "bar", meterMin: 0, meterMax: 1000 });
    expect(tileFor(layout, "sensor.kitchen_energy")?.appearance.display).toBeUndefined();
    // A screen whose firmware draws no meter keeps the value.
    expect(tileFor(make({ ...MIDDLE, firmware: "0.55.0" }, things).layout, "sensor.kitchen_co2")?.appearance.display).toBeUndefined();
  });
});
