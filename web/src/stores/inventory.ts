// What the add-on says: its inventory of screens, Home Assistant's entities and the catalogues the editor draws with
// (api/inventory), read in full and polled light, and followed over the live stream (api/events); whether the add-on can
// be reached and Home Assistant is connected; the editor's features it turns on; and the preview screens this browser
// keeps beside the add-on's screens. What follows from a new inventory is not this store's to say: whoever follows it
// (onArrival, the session) is told, so the inventory never reaches into the draft, the builds or the settings.
import { useEventListener } from "@vueuse/core";
import { defineStore } from "pinia";
import { computed, effectScope, onScopeDispose, ref } from "vue";
import { getJson, send, setCsrf } from "../api";
import { editorLanguage, t } from "../i18n";
import * as pages from "../model/pages";
import { previewGrids, usablePreview, validPreviewShape, type PreviewProfile } from "../model/preview";
import { sizesOn } from "../model/sizes";
import { slug } from "../model/slug";
import { readStored, writeStored } from "../storage";
import renderer from "../wasm/renderer.json";
import type { Inventory, PageDocument, Screen } from "../types";
import { lookups } from "./lookup";
import { useUiStore } from "./ui";

const VIRTUAL_SCREENS_KEY = "esp-screens.virtual-screens";
// The browser opens a broken stream again by itself, but one it gave up on (CLOSED: ingress answered 502 while the add-on
// restarted) stays closed: a new stream is opened instead, a little later each time, and the polls stand in meanwhile; a
// stream that opens starts the count again.
export const RECONNECT_MS = [1000, 2000, 5000, 10000, 30000];
// The whole catalogue again every five minutes; a light poll carries only the screens and the update status.
export const FULL_REFRESH_MS = 300000;
// How often the inventory is polled: rarely while the stream is open, every three seconds while something builds (or the
// add-on updates), every ten otherwise.
export const POLL_MS = { live: 60000, busy: 3000, down: 10000 };

export type Live = { busy?: () => boolean };

