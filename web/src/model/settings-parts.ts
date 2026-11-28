// The parts of the pages of parts (docs/PAGES.md, "Pages of parts"): the app's Settings, a screen's Settings tab and Events each
// open on a list of these parts, one row per part with what is set now, and a part opens as a page of its own. The part
// is in the address, so a link, a reload and Back reach it: #/settings/<part> for the app, `?settings=<part>` on a
// screen's address for its tab.

/** The parts of the app's Settings page (#/settings/<part>), in the order the list shows them. */
export const APP_SETTINGS_PARTS = ["updates", "builds", "language", "plugins", "home-assistant"] as const;
export type AppSettingsPart = (typeof APP_SETTINGS_PARTS)[number];

/** The parts of a screen's Settings tab (`?settings=<part>`), in the order the list shows them. */
export const SCREEN_SETTINGS_PARTS = ["display", "standby", "navigation", "board", "help"] as const;
export type ScreenSettingsPart = (typeof SCREEN_SETTINGS_PARTS)[number];

/** The rows of the screen's own settings (model/settings.ts SETTING_GROUPS) each part of the tab shows, by key and in
 *  this order. The screen's own page keeps its groups; the editor groups by what a person looks for. A part with more
 *  than one block names each block's title (editor.screen_settings.blocks.<block>). */
export const SCREEN_PART_ROWS: Partial<Record<ScreenSettingsPart, readonly { block: string; keys: readonly string[] }[]>> = {
  display: [{ block: "display", keys: ["brightness", "dark_mode", "rotation"] }],
  standby: [
    { block: "standby", keys: ["standby_enabled", "standby_seconds", "standby_brightness"] },
    { block: "night", keys: ["night_enabled", "night_start", "night_end", "night_brightness"] },
  ],
  navigation: [{ block: "navigation", keys: ["auto_home", "auto_home_seconds", "home_on_standby", "swipe_pages", "page_buttons", "loop_pages", "home_button"] }],
};

/** The part of the screen's tab that shows a setting (⌘K opens it there). */
export function screenPartOf(key: string): ScreenSettingsPart | null {
  for (const part of SCREEN_SETTINGS_PARTS) if (SCREEN_PART_ROWS[part]?.some((block) => block.keys.includes(key))) return part;
  return null;
}

export type { Tone } from "./parts";
import type { Tone } from "./parts";
import type { IconName } from "./ui-icons";

/** The parts of Events (#/events/<kind>): what Home Assistant shows on the screens. The first card is what an
 *  automation fires (an alert, a doorbell's ring), the second what the screens follow themselves (the alarm, a call). */
export const EVENT_PARTS = ["alerts", "doorbell", "alarm", "calls"] as const;
export type EventPart = (typeof EVENT_PARTS)[number];

/** How each part stands in its list (model/parts.ts): its icon, the colour of the round behind it, and the card it is in
 *  (like Home Assistant's Settings, a few separate cards of rows rather than one long one). */
export type PartLook = { icon: IconName; tone: Tone; card: number };
export const PART_LOOK: Record<AppSettingsPart | ScreenSettingsPart | EventPart, PartLook> = {
  updates: { icon: "update", tone: "teal", card: 0 }, builds: { icon: "hammer-wrench", tone: "orange", card: 0 },
  language: { icon: "translate", tone: "violet", card: 1 }, plugins: { icon: "puzzle-outline", tone: "yellow", card: 1 },
  "home-assistant": { icon: "home-assistant", tone: "blue", card: 1 },
  display: { icon: "white-balance-sunny", tone: "orange", card: 0 }, standby: { icon: "weather-night", tone: "indigo", card: 0 },
  navigation: { icon: "gesture-swipe", tone: "green", card: 0 }, board: { icon: "chip", tone: "rose", card: 1 },
  help: { icon: "lifebuoy", tone: "cyan", card: 2 },
  alerts: { icon: "bell-ring-outline", tone: "yellow", card: 0 }, doorbell: { icon: "doorbell", tone: "orange", card: 0 },
  alarm: { icon: "shield-home-outline", tone: "rose", card: 1 }, calls: { icon: "phone-ring-outline", tone: "green", card: 1 },
};
