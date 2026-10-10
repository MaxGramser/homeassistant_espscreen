// ⌘K (components/CommandPalette.vue): one search for everything the editor has, and a way to act on it. The screens (open,
// identify, update), the editor's actions (save, the tabs, New screen, update every screen, install what is set aside),
// the screens' settings (typing "brightness" finds it on every screen, with its value), the tiles that show an entity
// (on whichever screen they stand), the entities to add to the page that is open, and the plugins (open one, add it to
// this screen). Nothing typed shows what was chosen last first, then the screens and the actions; what is typed searches
// every row by its words, each group with its best matches first. What each row does is handed in (PaletteActions), so
// the rows are worked out here from what the page knows and nothing is done while they are. Pure, with the words from
// the translations.
import { t } from "../i18n";
import { domainInfo } from "./layout";
import { matchesWords, prefixRank, queryWords } from "./search";
import type { Entity, Screen } from "../types";

/** One row: `id` stays the same for the same thing (what was chosen last is kept by it), `hint` says what Enter does. */
export type PaletteItem = {
  id: string; group: string; label: string; detail?: string; icon?: string; glyphText?: string; key?: string; hint?: string;
  /** More words it is found by, beyond its label and detail. */
  words?: string;
  /** Shown only for what is typed, never in the list with nothing typed. */
  typed?: boolean;
  /** What the row is itself: one of the words typed has to be in these, so a screen's name alone does not bring every
   * setting and tile of that screen along. */
  own?: string;
  run: () => void;
};
/** A tile that shows an entity, where it stands (model/broken-tiles.ts tileEntities). */
export type PaletteTile = { screen: Screen; tileId: string; entity: string; label: string; page: number; pageTitle: string };
/** A setting of a screen as its settings page has it: its group's title, its value in words. */
export type PaletteSetting = { screen: Screen; key: string; label: string; group?: string; value: string };
/** A plugin: whether the open screen can take it now (it fits, it is not on it nor set aside for it). */
export type PalettePlugin = { id: string; name: string; summary: string; icon?: string; addable: boolean };
export type PaletteFacts = {
  query: string;
  screens: readonly Screen[];
  /** The open screen, while its layout is in the editor. */
  open: Screen | null;
  /** Its layout has changes that are not saved. */
  dirty: boolean;
  /** It can show an alert (identify). */
  alerts: boolean;
  entities: readonly Entity[];
  /** The entities its tiles show, which one can add again where the firmware takes an entity on several tiles. */
  placed: ReadonlySet<string>;
  repeatable: (id: string) => boolean;
  /** No room for another tile. */
  full: boolean;
  /** An entity's icon, where the add-on has icons. */
  icon?: (id: string) => string;
  /** The ids of the rows chosen last, the last one first. */
  recent?: readonly string[];
  /** Whether a screen can show an alert now (identify): its firmware has one and it is there. */
  canIdentify?: (screen: Screen) => boolean;
  /** The version an update would bring a screen, when one can go now from here. */
  updateTo?: (screen: Screen) => string | null;
  /** How many screens an update waits for, all of them at once. */
  updatesWaiting?: number;
  /** The plugins set aside to install, every screen together. */
  setAside?: number;
  tiles?: readonly PaletteTile[];
  entityName?: (id: string) => string;
  settings?: readonly PaletteSetting[];
  plugins?: readonly PalettePlugin[];
};
export type PaletteActions = {
  openScreen: (screen: Screen) => void;
  go: (route: "#new-screen" | "#firmware" | "#alerts" | "#settings" | "#plugins") => void;
  showTab: (tab: "layout" | "settings") => void;
  save: () => void;
  identify: (screen: Screen) => void;
  exportLayout: () => void;
  addTile: (id: string) => void;
  update?: (screen: Screen) => void;
  updateAll?: () => void;
  installSetAside?: () => void;
  showTile?: (screen: Screen, tileId: string) => void;
  openSetting?: (screen: Screen, key: string) => void;
  openPlugin?: (id: string) => void;
  addPlugin?: (id: string) => void;
};

// How many rows of a group show for what is typed: the best ones; typing more finds the rest.
const SHOWN = { screens: 12, actions: 12, settings: 8, tiles: 8, add: 8, plugins: 6 } as const;
const RECENT = 5;

