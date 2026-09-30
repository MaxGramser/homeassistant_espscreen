import { appendTiles, current, seedLayout } from "./page-fixtures";
// Every choice the tile panel shows is one the add-on saves (app 0.4.0, GitHub #47). A reporter found two that never
// could: Automatic for the second line once another was chosen ("Tile options need normalization"), and Perform action
// ("Invalid or unsupported page configuration fields"). The walk below clicks every choice of every field for tiles of
// many kinds and sizes, so an option added later that the add-on refuses fails here, not on someone's screen.
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ActionPicker from "../src/components/ActionPicker.vue";
import TileInspector from "../src/components/TileInspector.vue";
import { canonicalOptions, choiceOffered } from "../src/model/tile-options";
import { validatePages } from "../src/model/pages";
import { isSelected, openTile, state } from "../src/store";
import type { Inventory, Tile } from "../src/types";

function inventory(): Inventory {
  return {
    csrf: "t", connected: true,
    screens: [{ id: "living", name: "Living room", online: true, firmware: "0.4.0", board: "guition", tile_sizes: ["tall", "square"],
      shape: { width: 480, height: 480, columns: 2, rows: 3 }, layout: { title: "Living room", tiles: [] } } as any],
    entities: [
      { id: "light.a", name: "Lamp", state: "on", area: "" }, { id: "sensor.t", name: "Temperature", state: "21", area: "" },
      { id: "camera.door", name: "Door", state: "idle", area: "" }, { id: "weather.home", name: "Home", state: "sunny", area: "" },
      { id: "cover.c", name: "Blind", state: "open", area: "" }, { id: "media_player.m", name: "Speaker", state: "playing", area: "" },
      { id: "climate.c", name: "Heating", state: "heat", area: "" }, { id: "scene.s", name: "Evening", state: "", area: "" },
      { id: "switch.s", name: "Fan", state: "off", area: "" }, { id: "number.n", name: "Volume", state: "3", area: "" },
      { id: "automation.a", name: "Curtains at sunset", state: "on", area: "" },
    ],
    builtin: [],
    icons: { groups: [], weather: { partlycloudy: "F0595", sunny: "F0599" }, sun: { below_horizon: "F0594" }, defaults: {}, fallback: "F0335", builtin: {}, controls: {} },
    backgrounds: { auto: { label: "Default" } },
    controls: Object.fromEntries(Object.entries({ light: ["toggle", "brightness"], cover: ["buttons", "position"], media_player: ["volume", "playback"],
      climate: ["setpoint", "mode", "setpoint_mode"], switch: ["toggle"], scene: ["run"], number: ["stepper", "slider"], automation: ["toggle", "run"] })
      .map(([domain, keys]) => [domain, { default: keys[0], choices: [...keys, "none"].map((key) => ({ key, label: key })) }])),
  } as unknown as Inventory;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
  state.inventory = inventory();
  state.selected = "living";
  state.documentGrid = { columns: 2, rows: 3 };
  seedLayout({ title: "Living room", tiles: [] });
  state.subtitleValues = {};
  state.entityActions = {};
  state.toast = null;
  state.selectedTile = null; state.inspector = null; state.actionPickerOpen = false;
});

describe("the canonical options (tile-options.ts)", () => {
  it("drops what the add-on would change", () => {
    expect(canonicalOptions("light.a", { sub: "auto" })).toEqual({});
    expect(canonicalOptions("light.a", { sub: "text:  hi " })).toEqual({ sub: "text:hi" });
    expect(canonicalOptions("light.a", { sub: "text: " })).toEqual({ sub: "none" });
    expect(canonicalOptions("light.a", { tap: "auto", action: { action: "light.turn_on" } })).toEqual({ tap: "auto" });
    expect(canonicalOptions("camera.door", { display: "standard", refresh: 5, fit: "contain" })).toEqual({ display: "standard" });
    expect(canonicalOptions("camera.door", { display: "live", fit: "fill", overlay: "name" })).toEqual({ display: "live" });
    expect(canonicalOptions("screen.page_2", { display: "watch", controls: "none", icon: "auto" })).toEqual({ icon: "auto" });
    expect(canonicalOptions("weather.home", { display: "forecast" })).toEqual({ display: "forecast", size: "wide" });
  });

  it("offers Automatic after another second line, and Perform action", () => {
    const tile: Tile = { id: "a", entity: "light.a", name: "", slot: 0, options: { sub: "none" } };
    expect(choiceOffered(tile, "sub", "auto", true)).toBe(true);
    expect(choiceOffered(tile, "tap", "action", true)).toBe(true);
    // A built-in card has no action to perform, and nothing to toggle.
    const clock: Tile = { id: "c", entity: "screen.clock", name: "", slot: 0 };
    expect(choiceOffered(clock, "tap", "action", false)).toBe(false);
    expect(choiceOffered(clock, "tap", "toggle", false)).toBe(false);
    // A watch face has no mini slider: choosing the slider brings the standard face with it, so it is offered.
    expect(choiceOffered({ ...tile, options: { display: "watch" } }, "inline", "slider", true)).toBe(true);
    // A forecast needs a double-width card; a single card is not offered.
    expect(choiceOffered({ id: "w", entity: "weather.home", name: "", slot: 0, options: { display: "forecast", size: "wide" } }, "size", "single", false)).toBe(false);
  });
});

