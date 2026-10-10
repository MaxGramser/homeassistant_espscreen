// The editor's texts (app 0.2.90). Every language is one file in screen_manager/translations, the same file the firmware
// and the add-on read (docs/TRANSLATING.md). The page takes its `editor` section, and for the mockup the words the screens
// themselves show, plus the shared page/card validation errors; the build leaves the rest out and compiles every
// text (vite.config.ts). English is the source and comes with the page. Another language loads the first time the
// editor or a mockup needs it, and a text it doesn't have yet shows in English.
import metas from "virtual:esp-screens-languages";
import { createI18n } from "vue-i18n";
import english from "../../screen_manager/translations/en.json";
import { onReset } from "./resets";

export type LanguageMeta = { name: string; english: string; script?: string; plural: string; clock?: string; checked: boolean };
// A language's texts as the build hands them over: compiled, and only the page's part (not the file's own shape).
type Texts = Record<string, unknown>;
const en = english as unknown as Texts;

// Which form of a plural text ("1 hour ago | {n} hours ago") fits n, by the file's `_meta.plural`: the same rules as the
// screens (components/smart_display/screen_text_gen.py).
const few = (n: number) => n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14);
export const PLURAL_RULES: Record<string, (n: number) => number> = {
  one_other: (n) => (n === 1 ? 0 : 1),
  one_upto_1: (n) => (Math.abs(n) <= 1 ? 0 : 1),
  slavic_pl: (n) => (n === 1 ? 0 : few(n) ? 1 : 2),
  east_slavic: (n) => (n % 10 === 1 && n % 100 !== 11 ? 0 : few(n) ? 1 : 2),
  none: () => 0,
};

// Every other language by its code, as a chunk of its own; every language's _meta comes with the page.
const files = import.meta.glob<Texts>(
  ["../../screen_manager/translations/*.json", "!../../screen_manager/translations/en.json"], { import: "default" });
const LOADERS: Record<string, () => Promise<Texts>> = Object.fromEntries(
  Object.entries(files).map(([path, load]) => [path.slice(path.lastIndexOf("/") + 1, -".json".length), load]));
const META: Record<string, LanguageMeta> = { ...metas };
const LOADED = new Set(["en"]);
// A text with fewer forms than its language's rule uses its last one, as on the screens.
const RULES: Record<string, (choice: number, forms: number) => number> = {};
const addRule = (code: string) =>
  (RULES[code] = (choice, forms) => Math.min((PLURAL_RULES[META[code]?.plural] || PLURAL_RULES.one_other)(choice), forms - 1));

/** Every language the editor has, English first. */
export const languages = () => ["en", ...Object.keys(META).filter((code) => code !== "en").sort()];
languages().forEach(addRule);

export const i18n = createI18n({
  legacy: false,
  locale: "en",
  fallbackLocale: "en",
  messages: { en } as Record<string, any>,
  pluralRules: RULES,
  // A language without a text falls back to English quietly. Only a key English lacks is a mistake, told while developing.
  missingWarn: false,
  fallbackWarn: false,
  missing: (locale, key) => {
    if (import.meta.env.DEV && locale === "en") console.warn(`[i18n] ${key} is not in en.json`);
  },
});
export const t = i18n.global.t;
/** Whether a text exists, in English when no language is named. */
export const te = (key: string, locale = "en"): boolean => (i18n.global.te as (key: string, locale?: string) => boolean)(key, locale);
export const editorLanguage = () => i18n.global.locale.value;
/** A language's `_meta`: its own name, its name in English, its plural rule, whether it is checked. */
export const languageMeta = (code: string): LanguageMeta | undefined => META[code];

// Home Assistant opens the page in its ingress iframe, on its own origin, and sets its <html lang> to the language of
// the user's profile. Elsewhere (SCREEN_DEV, `npm run dev`) the browser's language, and English after that.
export function requestedLanguage(win: Window = window) {
  try {
    if (win.parent !== win) {
      const lang = win.parent.document.documentElement.lang;
      if (lang) return lang;
    }
  } catch {
    // A parent on another origin keeps its document to itself.
  }
  return win.navigator.language || "en";
}
// The language of the list that fits a code best: the same one (pt-BR), else its base language (pt), else none.
export function matchLanguage(wanted: string | null | undefined, available = languages()) {
  const find = (code: string) => available.find((own) => own.toLowerCase() === code.toLowerCase());
  const code = (wanted || "").trim();
  return code ? find(code) || find(code.split("-")[0]) : undefined;
}
export const pickLanguage = (wanted: string | null | undefined, available = languages()) => matchLanguage(wanted, available) || "en";

