// Which face a card on the mockup takes and the controls it draws (model/tile-face.ts), as the screens decide them.
import { describe, expect, it } from "vitest";
import { resolveControls } from "../src/model/catalogue";
import { displayOf, drawnControls, tileFace, type FaceInput } from "../src/model/tile-face";
import type { TileOptions } from "../src/types";

// A card as TileCard asks for its face: on a grid of two columns, a firmware with big keys and ranges.
function face(entity: string, size: [number, number] | "full" = [1, 1], options: TileOptions = {}, more: Partial<FaceInput> = {}) {
  const shape = size === "full" ? { columns: 2, rows: 3 } : { columns: size[0], rows: size[1] };
  const named = size === "full" ? "full" : size[0] === 2 && size[1] === 2 ? "square" : size[0] === 2 ? "wide" : size[1] === 2 ? "tall" : "single";
  const tileOptions = { ...options, ...(named !== "single" ? { size: named } : {}) };
  return tileFace({ entity, options: tileOptions, shape, full: size === "full", wide: size === "full" || shape.columns > 1,
    live: { state: "on", a: {} }, chosen: resolveControls({ entity, options: tileOptions }), rangeReady: true, bigKeys: true,
    favorite: false, plugin: false, pluginRow: false, watch: false, ...more });
}

describe("the face of a card", () => {
  it("draws what replaces the name first: a bedside clock, a plugin's tile, the energy diagram", () => {
    expect(face("screen.nightstand", "full").kind).toBe("bedside");
    expect(face("plugin:bus.departures", [2, 1], {}, { plugin: true }).kind).toBe("plugin");
    expect(face("plugin:bus.departures", [2, 1], {}, { plugin: true, pluginRow: true }).kind).toBe("plugin-live");
    expect(face("screen.energy", [2, 2]).kind).toBe("energy");
  });

  it("takes a clock's face, the flip clock wide on two by two from firmware 0.17.0", () => {
    expect(face("screen.clock", [1, 1], { display: "analog" }).kind).toBe("analog");
    expect(face("screen.clock", [2, 1], { display: "dial" }).kind).toBe("dial");
    expect(face("screen.clock", [2, 2], { display: "flip" }).kind).toBe("flip-wide");
    expect(face("screen.clock", [2, 2], { display: "flip" }, { bigKeys: false }).kind).toBe("flip");
    expect(face("screen.clock", [2, 1], { display: "flip" }).kind).toBe("flip");
    expect(face("screen.clock", [2, 1], { display: "digital" }).kind).toBe("digital");
    // A settings card is a plain card whatever it carries (GitHub #47).
    expect(displayOf("screen.settings", { display: "dial" })).toBe("standard");
    expect(face("screen.settings", [1, 1], { display: "dial" }).kind).toBe("standard");
  });

  it("fills a card with a picture: a favourite (not over the whole page) and a live camera", () => {
    expect(face("sensor.t", [2, 1], { display: "graph" }).kind).toBe("graph");
    expect(face("media_player.m", [2, 1], { display: "favorite" }, { favorite: true }).kind).toBe("favorite");
    expect(face("media_player.m", "full", { display: "favorite" }, { favorite: true }).kind).not.toBe("favorite");
    expect(face("camera.door", [2, 2], { display: "live" }).kind).toBe("camera");
    expect(face("sensor.t", [1, 1], { display: "watch" }, { watch: true }).kind).toBe("watch");
  });

  it("makes a tall card that only switches one big key from firmware 0.17.0, and keeps a slider's head", () => {
    expect(face("light.a", [1, 2]).kind).toBe("big-key");
    expect(face("light.a", [1, 2], {}, { bigKeys: false }).kind).toBe("tall");
    expect(face("light.a", [1, 2], { inline: "slider" }).kind).toBe("tall");
    expect(face("climate.c", [1, 2], { controls: "setpoint" }, { live: { state: "heat", a: { supported_features: 1, temperature: 21 } } }).kind).toBe("tall");
  });

  it("lays a card over the whole page out as a row, unless its modes or slats ask for a second row", () => {
    expect(face("light.a", "full").kind).toBe("full");
    const thermostat = face("climate.c", "full", { controls: "setpoint_mode" }, { live: { state: "heat", a: { supported_features: 1, temperature: 21, hvac_modes: ["heat", "cool"] } } });
    expect([thermostat.kind, thermostat.climateModes, thermostat.tall]).toEqual(["tall", true, true]);
    expect(face("light.a", [2, 1]).kind).toBe("wide");
    expect(face("light.a").kind).toBe("standard");
  });

  it("opens the settings or a page with a tall card that is one centred stack", () => {
    expect(face("screen.settings", [1, 2]).tallAction).toBe(true);
    expect(face("screen.page_2", [1, 2]).tallAction).toBe(true);
    expect(face("switch.s", [1, 2], { controls: "toggle" }).tallStack).toBe(true);
  });
});

describe("the controls a card draws", () => {
  it("draws the setpoint alone on one row, and a blind's own control without its slats", () => {
    const live = { state: "heat", a: { supported_features: 1, temperature: 21 } };
    expect(drawnControls("climate", "setpoint_mode", live, 1, true)).toBe("setpoint");
    expect(drawnControls("climate", "setpoint_mode", live, 2, true)).toBe("setpoint_mode");
    expect(drawnControls("cover", "position_tilt", { state: "open", a: { supported_features: 255 } }, 2, true)).toBe("position");
    expect(drawnControls("cover", "tilt", { state: "open", a: { supported_features: 255 } }, 2, true)).toBeNull();
    expect(drawnControls("light", null, null, 1, true)).toBeNull();
  });

  it("gives a wide card the keys the entity supports, and a control that fills its cell the cell", () => {
    const player = face("media_player.m", [2, 1], { controls: "playback" }, { live: { state: "playing", a: { supported_features: 16384 | 1 | 32 | 16 } } });
    expect(player.panelKeys.map((key) => key.icon)).toEqual(["skip-previous", "pause", "skip-next"]);
    expect(player.fillsCell).toBe(false);
    expect(face("light.a", [2, 1], { controls: "brightness" }).fillsCell).toBe(true);
    expect(face("select.s", [2, 1], { controls: "stepper" }, { live: { state: "a", a: { options: ["a", "b"] } } }).fillsCell).toBe(false);
    expect(face("number.n", [2, 1], { controls: "stepper" }).fillsCell).toBe(true);
  });

  it("puts a thermostat's modes on a bar on one row", () => {
    const modes = face("climate.c", [2, 1], { controls: "mode" }, { live: { state: "heat", a: { hvac_modes: ["off", "heat", "cool"] } } });
    expect([modes.modeBar, modes.controls]).toEqual([true, "mode"]);
  });
});
