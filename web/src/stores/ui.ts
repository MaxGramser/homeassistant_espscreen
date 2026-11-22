// The page around the screens: the toast, the sheets and menus that are open, the search (⌘K), the phone's editor of
// everyday changes, the view the address names (router.ts), the library drawer's filters, the editor's clock and the
// top bar's fonts. Nothing of it is a screen's: it is how this page is shown in this browser now.
import { syncRef, useTimeoutFn } from "@vueuse/core";
import { defineStore } from "pinia";
import { computed, effectScope, onScopeDispose, ref, shallowRef } from "vue";
import type { RouteLocationRaw } from "vue-router";
import { t } from "../i18n";
import { whenBarFontsLoad } from "../model/topbar";
import { flagSerializer, usePreference } from "../composables/usePreference";
import { showText } from "../composables/useConfirm";
import { atMost, useAtMost } from "../composables/useWidths";
import { iconsRoute, overrideRoute, reportRoute, router } from "../router";
import { APP_SETTINGS_PARTS, SCREEN_SETTINGS_PARTS, type AppSettingsPart, type ScreenSettingsPart } from "../model/settings-parts";

// ---- Routes: the pages of the app as the code names them, "" for the main view (the open screen, else the overview) ----
// The address itself is the router's (router.ts: #/settings, #/screens/<id>, ...); these names stay for every caller.
export const routes = ["", "#settings", "#new-screen", "#firmware", "#events", "#override", "#plugins", "#report", "#icons"] as const;
/** The parts of Events (#/events/<kind>): what an automation fires at the screens. */
export const eventKinds = ["alerts", "doorbell", "alarm", "calls"] as const;
export type EventKind = (typeof eventKinds)[number];
export type Route = (typeof routes)[number];
export type Toast = { message: string; action?: { label: string; run: () => void } };
// What was copied, each with its own sentences so every language can say it its own way.
export type Copied = "api_key" | "log" | "layout_json" | "action_name" | "yaml" | "icon_name" | "empty_color" | "color_name" | "screen_name";

