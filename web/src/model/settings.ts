// ---- Screen settings: the same groups and rows as the settings page on the screen itself ----
// Every change applies at once, like on the screen; no Save needed. A screen with firmware 0.2.49+ owns its
// settings and ESP Screens changes them through its entities in Home Assistant. A group's title and a row's label
// are the texts editor.screen_settings.groups.<group> and editor.screen_settings.rows.<key> (app 0.2.90). The store
// keeps what is being changed and sends it (setSetting); this is the table and its arithmetic.
import { t } from "../i18n";

export const SETTING_GROUPS = [
  { group: "brightness", icon: "F0599", rows: [
    { key: "brightness", kind: "number", min: 5, max: 100, step: 5, unit: "%" },
    { key: "dark_mode", kind: "toggle" },
    { key: "standby_enabled", kind: "toggle" },
    { key: "standby_seconds", kind: "duration", min: 60, max: 86400, needs: "standby_enabled" },
    { key: "standby_brightness", kind: "number", min: 0, max: 100, step: 5, unit: "%", needs: "standby_enabled", cap: "brightness" },
  ] },
  { group: "night", icon: "F0594", rows: [
    { key: "night_enabled", kind: "toggle" },
    { key: "night_start", kind: "moment", needs: "night_enabled" },
    { key: "night_end", kind: "moment", needs: "night_enabled" },
    { key: "night_brightness", kind: "number", min: 0, max: 100, step: 5, unit: "%", needs: "night_enabled", cap: "brightness" },
  ] },
  { group: "screen", icon: "F0379", rows: [
    { key: "auto_home", kind: "toggle" },
    { key: "auto_home_seconds", kind: "duration", min: 30, max: 3600, needs: "auto_home" },
    { key: "home_on_standby", kind: "toggle" },
    { key: "swipe_pages", kind: "toggle" },
    { key: "page_buttons", kind: "toggle" },
    { key: "home_button", kind: "toggle" },
    { key: "rotation", kind: "choice", options: [0, 90, 180, 270] },
  ] },
] as const;
export type SettingRow = (typeof SETTING_GROUPS)[number]["rows"][number] & { min?: number; max?: number; step?: number; unit?: string; needs?: string; cap?: string; options?: readonly unknown[] };
export const settingLabel = (row: SettingRow) => t(`editor.screen_settings.rows.${row.key}`);
// A choice in the same words in every language: the rotation's angle. The clock left this page for Settings → Language
// & region, one choice for every screen (app 0.2.90).
export const choiceText = (_row: SettingRow, value: unknown) => `${value}°`;

// The same steps as settings_screen.h: seconds low down, quarters of an hour up top; times by the quarter,
// whole hours while held.
export const ladderStep = (seconds: number) => (seconds < 300 ? 30 : seconds < 900 ? 60 : seconds < 3600 ? 300 : seconds < 7200 ? 900 : 1800);
export function steppedSetting(row: SettingRow, value: number, direction: number, held: boolean, values: Record<string, any>) {
  if (row.kind === "moment") {
    let next = held && value % 60 ? Math.floor(value / 60) * 60 + (direction > 0 ? 60 : 0) : value + direction * (held ? 60 : 15);
    next %= 1440;
    return next < 0 ? next + 1440 : next;
  }
  const step = row.kind === "duration" ? ladderStep(direction < 0 ? value - 1 : value) : row.step!;
  const max = row.cap ? Math.min(row.max!, values[row.cap]) : row.max!;
  return Math.min(max, Math.max(row.min!, value + direction * step));
}
export function durationText(seconds: number) {
  if (seconds < 60) return t("editor.screen_settings.duration.seconds", { n: seconds });
  if (seconds < 3600) return t("editor.screen_settings.duration.minutes", { n: Math.floor(seconds / 60) });
  const hours = Math.floor(seconds / 3600), minutes = Math.floor((seconds % 3600) / 60);
  return minutes
    ? t("editor.screen_settings.duration.hours_minutes", { h: hours, m: String(minutes).padStart(2, "0") })
    : t("editor.screen_settings.duration.hours", { n: hours });
}
export function momentText(minutes: number, clock24: boolean) {
  const hour = Math.floor(minutes / 60), minute = String(minutes % 60).padStart(2, "0");
  if (clock24) return `${String(hour).padStart(2, "0")}:${minute}`;
  return t(hour < 12 ? "editor.screen_settings.time.am" : "editor.screen_settings.time.pm", { time: `${hour % 12 || 12}:${minute}` });
}
/** What a row says: its value with its unit, a duration, a moment on a 24- or 12-hour clock. */
export function rowText(row: SettingRow, values: Record<string, any>, clock24: boolean) {
  const value = values[row.key];
  // Home Assistant has no value while the screen is offline or the entity is off.
  if (value === null || value === undefined) return "—";
  if (row.kind === "number") return `${value}${row.unit || ""}`;
  if (row.kind === "duration") return durationText(value);
  if (row.kind === "moment") return momentText(value, clock24);
  return "";
}
