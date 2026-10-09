// Plugins (docs/PLUGINS.md): whether a plugin fits a screen, the one rule the Plugins page and its details share.
import { describe, expect, it } from "vitest";
import { changesBetween, fit, flashShare, headroomKb, knowAppFit, offeredEntities, type Plugin } from "../src/model/plugins";
import { hasUpdate, plugins, stageOf } from "../src/plugin-state";
import type { Screen } from "../src/types";

// A plugin as the add-on describes it (plugins.editor_plugin), with only what fit() reads changed per test.
const plugin = (more: Partial<Plugin> = {}): Plugin => ({
  id: "bus", name: { en: "Bus" }, summary: { en: "The next bus." }, icon: "F00E7", maintainer: "someone", tessera: false,
  version: "1.0.0", repo: "", license: "MIT", type: "functions", boards: "any", requires: {}, flash_kb: 12,
  permissions: { home_assistant: [], network: [] }, readme: { en: "" }, languages: ["en"], attributes: [], ...more,
});
const screen = (board: string, more: Partial<Screen> = {}) =>
  ({ id: `text.${board}`, name: board, online: true, board, firmware: "0.52.0", pictures: board !== "cyd", layout: {}, ...more }) as Screen;

describe("plugins", () => {
  it("takes the releases of a changelog after the screen's version, up to the one on offer", () => {
    const log = "# Changelog\n\n## 1.2.3 - 2026-10-09\n- Topics.\n\n## 1.2.2\n- Example.\n\n## 1.2.0\n- Countdown.\n";
    expect(changesBetween(log, "1.2.0", "1.2.3")).toBe("## 1.2.3 - 2026-10-09\n- Topics.\n\n## 1.2.2\n- Example.");
    expect(changesBetween(log, "1.2.2", "1.2.3")).toBe("## 1.2.3 - 2026-10-09\n- Topics.");
    expect(changesBetween(log).startsWith("## 1.2.3")).toBe(true);
    expect(changesBetween("", "1.0.0", "1.1.0")).toBe("");
  });

  it("takes what only the add-on knows: a feature nothing brings, a plugin it needs that does not fit", () => {
    knowAppFit({ "text.guition": { voice: "feature" } });
    expect(fit(plugin({ id: "voice" }), screen("guition"))).toEqual({ ok: false, reason: "feature" });
    expect(fit(plugin({ id: "voice" }), screen("cyd", { pictures: true }))).toEqual({ ok: true });
    knowAppFit({});
  });

  it("offers an update only from the plugin's own origin, and a newer commit for a branch", () => {
    const s = screen("guition");
    plugins.installed = { [s.id]: [{ id: "bus", version: "1.0.0", source: "index", origin: "github.com/someone/fork" }] };
    expect(hasUpdate(s, plugin({ version: "1.1.0", origin: "github.com/maxgramser/tessera-plugins/plugins/bus" }))).toBe(false);
    plugins.installed = { [s.id]: [{ id: "bus", version: "1.0.0", source: "index", origin: "github.com/a/b" }] };
    expect(hasUpdate(s, plugin({ version: "1.1.0", origin: "github.com/a/b" }))).toBe(true);
    plugins.installed = { [s.id]: [{ id: "bus", version: "1.0.0", source: "branch", ref: "a".repeat(40), origin: "github.com/a/b" }] };
    expect(hasUpdate(s, plugin({ version: "1.0.0", ref: "b".repeat(40), origin: "github.com/a/b", source: "branch" }))).toBe(true);
    plugins.installed = {};
  });

  it("shows a badge for a beta plugin and an example, none for a stable one or a test", () => {
    expect(stageOf(plugin({ stage: "example", label: "tessera" }))).toBe("example");
    expect(stageOf(plugin({ stage: "beta", label: "community" }))).toBe("beta");
    expect(stageOf(plugin({ stage: "stable", label: "tessera" }))).toBe("");
    expect(stageOf(plugin({ stage: "example", label: "test" }))).toBe("");
  });

  it("offers a plugin for one board only on that board", () => {
    const audio = plugin({ boards: ["wavesharep4"], type: "hardware" });
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

describe("saving a plugin's settings on a screen", () => {
  it("asks for a build only when what is filled in differs from what the screen was built with", async () => {
    const { plugins, setupChanged, setValue, setParts } = await import("../src/plugin-state");
    const voice = plugin({ id: "voice", inputs: [
      { id: "key", kind: "secret", label: { en: "Key" }, scope: "all" },
      { id: "words", kind: "text", label: { en: "Words" }, scope: "screen" }],
      parts: [{ id: "aec", label: { en: "AEC" }, hint: { en: "" }, flash_kb: 38, default: false }] });
    const kitchen = screen("wavesharep4", { id: "kitchen", node: "kitchen" } as Partial<Screen>);
    plugins.installed.kitchen = [{ id: "voice", version: "1.0.0", source: "index", values: { words: "okay_nabu" }, parts: [] }];
    expect(setupChanged(kitchen, voice)).toBe(false);
    setValue(kitchen, voice, "words", "okay_nabu");
    expect(setupChanged(kitchen, voice)).toBe(false);          // the same value typed again
    setValue(kitchen, voice, "words", "okay_nabu, alexa");
    expect(setupChanged(kitchen, voice)).toBe(true);
    setValue(kitchen, voice, "words", "okay_nabu");
    setValue(kitchen, voice, "key", "");
    expect(setupChanged(kitchen, voice)).toBe(false);          // a secret left empty keeps the one the app has
    setValue(kitchen, voice, "key", "sk-new");
    expect(setupChanged(kitchen, voice)).toBe(true);
    setValue(kitchen, voice, "key", "");
    setParts(kitchen, voice, ["aec"]);
    expect(setupChanged(kitchen, voice)).toBe(true);
    setParts(kitchen, voice, []);
    expect(setupChanged(kitchen, voice)).toBe(false);
  });

  it("forgets what was filled in once the add-on has it, so a saved secret no longer counts as a change", async () => {
    const { plugins, setupChanged, setValue, forgetDrafts, valueOf } = await import("../src/plugin-state");
    const voice = plugin({ id: "voice2", inputs: [{ id: "key", kind: "secret", label: { en: "Key" }, scope: "all" }] });
    const hall = screen("guition", { id: "hall", node: "hall" } as Partial<Screen>);
    plugins.installed.hall = [{ id: "voice2", version: "1.0.0", source: "index", values: {}, parts: [] }];
    setValue(hall, voice, "key", "sk-new");
    expect(setupChanged(hall, voice)).toBe(true);
    forgetDrafts(hall, voice);
    expect(setupChanged(hall, voice)).toBe(false);
    expect(valueOf(hall, voice, "key")).toBe("");
  });
});
