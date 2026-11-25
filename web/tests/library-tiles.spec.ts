// The library's Tiles view (editor/library-tiles.ts): an entity as the tiles it can be on this screen, at up to three
// sizes, each as rich as the screen draws it there, and only what the add-on saves.
import { beforeEach, describe, expect, it, vi } from "vitest";
import { screenFixture } from "./helpers/fixtures";
import { samplesOf } from "../src/editor/library-tiles";
import { addTile } from "../src/editor/tiles";
import { optionsSave } from "../src/model/tile-options";
import { useDocumentStore } from "../src/stores/document";
import { useInventoryStore } from "../src/stores/inventory";
import { useScreenStore } from "../src/stores/screen";
import { useSessionStore } from "../src/stores/session";

const choices = (keys: string[]) => keys.map((key) => ({ key, label: key }));
const CONTROLS = {
  cover: { default: "buttons", choices: choices(["buttons", "position", "tilt", "buttons_tilt", "position_tilt", "none"]) },
  climate: { default: "setpoint", choices: choices(["setpoint", "mode", "setpoint_mode", "none"]) },
};
function screen(sizes = ["single", "wide", "full", "tall", "square"]) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ states: {}, previews: [], capabilities: {} }))));
  useScreenStore().selected = null;
  useInventoryStore().inventory = { screens: [screenFixture({ id: "test", name: "Test", firmware: "0.56.0", online: true, tile_sizes: sizes,
    layout: { title: "Home", tiles: [] } })], entities: [], editor_features: { tall_tiles: true }, controls: CONTROLS };
  useSessionStore().select("test");
}

describe("the tiles the library offers", () => {
  beforeEach(() => screen());

  it("shows one cell, a row of two and two rows of two, each with the richest controls that fit", () => {
    const samples = samplesOf("cover.blind");
    expect(samples.map((s) => [s.size, s.columns, s.rows])).toEqual([["single", 1, 1], ["wide", 2, 1], ["square", 2, 2]]);
    expect(samples[0].tile.options?.size).toBeUndefined();
    expect(samples[2].tile.options).toMatchObject({ size: "square", controls: "position_tilt" });
    expect(samples[2].controls).toBe("position_tilt");
  });

  it("gives a thermostat of two rows its temperature with its modes", () => {
    expect(samplesOf("climate.living").at(-1)?.tile.options?.controls).toBe("setpoint_mode");
  });

  it("offers only tiles the add-on saves", () => {
    for (const id of ["cover.blind", "climate.living", "light.hall", "sensor.power", "media_player.kitchen", "switch.fan"])
      for (const sample of samplesOf(id)) expect(optionsSave(sample.tile, sample.tile.options ?? {})).toBe(true);
  });

  it("shows a sensor's curve from two cells up (catalogue showcase)", () => {
    const [one, wide] = samplesOf("sensor.power");
    expect(one.tile.options?.display).not.toBe("graph");
    expect(wide.tile.options?.display).toBe("graph");
  });

  it("leaves out a size the screen does not take", () => {
    screen(["single", "wide", "full"]);
    expect(samplesOf("cover.blind").map((s) => s.size)).toEqual(["single", "wide"]);
  });

  it("puts the very tile it showed on the page", async () => {
    const square = samplesOf("climate.living").at(-1)!;
    await addTile("climate.living", square.tile);
    expect(useDocumentStore().layout?.tiles.find((tile) => tile.entity === "climate.living")?.options).toMatchObject({ size: "square", controls: "setpoint_mode" });
  });
});