describe("the tile panel", () => {
  it("stores Automatic again after Nothing (GitHub #47)", async () => {
    const tile: Tile = { entity: "light.a", name: "", slot: 0, options: { sub: "none" } };
    appendTiles(tile);
    const panel = mount(TileInspector, { props: { tile: current(tile)! } });
    const automatic = panel.findAll("button").find((b) => b.text() === "Automatic")!;
    await automatic.trigger("click");
    expect(state.toast).toBeNull();
    expect(current(tile)!.options?.sub).toBeUndefined();
    expect(state.dirty).toBe(true);
  });

  it("stores Perform action once an action is chosen, and keeps it (GitHub #47)", async () => {
    state.entityActions["light.a"] = [{ action: "light.turn_on", name: "Turn on", description: "", fields: [
      { key: "brightness_pct", name: "Brightness", required: false, selector: { number: { min: 0, max: 100 } } },
    ] }] as any;
    const tile: Tile = { entity: "light.a", name: "", slot: 0 };
    appendTiles(tile);
    const panel = mount(TileInspector, { props: { tile: current(tile)! } });
    const perform = panel.findAll("button").find((b) => b.text() === "Perform action")!;
    await perform.trigger("click");
    // The choice waits for its action: nothing is stored yet, and nothing fails.
    expect(state.toast).toBeNull();
    expect(current(tile)!.options?.tap).toBeUndefined();
    expect(perform.attributes("aria-pressed")).toBe("true");
    const picker = panel.findComponent(ActionPicker);
    expect(picker.exists()).toBe(true);
    await picker.find(".action-choice").trigger("click");
    expect(state.toast).toBeNull();
    expect(current(tile)!.options?.tap).toBe("action");
    expect(current(tile)!.options?.action).toEqual({ action: "light.turn_on" });
    // A field of the action goes into the document too.
    await panel.setProps({ tile: current(tile)! });
    const field = panel.find('input[type="number"]');
    await field.setValue("40");
    expect(current(tile)!.options?.action).toEqual({ action: "light.turn_on", data: { brightness_pct: 40 } });
    // Another tap choice leaves no action behind.
    await panel.setProps({ tile: current(tile)! });
    await panel.findAll("button").find((b) => b.text() === "Open control")!.trigger("click");
    expect(current(tile)!.options?.tap).toBe("detail");
    expect(current(tile)!.options?.action).toBeUndefined();
  });

  it("offers an automation On / off or Run automation actions, and says what holding it does (GitHub #62)", async () => {
    const tile: Tile = { entity: "automation.a", name: "", slot: 0 };
    appendTiles(tile);
    state.inventory.screens[0].firmware = "0.7.0";
    let panel = mount(TileInspector, { props: { tile: current(tile)! } });
    const tap = () => panel.findAll(".f").find((f) => f.text().startsWith("On tap"))!;
    expect(tap().findAll(".seg button").map((b) => b.text())).toEqual(["On / off", "Run automation actions", "View only", "Perform action"]);
    expect(tap().find(".seg button[aria-pressed='true']").text()).toBe("On / off");
    await tap().findAll(".seg button").find((b) => b.text() === "Run automation actions")!.trigger("click");
    expect(state.toast).toBeNull();
    expect(current(tile)!.options?.tap).toBe("run");
    expect(() => validatePages(state.document!, state.documentGrid!)).not.toThrow();
    panel.unmount();
    panel = mount(TileInspector, { props: { tile: current(tile)! } });
    expect(tap().find(".seg button[aria-pressed='true']").text()).toBe("Run automation actions");
    expect(panel.find(".warn").exists()).toBe(false);
    // Older firmware refuses the domain: the panel says so before a save would.
    state.inventory.screens[0].firmware = "0.6.0";
    panel.unmount();
    panel = mount(TileInspector, { props: { tile: current(tile)! } });
    expect(tap().find(".warn").text()).toContain("0.7.0");
  });

  it("shows a bedside clock and its keys only what they save: no second line (GitHub #93)", async () => {
    const clock: Tile = { entity: "screen.nightstand", name: "", slot: 0, options: { size: "full" } };
    const key: Tile = { entity: "light.a", name: "Bed", slot: -1, in: "screen.nightstand", key: 0 };
    appendTiles(clock, key);
    for (const tile of [clock, key]) {
      const panel = mount(TileInspector, { props: { tile: current(tile)! } });
      expect(panel.text(), tile.entity).not.toContain("Second line");
      // Firmware 0.4.0 draws every key's name: the switch that hides it waits for 0.17.0.
      expect(panel.find(".key-name-choice").exists()).toBe(false);
      expect(panel.find("#tile-name").exists()).toBe(true);
      for (const button of panel.findAll(".seg button")) {
        if (button.attributes("disabled") !== undefined) continue;
        state.toast = null;
        await button.trigger("click");
        expect(state.toast, `${tile.entity}: "${button.text()}"`).toBeNull();
        expect(() => validatePages(state.document!, state.documentGrid!)).not.toThrow();
      }
      panel.unmount();
    }
  });

  it("hides a key's name from firmware 0.17.0, and saves it", async () => {
    const clock: Tile = { entity: "screen.nightstand", name: "", slot: 0, options: { size: "full" } };
    const key: Tile = { entity: "light.a", name: "Bed", slot: -1, in: "screen.nightstand", key: 0 };
    appendTiles(clock, key);
    state.inventory.screens[0].firmware = "0.17.0";
    const panel = mount(TileInspector, { props: { tile: current(key)! } });
    const choice = panel.find(".key-name-choice");
    expect(choice.exists()).toBe(true);
    openTile(current(key)!);
    const id = current(key)!.id;
    await choice.find("[role=switch]").trigger("click");
    expect(current(key)!.options?.overlay).toBe("none");
    // The key stays open in the panel: the same tile, still chosen.
    expect(current(key)!.id).toBe(id);
    expect(state.inspector?.kind).toBe("tile");
    expect(isSelected(current(key)!)).toBe(true);
    expect(() => validatePages(state.document!, state.documentGrid!)).not.toThrow();
    const child = state.document!.pages.flatMap((page) => page.tiles).flatMap((tile) => tile.children || [])[0];
    expect(child.appearance).toEqual({ label: "Bed", overlay: "none" });
    panel.unmount();
  });

  const kinds: Tile[] = [
    { entity: "light.a", name: "", slot: 0 }, { entity: "light.a", name: "", slot: 0, options: { size: "wide" } },
    { entity: "light.a", name: "", slot: 0, options: { size: "tall" } }, { entity: "sensor.t", name: "", slot: 0 },
    { entity: "camera.door", name: "", slot: 0, options: { display: "live" } }, { entity: "weather.home", name: "", slot: 0, options: { size: "wide" } },
    { entity: "cover.c", name: "", slot: 0, options: { size: "square" } }, { entity: "media_player.m", name: "", slot: 0, options: { size: "wide" } },
    { entity: "climate.c", name: "", slot: 0, options: { size: "tall" } }, { entity: "scene.s", name: "", slot: 0 },
    { entity: "switch.s", name: "", slot: 0, options: { size: "wide" } }, { entity: "number.n", name: "", slot: 0 },
    { entity: "screen.clock", name: "", slot: 0, options: { size: "wide" } }, { entity: "screen.settings", name: "", slot: 0 },
    { entity: "screen.page_2", name: "", slot: 0 }, { entity: "automation.a", name: "", slot: 0 },
    { entity: "automation.a", name: "", slot: 0, options: { size: "wide", tap: "run" } },
  ];
  it.each(kinds.map((tile) => [`${tile.entity} ${tile.options?.size || "single"}`, tile] as const))("saves every choice it shows: %s", async (_, kind) => {
    const tile: Tile = JSON.parse(JSON.stringify(kind));
    appendTiles(tile);
    const fields = () => mount(TileInspector, { props: { tile: current(tile)! } }).findAll(".f");
    const count = fields().length;
    for (let f = 0; f < count; f++) {
      const labels = fields()[f]?.findAll(".seg button").map((b) => b.text()) || [];
      for (const label of labels) {
        const panel = mount(TileInspector, { props: { tile: current(tile)! } });
        const button = panel.findAll(".f")[f]?.findAll(".seg button").find((b) => b.text() === label);
        if (!button || button.attributes("disabled") !== undefined) continue;
        state.toast = null;
        await button.trigger("click");
        await nextTick();
        expect(state.toast, `${tile.entity}: "${label}"`).toBeNull();
        expect(() => validatePages(state.document!, state.documentGrid!)).not.toThrow();
        panel.unmount();
      }
    }
  });
});
