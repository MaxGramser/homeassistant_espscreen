// The page around the screens: the toast, the sheets and menus that are open, the search (⌘K), the phone's editor of
// everyday changes, the view the address names (the hash), the library drawer's filters, the editor's clock and the
// top bar's fonts. Nothing of it is a screen's: it is how this page is shown in this browser now.
import { syncRef, useEventListener, useTimeoutFn } from "@vueuse/core";
import { defineStore } from "pinia";
import { computed, effectScope, onScopeDispose, ref, shallowRef } from "vue";
import { t } from "../i18n";
import { whenBarFontsLoad } from "../model/topbar";
import { flagSerializer, usePreference } from "../composables/usePreference";
import { showText } from "../composables/useConfirm";
import { atMost, useAtMost } from "../composables/useWidths";

// ---- Routes: the hash keeps a view open across a reload (#settings did before) ----
export const routes = ["", "#settings", "#new-screen", "#firmware", "#alerts", "#override", "#plugins"] as const;
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
      let copied = false;
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

  // ---- What is open: the screen's menu, the search, and on a phone its sheets ----
  const menuOpen = ref(false);
  const palette = ref(false);
  const addSheet = ref(false);
  const pagesSheet = ref(false);
  const previewOpen = ref(false);
  const pageWizardOpen = ref(false);

  // ---- The phone (app 0.4.40) ----
  // A page as narrow as a phone gets the editor of everyday changes: the screen itself, one button to add a tile, a tile's
  // name, icon and colour, and everything else under the screen's menu. Wider pages, and a phone that chose the whole
  // editor (remembered in this browser), keep the editor as it was. The width is the browser's, so a desktop never sees
  // any of it. It is read when the store starts; start() follows it from then on (composables/useWidths.ts).
  const narrowPhone = ref(atMost("phone"));
  const fullEditor = usePreference("esp-screens.full-editor", false, { serializer: flagSerializer });
  const phone = computed(() => narrowPhone.value && !fullEditor.value);
  function setFullEditor(on: boolean) {
    fullEditor.value = on;
    addSheet.value = false; pagesSheet.value = false; menuOpen.value = false;
  }

  // ---- The view the address names ----
  const hash = ref(location.hash);
  const route = computed<Route>(() => (routes.includes(hash.value as Route) ? (hash.value as Route) : ""));
  function go(target: Route) {
    if (location.hash === target) { hash.value = target; return; }
    location.hash = target;
  }
  // The address bar's back and forward, and go() above: start() follows the hash.
  function followHash() { hash.value = location.hash; window.scrollTo(0, 0); }
  // The screen whose Override YAML is open (#override), by its profile and its name.
  const overrideProfile = ref<string | null>(null);
  const overrideFriendly = ref("");

  // ---- The library drawer along the bottom (app 0.4.32): open or folded, remembered in this browser, and its filters ----
  const libraryOpen = usePreference("esp-screens.library-open", true, { serializer: { read: (raw) => raw !== "0", write: (open) => (open ? "1" : "0") } });
  const filter = ref("");
  const search = ref("");
  const room = ref("");
  const hidePlaced = ref(false);

  // ---- The editor's clock and the top bar's fonts ----
  // The time the mockup's clocks and "last changed" lines read: the store's start ticks it (composables/useClock.ts).
  const now = shallowRef(Date.now());
  // Counts up once the top bar's fonts have loaded, so what was measured before them is measured again.
  const fontsVersion = ref(0);

  // ---- Started once the page is on the screen (store.ts startStore); the returned function stops it ----
  let running: (() => void) | null = null;
  function start() {
    if (running) return running;
    const scope = effectScope(true);
    scope.run(() => {
      // The width of a phone, read when the page loads and followed from here on.
      syncRef(useAtMost("phone"), narrowPhone, { direction: "ltr" });
      hash.value = location.hash;
      useEventListener(window, "hashchange", followHash);
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
    menuOpen, palette, addSheet, pagesSheet, previewOpen, pageWizardOpen,
    narrowPhone, fullEditor, phone, setFullEditor,
    hash, route, go, overrideProfile, overrideFriendly,
    libraryOpen, filter, search, room, hidePlaced,
    now, fontsVersion, start,
  };
});
