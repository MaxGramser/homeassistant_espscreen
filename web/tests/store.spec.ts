import { seedLayout, seedTiles, seedPages, seedTitles, appendTiles, screenFixture, documentFixture, current } from "./page-fixtures";
// The store: selecting a screen, editing its layout, what's new, progress, copy and import.
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  addTile, canAlert, copyLayoutFrom, copyText, deviceStyle, fullPage, importLayout, isCompact, layoutJson, liveOf, movePage, moveTileToPage,
  pageReachWarning, pageTilesRepeat, phaseText, removePage, removeTile, retargetPageTile, save, select, setTileOption, state, supports,
  tileLimit, topbarItems, topbarView, updateProgress, whatsNew,
} from "../src/store";
import type { Inventory, Screen } from "../src/types";

const screen = (id: string, name: string, firmware: string, tiles: any[]): Screen => screenFixture({
  id, name, online: true, firmware, board: "guition", layout: { title: name, tiles }, update: { available: true, target: "0.2.62" },
  alert_action: `esphome.${id}_show_alert`,
} as unknown as Screen);

function inventory(): Inventory {
  return {
    csrf: "t", connected: true,
    screens: [
      screen("living", "Living room", "0.2.60", [{ entity: "light.a", name: "", slot: 0 }, { entity: "sensor.t", name: "Temp", slot: 1, options: { display: "graph" } }]),
      screen("kitchen", "Kitchen", "0.2.6", [{ entity: "switch.c", name: "", slot: 0, options: { background: "orange" } }]),
    ],
    entities: [
      { id: "light.a", name: "Lamp A", state: "on", area: "Living room" }, { id: "sensor.t", name: "Temperature", state: "21.5", area: "Living room" },
      { id: "switch.c", name: "Coffee", state: "off", area: "Kitchen" }, { id: "light.b", name: "Lamp B", state: "off", area: "Kitchen" },
    ],
    updates: { target: "0.2.62" },
    // The full inventory carries the changelog next to the screens, not in the update summary (app 0.2.78).
    changelog: [
      { app: "0.2.74", firmware: "0.2.62", lines: ["Full-page tiles.", "Live values."] },
      { app: "0.2.71", firmware: "0.2.60", lines: ["Slider stays put."] },
      { app: "0.2.40", firmware: "0.2.34", lines: ["English."] },
    ],
    alerts: { min_firmware: "0.2.31" },
    controls: { light: { default: "toggle", choices: [{ key: "toggle", label: "On/off" }, { key: "brightness", label: "Brightness" }, { key: "none", label: "None" }] } },
    backgrounds: { auto: { label: "Default" }, orange: { label: "Orange", color: "#ffe1c6" } },
  } as unknown as Inventory;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
  vi.spyOn(window, "confirm").mockReturnValue(true);
  state.inventory = inventory();
  state.selected = null;
  seedLayout(null);
  state.dirty = false;
  state.liveStates = {};
  state.toast = null;
  state.updating = [];
  state.firmwareJob = null;
});

