import { seedLayout, seedTiles, seedPages, seedTitles, appendTiles, screenFixture, documentFixture, current } from "./page-fixtures";
// The editor's texts (app 0.2.90): English from en.json with the page, another language when it is needed, the plural
// rules of the screens, and which language the page, the add-on's answers and the mockup speak.
import { mount } from "@vue/test-utils";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import en from "../../screen_manager/translations/en.json";
import { send } from "../src/api";
import TileCard from "../src/components/TileCard.vue";
import {
  addLanguage, andList, haProfile, i18n, languageMarks, languageMeta, languages, loadLanguage, matchLanguage, numberText, pickLanguage,
  PLURAL_RULES, requestedLanguage, setEditorLanguage, STYLE_MARKS, t,
} from "../src/i18n";
import { agoText, dateText } from "../src/model/topbar";
import { state } from "../src/store";
import { pageTexts, TRANSLATIONS } from "../translations";

const meta = (plural: string) => ({ name: "Test", english: "Test", script: "latin", plural, checked: false });
// Every text of a part as [key, text]; a list's items get .0, .1, ... as in tools/i18n.py.
function flat(node: unknown, path: string): [string, unknown][] {
  if (node && typeof node === "object") return Object.entries(node).flatMap(([key, value]) => flat(value, `${path}.${key}`));
  return [[path, node]];
}
// en.json as it is, and the part of it the page takes.
const file = JSON.parse(readFileSync(join(TRANSLATIONS, "en.json"), "utf8"));
const page = pageTexts(file);
const texts = [...flat(page.editor, "editor"), ...flat(page.screen, "screen")];

afterEach(() => {
  i18n.global.locale.value = "en";
  vi.unstubAllGlobals();
});

describe("English", () => {
  it("comes with the page: the editor's texts and the screens' words the mockup draws, and every language's _meta", () => {
    // Only shared validation errors from the add-on accompany the editor and screen mockup texts.
    expect(Object.keys(en).sort()).toEqual(["addon", "editor", "screen"]);
    expect(Object.keys((en as any).addon.errors).sort()).toEqual(['layout', 'pages', 'top_bar']);
    expect(Object.keys((en as any).screen).sort()).toEqual(["climate", "cover", "date", "ha", "navigation", "number", "script", "tile", "time"]);
    expect(Object.keys((en as any).screen.tile)).toEqual(["page"]);
    expect(languageMeta("en")?.plural).toBe("one_other");
    expect(languages()[0]).toBe("en");
    // Every file in the folder is a language the editor can load.
    const files = readdirSync(TRANSLATIONS).filter((name) => name.endsWith(".json")).map((name) => name.slice(0, -5)).sort();
    expect([...languages()].sort()).toEqual(files);
  });
  it("leaves out empty texts, keeps a space, and takes nothing else from a file", () => {
    const part = pageTexts({
      _meta: meta("one_other"), addon: { x: "y" },
      screen: { number: { decimal: ",", group: " ", group_min: "" }, status: { home: "Thuis" }, tile: { page: "Pagina {n}", refused: "Geweigerd" }, time: { just_now: "" } },
      editor: { common: { close: "Sluiten", cancel: "" }, empty: {} },
    });
    expect(part).toEqual({ editor: { common: { close: "Sluiten" } }, screen: { number: { decimal: ",", group: " " }, tile: { page: "Pagina {n}" } } });
  });
  it("has a readable text for every key, and no text vue-i18n reads as something else", () => {
    for (const [key, text] of texts) {
      expect(typeof text, key).toBe("string");
      expect(t(key), key).not.toBe(key);
      // @ links another text and | separates plural forms: a text uses them only as that.
      expect(text as string, key).not.toMatch(/@|\$|\|\|/);
      if ((text as string).includes("|")) expect(text as string, key).toMatch(/ \| /);
    }
  });
  it("has every key the code asks for, and no editor key the code doesn't use", () => {
    const files = (dir: string): string[] => readdirSync(dir).flatMap((name) => {
      const path = join(dir, name);
      return statSync(path).isDirectory() ? files(path) : /\.(ts|vue)$/.test(name) ? [path] : [];
    });
    const code = files(join(__dirname, "..", "src")).map((path) => readFileSync(path, "utf8")).join("\n");
    const key = String.raw`(?:editor|screen\.(?:ha|time|date|number|tile))\.[a-z0-9_.]*`;
    const keys = new Set([...code.matchAll(new RegExp(`["'\`](${key}[a-z0-9_])["'\`]`, "g"))].map((m) => m[1]));
    // A key built at run time, such as `editor.library.filters.${value}`, counts for every text under its start.
    const starts = new Set([...code.matchAll(new RegExp(`\`(${key})\\$\\{`, "g"))].map((m) => m[1]));
    const known = new Set(texts.map(([key]) => key));
    for (const key of keys) expect(known.has(key) || texts.some(([other]) => other.startsWith(`${key}.`)), key).toBe(true);
    for (const start of starts) expect(texts.some(([key]) => key.startsWith(start)), start).toBe(true);
    // The screens' words come as whole parts (screen.ha, time, date, number); the editor's own texts are all in use.
    const unused = texts.map(([key]) => key)
      .filter((key) => key.startsWith("editor.") && !keys.has(key) && ![...starts].some((start) => key.startsWith(start)));
    expect(unused).toEqual([]);
  });
});

