// The top bar of a page (app 0.2.105): its items, as the editor lists, adds, moves and takes them off (undo included), a
// page's bar copied onto others, the home key, and what each item shows on the mockup. An entity item shows what the screen
// will show (the add-on's header-preview), asked for when the items change and again every half minute while a screen is
// open: the store follows them from its start (boot.ts), the draft never asks.
import { defineStore } from "pinia";
import { effectScope, onScopeDispose, ref, watch } from "vue";
import { send } from "../api";
import { t } from "../i18n";
import { clockSample } from "../model/clock";
import * as pages from "../model/pages";
import { agoText, batteryView, itemKey, LINK_GLYPH, SAMPLE_BATTERY, SAMPLE_RSSI, type ItemView, wifiView } from "../model/topbar";
import { useVisibleInterval } from "../composables/useVisibleInterval";
import { applyDocument, closeInspector, heldTo, openBar, pageAt, state } from "../store";
import type { HeaderItem } from "../types";
import { useEntitiesStore } from "./entities";
import { useInventoryStore } from "./inventory";
import { lookups } from "./lookup";
import { usePluginsStore } from "./plugins";
import { useRegionStore } from "./region";
import { useScreenStore } from "./screen";
import { useSettingsStore } from "./settings";
import { useUiStore } from "./ui";

type Toast = ReturnType<typeof useUiStore>["toast"];
// One ordered list of bar items with the editor's add, update, move and remove (undo included): a page's top bar and the
// screensaver clock's row are both one (stores/screensaver.ts). `label` names an item in the toast that takes it off.
export function itemList(o: {
  items: () => HeaderItem[]; set: (items: HeaderItem[]) => void; max: () => number; open: (index: number) => void;
  inspector: string; same: (a: HeaderItem, b: HeaderItem) => boolean; label: (item: HeaderItem) => string; toast: Toast;
  full: () => string; already: () => string; removed: (name: string) => string; added?: (item: HeaderItem) => void; back?: () => void;
}) {
  return {
    add(item: HeaderItem) {
      const items = o.items();
      if (items.length >= o.max()) return o.toast(o.full());
      if (items.some((other) => o.same(other, item))) return o.toast(o.already());
      o.added?.(item);
      o.set([...items, item]);
      o.open(items.length);
    },
    update(index: number, patch: Partial<HeaderItem>) {
      const items = [...o.items()];
      if (!items[index]) return;
      items[index] = { ...items[index], ...patch };
      o.set(items);
    },
    move(from: number, to: number) {
      const items = [...o.items()];
      if (to < 0 || to >= items.length || from === to) return false;
      items.splice(to, 0, ...items.splice(from, 1));
      o.set(items);
      return true;
    },
    remove(index: number) {
      const items = [...o.items()];
      const [item] = items.splice(index, 1);
      if (!item) return;
      if (state.inspector?.kind === o.inspector) (o.back || closeInspector)();
      o.set(items);
      o.toast(o.removed(o.label(item)), {
        label: t("editor.common.undo"),
        run: () => { const back = [...o.items()]; back.splice(Math.min(index, back.length), 0, item); o.set(back); },
      });
    },
  };
}