describe("selecting and editing", () => {
  it("gates taller sizes and resizes without taking a neighbor's cells", () => {
    state.inventory.editor_features = { tall_tiles: true };
    select('living');
    const lamp = state.layout!.tiles[0];
    setTileOption(lamp, 'size', 'tall');
    expect(current(lamp).options?.size).toBeUndefined();
    state.inventory.screens[0].tile_sizes = ['single', 'wide', 'full', 'tall', 'square'];
    setTileOption(lamp, 'size', 'tall');
    expect(current(lamp)).toMatchObject({ slot: 0, options: { size: 'tall' } });
    expect(state.layout!.tiles.find((tile) => tile.entity === 'sensor.t')!.slot).toBe(1);
    setTileOption(lamp, 'size', 'square');
    expect(current(lamp)).toMatchObject({ slot: 2, options: { size: 'square' } });
    expect(state.layout!.tiles.find((tile) => tile.entity === 'sensor.t')!.slot).toBe(1);
  });
  it("copies the stored layout so edits never touch the inventory until saved", () => {
    select("living");
    expect(state.layout).not.toBe(state.inventory.screens[0].layout);
    expect(state.layout!.tiles.map((t) => t.slot)).toEqual([0, 1]);
    expect(state.dirty).toBe(false);
    state.layout!.tiles[0].name = "Changed";
    expect(state.inventory.screens[0].layout.tiles[0].name).toBe("");
  });
  it("adds a tile to the first free cell once, within the firmware's limit", () => {
    select("living");
    addTile("light.b");
    expect(state.layout!.tiles.map((t) => t.entity)).toEqual(["light.a", "sensor.t", "light.b"]);
    expect(state.layout!.tiles[2].slot).toBe(2);
    expect(state.dirty).toBe(true);
    addTile("light.b");
    expect(state.layout!.tiles).toHaveLength(3);
    expect(tileLimit.value).toBe(20);
  });
  it("keeps a wide tile at the start of a row and lets a display change fix the controls", () => {
    select("living");
    const sensor = state.layout!.tiles[1];
    setTileOption(sensor, "size", "wide");
    expect(current(sensor).slot).toBe(2);
    expect(state.layout!.tiles.map((t) => t.slot)).toEqual([0, 2]);
    const lamp = state.layout!.tiles[0];
    setTileOption(lamp, "size", "wide");
    setTileOption(lamp, "controls", "brightness");
    setTileOption(lamp, "display", "watch");
    expect(current(lamp).options).toMatchObject({ size: "wide", display: "watch", controls: "none", inline: "none" });
  });
  it("removes a tile and offers to undo", () => {
    select("living");
    removeTile(state.layout!.tiles[0]);
    expect(state.layout!.tiles.map((t) => t.entity)).toEqual(["sensor.t"]);
    expect(state.toast?.action?.label).toBe("Undo");
    state.toast!.action!.run();
    expect(state.layout!.tiles.map((t) => t.entity)).toEqual(["light.a", "sensor.t"]);
  });
  it("shows the clock of the stored setting when there is no top bar yet", () => {
    select("living");
    expect(topbarItems()).toEqual([expect.objectContaining({ type: "clock" })]);
    state.now = new Date(2026, 8, 15, 10, 8).getTime();
    expect(topbarView({ type: "clock" }).text).toBe("10:08");
    expect(topbarView({ type: "date" }).text).toBe("Tu 15 Sep");
    expect(topbarView({ type: "analog" }).analog).toBe(true);
  });
});

describe("live values", () => {
  it("falls back to what the inventory knew", () => {
    expect(liveOf("light.a")).toEqual({ state: "on", word: null, a: {} });
    state.liveStates["light.a"] = { state: "off", word: "Off", a: { brightness: 0 } };
    expect(liveOf("light.a")!.word).toBe("Off");
    expect(liveOf("light.nope")).toBeNull();
  });
});

describe("copy, export and import", () => {
  it("copies a layout with fresh identities and keeps this screen's title", () => {
    select("living");
    copyLayoutFrom("kitchen");
    expect(state.layout!.title).toBe("Living room");
    expect(state.layout!.tiles.map((t) => t.entity)).toEqual(["switch.c"]);
    expect(state.layout!.tiles[0].options).toEqual({ background: "orange" });
    expect(state.dirty).toBe(true);
    expect(JSON.parse(layoutJson())).toMatchObject({ esp_screens_layout: 2, sourceGrid: { columns: 2, rows: 3 },
      layout: { title: "Living room", pages: [{ tiles: [{ content: { kind: "entity", entityId: "switch.c" } }] }] } });
    const source = state.inventory.screens[1].page_document!;
    if (source.format === "pages-v2") expect(state.document!.pages[0].id).not.toBe(source.layout.pages[0].id);
  });
  it("refuses garbage or a rejected import without changing or trimming the draft", async () => {
    select("kitchen"); // firmware 0.2.6: ten tiles
    await importLayout("not json");
    expect(state.toast?.message).toMatch(/isn't JSON/);
    const before = JSON.stringify(state.document);
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: "Invalid layout" }), { status: 400 })));
    await importLayout(JSON.stringify({ hello: 1 }));
    expect(state.toast?.message).toBe("Invalid layout");
    const many = Array.from({ length: 14 }, (_, i) => ({ entity: `light.l${i}`, name: "", slot: i }));
    await importLayout(JSON.stringify({ tiles: [...many, { entity: "light.l0" }, { bogus: true }, { entity: "no-dot" }] }));
    expect(JSON.stringify(state.document)).toBe(before);
  });
  // Home Assistant over plain http has no Clipboard API (GitHub #33): a button that passes no element copies the text
  // itself through a hidden textarea, and leaves nothing behind.
  it("copies text without an element on a page that is no secure context", async () => {
    vi.stubGlobal("isSecureContext", false);
    let copied = "";
    document.execCommand = vi.fn(() => {
      const box = document.activeElement as HTMLTextAreaElement;
      copied = box.value.slice(box.selectionStart, box.selectionEnd);
      return true;
    });
    await copyText("the-key");
    expect(copied).toBe("the-key");
    expect(state.toast?.message).toBe("API key copied.");
    expect(document.querySelector("textarea")).toBeNull();
    vi.unstubAllGlobals();
  });
  it("shows the text in a prompt when even the old way cannot copy", async () => {
    vi.stubGlobal("isSecureContext", false);
    document.execCommand = vi.fn(() => false);
    const prompt = vi.spyOn(window, "prompt").mockReturnValue(null);
    await copyText("the-key");
    expect(prompt).toHaveBeenCalledWith(expect.stringMatching(/selected/), "the-key");
    vi.unstubAllGlobals();
  });
});