describe("choosing a language", () => {
  const available = ["en", "nl", "pt-BR", "zh-Hans"];
  it("takes the same code, else its base language, else English", () => {
    expect(matchLanguage("nl", available)).toBe("nl");
    expect(matchLanguage("PT-br", available)).toBe("pt-BR");
    expect(matchLanguage("zh-hans", available)).toBe("zh-Hans");
    expect(matchLanguage("nl-BE", available)).toBe("nl");
    expect(matchLanguage("fr", available)).toBeUndefined();
    expect(pickLanguage("fr", available)).toBe("en");
    expect(pickLanguage("pt", available)).toBe("en");
    expect(pickLanguage(null, available)).toBe("en");
    expect(pickLanguage("", available)).toBe("en");
  });
  it("reads Home Assistant's <html lang> inside its iframe, else the browser's language", () => {
    const frame = document.createElement("iframe");
    document.body.append(frame);
    const inner = frame.contentWindow!;
    document.documentElement.lang = "nl";
    expect(requestedLanguage(inner)).toBe("nl");
    document.documentElement.lang = "";
    expect(requestedLanguage(inner)).toBe(inner.navigator.language);
    expect(requestedLanguage(window)).toBe(navigator.language);
    // A parent on another origin throws on its document.
    const foreign = { get parent(): Window { throw new Error("cross-origin"); }, navigator: { language: "de-DE" } } as unknown as Window;
    expect(requestedLanguage(foreign)).toBe("de-DE");
    frame.remove();
  });
  it("sets the page's own language, loads a language from its file, and keeps English for one it doesn't have", async () => {
    addLanguage("tt", { editor: { common: { close: "Sluiten" } } }, meta("one_other"));
    expect(await setEditorLanguage("tt")).toBe("tt");
    expect(document.documentElement.lang).toBe("tt");
    expect(t("editor.common.close")).toBe("Sluiten");
    // A text the language doesn't have yet shows in English.
    expect(t("editor.common.cancel")).toBe("Cancel");
    expect(await setEditorLanguage("xx")).toBe("en");
    expect(document.documentElement.lang).toBe("en");
    expect(await loadLanguage("xx")).toBe(false);
    // A language with a file comes from its own chunk, compiled like English.
    expect(await loadLanguage("nl")).toBe(true);
    expect(t("screen.tile.page", { n: 2 }, { locale: "nl" })).toBe("Pagina 2");
  });
});