export const useTopbarStore = defineStore("topbar", () => {
  const inv = useInventoryStore();
  const ui = useUiStore();
  const scr = useScreenStore();
  const entities = useEntitiesStore();
  const region = useRegionStore();
  const plugins = usePluginsStore();
  const settings = useSettingsStore();

  // ---- A page's top bar ----
  // Without a stored top bar the screen shows what it always did: the clock of show_clock.
  const topbarItems = (page = state.barPage): HeaderItem[] => pageAt(page)?.topbar.trailing || [];
  function setTopbarItems(items: HeaderItem[], page = state.barPage) {
    if (!state.document || !state.documentGrid || !state.document.pages[page]) return;
    try { applyDocument(pages.setBarItems(state.document, heldTo(state.documentGrid), state.document.pages[page].id, items, !scr.pageReady)); }
    catch (error: any) { ui.toast(error.message); }
  }
  function copyPageBars(source: string, targets: string[], whole: boolean) {
    if (!scr.pageReady || !state.document || !state.documentGrid || !targets.length) return false;
    try { return applyDocument(pages.replaceBar(state.document, heldTo(state.documentGrid), source, targets, whole)); }
    catch (error: any) { ui.toast(error.message); return false; }
  }
  // The home key in the top bar of the mockup (app 0.2.122, firmware 0.2.100+), the Tessera mark since firmware 0.10.0: on
  // every page, as on the screen, unless the screen's Show home button is off. A screen whose value nobody can read right
  // now (offline) is drawn as set.
  const homeKeyShown = (page = state.barPage) =>
    scr.supports(0, 2, 100) && settings.settingValues().home_button !== false && Boolean(pageAt(page)?.topbar.leading.length);

  // ---- What an item is called, and what it shows right now ----
  function topbarLabel(item: HeaderItem) {
    if (item.type === "entity") return entities.entityName(item.entity!);
    if (item.type === "plugin") return plugins.barItemOf(item.item)?.label || item.item || "";
    return inv.inventory.header?.builtin.find((b) => b.type === item.type)?.label || item.type;
  }
  // What the item shows right now: { icon, text, color, shown }. Entities wait for the add-on's preview.
  function topbarView(item: HeaderItem): ItemView {
    if (item.type === "clock" || item.type === "date") {
      const clock = clockSample(ui.now, region.clock24, region.screenLanguage);
      return { text: item.type === "clock" ? clock.time : clock.date, shown: true };
    }
    if (item.type === "analog") return { analog: true, shown: true };
    // The screen's own items (firmware 0.38.0): a good signal, and every link there, so the link mark hides.
    const percent = (n: number) => `${n}${region.screenText("screen.number.percent")}`;
    if (item.type === "wifi") return wifiView(item, SAMPLE_RSSI, percent);
    if (item.type === "link") return { icon: LINK_GLYPH, text: "", shown: false };
    // The battery (firmware 0.41.0): three quarters and not charging, as the firmware's preview draws it.
    if (item.type === "battery") return batteryView(item, SAMPLE_BATTERY, false, percent);
    // A plugin's item shows its example, or its icon alone when a person chose so (plugin API 0.8).
    if (item.type === "plugin") { const known = plugins.barItemOf(item.item); return { icon: known?.icon || "F0A66", text: item.content === "icon" ? "" : known?.example || "", shown: true }; }
    const p = entities.topbarPreviews[itemKey(item)];
    if (!p) return { icon: item.icon === "none" ? null : entities.iconNamed(item.icon)?.cp || entities.automaticIcon(item.entity!), text: item.content === "icon" ? "" : "…", shown: true, loading: true };
    return { icon: p.i || null, text: p.k === "ago" ? agoText(p.e, Math.floor(ui.now / 1000), region.screenLanguage) : p.t, color: p.c ? `#${p.c}` : null, shown: p.shown };
  }

  // ---- Adding, moving and taking items off a page's bar ----
  // The new chip lights up briefly so the eye finds it.
  const topbarAdded = ref<null | { key: string; time: number }>(null);
  const topbarList = itemList({
    items: () => topbarItems(), set: (items) => setTopbarItems(items), max: () => scr.topbarMax, open: (index) => openBar(index), inspector: "bar",
    same: (a, b) => itemKey(a) === itemKey(b), label: topbarLabel, toast: (message, action) => ui.toast(message, action),
    full: () => t("editor.topbar.full", scr.topbarMax), already: () => t("editor.topbar.already"),
    removed: (name) => t("editor.topbar.removed", { name }),
    added: (item) => { topbarAdded.value = { key: itemKey(item), time: Date.now() }; },
  });

  // ---- The entity items as the screen will show them (stores/entities.ts topbarPreviews) ----
  // Every page's bar and the screensaver clock's row, each item once, asked for after a short pause, in sixes as a header
  // takes them; an answer for a screen no longer open, or for an item no longer used, is dropped.
  const used = () => [...(state.document?.pages.flatMap((page) => page.topbar.trailing) || []), ...(scr.currentScreen?.screensaver?.items || [])];
  let timer = 0;
  function loadTopbarPreview(delay = 150) {
    clearTimeout(timer);
    timer = window.setTimeout(async () => {
      const screen = scr.selected;
      const entityItems = [...new Map(used().map((item) => [itemKey(item), item])).values()].filter((item) => item.type === "entity");
      if (!entityItems.length) return;
      try {
        for (let at = 0; at < entityItems.length; at += 6) {
          const batch = entityItems.slice(at, at + 6), data = await send("header-preview", "POST", { header: { items: batch.map(({ id: _id, ...item }) => item) } });
          if (scr.selected !== screen) return;
          const stillUsed = new Set(used().map(itemKey));
          batch.forEach((item, i) => { if (stillUsed.has(itemKey(item))) entities.topbarPreviews[itemKey(item)] = data.items[i]; });
        }
      } catch {
        // Keep the last preview; the next change or the next half minute tries again.
      }
    }, delay);
  }

  // ---- Started once the page is on the screen (stores/session.ts start); the returned function stops it ----
  // The previews follow the items: at once for another screen or a change of the screensaver clock's row, after a short
  // pause for a page's bar (typing), and every half minute while a screen is open and nothing is dragged.
  let running: (() => void) | null = null;
  function start() {
    if (running) return running;
    const scope = effectScope(true);
    scope.run(() => {
      const keys = (items: HeaderItem[]) => items.filter((item) => item.type === "entity").map(itemKey).join("|");
      watch([() => scr.selected, () => keys(state.document?.pages.flatMap((page) => page.topbar.trailing) || []),
        () => keys(scr.currentScreen?.screensaver?.items || [])],
      ([screen, , saver], [before, , saverBefore]) => loadTopbarPreview(screen !== before || saver !== saverBefore ? 0 : 150));
      useVisibleInterval(() => loadTopbarPreview(0), 30000, { when: () => Boolean(state.layout) && !state.drag.active });
    });
    running = () => { running = null; scope.stop(); };
    return running;
  }
  onScopeDispose(() => { running?.(); clearTimeout(timer); });

  return {
    topbarAdded,
    // What the mockup and the drawer read as they draw (stores/lookup.ts).
    ...lookups({ topbarItems, homeKeyShown, topbarLabel, topbarView }),
    setTopbarItems, copyPageBars, addTopbarItem: topbarList.add, moveTopbarItem: topbarList.move, removeTopbarItem: topbarList.remove,
    loadTopbarPreview, start,
  };
});