describe("updates with content", () => {
  it("lists what a screen gets, and nothing it already has", () => {
    const [living, kitchen] = state.inventory.screens;
    expect(whatsNew(living)).toEqual(["Full-page tiles.", "Live values."]);
    expect(whatsNew(kitchen)).toEqual(["Full-page tiles.", "Live values.", "Slider stays put.", "English."]);
    expect(whatsNew({ ...living, firmware: "0.2.62" })).toEqual([]);
  });
  it("goes by the screen's own target and leaves out a fix for another board (app 0.3.20)", () => {
    const [living] = state.inventory.screens;
    state.inventory.changelog = [
      { app: "0.2.76", firmware: "0.2.64", lines: ["Shared."] },
      { app: "0.2.75", firmware: "0.2.63", boards: ["cyd"], lines: ["CYD fix."] },
      { app: "0.2.74", firmware: "0.2.62", lines: ["Full-page tiles."] },
    ];
    // The Guition is offered 0.2.64: the shared release, not the CYD's own fix in between.
    expect(whatsNew({ ...living, update: { available: true, target: "0.2.64" } })).toEqual(["Shared.", "Full-page tiles."]);
    // A CYD offered only its own fix sees that and what came before, never the newer shared notes.
    expect(whatsNew({ ...living, board: "cyd", update: { available: true, target: "0.2.63" } })).toEqual(["CYD fix.", "Full-page tiles."]);
  });
  it("turns the phase and the ESPHome stage into a progress bar", () => {
    const living = state.inventory.screens[0];
    expect(updateProgress(living)).toBeNull();
    living.update!.state = "running";
    living.update!.phase = "install";
    expect(updateProgress(living)).toEqual({ percent: 12, text: phaseText("install") });
    expect(phaseText("install")).toBe("Building and installing…");
    state.firmwareJob = { job: { stage: "compile" }, logs: [] };
    expect(updateProgress(living)!.percent).toBe(40);
    state.firmwareJob = { job: { stage: "upload" }, logs: [] };
    expect(updateProgress(living)!.percent).toBe(66);
    living.update!.phase = "verify";
    expect(updateProgress(living)!.percent).toBe(78);
    living.update!.phase = "settle";
    expect(updateProgress(living)!.percent).toBe(92);
  });
  it("knows which screen can show an alert", () => {
    const [living, kitchen] = state.inventory.screens;
    expect(canAlert(living)).toBe(true);
    expect(canAlert(kitchen)).toBe(false);
    expect(canAlert(undefined)).toBe(false);
  });
});

describe("full-page and navigation tiles", () => {
  it("moves the other tiles of the page behind a tile that grows to the whole page", () => {
    select("living");
    const [lamp, sensor] = state.layout!.tiles;
    setTileOption(lamp, "size", "full");
    expect(current(lamp).slot).toBe(0);
    expect(current(sensor).slot).toBe(6);
    expect(state.layout!.pages).toBe(2);
    expect(state.toast).toBeNull();
  });
  it("takes the first empty page when the others cannot move, and gives up with a toast when none is free", () => {
    select("living");
    seedTiles(Array.from({ length: 48 }, (_, i) => ({ entity: `light.l${i}`, name: "", slot: i })));
    const first = state.layout!.tiles[0];
    setTileOption(first, "size", "full");
    expect(current(first).options?.size ?? "single").toBe("single");
    expect(state.toast?.message).toMatch(/No page is free/);
  });
  it("lets a navigation tile point at another page, once per page", () => {
    select("living");
    addTile("screen.page_2");
    const nav = state.layout!.tiles.find((t) => t.entity === "screen.page_2")!;
    expect(current(nav).options).toBeUndefined();
    expect(retargetPageTile(nav, 3)).toBe(true);
    expect(current(nav).entity).toBe("screen.page_3");
    addTile("screen.page_4");
    expect(retargetPageTile(nav, 4)).toBe(false);
    expect(state.toast?.message).toMatch(/already has a tile that goes to page 4/);
    expect(retargetPageTile(nav, 9)).toBe(false);
  });
});