describe("plural forms", () => {
  it("follow the rules of the screens", () => {
    const forms = (rule: string, numbers: number[]) => numbers.map(PLURAL_RULES[rule]);
    expect(forms("one_other", [0, 1, 2, 11])).toEqual([1, 0, 1, 1]);
    expect(forms("one_upto_1", [0, 1, 2, 11])).toEqual([0, 0, 1, 1]);
    expect(forms("slavic_pl", [1, 2, 4, 5, 12, 14, 21, 22, 25, 102])).toEqual([0, 1, 1, 2, 2, 2, 2, 1, 2, 1]);
    expect(forms("east_slavic", [1, 2, 5, 11, 12, 21, 22, 25, 111])).toEqual([0, 1, 2, 2, 2, 0, 1, 2, 2]);
    expect(forms("none", [0, 1, 2, 5])).toEqual([0, 0, 0, 0]);
  });
  it("pick the form of a text by its language's rule, with {n}, and the last form when a text has fewer", () => {
    expect(t("editor.library.entities", 1)).toBe("1 entity");
    expect(t("editor.library.entities", 5)).toBe("5 entities");
    addLanguage("tp", { editor: { library: { entities: "{n} encja | {n} encje | {n} encji" }, common: { results: "{n} wynik | {n} wyników" } } }, meta("slavic_pl"));
    const tp = (key: string, n: number) => t(key, n, { locale: "tp" });
    expect([1, 3, 5, 22].map((n) => tp("editor.library.entities", n))).toEqual(["1 encja", "3 encje", "5 encji", "22 encje"]);
    expect(tp("editor.common.results", 3)).toBe("3 wyników");
    // One form: every number takes it.
    addLanguage("tz", { editor: { library: { entities: "{n} 个实体" } } }, meta("none"));
    expect(t("editor.library.entities", 7, { locale: "tz" })).toBe("7 个实体");
    // French counts 0 as one.
    addLanguage("tf", { editor: { library: { entities: "{n} entité | {n} entités" } } }, meta("one_upto_1"));
    expect([0, 1, 2].map((n) => t("editor.library.entities", n, { locale: "tf" }))).toEqual(["0 entité", "1 entité", "2 entités"]);
  });
});

