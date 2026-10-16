// The editor's tile catalogue answers as the add-on's (app 0.4.32): tests/fixtures/catalogue-conformance.json holds what
// screen_manager/app/catalogue.py answers for every type with controls, size, choice, entity and screen.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { bits, drawable, resolveControls, roomless } from "../src/model/catalogue";

const cases = JSON.parse(readFileSync(resolve(process.cwd(), "../tests/fixtures/catalogue-conformance.json"), "utf8")).cases as any[];

describe("the tile catalogue in the editor", () => {
  it("draws on every card what the add-on sends it", () => {
    const wrong = cases.filter((c) => c.kind === "resolve" && resolveControls(c.tile) !== c.expect)
      .map((c) => `${c.tile.entity} ${JSON.stringify(c.tile.options)}: ${resolveControls(c.tile)} instead of ${c.expect}`);
    expect(wrong.slice(0, 8)).toEqual([]);
    expect(cases.filter((c) => c.kind === "resolve").length).toBeGreaterThan(500);
  });
  it("gives every screen what the add-on gives it", () => {
    const wrong = cases.filter((c) => c.kind === "drawable" && drawable(c.domain, c.key, c.attributes, c.features === null ? null : new Set(c.features)) !== c.expect)
      .map((c) => `${c.domain} ${c.key} ${JSON.stringify(c.attributes)} ${JSON.stringify(c.features)}: not ${c.expect}`);
    expect(wrong.slice(0, 8)).toEqual([]);
  });
  it("cuts a control the screen lays out by its room as the add-on does for an older screen", () => {
    const wrong = cases.filter((c) => c.kind === "roomless" && roomless(c.domain, c.key, c.size) !== c.expect)
      .map((c) => `${c.domain} ${c.key} ${c.size}: ${roomless(c.domain, c.key, c.size)} instead of ${c.expect}`);
    expect(wrong.slice(0, 8)).toEqual([]);
    expect(cases.filter((c) => c.kind === "roomless").length).toBeGreaterThan(40);
  });
  it("names Home Assistant's feature bits as its source does", () => {
    expect(bits("climate", "TARGET_TEMPERATURE", "TARGET_TEMPERATURE_RANGE")).toBe(3);
    expect(bits("cover", "SET_POSITION")).toBe(4);
    expect(bits("media_player", "VOLUME_SET", "VOLUME_MUTE")).toBe(12);
  });
});