describe("the open screen chosen again (app 0.2.78)", () => {
  it("keeps unsaved edits and only brings the layout back into view", () => {
    select("living");
    addTile("light.b");
    state.tab = "settings";
    state.route = "#firmware";
    select("living");
    expect(state.layout!.tiles.map((t) => t.entity)).toEqual(["light.a", "sensor.t", "light.b"]);
    expect(state.dirty).toBe(true);
    expect(state.tab).toBe("layout");
    expect(state.inspector).toBeNull();
    expect(state.route).toBe("");
    expect(window.confirm).not.toHaveBeenCalled();
  });
  it("reads the stored layout again when nothing is unsaved, so a change from Claude or another tab shows up", () => {
    select("living");
    state.inventory.screens[0].layout.tiles.push({ entity: "light.b", name: "", slot: 2 });
    state.inventory.screens[0].page_document = documentFixture(state.inventory.screens[0].layout);
    select("living");
    expect(state.layout!.tiles.map((t) => t.entity)).toEqual(["light.a", "sensor.t", "light.b"]);
    expect(state.dirty).toBe(false);
  });
});

describe("saving while you keep editing (app 0.2.78)", () => {
  // The PUT waits until the test answers it; every other request fails, which the store shrugs off.
  function slowServer() {
    const control = { answer: () => {} };
    const fetchMock = vi.fn((_url: string, init?: RequestInit) => init?.method !== "PUT"
      ? Promise.reject(new Error("offline"))
      : new Promise((resolve) => { control.answer = () => {
        const body = JSON.parse(String(init.body));
        resolve(new Response(JSON.stringify({ saved: true, document: { format: "pages-v2", revision: "saved-revision",
          layout: body.layout, sourceGrid: { columns: 2, rows: 3 }, workspace: { revision: "workspace-revision", positions: {} } } }), { status: 200 }));
      }; }));
    vi.stubGlobal("fetch", fetchMock);
    return { control, fetchMock };
  }
  it("marks the layout saved when nothing changed while the request was on its way", async () => {
    select("living");
    addTile("light.b");
    const { control } = slowServer();
    const saving = save();
    control.answer();
    await saving;
    expect(state.dirty).toBe(false);
    expect(state.saved).toBeGreaterThan(0);
    expect(state.toast?.message).toBe("Saved. Your screen is being updated.");
  });
  it("keeps a change made during the save unsaved and says so", async () => {
    select("living");
    addTile("light.b");
    const { control, fetchMock } = slowServer();
    const saving = save();
    setTileOption(state.layout!.tiles[0], "background", "orange");
    control.answer();
    await saving;
    expect(state.dirty).toBe(true);
    expect(state.saved).toBe(0);
    expect(state.toast?.message).toBe("Saved. Your newest change isn't sent yet: press Save & send again.");
    // What went out is the layout from before that change.
    const body = JSON.parse((fetchMock.mock.calls[0] as any[])[1].body);
    expect(body.layout.pages[0].tiles.map((t: any) => t.content.entityId)).toEqual(["light.a", "sensor.t", "light.b"]);
    expect(body.layout.pages[0].tiles[0].appearance.background).toBeUndefined();
  });
  it("leaves the unsaved flag of a screen opened meanwhile alone", async () => {
    select("living");
    addTile("light.b");
    const { control } = slowServer();
    const saving = save();
    select("kitchen");
    addTile("light.b");
    control.answer();
    await saving;
    expect(state.selected).toBe("kitchen");
    expect(state.dirty).toBe(true);
    expect(state.toast?.message).toBe("Saved. Living room is being updated.");
  });
});

