// The parts of the two settings pages (docs/PAGES.md, "Settings"): a page of the app and a screen's Settings tab each
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