export const useInventoryStore = defineStore("inventory", () => {
  const ui = useUiStore();

  const inventory = ref<Inventory>({ screens: [], entities: [] } as Inventory);
  // Whether the add-on answered the last request for its inventory, and whether it is connected to Home Assistant.
  const reachable = ref(true);
  const connected = computed(() => Boolean(inventory.value.connected));
  // The editor's features the add-on turns on (UI experiments, opt-in; saved documents and device support stay independent).
  const tallerTilesEnabled = computed(() => inventory.value.editor_features?.tall_tiles === true);
  // Plugins are on in the dev app (editor_features.plugins, docs/PLUGINS.md) and in `npm run dev`: a person with a released
  // add-on never sees the page or the tab. The add-on takes plugin tiles and items only then.
  const pluginsEnabled = computed(() => import.meta.env.DEV || inventory.value.editor_features?.plugins === true);
  // An entity by its id, the first one of that id as the list has it: a card asks for its own many times as it is drawn,
  // where looking through the whole list each time took long on a page of many tiles.
  const entityIndex = computed(() => {
    const index = new Map<string, Inventory["entities"][number]>();
    for (const entity of inventory.value.entities) if (!index.has(entity.id)) index.set(entity.id, entity);
    return index;
  });
  const entityOf = (id: string) => entityIndex.value.get(id);

  // ---- Preview screens (app 0.4.32): kept in this browser's storage, shown beside the add-on's screens ----
  // What a preview screen's firmware says it takes, as a screen of that grid says it (the five names and its spans). One
  // that no longer reads is left out with a word about it (model/preview.ts usablePreview), the word said once for the
  // same names.
  let previewsSkipped = "";
  function virtualScreens(): Screen[] {
    let value: any[];
    try {
      const stored = JSON.parse(readStored(VIRTUAL_SCREENS_KEY) || "[]");
      value = Array.isArray(stored) ? stored : [];
    } catch { value = []; }
    const usable = value.filter((s) => usablePreview(s, pluginsEnabled.value));
    const skipped = value.filter((s) => !usable.includes(s)).map((s) => (typeof s?.name === "string" && s.name) || "?").join(", ");
    if (skipped && skipped !== previewsSkipped) { previewsSkipped = skipped; setTimeout(() => ui.toast(t("editor.preview.skipped", { names: skipped })), 0); }
    return usable.map((s) => ({ ...s, firmware: renderer.firmware, firmware_known: renderer.firmware,
      tile_sizes: sizesOn(s.shape), grids: previewGrids(s.shape, s.orientation), page_capability: 'ready' }));
  }
  // A storage that keeps nothing (a private window, full or blocked) is said in the page's words, not the browser's, to
  // whoever wrote: a new preview screen, a save, a rename, a removal. Each writes here first, so what was not kept is not
  // changed either.
  function persistVirtualScreens(screens = inventory.value.screens) {
    if (!writeStored(VIRTUAL_SCREENS_KEY, JSON.stringify(screens.filter((s) => s.virtual)))) throw new Error(t("editor.preview.not_kept"));
  }
  // A preview screen kept before page documents (app 0.3.1) is brought to one by the add-on, once; one it cannot bring
  // keeps what was kept.
  async function migrateVirtualScreens() {
    for (const screen of virtualScreens()) {
      if (screen.page_document?.format === 'pages-v2') continue;
      const sourceGrid = { columns: screen.shape!.columns, rows: screen.shape!.rows };
      try {
        const record = await send<PageDocument>('firmware-preview/import', 'POST', { document: screen.layout, sourceGrid });
        record.revision = pages.instanceId();
        persistVirtualScreens(virtualScreens().map(current => current.id === screen.id && !current.page_document
          ? { ...current, page_document: record, source_grid: record.sourceGrid } : current));
      } catch (error: any) { ui.toast(error.message); }
    }
    return virtualScreens();
  }
  // A new preview screen, kept in this browser; the session opens it (stores/session.ts createVirtualScreen).
  function createVirtualScreen(name: string, profile: PreviewProfile) {
    if (!name.trim() || !validPreviewShape(profile.shape)) throw new Error(t("editor.preview.invalid_shape"));
    const { board, orientation } = profile;
    const shape = JSON.parse(JSON.stringify(profile.shape));
    const id = `virtual.${slug(name) || "preview"}-${Date.now().toString(36)}`;
    const sourceGrid = { columns: shape.columns, rows: shape.rows };
    const document: PageDocument = { format: 'pages-v2', revision: pages.instanceId(), sourceGrid,
      layout: pages.emptyLayout(name.trim()), workspace: { revision: pages.instanceId(), positions: {} } };
    const screen: Screen = {
      id, name: name.trim(), online: false, virtual: true, board, orientation,
      firmware: renderer.firmware, firmware_known: renderer.firmware, tile_limit: 64, full_page: true,
      page_tiles_repeat: true, entity_tiles_repeat: true, no_title: true, climate_range: true, in_sync: true, shape, layout: { title: name.trim(), tiles: [], pages: 1 },
      source_grid: sourceGrid, page_document: document, page_capability: 'ready',
      tile_sizes: sizesOn(shape), grids: previewGrids(shape, orientation),
    };
    persistVirtualScreens([...inventory.value.screens, screen]);
    inventory.value.screens.push(screen);
    return screen;
  }

  // ---- A new inventory, and who follows it ----
  // Whoever follows it (the session) is told once each inventory has arrived, in full, light or from the stream.
  const followers = new Set<() => void>();
  function onArrival(follower: () => void) {
    followers.add(follower);
    return () => { followers.delete(follower); };
  }
  const arrived = () => { for (const follower of followers) follower(); };
  async function refresh(full = true) {
    try {
      const data = await getJson(full ? "inventory" : "inventory?light=1");
      if (data.csrf) setCsrf(data.csrf);
      const virtual = await migrateVirtualScreens();
      // A light poll carries only screens and update status; keep the catalogues we have.
      inventory.value = full ? data : { ...inventory.value, ...data };
      inventory.value.screens = [...inventory.value.screens.filter((screen) => !screen.virtual), ...virtual];
      if (data.csrf) setCsrf(data.csrf);
      reachable.value = true;
      arrived();
    } catch {
      reachable.value = false;
    }
  }
  function applyLive(data: Partial<Inventory>) {
    inventory.value = { ...inventory.value, ...data } as Inventory;
    inventory.value.screens = [...inventory.value.screens.filter((screen) => !screen.virtual), ...virtualScreens()];
    arrived();
  }

  // ---- The live stream, and the polls that stand in for it ----
  // Live updates arrive over server-sent events; polling is the fallback while the stream is down, plus a full catalogue
  // refresh every five minutes. Nothing is polled while the tab is hidden, and a stream given up is opened again only once
  // the tab is shown: a hidden tab would keep the add-on busy, and it is read in full again when it is shown. A stream that
  // opens or speaks proves the add-on is there again; one that opens after it could not be reached reads what changed
  // meanwhile at once, rather than at the next full refresh.
  let following = false, live = false, stream: EventSource | null = null, busy: () => boolean = () => false;
  let pollTimer = 0, reconnectTimer = 0, reconnects = 0, lastFull = 0;
  function listen() {
    if (stream || !following || typeof EventSource === "undefined" || document.hidden) return;
    // An EventSource sends no headers of its own: the editor's language goes along in the address (app 0.2.90).
    const source = (stream = new EventSource(`api/events?language=${encodeURIComponent(editorLanguage())}`));
    source.onopen = () => {
      live = true; reconnects = 0;
      if (!reachable.value) void refresh(false);
      poll();
    };
    source.onmessage = (e) => { reachable.value = true; if (!document.hidden) applyLive(JSON.parse(e.data)); };
    source.onerror = () => {
      live = false;
      poll();
      if (stream !== source || source.readyState !== EventSource.CLOSED) return;
      stream = null;
      clearTimeout(reconnectTimer);
      reconnectTimer = window.setTimeout(listen, RECONNECT_MS[Math.min(reconnects++, RECONNECT_MS.length - 1)]);
    };
  }
  function poll() {
    clearTimeout(pollTimer);
    if (!following) return;
    const wait = live ? POLL_MS.live : busy() || inventory.value.updates?.busy ? POLL_MS.busy : POLL_MS.down;
    pollTimer = window.setTimeout(async () => {
      if (!document.hidden) {
        const full = Date.now() - lastFull >= FULL_REFRESH_MS;
        if (full) lastFull = Date.now();
        if (full || !live) await refresh(full);
      }
      poll();
    }, wait);
  }

  // ---- Started once the page is on the screen (stores/session.ts start); the returned function stops it ----
  // The inventory, the live stream and the polls that stand in for it, and a full refresh when the tab is shown again.
  // `busy`: whether something builds, which the polls follow more closely (the builds store's, handed in by the session).
  let running: (() => void) | null = null;
  function start(options: Live = {}) {
    if (running) return running;
    const scope = effectScope(true);
    busy = options.busy || (() => false);
    scope.run(() => {
      following = true;
      lastFull = Date.now();
      refresh();
      listen();
      poll();
      useEventListener(document, "visibilitychange", async () => {
        if (document.hidden) return;
        lastFull = Date.now();
        listen();
        await refresh();
        poll();
      });
      onScopeDispose(() => {
        following = false;
        clearTimeout(pollTimer); clearTimeout(reconnectTimer);
        stream?.close(); stream = null; live = false; reconnects = 0;
      });
    });
    running = () => { running = null; scope.stop(); };
    return running;
  }
  onScopeDispose(() => running?.());

  // ---- The Tessera skill for Claude Code in Home Assistant (Settings), which the add-on writes ----
  async function installClaudeSkill() {
    try {
      inventory.value.claude_skill = await send("claude-skill", "POST");
      ui.toast(t(inventory.value.claude_skill?.restart ? "editor.settings.claude.installed_restart" : "editor.settings.claude.installed"));
    } catch (e: any) {
      ui.toast(e.message);
    }
  }

  return {
    inventory, reachable, connected, tallerTilesEnabled, pluginsEnabled,
    ...lookups({ entityOf }),
    persistVirtualScreens, createVirtualScreen, onArrival, refresh, applyLive, installClaudeSkill, start,
  };
});