describe("moving a tile to another page without dragging (app 0.2.78)", () => {
  it("takes the first free cell of that page, or a new page after the last one", () => {
    select("living");
    const [lamp, sensor] = state.layout!.tiles;
    seedPages(2);
    expect(moveTileToPage(sensor, 1)).toBe(true);
    expect(current(sensor).slot).toBe(6);
    expect(moveTileToPage(lamp, 1)).toBe(true);
    expect(current(lamp).slot).toBe(7);
    expect(moveTileToPage(lamp, 2)).toBe(true);
    expect(current(lamp).slot).toBe(12);
    expect(state.layout!.pages).toBe(3);
    expect(state.dirty).toBe(true);
    expect(moveTileToPage(lamp, 2)).toBe(false);
    expect(moveTileToPage(lamp, 8)).toBe(false);
  });
  it("swaps with the first tile of a full page, as a drop there does", () => {
    select("living");
    seedTiles([
      ...Array.from({ length: 6 }, (_, i) => ({ entity: `light.l${i}`, name: "", slot: i })),
      { entity: "light.b", name: "", slot: 6 },
    ]);
    const b = state.layout!.tiles[6];
    expect(moveTileToPage(b, 0)).toBe(true);
    expect(current(b).slot).toBe(0);
    expect(state.layout!.tiles.find((t) => t.entity === "light.l0")!.slot).toBe(6);
  });
  it("moves a full-page tile to a page of its own and says so when a tile finds no room", () => {
    select("living");
    seedTiles([
      { entity: "light.big", name: "", slot: 0, options: { size: "full" } },
      { entity: "light.w", name: "", slot: 6, options: { size: "wide" } },
      ...[8, 9, 10, 11].map((slot) => ({ entity: `light.p${slot}`, name: "", slot })),
      ...Array.from({ length: 36 }, (_, i) => ({ entity: `light.l${i}`, name: "", slot: 12 + i })),
    ]);
    const [big, wide] = state.layout!.tiles;
    // Page 1 holds the full-page tile and every other page is taken: the wide tile would have to push it off.
    expect(moveTileToPage(wide, 0)).toBe(false);
    expect(current(wide).slot).toBe(6);
    expect(state.toast?.message).toBe("There is no room for this tile on page 1.");
    // The full-page tile and the tiles of page 2 change places.
    expect(moveTileToPage(big, 1)).toBe(true);
    expect(current(big).slot).toBe(6);
    expect(state.layout!.tiles.filter((t) => t.slot < 6).map((t) => t.entity).sort()).toEqual(["light.p10", "light.p11", "light.p8", "light.p9", "light.w"]);
  });
});

describe("what the add-on says about a screen's firmware (app 0.2.78)", () => {
  it("takes the tile limit and the features from the screen entry", async () => {
    const living = state.inventory.screens[0];
    Object.assign(living, { firmware: "unknown", firmware_known: null, tile_limit: 48, full_page: true, page_tiles_repeat: true });
    select("living");
    expect(tileLimit.value).toBe(48);
    expect(fullPage.value).toBe(true);
    expect(pageTilesRepeat.value).toBe(true);
    // A version Home Assistant can't report right now no longer cuts a copied or imported layout to ten.
    const many = Array.from({ length: 30 }, (_, i) => ({ entity: `light.l${i}`, name: "", slot: i }));
    const imported = documentFixture({ title: "Imported", tiles: many });
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(imported), { status: 200 })));
    await importLayout(JSON.stringify({ tiles: many }));
    expect(state.layout!.tiles).toHaveLength(30);
    expect(state.toast?.message).toBe("Layout imported. Save & send when it looks right.");
  });
  it("goes by firmware_known for the version and the notes", () => {
    const living = state.inventory.screens[0];
    Object.assign(living, { firmware: "unknown", firmware_known: "0.2.60" });
    select("living");
    expect(supports(0, 2, 60)).toBe(true);
    expect(supports(0, 2, 61)).toBe(false);
    expect(whatsNew(living)).toEqual(["Full-page tiles.", "Live values."]);
    expect(canAlert(living)).toBe(true);
    Object.assign(living, { firmware: "0.2.63", firmware_known: null });
    expect(supports(0, 2, 31)).toBe(false);
    expect(canAlert(living)).toBe(false);
  });
  it("keeps today's rule, with a strict X.Y.Z, for a screen entry without the fields", () => {
    select("living");
    expect(tileLimit.value).toBe(20);
    expect(fullPage.value).toBe(false);
    expect(pageTilesRepeat.value).toBe(false);
    state.inventory.screens[0].firmware = "0.2.65";
    expect(tileLimit.value).toBe(48);
    expect(fullPage.value).toBe(true);
    expect(pageTilesRepeat.value).toBe(true);
    state.inventory.screens[0].firmware = "0.2.65 (ESPHome 2026.6.2)";
    expect(tileLimit.value).toBe(10);
    expect(fullPage.value).toBe(false);
    state.inventory.screens[0].firmware = "unknown";
    expect(tileLimit.value).toBe(10);
  });
});

