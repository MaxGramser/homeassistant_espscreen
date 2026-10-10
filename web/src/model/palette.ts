// ⌘K (components/CommandPalette.vue): the screens, the editor's actions and, once something is typed, the entities the
// open screen can take, from one search field, in groups. What each row does is handed in (PaletteActions), so the rows
// are worked out here from what the page knows and nothing is done while they are. Pure, with the words from the
// translations.
import { t } from "../i18n";
import { domainInfo } from "./layout";
import { matchesQuery } from "./search";
import type { Entity, Screen } from "../types";

export type PaletteItem = { group: string; label: string; detail?: string; icon?: string; glyphText?: string; key?: string; run: () => void };
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
};
export type PaletteActions = {
  openScreen: (screen: Screen) => void;
  go: (route: "#new-screen" | "#firmware" | "#alerts" | "#settings") => void;
  showTab: (tab: "layout" | "settings") => void;
  save: () => void;
  identify: (screen: Screen) => void;
  exportLayout: () => void;
  addTile: (id: string) => void;
};

/** The rows for what is typed: every screen, the actions (the open screen's first), the entities to add once something is
 * typed (60 rows at most), and of those what the search finds. */
export function paletteItems(facts: PaletteFacts, actions: PaletteActions): PaletteItem[] {
  const q = facts.query.trim().toLocaleLowerCase();
  const list: PaletteItem[] = [];
  const screens = t("editor.palette.groups.screens"), group = t("editor.palette.groups.actions");
  for (const screen of facts.screens)
    list.push({ group: screens, label: screen.name, detail: `${screen.online ? t("editor.common.online") : t("editor.common.offline")} · ${screen.firmware || t("editor.common.unknown")}`,
      glyphText: "▦", run: () => actions.openScreen(screen) });
  const items: PaletteItem[] = [
    { group, label: t("editor.nav.new_screen"), detail: t("editor.nav.new_screen_detail"), glyphText: "+", run: () => actions.go("#new-screen") },
    { group, label: t("editor.nav.firmware"), icon: "F0241", run: () => actions.go("#firmware") },
    { group, label: t("editor.nav.alerts"), detail: t("editor.palette.alerts_detail"), icon: "F0594", run: () => actions.go("#alerts") },
    { group, label: t("editor.nav.settings"), detail: t("editor.palette.settings_detail"), icon: "F0493", run: () => actions.go("#settings") },
  ];
  const screen = facts.open;
  if (screen) {
    items.unshift(
      { group, label: t("editor.common.save_send"), detail: facts.dirty ? t("editor.common.unsaved") : t("editor.palette.nothing_to_save"), key: "⌘S", run: actions.save },
      { group, label: t("editor.screen_view.tabs.layout"), detail: screen.name, run: () => actions.showTab("layout") },
      { group, label: t("editor.screen_view.tabs.settings"), detail: screen.name, run: () => actions.showTab("settings") },
      { group, label: t("editor.palette.identify"), detail: facts.alerts ? t("editor.palette.identify_detail") : t("editor.palette.identify_needs"),
        run: () => { if (facts.alerts) actions.identify(screen); } },
      { group, label: t("editor.palette.export"), detail: t("editor.palette.export_detail"), run: actions.exportLayout },
    );
  }
  list.push(...items);
  if (screen && q) {
    for (const e of facts.entities) {
      // One on the screen comes again when the firmware takes an entity on several tiles (0.16.0+).
      if (e.tile === false || (facts.placed.has(e.id) && !facts.repeatable(e.id))) continue;
      if (!matchesQuery(q, e.name, e.id, e.area, e.device)) continue;
      list.push({ group: t("editor.palette.groups.add"), label: e.name, detail: [domainInfo(e.id)[0], e.area].filter(Boolean).join(" · "), icon: facts.icon?.(e.id),
        run: () => { if (!facts.full) actions.addTile(e.id); } });
      if (list.length > 60) break;
    }
  }
  return q ? list.filter((item) => matchesQuery(q, item.label, item.detail)) : list;
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
