// Plugins (docs/PLUGINS.md): whether a plugin fits a screen, the one rule the Plugins page and its details share.
import { describe, expect, it } from "vitest";
import { fit, flashShare, headroomKb, offeredEntities, type Plugin } from "../src/model/plugins";
import { stageOf } from "../src/plugin-state";
import type { Screen } from "../src/types";

// A plugin as the add-on describes it (plugins.editor_plugin), with only what fit() reads changed per test.
const plugin = (more: Partial<Plugin> = {}): Plugin => ({
  id: "bus", name: { en: "Bus" }, summary: { en: "The next bus." }, icon: "F00E7", maintainer: "someone", tessera: false,
  version: "1.0.0", repo: "", license: "MIT", kind: "behaviour", boards: "any", requires: {}, flash_kb: 12,
  permissions: { home_assistant: [], network: [] }, readme: { en: "" }, languages: ["en"], attributes: [], ...more,
});
const screen = (board: string, more: Partial<Screen> = {}) =>
  ({ id: `text.${board}`, name: board, online: true, board, firmware: "0.52.0", pictures: board !== "cyd", layout: {}, ...more }) as Screen;

describe("plugins", () => {
  it("shows a badge for a beta plugin and an example, none for a stable one or a test", () => {
    expect(stageOf(plugin({ stage: "example", label: "tessera" }))).toBe("example");
    expect(stageOf(plugin({ stage: "beta", label: "community" }))).toBe("beta");
    expect(stageOf(plugin({ stage: "stable", label: "tessera" }))).toBe("");
    expect(stageOf(plugin({ stage: "example", label: "test" }))).toBe("");
  });

  it("offers a plugin for one board only on that board", () => {
    const audio = plugin({ boards: ["wavesharep4"], kind: "hardware" });
    expect(fit(audio, screen("wavesharep4"))).toEqual({ ok: true });
    expect(fit(audio, screen("guition"))).toEqual({ ok: false, reason: "board" });
  });

  it("asks for PSRAM where the plugin says it needs it", () => {
    const needsPsram = plugin({ requires: { psram: true } });
    expect(fit(needsPsram, screen("cyd"))).toEqual({ ok: false, reason: "psram" });
    expect(fit(needsPsram, screen("guition"))).toEqual({ ok: true });
  });

  it("asks for newer firmware when the add-on says the plugin's API is newer than its own", () => {
    expect(fit(plugin({ fits_api: false }), screen("guition"))).toEqual({ ok: false, reason: "firmware" });
  });

  it("says a blocked version is blocked before anything else", () => {
    expect(fit(plugin({ blocked: "Sends the key elsewhere", boards: ["cyd"] }), screen("guition"))).toEqual({ ok: false, reason: "blocked" });
  });

  it("measures the room from the screen's own last build when the add-on reports it", () => {
    const measured = screen("hosyond40", { firmware_image: { size: 1_880_000, slot: 2_031_616 } });
    expect(headroomKb(measured)).toBe(9);
    expect(fit(plugin({ flash_kb: 12 }), measured)).toEqual({ ok: false, reason: "flash" });
    expect(fit(plugin({ flash_kb: 3 }), measured)).toEqual({ ok: true });
  });

  it("keeps a 4 MB board under the 93 % line of its slot", () => {
    expect(headroomKb()).toBe(34);
    expect(fit(plugin(), screen("cyd"))).toEqual({ ok: true });
    expect(fit(plugin({ flash_kb: 40 }), screen("cyd"))).toEqual({ ok: false, reason: "flash" });
    const share = flashShare(plugin(), screen("cyd"))!;
    expect(share.before).toBeCloseTo(0.912, 3);
    expect(share.after).toBeCloseTo((1_853_664 + 12 * 1024) / 2_031_616, 3);
    expect(flashShare(plugin(), screen("guition"))).toBeNull();
  });
});

describe("the entities a plugin tile offers", () => {
  const all = [{ id: "sensor.price" }, { id: "sensor.temperature" }, { id: "sensor.price_unavailable" }];
  it("are every entity of its domains when the tile names no attributes", () => {
    expect(offeredEntities(all, {})).toEqual(all);
  });
  it("are those with the attributes it needs, and always the one it has", () => {
    expect(offeredEntities(all, { entities: ["sensor.price"] }).map((e) => e.id)).toEqual(["sensor.price"]);
    expect(offeredEntities(all, { entities: ["sensor.price"] }, "sensor.price_unavailable").map((e) => e.id))
      .toEqual(["sensor.price", "sensor.price_unavailable"]);
  });
});
