// The open screen: which one it is (selected), what its firmware takes (supports, the page and tile rules it reported,
// its pictures, its memory, the items its top bar holds), what can be done to a screen from here (identify it, calibrate
// its touch, rename it, its screensaver, its feedback, letting it perform actions, a test alert), and how each screen is
// doing as the sidebar and the overview say it (model/screen-status.ts). Choosing another screen is the session's
// (stores/session.ts): it asks about unsaved edits first and opens the screen's draft.
import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { send } from "../api";
import { t } from "../i18n";
import { pageTarget, supportsFirmware, versionAtLeast } from "../model/layout";
import { measuring } from "../model/memory";
import pageRules from "../model/page-rules.json";
import * as status from "../model/screen-status";
import { askConfirm } from "../composables/useConfirm";
import type { BoardChoice, FeedbackView, Screen, ScreensaverChoice } from "../types";
import { useBuildsStore } from "./builds";
import { useInventoryStore } from "./inventory";
import { lookups } from "./lookup";
import { useRegionStore } from "./region";
import { useUiStore } from "./ui";

// Whether a screen's board draws pictures, for its firmware preview (firmware 0.46.0 keeps no square for an album cover
// on a board without them): the add-on says it per screen; a preview screen takes it from its board.
export const drawsPictures = (screen?: Screen) =>
  screen?.pictures ?? (screen?.shape?.catalog as Partial<BoardChoice> | undefined)?.camera ?? true;