describe("the changelog from the full inventory (app 0.2.78)", () => {
  it("reads the notes next to the screens and ignores an update summary that still has them", () => {
    const living = state.inventory.screens[0];
    state.inventory.updates = { target: "0.2.62", changelog: [{ app: "0.2.1", firmware: "0.2.62", lines: ["Old place."] }] } as any;
    expect(whatsNew(living)).toEqual(["Full-page tiles.", "Live values."]);
  });
  it("shows nothing without a changelog", () => {
    delete state.inventory.changelog;
    expect(whatsNew(state.inventory.screens[1])).toEqual([]);
  });
});

describe("several tiles that go to the same page (firmware 0.2.65)", () => {
  it("adds, retargets and imports another copy when the screen takes them", async () => {
    Object.assign(state.inventory.screens[0], { firmware: "0.2.65", page_tiles_repeat: true });
    select("living");
    addTile("screen.page_1");
    addTile("screen.page_1");
    expect(state.layout!.tiles.filter((t) => t.entity === "screen.page_1")).toHaveLength(2);
    addTile("screen.page_2");
    const nav = state.layout!.tiles.find((t) => t.entity === "screen.page_2")!;
    expect(retargetPageTile(nav, 1)).toBe(true);
    expect(state.layout!.tiles.filter((t) => t.entity === "screen.page_1")).toHaveLength(3);
    // Only a navigation tile repeats; any other entity still appears once.
    addTile("light.a");
    expect(state.layout!.tiles.filter((t) => t.entity === "light.a")).toHaveLength(1);
    const imported = documentFixture({ title: "Imported", tiles: [
      { entity: "screen.page_1", name: "", slot: 0 }, { entity: "light.a", name: "", slot: 1 }, { entity: "screen.page_1", name: "", slot: 6 },
    ] });
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(imported), { status: 200 })));
    await importLayout(JSON.stringify({ esp_screens_layout: 2, layout: imported.layout, sourceGrid: imported.sourceGrid }));
    expect(state.layout!.tiles.map((t) => t.entity)).toEqual(["screen.page_1", "light.a", "screen.page_1"]);
  });
  it("keeps one tile per page when the screen doesn't", () => {
    Object.assign(state.inventory.screens[0], { firmware: "0.2.65", page_tiles_repeat: false });
    select("living");
    addTile("screen.page_1");
    addTile("screen.page_1");
    expect(state.layout!.tiles.filter((t) => t.entity === "screen.page_1")).toHaveLength(1);
    addTile("screen.page_2");
    expect(retargetPageTile(state.layout!.tiles.find((t) => t.entity === "screen.page_2")!, 1)).toBe(false);
    expect(state.toast?.message).toMatch(/already has a tile that goes to page 1/);
  });
  it("starts the empty page after the last one when a tile goes there", () => {
    select("living");
    addTile("screen.page_1");
    const nav = state.layout!.tiles.find((t) => t.entity === "screen.page_1")!;
    expect(state.layout!.pages).toBe(1);
    expect(retargetPageTile(nav, 1)).toBe(false);
    expect(retargetPageTile(nav, 2)).toBe(true);
    expect(state.layout!.pages).toBe(2);
    expect(state.dirty).toBe(true);
  });
});

describe("page buttons and swiping both off (firmware 0.2.69)", () => {
  const settings = (values: Record<string, unknown>) =>
    Object.assign(state.inventory.screens[0], { settings: { owner: "screen", values, keys: Object.keys(values), unavailable: [] } });
  const tiles = (list: [string, number][]) => { seedTiles(list.map(([entity, slot]) => ({ entity, name: "", slot, options: {} }))); seedPages(1); };
  it("says which pages the Go to page tiles lead to, and which one they leave out", () => {
    settings({ page_buttons: false, swipe_pages: false });
    select("living");
    tiles([["screen.page_2", 0], ["screen.page_3", 1], ["screen.page_1", 6], ["screen.page_1", 12], ["light.a", 18]]);
    expect(pageReachWarning()).toBe("From Home there is no route to page 4. Add a navigation tile or include the page in page navigation.");
    tiles([["light.a", 0], ["light.b", 6], ["switch.c", 12]]);
    expect(pageReachWarning()).toBe("From Home there is no route to pages 2 and 3. Add a navigation tile or include the page in page navigation.");
    tiles([["screen.page_2", 0], ["light.a", 6]]);
    expect(pageReachWarning()).toBe("From page 2 there is no route back to Home. Add a return tile or enable the Home control.");
  });
  it("stays quiet while either way of paging is on, the values are unknown, or every page can be reached and left", () => {
    select("living");
    tiles([["light.a", 0], ["light.b", 6]]);
    for (const values of [{ page_buttons: true, swipe_pages: false }, { page_buttons: false, swipe_pages: true }, { page_buttons: null, swipe_pages: false }, {}]) {
      settings(values);
      expect(pageReachWarning()).toBe("");
    }
    settings({ page_buttons: false, swipe_pages: false });
    tiles([["screen.page_2", 0], ["screen.page_1", 6]]);
    expect(pageReachWarning()).toBe("");
    tiles([["light.a", 0]]);
    expect(pageReachWarning()).toBe("");
  });
});