/** The rows for what is typed, in their groups, in the order the arrow keys walk them. */
export function paletteItems(facts: PaletteFacts, actions: PaletteActions): PaletteItem[] {
  const groups = { recent: t("editor.search.groups.recent"), screens: t("editor.palette.groups.screens"), actions: t("editor.palette.groups.actions"),
    settings: t("editor.search.groups.settings"), tiles: t("editor.search.groups.tiles"), add: t("editor.palette.groups.add"),
    plugins: t("editor.search.groups.plugins") };
  const hint = { open: t("editor.search.hint.open"), run: t("editor.search.hint.run"), show: t("editor.search.hint.show"), add: t("editor.search.hint.add") };
  const rows: Record<keyof typeof SHOWN, PaletteItem[]> = { screens: [], actions: [], settings: [], tiles: [], add: [], plugins: [] };
  const screen = facts.open;

  // ---- The screens, and what can be done to each ----
  for (const each of facts.screens)
    rows.screens.push({ id: `screen:${each.id}`, group: groups.screens, label: each.name, hint: hint.open, glyphText: "▦",
      detail: `${each.online ? t("editor.common.online") : t("editor.common.offline")} · ${each.firmware || t("editor.common.unknown")}`,
      words: [each.area, each.ha_name].filter(Boolean).join(" "), run: () => actions.openScreen(each) });

  // ---- The editor's actions: the open screen's first ----
  const act = rows.actions;
  if (screen) act.push(
    { id: "action:save", group: groups.actions, label: t("editor.common.save_send"), detail: facts.dirty ? t("editor.common.unsaved") : t("editor.palette.nothing_to_save"), key: "⌘S", run: actions.save },
    { id: "action:layout", group: groups.actions, label: t("editor.screen_view.tabs.layout"), detail: screen.name, hint: hint.show, run: () => actions.showTab("layout") },
    { id: "action:settings-tab", group: groups.actions, label: t("editor.screen_view.tabs.settings"), detail: screen.name, hint: hint.show, run: () => actions.showTab("settings") },
    { id: "action:identify", group: groups.actions, label: t("editor.palette.identify"), detail: facts.alerts ? t("editor.palette.identify_detail") : t("editor.palette.identify_needs"),
      run: () => { if (facts.alerts) actions.identify(screen); } },
    { id: "action:export", group: groups.actions, label: t("editor.palette.export"), detail: t("editor.palette.export_detail"), run: actions.exportLayout },
  );
  if (facts.updatesWaiting && actions.updateAll)
    act.push({ id: "action:update-all", group: groups.actions, label: t("editor.search.update_all"), icon: "F06B0", hint: hint.run,
      detail: t("editor.search.update_all_detail", facts.updatesWaiting), run: actions.updateAll });
  if (facts.setAside && actions.installSetAside)
    act.push({ id: "action:install-set-aside", group: groups.actions, label: t("editor.search.install"), icon: "F0A66", hint: hint.run,
      detail: t("editor.search.install_detail", facts.setAside), run: actions.installSetAside });
  act.push(
    { id: "go:new-screen", group: groups.actions, label: t("editor.nav.new_screen"), detail: t("editor.nav.new_screen_detail"), glyphText: "+", run: () => actions.go("#new-screen") },
    { id: "go:firmware", group: groups.actions, label: t("editor.nav.firmware"), icon: "F0241", run: () => actions.go("#firmware") },
    { id: "go:alerts", group: groups.actions, label: t("editor.nav.alerts"), detail: t("editor.palette.alerts_detail"), icon: "F0594", run: () => actions.go("#alerts") },
    { id: "go:settings", group: groups.actions, label: t("editor.nav.settings"), detail: t("editor.palette.settings_detail"), icon: "F0493", run: () => actions.go("#settings") },
  );
  // Each screen's own actions are found by name ("identify kitchen", "update"); the open screen's identify stands above.
  for (const each of facts.screens) {
    if (each.virtual) continue;
    if (each.id !== screen?.id && facts.canIdentify?.(each))
      act.push({ id: `identify:${each.id}`, group: groups.actions, label: t("editor.search.identify", { name: each.name }), detail: t("editor.palette.identify_detail"),
        icon: "F13B4", hint: hint.run, typed: true, run: () => actions.identify(each) });
    const version = facts.updateTo?.(each);
    if (version && actions.update)
      act.push({ id: `update:${each.id}`, group: groups.actions, label: t("editor.search.update", { name: each.name }), detail: t("editor.search.update_detail", { version }),
        icon: "F06B0", hint: hint.run, typed: true, run: () => actions.update!(each) });
  }

  // ---- The screens' settings, as each screen's settings page has them ----
  if (actions.openSetting)
    for (const setting of facts.settings || [])
      // A label that does not say its group ("Starts" of Night) says it beside the screen.
      rows.settings.push({ id: `setting:${setting.screen.id}:${setting.key}`, group: groups.settings, label: setting.label, icon: "F1542", hint: hint.show, typed: true,
        detail: [setting.screen.name, setting.group && !setting.label.toLocaleLowerCase().includes(setting.group.toLocaleLowerCase()) ? setting.group : "", setting.value]
          .filter(Boolean).join(" · "), words: setting.group, own: `${setting.label} ${setting.group || ""}`, run: () => actions.openSetting!(setting.screen, setting.key) });

  // ---- The tiles that show an entity, on every screen ----
  if (actions.showTile)
    for (const tile of facts.tiles || []) {
      const name = facts.entityName?.(tile.entity) || tile.entity;
      rows.tiles.push({ id: `tile:${tile.screen.id}:${tile.tileId}`, group: groups.tiles, label: tile.label || name, icon: facts.icon?.(tile.entity), hint: hint.show, typed: true,
        detail: [tile.screen.name, tile.pageTitle || t("editor.page.label", { page: tile.page + 1 })].join(" · "),
        words: [tile.label ? name : "", tile.entity].join(" "), own: `${tile.label} ${name} ${tile.entity}`, run: () => actions.showTile!(tile.screen, tile.tileId) });
    }

  // ---- The entities the open page can take ----
  if (screen)
    for (const e of facts.entities) {
      // One on the screen comes again when the firmware takes an entity on several tiles (0.16.0+).
      if (e.tile === false || (facts.placed.has(e.id) && !facts.repeatable(e.id))) continue;
      rows.add.push({ id: `add:${e.id}`, group: groups.add, label: e.name, detail: [domainInfo(e.id)[0], e.area].filter(Boolean).join(" · "), icon: facts.icon?.(e.id),
        hint: hint.add, typed: true, words: [e.id, e.device].filter(Boolean).join(" "), run: () => { if (!facts.full) actions.addTile(e.id); } });
    }

  // ---- The plugins: open one, or add it to this screen ----
  if (actions.openPlugin)
    for (const plugin of facts.plugins || []) {
      rows.plugins.push({ id: `plugin:${plugin.id}`, group: groups.plugins, label: plugin.name, detail: plugin.summary, icon: plugin.icon, hint: hint.open, typed: true,
        run: () => actions.openPlugin!(plugin.id) });
      if (screen && plugin.addable && actions.addPlugin)
        rows.plugins.push({ id: `plugin-add:${screen.id}:${plugin.id}`, group: groups.plugins, label: t("editor.search.add_plugin", { plugin: plugin.name, screen: screen.name }),
          detail: t("editor.search.add_plugin_detail"), icon: plugin.icon, hint: hint.add, typed: true, run: () => actions.addPlugin!(plugin.id) });
    }

  const all = Object.values(rows).flat();
  const recent = (facts.recent || []).map((id) => all.find((row) => row.id === id)).filter((row): row is PaletteItem => Boolean(row));
  const words = queryWords(facts.query);
  if (!words.length) {
    // Nothing typed: what was chosen last, then the screens and the actions, each once.
    const first = recent.slice(0, RECENT), shown = new Set(first.map((row) => row.id));
    return [...first.map((row) => ({ ...row, group: groups.recent })),
      ...[...rows.screens, ...rows.actions].filter((row) => !row.typed && !shown.has(row.id))];
  }
  // Something typed: each group's rows that have every word, what was chosen before first, then the best names.
  const rank = new Map(recent.map((row, index) => [row.id, index]));
  const score = (row: PaletteItem) => (rank.has(row.id) ? rank.get(row.id)! - 100 : 0) + prefixRank(row.label, words[0]);
  return (Object.keys(rows) as (keyof typeof SHOWN)[]).flatMap((group) => rows[group]
    .filter((row) => matchesWords(words, row.label, row.detail, row.words) && (row.own === undefined || words.some((word) => matchesWords([word], row.own))))
    .map((row, index) => ({ row, index })).sort((a, b) => score(a.row) - score(b.row) || a.index - b.index)
    .slice(0, SHOWN[group]).map(({ row }) => row));
}
/** The rows under their group, in the order the groups first come, each with its place in the whole list (what the arrow
 * keys walk). */
export function paletteGroups(items: readonly PaletteItem[]) {
  const out: { group: string; items: { item: PaletteItem; index: number }[] }[] = [];
  items.forEach((item, index) => {
    const group = out.find((o) => o.group === item.group) || (out.push({ group: item.group, items: [] }), out[out.length - 1]);
    group.items.push({ item, index });
  });
  return out;
}
/** What was chosen last, the newest first, at most `keep` of them. */
export const rememberChoice = (recent: readonly string[], id: string, keep = 8) => [id, ...recent.filter((other) => other !== id)].slice(0, keep);
