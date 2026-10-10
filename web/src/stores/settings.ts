// ---- Screen settings: the same groups and rows as the settings page on the screen itself (model/settings.ts) ----
// Every change applies at once, like on the screen; no Save needed. A change shows at once and goes to the add-on after a
// short pause (the next change in the pause goes with it), one screen's changes at a time. What the screen has not
// reported back yet wins over what Home Assistant still shows for a few seconds, so a value never flicks back while it
// travels; what did not arrive is taken back.
import { useEventListener } from "@vueuse/core";
import { defineStore } from "pinia";
import { computed, effectScope, onScopeDispose, ref, shallowRef } from "vue";
import { api } from "../api";
import { t } from "../i18n";
import type { NavigationSettings } from "../model/pages";
import { rowText, type SettingRow } from "../model/settings";
import { useInventoryStore } from "./inventory";
import { lookups } from "./lookup";
import { useRegionStore } from "./region";
import { useScreenStore } from "./screen";
import { useUiStore } from "./ui";

// How long a change made here wins over what Home Assistant still reports.
export const SETTING_EDIT_MS = 4000;
// A lower brightness pulls both dim levels down with it, as on the screen.
const DIM_LEVELS = ["standby_brightness", "night_brightness"];
export type SettingEdit = { value: any; at: number };

export const useSettingsStore = defineStore("settings", () => {
  const inv = useInventoryStore();
  const ui = useUiStore();
  const region = useRegionStore();
  const scr = useScreenStore();

  // The changes made here, by setting, and when.
  const settingEdits = ref<Record<string, SettingEdit>>({});
  // What waits for its pause, the screen it goes to, the pause, and the request on its way.
  const queue = ref<Record<string, any>>({});
  let target: string | null = null, timer = 0;
  const flight = shallowRef<Promise<Response> | null>(null);
  // Whether a change has not gone out yet, or is on its way.
  const settingPending = computed(() => Object.keys(queue.value).length > 0 || flight.value !== null);
  // The looks again after a change came back, each four seconds later.
  const settles = new Set<number>();

  const settingsView = () => scr.currentScreen?.settings;
  function settingValues(): Record<string, any> {
    const view = settingsView(), values = { ...(view?.values || {}) };
    for (const [key, edit] of Object.entries(settingEdits.value)) values[key] = edit.value;
    return values;
  }
  // What a row says: its value with its unit, a duration, a moment in the clock the screens use (Language & region).
  const settingText = (row: SettingRow, values: Record<string, any>) => rowText(row, values, region.clock24);
  // Device navigation settings are separate from the page document. Unknown settings remain permissive for warnings,
  // avoiding a false unreachable report.
  function navigationSettings(): NavigationSettings {
    const values = settingValues();
    return { pageButtons: values.page_buttons !== false, swipe: values.swipe_pages !== false,
      homeButton: scr.supports(0, 2, 100) && values.home_button !== false };
  }

  function setSetting(key: string, value: any, delay: number) {
    // One screen's changes at a time: the ones for the screen shown before go out first.
    if (target && target !== scr.selected && Object.keys(queue.value).length) {
      flushSettings();
      ui.toast(t("editor.screen_settings.other_screen_busy"));
      return;
    }
    target = scr.selected;
    const values = settingValues();
    settingEdits.value[key] = { value, at: Date.now() };
    queue.value[key] = value;
    if (key === "brightness")
      for (const dim of DIM_LEVELS)
        if (values[dim] > value) settingEdits.value[dim] = { value, at: Date.now() };
    clearTimeout(timer);
    timer = window.setTimeout(() => flushSettings(), delay);
  }
  // `unloading`: the page is closing (pagehide), so the request is kept alive past it.
  async function flushSettings(unloading = false) {
    clearTimeout(timer);
    if (flight.value || !Object.keys(queue.value).length || !target) return;
    const screen = target, changes = queue.value;
    queue.value = {};
    const request = api(`screens/${encodeURIComponent(screen)}/settings`, {
      method: "PUT",
      body: JSON.stringify({ settings: changes }),
      keepalive: unloading,
    });
    flight.value = request;
    try {
      const view = await (await request).json();
      const current = inv.inventory.screens.find((s) => s.id === screen);
      if (current) current.settings = view;
    } catch (e: any) {
      ui.toast(e.message);
      // What did not arrive is not kept: the panel shows the screen's own values again.
      if (screen === scr.selected) for (const key of Object.keys(changes)) delete settingEdits.value[key];
      if (screen === scr.selected && changes.brightness !== undefined) for (const dim of DIM_LEVELS) delete settingEdits.value[dim];
    } finally {
      flight.value = null;
      if (Object.keys(queue.value).length) timer = window.setTimeout(() => flushSettings(), 150);
      else target = null;
      if (screen === scr.selected) settleSettings();
      // A value the screen refused or clamped comes back without a live update: look again once edits expire.
      const settle = window.setTimeout(() => { settles.delete(settle); if (screen === scr.selected) settleSettings(); }, SETTING_EDIT_MS + 100);
      settles.add(settle);
    }
  }
  // Values Home Assistant reports take over again once they match a change made here, or after a few seconds
  // (the screen refused or clamped it).
  function settleSettings() {
    const view = settingsView();
    for (const [key, edit] of Object.entries(settingEdits.value)) {
      if (queue.value[key] !== undefined || flight.value) continue;
      if ((view && view.values[key] === edit.value) || Date.now() - edit.at > SETTING_EDIT_MS) delete settingEdits.value[key];
    }
  }
  /** Another screen opens: what waits goes out to the screen it was for, and this one's changes are no longer shown. */
  function leaveScreen() {
    flushSettings();
    settingEdits.value = {};
  }
  /** The open screen went (removed): nothing of it is left to send. */
  function forget() {
    clearTimeout(timer);
    queue.value = {};
    target = null;
    settingEdits.value = {};
  }

  // ---- Started once the page is on the screen (boot.ts); the returned function stops it ----
  // A change still waiting for its short pause goes out when the page closes.
  let running: (() => void) | null = null;
  function start() {
    if (running) return running;
    const scope = effectScope(true);
    scope.run(() => useEventListener(window, "pagehide", () => flushSettings(true)));
    running = () => { running = null; scope.stop(); };
    return running;
  }
  onScopeDispose(() => {
    running?.();
    clearTimeout(timer);
    for (const settle of settles) clearTimeout(settle);
  });

  // The setting ⌘K found (model/palette.ts): the settings page brings its row into sight and marks it a moment.
  const spotlight = ref<string | null>(null);

  return {
    spotlight, settingEdits, settingPending, ...lookups({ settingsView, settingValues, settingText, navigationSettings }),
    setSetting, flushSettings, settleSettings, leaveScreen, forget, start,
  };
});