export const useUiStore = defineStore("ui", () => {
  // ---- Toasts ----
  // A toast goes by itself after five seconds, eight when it offers something to do (Undo); a new one starts the count again.
  const notice = ref<Toast | null>(null);
  let toastMs = 5000;
  const toastExpiry = useTimeoutFn(() => { notice.value = null; }, () => toastMs, { immediate: false });
  function toast(message: string, action?: Toast["action"]) {
    notice.value = { message, action };
    toastMs = action ? 8000 : 5000;
    toastExpiry.start();
  }
  function dismissToast() {
    notice.value = null;
  }
  async function copyText(text: string, element?: Element | null, what: Copied = "api_key") {
    try {
      if (!navigator.clipboard || !window.isSecureContext) throw new Error();
      await navigator.clipboard.writeText(text);
      toast(t(`editor.copy.${what}.copied`));
    } catch {
      // Home Assistant over plain http is no secure context, so the Clipboard API is missing there. The old way copies
      // what is selected: the text on the page when there is one, else a hidden textarea holding it. Without anything
      // selected, execCommand still says it copied, and the clipboard stays empty (GitHub #33).
      let spare: HTMLTextAreaElement | null = null;
      const focused = document.activeElement as HTMLElement | null;
      const selection = window.getSelection();
      if (element) {
        const range = document.createRange();
        range.selectNodeContents(element);
        selection?.removeAllRanges();
        selection?.addRange(range);
      } else {
        spare = document.createElement("textarea");
        spare.value = text;
        spare.setAttribute("readonly", "");
        spare.style.cssText = "position: fixed; top: 0; left: 0; width: 1px; height: 1px; opacity: 0";
        document.body.appendChild(spare);
        spare.focus();
        spare.select();
      }
      let copied: boolean;
      try {
        copied = document.execCommand("copy");
      } catch {
        copied = false;
      }
      if (spare) {
        spare.remove();
        selection?.removeAllRanges();
        focused?.focus?.();
        // Nothing on the page to leave selected: the editor shows the text selected, which is what "selected" promises.
        if (!copied) {
          void showText(t(`editor.copy.${what}.selected`), text);
          return;
        }
      }
      toast(t(copied ? `editor.copy.${what}.copied` : `editor.copy.${what}.selected`));
    }
  }
  function openIntegrations() {
    // Pairing happens in Home Assistant itself. This page lives in HA's ingress iframe,
    // so send the top window to Devices & services (same origin); elsewhere open a tab.
    const path = "/config/integrations/dashboard";
    try {
      window.top!.location.assign(path);
    } catch {
      window.open(path, "_blank");
    }
  }

  // ---- What is open: the open screen's tab, its menu, the search, and on a phone its sheets ----
  const tab = ref<"layout" | "settings" | "plugins">("layout");
  const menuOpen = ref(false);
  const palette = ref(false);
  const addSheet = ref(false);
  const pagesSheet = ref(false);
  const previewOpen = ref(false);
  const pageWizardOpen = ref(false);
  // The first layout's dialog (components/AutoLayoutDialog.vue, docs/AUTO_LAYOUT.md).
  const autoLayoutOpen = ref(false);

  // ---- The phone (app 0.4.40) ----
  // A page as narrow as a phone gets the editor of everyday changes: the screen itself, one button to add a tile, a tile's
  // name, icon and colour, and everything else under the screen's menu. Wider pages, and a phone that chose the whole
  // editor (remembered in this browser), keep the editor as it was. The width is the browser's, so a desktop never sees
  // any of it. It is read when the store starts; start() follows it from then on (composables/useWidths.ts).
  const narrowPhone = ref(atMost("phone"));
  const fullEditor = usePreference("esp-screens.full-editor", false, { serializer: flagSerializer });
  const phone = computed(() => narrowPhone.value && !fullEditor.value);
  // The sidebar of a phone, a sheet from the left (App.vue): open until a screen or a page is chosen in it.
  const sideOpen = ref(false);
  function setFullEditor(on: boolean) {
    fullEditor.value = on;
    addSheet.value = false; pagesSheet.value = false; menuOpen.value = false;
  }

  // ---- The view the address names (router.ts) ----
  // The route's name as the pages know it: "" for the main view (a screen or the overview), "#settings" and the rest for
  // the pages of the app. The address bar's Back and Forward change it as go() does.
  const current = router.currentRoute;
  const route = computed<Route>(() => {
    const name = current.value.name;
    return !name || name === "home" || name === "screen" ? "" : (`#${String(name)}` as Route);
  });
  // The main view is the open screen when there is one, else the overview: the session says which (setMainView), so
  // this store needs no screen store (which needs this one).
  let mainView: () => RouteLocationRaw = () => "/";
  function setMainView(view: () => RouteLocationRaw) { mainView = view; }
  // `replace`: in place of the entry the browser has (Layoutbot's Yes on its way through other screens), so Back goes where
  // the person was before, never to a screen only passed through.
  function go(target: Route, { replace = false } = {}) {
    const to = target === "" ? withChat(mainView()) : `/${target.slice(1)}`;
    return replace ? router.replace(to) : router.push(to);
  }
  // Layoutbot's chat (docs/LAYOUTBOT.md): open while the address says so, `#/screens/<id>?chat=layoutbot`, so Back closes
  // it and a reload opens it again. It stays open while the main view moves to another screen (go(""), as its Yes does on
  // its way through the screens and home again), and closes with the screen (the overview, a page of the app).
  const chatOpen = computed(() => current.value.name === "screen" && current.value.query.chat === "layoutbot");
  // The part of the Settings tab stays too while the main view is the screen the address already has (a reload, a link
  // to a part opening its screen), and goes with any other.
  function withChat(view: RouteLocationRaw): RouteLocationRaw {
    if (typeof view !== "object" || !("name" in view) || view.name !== "screen") return view;
    const here = current.value;
    const part = here.name === "screen" && view.params?.id === here.params.id ? here.query.settings : undefined;
    const query = { ...(chatOpen.value ? { chat: "layoutbot" } : {}), ...(typeof part === "string" ? { settings: part } : {}) };
    return Object.keys(query).length ? { ...view, query } : view;
  }
  function openChat(open: boolean) {
    const here = current.value;
    if (open === chatOpen.value || here.name !== "screen") return;
    const { chat: _, ...query } = here.query;
    if (open) return router.push({ name: "screen", params: here.params, query: { ...query, chat: "layoutbot" } });
    // Closed the way it was opened where it can be (Back, the history the address bar walks), else in place.
    const back = (window.history.state as { back?: string | null } | null)?.back;
    const without = router.resolve({ name: "screen", params: here.params, query }).fullPath;
    return back === without ? router.back() : router.replace({ name: "screen", params: here.params, query });
  }
  // The screen whose Override YAML is open (#/override/<profile>): the profile is in the address, so a reload keeps it.
  const overrideProfile = computed(() => current.value.name === "override" ? (String(current.value.params.profile || "") || null) : null);
  function openOverride(profile: string | null) { return router.push(overrideRoute(profile)); }
  // The part of Events that is open (#/events/<kind>): the alerts unless the address names another.
  const eventsKind = computed<EventKind>(() => {
    const kind = current.value.name === "events" ? current.value.params.kind : undefined;
    return (eventKinds as readonly unknown[]).includes(kind) ? (kind as EventKind) : "alerts";
  });
  function openEvents(kind: EventKind) { return router.push({ name: "events", params: { kind } }); }
  // The part of Settings that is open (#/settings/<part>), or null for the list of its parts.
  const settingsPart = computed<AppSettingsPart | null>(() => {
    const part = current.value.name === "settings" ? current.value.params.part : undefined;
    return (APP_SETTINGS_PARTS as readonly unknown[]).includes(part) ? (part as AppSettingsPart) : null;
  });
  function openSettings(part: AppSettingsPart | null) { return router.push(part ? `/settings/${part}` : "/settings"); }
  // The part of the open screen's Settings tab (`?settings=<part>` on its address), or null for the list of its parts.
  // Like the chat, it goes with the screen: another screen, or the overview, opens without it.
  const screenSettingsPart = computed<ScreenSettingsPart | null>(() => {
    const part = current.value.name === "screen" ? current.value.query.settings : undefined;
    return (SCREEN_SETTINGS_PARTS as readonly unknown[]).includes(part) ? (part as ScreenSettingsPart) : null;
  });
  function openScreenSettings(part: ScreenSettingsPart | null, { replace = false } = {}) {
    const here = current.value;
    if (here.name !== "screen" || part === screenSettingsPart.value) return Promise.resolve();
    const { settings: _, ...query } = here.query;
    const to = { name: "screen", params: here.params, query: part ? { ...query, settings: part } : query };
    return replace ? router.replace(to) : router.push(to);
  }
  // The screen whose troubleshooting report is open (#/screens/<id>/report, components/ReportPanel.vue).
  const reportScreen = computed(() => current.value.name === "report" ? (String(current.value.params.id || "") || null) : null);
  function openReport(id: string) { return router.push(reportRoute(id)); }
  // The screen whose icons are open (#/screens/<id>/icons, components/ScreenIconsPanel.vue).
  const iconsScreen = computed(() => current.value.name === "icons" ? (String(current.value.params.id || "") || null) : null);
  function openIcons(id: string) { return router.push(iconsRoute(id)); }

  // ---- The library drawer along the bottom (app 0.4.32): open or folded, remembered in this browser, and its filters ----
  const libraryOpen = usePreference("esp-screens.library-open", true, { serializer: { read: (raw) => raw !== "0", write: (open) => (open ? "1" : "0") } });
  const filter = ref("");
  const search = ref("");
  const room = ref("");
  const hidePlaced = ref(false);

  // ---- The tip beside a tile that grew (app 0.4.89, components/GrowTip.vue) ----
  // Which tile, the size it had and has, and the control set its growing put on it (null: it kept its own). Asking is
  // remembered in this browser: "Don't show this again" leaves the richer default and only the tip goes.
  const growTip = ref<{ tileId: string; before: string; size: string; applied: string | null } | null>(null);
  const growTips = usePreference("esp-screens.grow-tips", true, { serializer: flagSerializer });
  // The tip beside a sensor just added as a meter (LookTip): its other looks, each drawn on the tile as the pointer rests.
  const lookTip = ref<{ tileId: string } | null>(null);
  const lookTips = usePreference("esp-screens.look-tips", true, { serializer: flagSerializer });

  // ---- The editor's clock and the top bar's fonts ----
  // The time the mockup's clocks and "last changed" lines read: the store's start ticks it (composables/useClock.ts).
  const now = shallowRef(Date.now());
  // Counts up once the top bar's fonts have loaded, so what was measured before them is measured again.
  const fontsVersion = ref(0);

  // ---- Started once the page is on the screen (stores/session.ts start); the returned function stops it ----
  let running: (() => void) | null = null;
  function start() {
    if (running) return running;
    const scope = effectScope(true);
    scope.run(() => {
      // The width of a phone, read when the page loads and followed from here on.
      syncRef(useAtMost("phone"), narrowPhone, { direction: "ltr" });
      let fonts = true;
      whenBarFontsLoad(() => { if (fonts) fontsVersion.value++; });
      onScopeDispose(() => { fonts = false; });
    });
    running = () => { running = null; scope.stop(); };
    return running;
  }
  onScopeDispose(() => running?.());

  return {
    notice, toast, dismissToast, copyText, openIntegrations,
    tab, menuOpen, palette, addSheet, pagesSheet, previewOpen, pageWizardOpen, autoLayoutOpen,
    narrowPhone, fullEditor, phone, setFullEditor, sideOpen,
    route, go, setMainView, chatOpen, openChat, settingsPart, openSettings, screenSettingsPart, openScreenSettings, overrideProfile, openOverride, reportScreen, openReport, iconsScreen, openIcons, eventsKind, openEvents,
    libraryOpen, filter, search, room, hidePlaced, growTip, growTips, lookTip, lookTips,
    now, fontsVersion, start,
  };
});