// A screen standing up (app 0.2.107): the add-on sends the canvas and the grid it was built with, and the editor
// only draws them. Every mockup has the same shorter side, so a page of a screen standing up is as wide as one
// lying down and taller, the way the glass is (app 0.2.108; drawn the same height it came out smaller than a
// square screen with less glass).
describe("the mockup of a screen, whichever way it hangs", () => {
  const shaped = (shape: Record<string, unknown>) => {
    state.inventory.screens[0] = screenFixture({ ...state.inventory.screens[0], shape, layout: { title: 'Screen', tiles: [] } } as any);
    select("living");
  };
  const px = (style: Record<string, string>) => Number(style["--mockup-width"].replace("px", ""));
  const height = (style: Record<string, string>) => {
    const [width, tall] = style["--screen-aspect"].split(" / ").map(Number);
    return (px(style) * tall) / width;
  };
  const shorter = (style: Record<string, string>) => Math.min(px(style), height(style));
  it("draws every screen with the same shorter side, standing up as well as lying down", () => {
    for (const shape of [{ width: 800, height: 480, columns: 3, rows: 3, look: "standard" },
                         { width: 480, height: 480, columns: 2, rows: 3, look: "standard" },
                         { width: 480, height: 800, columns: 1, rows: 4, look: "standard" },
                         { width: 240, height: 320, columns: 1, rows: 4, look: "compact" },
                         { width: 800, height: 1280, columns: 4, rows: 5, look: "standard" }]) {
      shaped(shape);
      expect(Math.round(shorter(deviceStyle.value))).toBe(300);
    }
  });
  it("gives a page the screen's own proportions and its own cells", () => {
    shaped({ width: 480, height: 800, columns: 1, rows: 4, look: "standard" });
    expect(deviceStyle.value).toEqual({
      "--screen-aspect": "480 / 800", "--screen-columns": "1", "--screen-rows": "4",
      // One column: a wide tile is that one cell, not two.
      "--screen-wide-span": "1", "--mockup-width": "300px",
    });
    expect(height(deviceStyle.value)).toBe(500);
    shaped({ width: 800, height: 480, columns: 3, rows: 3, look: "standard" });
    expect(px(deviceStyle.value)).toBe(500);
    expect(deviceStyle.value["--screen-wide-span"]).toBe("2");
    // Glass wider than the cap is drawn shorter rather than wider, so a page still fits beside its neighbour.
    shaped({ width: 1920, height: 480, columns: 4, rows: 2, look: "standard" });
    expect(px(deviceStyle.value)).toBe(560);
  });
  it("keeps a board's look when it is built standing up", () => {
    // The board says which look it is, and that is what counts. Without it the shorter side decides, because the
    // width alone would read a 480 x 800 standard screen as a compact one.
    shaped({ width: 480, height: 800, columns: 1, rows: 4, look: "standard" });
    expect(isCompact.value).toBe(false);
    shaped({ width: 480, height: 800, columns: 1, rows: 4 });
    expect(isCompact.value).toBe(false);
    shaped({ width: 240, height: 320, columns: 1, rows: 4 });
    expect(isCompact.value).toBe(true);
    shaped({ width: 320, height: 240, columns: 2, rows: 3 });
    expect(isCompact.value).toBe(true);
  });
});