describe("the add-on hears the editor's language", () => {
  it("in a header on every request", async () => {
    const fetch = vi.fn(async () => new Response("", { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    await send("screens/x/identify", "POST");
    addLanguage("tt", { editor: {} }, meta("one_other"));
    i18n.global.locale.value = "tt";
    await send("inventory", "GET");
    const headers = fetch.mock.calls.map((call: any[]) => call[1].headers["X-ESP-Screens-Language"]);
    expect(headers).toEqual(["en", "tt"]);
  });
  it("and a failed answer without the add-on's own words says so in the editor's language", async () => {
    addLanguage("tu", { editor: { api: { failed: "Dat lukte niet." } } }, meta("one_other"));
    i18n.global.locale.value = "tu";
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>502</html>", { status: 502 })));
    await expect(send("screens/x", "PUT", {})).rejects.toThrow("Dat lukte niet.");
  });
});

describe("the mockup speaks the screens' language", () => {
  it("draws the screens' own words in their language while the editor keeps its own", async () => {
    addLanguage("td", {
      editor: { tile_card: { remove: "Kachel entfernen" } },
      screen: {
        ha: { unavailable: "Nicht verfügbar", on: "An", weather: { windy: "Windig" }, binary: { door_on: "Offen" }, button: { run: "Ausführen" } },
        tile: { page: "Seite {n}" },
        time: { hours_ago: "Vor 1 Stunde | Vor {n} Stunden", just_now: "Gerade eben" },
        date: { weekdays_min: ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"], weekdays_short: ["So.", "Mo.", "Di.", "Mi.", "Do.", "Fr.", "Sa."],
                months_short: ["Jan.", "Feb.", "März", "Apr.", "Mai", "Juni", "Juli", "Aug.", "Sept.", "Okt.", "Nov.", "Dez."], top_bar: "{weekday}, {day}. {month}" },
        number: { decimal: ",", group: ".", group_min: "2" },
      },
    }, meta("one_other"));
    state.inventory = {
      screens: [], entities: [{ id: "light.b", name: "Lamp B", state: "unavailable" }],
      // The add-on says how the screens write numbers: Automatic, worked out for their language (1.234,5).
      language: { setting: "td", effective: "td", ha: "en", languages: [], numbers: "auto", numbers_effective: "comma", group_min: 2 },
      controls: { script: { default: "run", choices: [{ key: "run", label: "Run" }, { key: "none", label: "None" }] } },
    } as any;
    seedLayout({ title: "Living room", tiles: [] });
    state.liveStates = {
      "light.c": { state: "on", word: null, a: {} },
      "weather.home": { state: "windy-variant", word: null, a: { temperature: 12.5 } },
      "binary_sensor.door": { state: "on", word: null, a: { device_class: "door" } },
      "sensor.power": { state: "1249", word: null, a: { unit_of_measurement: "W" } },
      "sensor.energy": { state: "12345.5", word: null, a: { unit_of_measurement: "kWh" } },
    };
    const card = (entity: string, slot: number, options?: Record<string, unknown>) => {
      const tile = { entity, name: "", slot, ...(options ? { options } : {}) };
      appendTiles(tile);
      return mount(TileCard, { props: { tile, slot } });
    };
    const gone = card("light.b", 0);
    expect(gone.find(".st").text()).toBe("Nicht verfügbar");
    // The editor's own words stay in the editor's language.
    expect(gone.find(".remove").attributes("title")).toBe("Remove tile");
    expect(card("screen.page_2", 1).find(".goto").text()).toBe("Seite 2 ›");
    expect(card("light.c", 2).find(".st").text()).toBe("An");
    expect(card("weather.home", 3).find(".st").text()).toBe("Windig · 12,5°");
    expect(card("binary_sensor.door", 4).find(".st").text()).toBe("Offen");
    expect(card("script.movie", 5, { size: "wide", controls: "run" }).find(".run").text()).toBe("Ausführen");
    // 1249 has too few digits for a mark in this language; 12345 gets one, as the screen writes them.
    expect(card("sensor.power", 6).find(".st").text()).toBe("1249 W");
    expect(card("sensor.energy", 7).find(".st").text()).toBe("12.345,5 kWh");
    expect(agoText(1_000_000 - 7200, 1_000_000, "td")).toBe("Vor 2 Stunden");
    expect(agoText(1_000_000 - 7200, 1_000_000)).toBe("2 hours ago");
    expect(dateText(new Date(2026, 8, 15), "td")).toBe("Di., 15. Sept.");
    // A word the language doesn't have yet is English, as on the screen.
    expect(agoText(1_000_000 - 90000, 1_000_000, "td")).toBe("Yesterday");
  });
});

describe("numbers, lists and the profile", () => {
  it("writes numbers as the screens do", () => {
    expect(["1249", "21.4", "-1234567.25", "0", "999"].map((n) => numberText(n, STYLE_MARKS.point))).toEqual(["1,249", "21.4", "-1,234,567.25", "0", "999"]);
    expect(["1249", "21.4", "-1234567.25"].map((n) => numberText(n, STYLE_MARKS.comma))).toEqual(["1.249", "21,4", "-1.234.567,25"]);
    expect(["1249", "21.4"].map((n) => numberText(n, STYLE_MARKS.space))).toEqual(["1 249", "21,4"]);
    // Anything that isn't a plain number stays as it is.
    expect(["on", "1e5", "12:30", "", ".5", "5."].map((n) => numberText(n, STYLE_MARKS.comma))).toEqual(["on", "1e5", "12:30", "", ".5", "5."]);
    expect(numberText(1234.5, STYLE_MARKS.comma)).toBe("1.234,5");
    // A language's own marks: English and Dutch from four digits, Italian from five.
    expect(numberText("1234.5", languageMarks("en"))).toBe("1,234.5");
    addLanguage("ti", { screen: { number: { decimal: ",", group: ".", group_min: "2" } } }, meta("one_other"));
    expect(["1234.5", "12345.5"].map((n) => numberText(n, languageMarks("ti")))).toEqual(["1234,5", "12.345,5"]);
  });
  it("writes a list the way the language does, the English one without a comma before and", () => {
    expect(andList([1, 2, 3])).toBe("1, 2 and 3");
    expect(andList([2, 3], "nl")).toBe("2 en 3");
  });
  it("reads the clock and number format of the user's Home Assistant profile, where it names one", () => {
    const frame = document.createElement("iframe");
    document.body.append(frame);
    const inner = frame.contentWindow!;
    const ha = document.createElement("home-assistant") as any;
    document.body.append(ha);
    ha.hass = { locale: { language: "nl", time_format: "24", number_format: "decimal_comma" } };
    expect(haProfile(inner)).toEqual({ clock: "24", numbers: "comma" });
    ha.hass = { locale: { time_format: "12", number_format: "comma_decimal" } };
    expect(haProfile(inner)).toEqual({ clock: "12", numbers: "point" });
    ha.hass = { locale: { time_format: "language", number_format: "space_comma" } };
    expect(haProfile(inner)).toEqual({ numbers: "space" });
    ha.hass = { locale: { time_format: "system", number_format: "none" } };
    expect(haProfile(inner)).toEqual({});
    // Outside Home Assistant's page there is no profile.
    expect(haProfile(window)).toEqual({});
    ha.remove();
    frame.remove();
  });
});