/** A language's texts, as the build hands them over; `meta` for a language without a file (the tests). */
export function addLanguage(code: string, texts: Texts, meta: LanguageMeta | undefined = META[code]) {
  if (meta) META[code] = meta;
  if (!RULES[code]) addRule(code);
  i18n.global.setLocaleMessage(code, texts as any);
  LOADED.add(code);
}
const loading: Record<string, Promise<boolean>> = {};
// Back to the languages of the files, in English: a language a test made up with addLanguage goes again. One a file has
// stays loaded, since loading it again would bring the same texts.
onReset(() => {
  for (const code of Object.keys(META)) {
    if (code in metas) continue;
    delete META[code]; delete RULES[code]; delete loading[code];
    LOADED.delete(code);
    delete (i18n.global.messages.value as Record<string, unknown>)[code];
  }
  Object.assign(META, metas);
  i18n.global.locale.value = "en";
});
/** Loads a language once; true when the editor has it. */
export function loadLanguage(code: string): Promise<boolean> {
  if (LOADED.has(code)) return Promise.resolve(true);
  const load = LOADERS[code];
  if (!load) return Promise.resolve(false);
  return (loading[code] ??= load().then(
    (texts) => (addLanguage(code, texts), true),
    () => (delete loading[code], false),
  ));
}
/** The editor's own language: the one of the user's Home Assistant profile, as far as ESP Screens has it. */
export async function setEditorLanguage(code = pickLanguage(requestedLanguage())) {
  const chosen = (await loadLanguage(code)) ? code : "en";
  i18n.global.locale.value = chosen;
  document.documentElement.lang = chosen;
  return chosen;
}

// How the screens write a number (app 0.2.90), as the firmware does (screen_text::localize): the decimal mark, the mark
// between thousands, and from how many digits a whole number gets them. The choice under Language & region is one of
// three styles; "auto" writes numbers as the screens' language does (its screen.number).
export type NumberStyle = "point" | "comma" | "space";
export type NumberMarks = { decimal: string; group: string; from: number };
export const STYLE_MARKS: Record<NumberStyle, NumberMarks> = {
  point: { decimal: ".", group: ",", from: 4 }, comma: { decimal: ",", group: ".", from: 4 }, space: { decimal: ",", group: " ", from: 4 },
};
/** The marks of a language's own numbers: "1.234,5" in Dutch, 1234 but 12.345 in Italian (CLDR's minimum grouping). */
export function languageMarks(locale: string): NumberMarks {
  const say = (key: string) => t(`screen.number.${key}`, {}, { locale });
  return { decimal: say("decimal"), group: say("group"), from: Number(say("group_min")) >= 2 ? 5 : 4 };
}
/** A state as Home Assistant sends a number ("1234.5", "-3"), written with these marks; any other text as it is. */
export function numberText(value: string | number, marks: NumberMarks) {
  const text = String(value), plain = /^(-?)(\d+)(?:\.(\d+))?$/.exec(text);
  if (!plain) return text;
  const whole = plain[2].length >= marks.from ? plain[2].replace(/\B(?=(\d{3})+$)/g, marks.group) : plain[2];
  return `${plain[1]}${whole}${plain[3] !== undefined ? marks.decimal + plain[3] : ""}`;
}
/** A number in the editor's own words, as its language writes numbers: kilobytes, inches, gigabytes, a share. */
export const editorNumber = (value: string | number) => numberText(value, languageMarks(editorLanguage()));

// The time and number format of the user's own Home Assistant profile, where it names one: a 12- or 24-hour clock, and
// "1,234.5" (comma_decimal), "1.234,5" (decimal_comma) or "1 234,5" (space_comma). "Follow the language", "use the
// system's" and "none" name none. Only inside Home Assistant's page, whose <home-assistant> element holds them.
const PROFILE_NUMBERS: Record<string, NumberStyle> = { comma_decimal: "point", decimal_comma: "comma", space_comma: "space" };
export function haProfile(win: Window = window): { clock?: "12" | "24"; numbers?: NumberStyle } {
  try {
    if (win.parent === win) return {};
    const locale = (win.parent.document.querySelector("home-assistant") as any)?.hass?.locale;
    const clock = ["12", "24"].includes(locale?.time_format) ? locale.time_format : undefined;
    return { ...(clock ? { clock } : {}), ...(PROFILE_NUMBERS[locale?.number_format] ? { numbers: PROFILE_NUMBERS[locale.number_format] } : {}) };
  } catch {
    return {};
  }
}

// "1, 2 and 3", the way the language writes a list (the CLDR, from the browser). The English texts write it without a
// comma before "and", as British English does.
export const andList = (items: (string | number)[], locale = editorLanguage()) =>
  new Intl.ListFormat(locale === "en" ? "en-GB" : locale, { type: "conjunction" }).format(items.map(String));
