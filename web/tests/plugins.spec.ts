// Plugins (docs/PLUGINS.md): whether a plugin fits a screen, the one rule the Plugins page and its details share.
import { describe, expect, it } from "vitest";
import { applyText, changesBetween, compareUrl, fit, flashShare, headroomKb, offeredEntities, type Plugin } from "../src/model/plugins";
import { t } from "../src/i18n";
import { useInventoryStore } from "../src/stores/inventory";
import { usePluginsStore } from "../src/stores/plugins";
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
    expect(fit(plugin({ id: "voice" }), screen("guition"), { voice: "feature" })).toEqual({ ok: false, reason: "feature" });
    expect(fit(plugin({ id: "voice" }), screen("cyd", { pictures: true }), {})).toEqual({ ok: true });
    // The plugins store hands each screen its part of what the add-on said.
    const plugins = usePluginsStore();
    plugins.appFit = { "text.guition": { voice: "feature" } };
    expect(plugins.fits(plugin({ id: "voice" }), screen("guition"))).toEqual({ ok: false, reason: "feature" });
    expect(plugins.fits(plugin({ id: "voice" }), screen("cyd", { pictures: true }))).toEqual({ ok: true });
  });

  it("offers an update only from the plugin's own origin, and a newer commit for a branch", () => {
    const s = screen("guition"), plugins = usePluginsStore(), hasUpdate = plugins.hasUpdate;
    plugins.installed = { [s.id]: [{ id: "bus", version: "1.0.0", source: "index", origin: "github.com/someone/fork" }] };
    expect(hasUpdate(s, plugin({ version: "1.1.0", origin: "github.com/maxgramser/tessera-plugins/plugins/bus" }))).toBe(false);
    plugins.installed = { [s.id]: [{ id: "bus", version: "1.0.0", source: "index", origin: "github.com/a/b" }] };
    expect(hasUpdate(s, plugin({ version: "1.1.0", origin: "github.com/a/b" }))).toBe(true);
    plugins.installed = { [s.id]: [{ id: "bus", version: "1.0.0", source: "branch", ref: "a".repeat(40), origin: "github.com/a/b" }] };
    expect(hasUpdate(s, plugin({ version: "1.0.0", ref: "b".repeat(40), origin: "github.com/a/b", source: "branch" }))).toBe(true);
  });

  it("shows a badge for a beta plugin and an example, none for a stable one or a test", () => {
    const { stageOf } = usePluginsStore();
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
    const plugins = usePluginsStore(), { setupChanged, setValue, setParts } = plugins;
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
    const plugins = usePluginsStore(), { setupChanged, setValue, forgetDrafts, valueOf } = plugins;
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

describe("a plugin's details (the plugins store, model/plugins.ts)", () => {
  const origin = "github.com/a/b";
  it("takes a plugin off with the ones that need it, and offers to take what only came along with them", () => {
    const s = screen("guition"), plugins = usePluginsStore();
    // The voice plugin needs the speaker, which came along with it; the helper came along with the speaker; the other
    // plugin stands on its own.
    plugins.index = [plugin({ id: "voice", requires: { plugins: ["speaker"] } }), plugin({ id: "speaker", requires: { plugins: ["helper"] } }),
      plugin({ id: "helper" }), plugin({ id: "other" })];
    plugins.installed = { [s.id]: [
      { id: "voice", version: "1.0.0", source: "index" }, { id: "speaker", version: "1.0.0", source: "index", auto: true },
      { id: "helper", version: "1.0.0", source: "index", auto: true }, { id: "other", version: "1.0.0", source: "index" },
    ] };
    expect(plugins.removalPlan([s], plugins.index[1])).toEqual({ with: ["voice"], orphans: ["helper"] });
    expect(plugins.removalPlan([s], plugins.index[3])).toEqual({ with: [], orphans: [] });
  });

  it("brings an update's changelog from the version a screen runs, the oldest on the Plugins page, with GitHub's comparison", () => {
    const a = screen("guition"), b = screen("cyd"), plugins = usePluginsStore();
    useInventoryStore().inventory = { screens: [a, b], entities: [] } as any;
    const bus = plugin({ version: "1.2.0", origin, ref: "b".repeat(40), repo: "https://github.com/a/b/tree/main/plugins/bus" });
    plugins.index = [bus];
    plugins.installed = { [a.id]: [{ id: "bus", version: "1.1.0", source: "index", origin, ref: "a".repeat(40) }],
      [b.id]: [{ id: "bus", version: "1.0.0", source: "index", origin, ref: "c".repeat(40) }] };
    expect(plugins.newsFrom(bus, a)).toBe("1.1.0");
    expect(plugins.newsFrom(bus, null)).toBe("1.0.0");
    expect(plugins.compareFor(bus, a)).toBe(`https://github.com/a/b/compare/${"a".repeat(40)}...${"b".repeat(40)}`);
    expect(plugins.compareFor(bus, null)).toBe(`https://github.com/a/b/compare/${"a".repeat(40)}...${"b".repeat(40)}`);
    expect(compareUrl("https://github.com/a/b", "v1", "b".repeat(40))).toBeNull();
    expect(compareUrl("https://github.com/a/b", "a".repeat(40), "a".repeat(40))).toBeNull();
    plugins.installed = {};
    expect(plugins.newsFrom(bus, a)).toBeNull();
    expect(plugins.newsFrom(bus, null)).toBeNull();
  });

  it("says on a screen's row what its box asks, what it runs, or why it does not fit", () => {
    const a = screen("guition", { update: { profile: "a.yaml" } as any }), plugins = usePluginsStore();
    const bus = plugin({ version: "1.2.0", origin });
    plugins.installed = { [a.id]: [{ id: "bus", version: "1.1.0", source: "index", origin }] };
    expect(plugins.screenLine(bus, a, false)).toBe(t("editor.plugins.pending.remove"));
    expect(plugins.screenLine(bus, a, true)).toBe(t("editor.plugins.screen_update", { from: "1.1.0", to: "1.2.0" }));
    plugins.installed = {};
    expect(plugins.screenLine(bus, a, true)).toBe(t("editor.plugins.pending.add"));
    expect(plugins.screenLine(plugin({ requires: { psram: true } }), screen("cyd", { update: { profile: "c.yaml" } as any }), false))
      .toBe(t("editor.plugins.misfit_short.psram"));
  });

  it("says what applying the boxes does", () => {
    expect([applyText(0, 0), applyText(2, 0), applyText(0, 1), applyText(1, 1)])
      .toEqual([t("editor.plugins.apply.none"), t("editor.plugins.apply.add", { n: 2 }, 2), t("editor.plugins.apply.remove", { n: 1 }, 1), t("editor.plugins.apply.both", { n: 2 }, 2)]);
  });
});
