// The session: what the page does as a whole, over the other stores. It opens a screen (select: asking first about unsaved
// edits) and goes home, closes the open screen when it is removed, opens a new preview screen, says what follows from a
// new inventory, and starts everything the page follows while it is open (start, from boot.ts). The other stores never
// reach up into it, so none of them needs another one that needs it back: the inventory does not know about the draft, the
// builds or the settings, the session tells each of them.
import { defineStore } from "pinia";
import { onScopeDispose } from "vue";
import { send } from "../api";
import { t } from "../i18n";
import { askConfirm } from "../composables/useConfirm";
import { followBuilds } from "../composables/useFirmwareJob";
import { startDrag } from "../drag";
import type { PreviewProfile } from "../model/preview";
import { closeDocument, closeInspector, openDocument, reconcileDocument, startStore, state } from "../store";
import type { Screen } from "../types";
import { useBuildsStore } from "./builds";
import { usePluginsStore } from "./plugins";
import { useRegionStore } from "./region";
import { useScreenStore } from "./screen";
import { useSettingsStore } from "./settings";
import { useTopbarStore } from "./topbar";
import { useUiStore } from "./ui";
import { useInventoryStore } from "./inventory";

export const useSessionStore = defineStore("session", () => {
  const inv = useInventoryStore();
  const ui = useUiStore();
  const scr = useScreenStore();
  const builds = useBuildsStore();
  const settings = useSettingsStore();
  const region = useRegionStore();
  const plugins = usePluginsStore();
  const topbar = useTopbarStore();

  // ---- Opening a screen ----
  // Another screen, or none (the overview). With unsaved changes the editor asks first, and the switch waits for the answer
  // (the promise returned then); otherwise it happens at once. The open screen again, with unsaved changes, comes back to
  // its layout as it is.
  function select(id: string | null): void | Promise<void> {
    if (id === scr.selected && state.document && state.dirty) {
      state.tab = "layout"; ui.menuOpen = false; closeInspector(); ui.go(""); return;
    }
    if (id !== scr.selected && state.dirty) return askConfirm(t("editor.screen_view.confirm.switch")).then((yes) => { if (yes) open(id); });
    open(id);
  }
  function open(id: string | null) {
    // What waits to go to the screen shown before goes out first, and its changes are no longer shown.
    if (id !== scr.selected) settings.leaveScreen();
    scr.selected = id;
    ui.$patch({ menuOpen: false, addSheet: false, pagesSheet: false, previewOpen: false, pageWizardOpen: false });
    // Nothing chosen (the overview, app 0.4.0): the draft that was confirmed away is gone, so nothing is unsaved.
    if (openDocument(inv.inventory.screens.find((item) => item.id === id))) ui.go("");
  }
  // The logo: back to the overview, the way a home key goes home. An unsaved edit asks first, as switching screens does.
  function goHome(): void | Promise<void> {
    const home = () => { if (!scr.selected) ui.go(""); };
    const asking = scr.selected ? select(null) : undefined;
    if (asking) return asking.then(home);
    home();
  }
  // The open screen, without the questions `select` asks: nothing of it is left to save or to send.
  function forgetOpenScreen() {
    settings.forget();
    scr.selected = null;
    closeDocument();
    ui.menuOpen = false;
  }

  // ---- A new preview screen (New screen's preview, app 0.4.32): kept in this browser, and opened ----
  function createVirtualScreen(name: string, profile: PreviewProfile) {
    const screen = inv.createVirtualScreen(name, profile);
    select(screen.id);
    return screen;
  }

  // ---- Removing a screen (app 0.2.112): the mirror of New screen ----
  // Home Assistant, the ESPHome profile and everything kept here, in one request. The sidebar says what goes before it
  // asks; here only what came back is shown. The screen that was open closes without asking about its edits: its layout
  // went with it. A preview screen goes from this browser's storage, where nothing that was not kept goes either.
  async function removeScreen(screen: Screen) {
    if (scr.removing) return false;
    if (screen.virtual) {
      const remaining = inv.inventory.screens.filter((s) => s.id !== screen.id);
      try { inv.persistVirtualScreens(remaining); } catch (e: any) { ui.toast(e.message); return false; }
      if (scr.selected === screen.id) forgetOpenScreen();
      inv.inventory.screens = remaining;
      ui.toast(t("editor.sidebar.remove.done", { name: screen.name }));
      return true;
    }
    scr.removing = screen.id;
    try {
      const result = await send<{ name?: string; kept?: string[] }>(`screens/${encodeURIComponent(screen.id)}`, "DELETE");
      const name = result?.name || screen.name;
      if (scr.selected === screen.id) forgetOpenScreen();
      builds.forget(screen.id);
      inv.inventory.screens = inv.inventory.screens.filter((s) => s.id !== screen.id);
      ui.toast(result?.kept?.length
        ? t("editor.sidebar.remove.kept", { name, file: result.kept[0] })
        : t("editor.sidebar.remove.done", { name }));
      await inv.refresh(false);
      return true;
    } catch (e: any) {
      ui.toast(e.message);
      return false;
    } finally {
      scr.removing = null;
    }
  }

  // ---- A new inventory (a refresh, a poll or the live stream) ----
  // What follows from it, in this order: a build the add-on now names is no longer only asked for, a setting the screen
  // reported back takes over from the change made here, and the open screen's draft is read again when the add-on has a
  // newer one (or a conflict is said when this page has unsaved changes).
  function arrived() {
    builds.prune();
    if (scr.selected) { settings.settleSettings(); reconcileDocument(); }
  }
  // Followed from the moment the session is made (the page makes it as it boots): it is no listener of the page, and a test
  // that makes the session has what follows from a new inventory as the page has it.
  onScopeDispose(inv.onArrival(arrived));

  // ---- Started once the page is on the screen (boot.ts); the returned function stops all of it ----
  // The page around the screens (the address, the width of a phone), the screens' language, a screen setting still
  // waiting when the page closes, the plugins' reactions, the click a finished drag swallows, the inventory with its live
  // stream and polls (closer while something builds), the draft's clocks and page events, the top bar's previews, and
  // the firmware job while something builds (its log).
  let running: (() => void) | null = null;
  function start() {
    if (running) return running;
    const stops = [ui.start(), region.start(), settings.start(), plugins.start(), startDrag(),
      inv.start({ busy: () => builds.anyBuilding }), startStore(), topbar.start(), followBuilds()];
    running = () => { running = null; for (const stop of stops.reverse()) stop(); };
    return running;
  }
  onScopeDispose(() => running?.());

  return { select, goHome, forgetOpenScreen, createVirtualScreen, removeScreen, arrived, start };
});
