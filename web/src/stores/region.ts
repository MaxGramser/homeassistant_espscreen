// ---- Languages (app 0.2.90) ----
// The editor speaks the language of the user's Home Assistant profile (i18n.ts). The screens have one language for all
// of them, Home Assistant's unless the setting says another; the mockup draws their words in it, and in English until
// the add-on tells which one it is. Their time and number format, for every screen at once under Settings → Language &
// region, live here too. What the add-on says of them is the inventory's (stores/inventory.ts, its language).
import { defineStore } from "pinia";
import { computed, effectScope, onScopeDispose, watch } from "vue";
import { send } from "../api";
import { languageMeta, loadLanguage, type NumberMarks, pickLanguage, STYLE_MARKS, t } from "../i18n";
import { useInventoryStore } from "./inventory";
import { lookups } from "./lookup";
import { useUiStore } from "./ui";

export type LanguageChanges = { setting?: string; clock?: string; numbers?: string };

export const useRegionStore = defineStore("region", () => {
  const inv = useInventoryStore();
  const ui = useUiStore();

  const screenLanguage = computed(() => pickLanguage(inv.inventory.language?.effective));
  /** A text as the screens show it: in their language, not the editor's. */
  const screenText = (key: string, named: Record<string, unknown> = {}) => t(key, named, { locale: screenLanguage.value });
  /** A language by its own name ("Nederlands"), as the add-on lists it. */
  const languageName = (code: string | null | undefined) =>
    inv.inventory.language?.languages?.find((l) => l.code === code)?.name || languageMeta(code || "")?.name || code || "";
  /** A built-in card's name as the screens show it (Settings, Clock, Go to page 2), in their language. */
  const screenBuiltinName = (id: string) => inv.inventory.builtin?.find((e) => e.id === id)?.screen_name;

  // A 24-hour clock and "1,234.5" until the add-on says otherwise. The mockup's clocks and numbers follow what the add-on
  // sends the screens: the style, from how many digits a number is grouped, and the space before "%" (Home Assistant's
  // language decides "auto").
  const clock24 = computed(() => inv.inventory.language?.clock_effective !== "12");
  const numberMarks = computed<NumberMarks>(() => {
    const language = inv.inventory.language;
    const marks = STYLE_MARKS[language?.numbers_effective || "point"] || STYLE_MARKS.point;
    return { ...marks, from: (language?.group_min || 1) >= 2 ? 5 : 4 };
  });
  /** How Automatic writes numbers: the marks of the language that decides, for the label of that choice. */
  const autoMarks = computed<NumberMarks>(() => {
    const language = inv.inventory.language;
    return { ...(STYLE_MARKS[language?.numbers_auto || "point"] || STYLE_MARKS.point), from: (language?.group_min_auto || 1) >= 2 ? 5 : 4 };
  });
  /** What follows a number for its unit, as Home Assistant spaces it: "°", "%" or " %" by the language, " kWh". */
  function unitSuffix(unit: string | undefined | null) {
    if (!unit || unit === "°") return unit || "";
    if (unit === "%") return inv.inventory.language?.percent_space ? " %" : "%";
    return ` ${unit}`;
  }

  /** Saves any of the screen language, the time format and the number format. */
  async function saveLanguage(changes: LanguageChanges) {
    try {
      const answer = await send("language", "PUT", changes);
      if (answer?.language) inv.inventory.language = answer.language;
      // A language is built into the firmware; the time and number format are not.
      ui.toast(t(changes.setting === undefined ? "editor.settings.language.saved" : "editor.settings.language.saved_language"));
      // Every screen now wants an update, which the inventory reports.
      await inv.refresh();
      return true;
    } catch (e: any) {
      ui.toast(e.message);
      return false;
    }
  }

  // ---- Started once the page is on the screen (boot.ts); the returned function stops it ----
  // The language the screens speak loads as soon as the add-on names it, for the mockup's words.
  let running: (() => void) | null = null;
  function start() {
    if (running) return running;
    const scope = effectScope(true);
    scope.run(() => watch(screenLanguage, (code) => loadLanguage(code), { immediate: true }));
    running = () => { running = null; scope.stop(); };
    return running;
  }
  onScopeDispose(() => running?.());

  return { screenLanguage, ...lookups({ screenText, languageName, screenBuiltinName, unitSuffix }), clock24, numberMarks, autoMarks, saveLanguage, start };
});