export const useScreenStore = defineStore("screen", () => {
  const inv = useInventoryStore();
  const ui = useUiStore();
  const builds = useBuildsStore();
  const region = useRegionStore();

  // ---- Which screen is open, and what its firmware says it takes ----
  const selected = ref<string | null>(null);
  const currentScreen = computed<Screen | undefined>(() => inv.inventory.screens.find((s) => s.id === selected.value));
  const firmwareOf = computed(() => status.firmwareVersion(currentScreen.value));
  const supports = (major: number, minor: number, patch: number) => supportsFirmware(firmwareOf.value, major, minor, patch);
  /** Whether the open screen's firmware is this version or newer, the version as the add-on names one ("0.38.0"). */
  const supportsVersion = (version: string) => versionAtLeast(firmwareOf.value, version);
  // Whether the screen's board draws pictures (camera tiles, an album cover): the add-on says so per screen from the
  // board's own camera sizes (app 0.2.94), and this page always comes with that add-on.
  const pictures = computed(() => Boolean(currentScreen.value?.pictures));
  // A new media tile starts with its album cover where the screen draws one (app 0.4.42): a board with pictures, firmware 0.2.78+.
  const coversByDefault = computed(() => pictures.value && supports(0, 2, 78));
  // The memory this screen has for its tiles (firmware 0.34.0+, its hello): the meter beside the tile count, and the
  // library's "nearly full" (model/memory.ts). A screen that is still measuring its room (firmware 0.51.0) has no share
  // yet: the meter says so, and nothing asks.
  const screenMemory = computed(() => currentScreen.value?.memory || null);
  const memoryMeasuring = computed(() => !!screenMemory.value && measuring(screenMemory.value));
  const fullPage = computed(() => {
    const full = currentScreen.value?.full_page;
    return typeof full === "boolean" ? full : supports(0, 2, 62);
  });
  // Several tiles that go to the same page, such as a way back to page 1 on every sub-page (firmware 0.2.65), and any
  // entity on several tiles (firmware 0.16.0, GitHub #83) but a clock with keys, which its keys name.
  const pageTilesRepeat = computed(() => {
    const repeat = currentScreen.value?.page_tiles_repeat;
    return typeof repeat === "boolean" ? repeat : supports(0, 2, 65);
  });
  const entityTilesRepeat = computed(() => {
    const repeat = currentScreen.value?.entity_tiles_repeat;
    return typeof repeat === "boolean" ? repeat : supports(0, 16, 0);
  });
  // A screen without a title, its top bar showing the home key alone (firmware 0.17.0).
  const noTitle = computed(() => {
    const allowed = currentScreen.value?.no_title;
    return typeof allowed === "boolean" ? allowed : supports(0, 17, 0);
  });
  const repeatable = (id: string) => pageTarget(id) > 0 ? pageTilesRepeat.value : entityTilesRepeat.value && !(id in pageRules.keyHolders);
  const pageReady = computed(() => currentScreen.value?.page_capability === "ready" ||
    (currentScreen.value?.page_capability === "offline" && currentScreen.value?.page_last_capability === "ready"));
  // The items one page's top bar takes on this screen: its own (firmware 0.34.0+), else the add-on's six.
  const topbarMax = computed(() => currentScreen.value?.bar_limit || inv.inventory.header?.max_items || 6);

  // ---- Identify and the test alert (app 0.2.73): a screen's own show_alert action ----
  const canAlert = (screen: Screen | undefined) =>
    Boolean(screen && screen.alert_action && versionAtLeast(status.firmwareVersion(screen), inv.inventory.alerts?.min_firmware || "0.2.31"));
  async function identify(screen: Screen) {
    try {
      await send(`screens/${encodeURIComponent(screen.id)}/identify`, "POST");
      ui.toast(t("editor.screen_view.identified", { name: screen.name }));
    } catch (e: any) {
      ui.toast(e.message);
    }
  }
  async function sendTestAlert(target: string, data: Record<string, unknown>) {
    return (await send("alerts/test", "POST", { screen: target, data })) as { sent: number; failed: number; skipped: number; unusable?: string[] };
  }
  // ---- Calibrate touch (app 0.2.117): the screen's own Calibrate touch button, pressed from here ----
  // Only a screen whose panel is one you calibrate has it, and the add-on says so by the button being on its device
  // in Home Assistant. It asks first: the screen goes to the crosses and stays there until someone standing in front
  // of it has tapped all five, so it is not something to set off by accident from a browser.
  async function calibrateTouch(screen: Screen) {
    if (!(await askConfirm(t("editor.screen_settings.actions.calibrate.confirm", { name: screen.name }), { confirm: t("editor.confirm.calibrate") }))) return;
    try {
      await send(`screens/${encodeURIComponent(screen.id)}/calibrate`, "POST");
      ui.toast(t("editor.screen_settings.actions.calibrate.done", { name: screen.name }));
    } catch (e: any) {
      ui.toast(e.message);
    }
  }
  // ---- Does this screen work as you expect (app 0.3.10) ----
  // One request per choice on the feedback card; the add-on keeps the board's key, picks the revision and talks to the
  // website. What comes back replaces the screen's feedback view, so the card and Settings agree at once.
  async function feedbackAction(screen: Screen, body: Record<string, unknown>): Promise<boolean> {
    try {
      const result = await send<{ feedback: Partial<FeedbackView> }>(`screens/${encodeURIComponent(screen.id)}/feedback`, "POST", body);
      const live = inv.inventory.screens.find((s) => s.id === screen.id) || screen;
      if (live.feedback && result?.feedback) live.feedback = { ...live.feedback, ...result.feedback };
      return true;
    } catch (e: any) {
      ui.toast(e.message);
      return false;
    }
  }
  // The screensaver of a screen (app 0.4.48): the change shows at once and the whole choice goes to the add-on, which tells
  // the screen on its next pass. The latest change wins: an answer to an older one is not shown, and only the latest one
  // that failed takes the screensaver back to what it was before it.
  let saverEdits = 0;
  async function setScreensaver(screen: Screen, patch: Partial<ScreensaverChoice>) {
    const before = screen.screensaver;
    if (!before) return;
    const next = { ...before, ...patch };
    screen.screensaver = next;
    if (screen.virtual) return;
    const edit = ++saverEdits;
    try {
      const { show, media, camera, order, off, weather = "auto", more = [], items = [] } = next;
      const result = await send<{ screensaver: ScreensaverChoice }>(`screens/${encodeURIComponent(screen.id)}/screensaver`, "PUT",
        { screensaver: { show, media, camera, order, off, weather, more, items: items.map(({ id: _id, ...item }) => item) } });
      if (result?.screensaver && edit === saverEdits) screen.screensaver = { ...next, ...result.screensaver };
    } catch (e: any) {
      if (edit === saverEdits) screen.screensaver = { ...before };
      ui.toast(e.message);
    }
  }
  // A screen's own name in this app (app 0.4.2): only the editor shows it, so it needs no flash. Empty gives Home Assistant's back.
  async function renameScreen(screen: Screen, name: string) {
    try {
      if (screen.virtual) {
        const updated = { ...screen, name: name.trim() || screen.name };
        inv.persistVirtualScreens(inv.inventory.screens.map(item => item.id === screen.id ? updated : item));
        Object.assign(screen, updated);
        return true;
      }
      const result = await send<{ name: string }>(`screens/${encodeURIComponent(screen.id)}/name`, "PUT", { name });
      const live = inv.inventory.screens.find((s) => s.id === screen.id);
      if (live && result?.name) live.name = result.name;
      return true;
    } catch (e: any) {
      ui.toast(e.message);
      return false;
    }
  }
  // ---- Removing a screen (app 0.2.112): the mirror of New screen ----
  // The screen whose removal is running, so its button waits instead of being pressed twice (app 0.2.112); the removal
  // itself is the session's (stores/session.ts), which closes the screen when it was open.
  const removing = ref<string | null>(null);
  // A screen New screen wrote but that never got its firmware (GitHub #114, app 0.4.32): its profile and what it built go;
  // the app refuses one a paired screen builds from.
  async function forgetPending(file: string, name: string) {
    if (removing.value) return false;
    removing.value = `pending:${file}`;
    try {
      await send(`firmware/profiles/${encodeURIComponent(file)}`, "DELETE");
      inv.inventory.pending = (inv.inventory.pending || []).filter((p) => p.file !== file);
      ui.toast(t("editor.sidebar.remove.done", { name }));
      return true;
    } catch (e: any) {
      ui.toast(e.message);
      return false;
    } finally {
      removing.value = null;
    }
  }
  // Home Assistant ignored a tap of this screen (app 0.4.63): one click turns on the switch in its ESPHome integration's
  // Configure dialog that lets it perform actions (app 0.4.73). `allowing` is the screen whose actions are being allowed.
  const allowing = ref<string | null>(null);
  async function allowActions(screen: Screen) {
    if (allowing.value) return;
    allowing.value = screen.id;
    try {
      const result = await send<{ name?: string }>(`screens/${encodeURIComponent(screen.id)}/allow-actions`, "POST");
      screen.actions_blocked = false;
      ui.toast(t("editor.pages.actions_allowed", { name: result?.name || screen.name }));
    } catch (e: any) {
      ui.toast(e.message);
    } finally {
      allowing.value = null;
    }
  }

  // ---- A screen's status, as the sidebar and the overview show it (model/screen-status.ts) ----
  // The screens' language by its own name (stores/region.ts), for what an update brings.
  const screensLanguage = () => region.languageName(inv.inventory.language?.effective);
  const facts = (screen: Screen): status.StatusFacts => ({ ...builds.building(screen), language: screensLanguage(), now: Date.now() });
  const newLanguageText = computed(() => status.newLanguageText(screensLanguage()));
  const updateState = (screen: Screen) => status.updateState(screen, facts(screen));
  const screenLight = (screen: Screen) => status.screenLight(screen, facts(screen));
  const screenSubline = (screen: Screen) => status.screenSubline(screen, facts(screen));
  const needsAttention = (screen: Screen) => status.needsAttention(screen, facts(screen));

  return {
    selected, currentScreen, firmwareOf, pictures, coversByDefault, screenMemory, memoryMeasuring, fullPage, pageTilesRepeat,
    entityTilesRepeat, noTitle, pageReady, topbarMax, newLanguageText, removing, allowing,
    // What the editor's parts read as they draw (stores/lookup.ts).
    ...lookups({ supports, supportsVersion, repeatable, canAlert, updateState, screenLight, screenSubline, needsAttention }),
    identify, sendTestAlert, calibrateTouch, feedbackAction, setScreensaver, renameScreen, forgetPending, allowActions,
  };
});