// A page moves as a whole (app 0.2.121, GitHub #24): everything that belongs to it goes along.
describe("moving a whole page", () => {
  // Three pages: page 1 leads to the other two, page 2 has a title of its own, page 3 leads back.
  function threePages() {
    select("living");
    seedTiles([
      { entity: "screen.page_2", name: "", slot: 0 }, { entity: "screen.page_3", name: "", slot: 1 },
      { entity: "light.a", name: "", slot: 6 }, { entity: "light.w", name: "", slot: 8, options: { size: "wide" } },
      { entity: "screen.page_1", name: "", slot: 12 },
    ]);
    seedPages(3);
    seedTitles(["", "Kitchen"]);
    state.dirty = false;
  }
  it("takes the tiles on their own cells, the page's own title, and the tiles that lead to it", () => {
    threePages();
    expect(movePage(1, 2)).toBe(true);
    const by = Object.fromEntries(state.layout!.tiles.map((t) => [t.entity, t.slot]));
    // Page 2 and page 3 changed places: the cells within a page stay as they were.
    expect(by["light.a"]).toBe(12);
    expect(by["light.w"]).toBe(14);
    expect(by["screen.page_1"]).toBe(6);
    // The tiles on page 1 still lead to the same two pages, by their new numbers: the one that led to the kitchen
    // page says page 3 now, the one that led to the last page says page 2.
    expect(state.layout!.tiles.find((t) => t.slot === 0)!.entity).toBe("screen.page_3");
    expect(state.layout!.tiles.find((t) => t.slot === 1)!.entity).toBe("screen.page_2");
    // The title went with the kitchen page.
    expect(state.layout!.page_titles).toEqual(["", "", "Kitchen"]);
    expect(state.layout!.tiles.map((t) => t.slot)).toEqual([0, 1, 6, 12, 14]);
    expect(state.dirty).toBe(true);
  });
  it("keeps a page's own title when it lands first, and says nothing about it", () => {
    threePages();
    const title = state.layout!.title;
    expect(movePage(1, 0)).toBe(true);
    // The kitchen page stands first now and still says Kitchen; the screen's own title is untouched (app 0.2.123).
    expect(state.layout!.page_titles).toEqual(["Kitchen"]);
    expect(state.layout!.title).toBe(title);
    expect(state.layout!.tiles.find((t) => t.entity === "light.a")!.slot).toBe(0);
    expect(state.toast).toBeNull();
  });
  it("leaves a move outside the row alone, and says nothing when no title is at stake", () => {
    threePages();
    expect(movePage(0, 3)).toBe(false);
    expect(movePage(2, 2)).toBe(false);
    expect(movePage(-1, 0)).toBe(false);
    expect(state.dirty).toBe(false);
    expect(movePage(2, 0)).toBe(true);
    expect(state.toast).toBeNull();
    expect(state.layout!.page_titles).toEqual(["", "", "Kitchen"]);
  });
  it("takes the pages after a removed one up with their titles and the tiles that lead to them", () => {
    select("living");
    seedTiles([{ entity: "screen.page_3", name: "", slot: 0 }, { entity: "light.a", name: "", slot: 12 }]);
    seedPages(3);
    seedTitles(["", "Kitchen", "Bedroom"]);
    // Page 2 is empty, so it can go; page 3 becomes page 2, with its title and the tile that leads to it.
    removePage(1);
    expect(state.layout!.tiles.find((t) => t.entity === "light.a")!.slot).toBe(6);
    expect(state.layout!.tiles.find((t) => t.slot === 0)!.entity).toBe("screen.page_2");
    expect(state.layout!.page_titles).toEqual(["", "Bedroom"]);
    expect(state.layout!.pages).toBe(2);
  });
  // A page leaves whether it is empty or not (app 0.2.123): what was only its own goes with it, and Undo is there.
  it("takes the tiles on a removed page and the tiles that led to it, and hands them all back", () => {
    threePages();
    removePage(1);
    // The kitchen page is gone with the tile in its cell, and so is the tile on page 1 that opened it.
    // The tile that led to page 3 keeps its own cell and now says page 2; the tile beside it went with the page.
    expect(state.layout!.tiles.map((t) => [t.entity, t.slot])).toEqual([["screen.page_2", 1], ["screen.page_1", 6]]);
    expect(state.layout!.page_titles).toBeUndefined();
    expect(state.layout!.pages).toBe(2);
    expect(state.toast?.message).toBe("Page 2 and 3 tiles are gone.");
    state.toast!.action!.run();
    // Back exactly as it stood: the same tiles, in their cells, opening the pages they opened.
    expect(state.layout!.tiles.map((t) => [t.entity, t.slot])).toEqual([
      ["screen.page_2", 0], ["screen.page_3", 1], ["light.a", 6], ["light.w", 8], ["screen.page_1", 12]]);
    expect(state.layout!.page_titles).toEqual(["", "Kitchen"]);
    expect(state.layout!.pages).toBe(3);
  });
  it("says a page went without tiles, and never takes the only page", () => {
    threePages();
    seedTiles([{ entity: "light.a", name: "", slot: 0 }]);
    seedPages(2);
    removePage(1);
    expect(state.toast?.message).toBe("Page 2 is gone.");
    expect(state.layout!.pages).toBe(1);
    state.toast = null;
    removePage(0);
    expect(state.layout!.pages).toBe(1);
    expect(state.toast).toBeNull();
  });
});
