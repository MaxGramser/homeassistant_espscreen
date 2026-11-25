<script setup lang="ts">
// The shared firmware and LVGL in WebAssembly, fed the same packets a screen gets. `still` shows a layout without
// touch at a few frames a second (the home page); otherwise it takes taps and swipes, and `controls` decides whether
// a tap on a tile reaches Home Assistant. The plugins a screen runs draw their own tiles in it: their code is loaded
// into the firmware (stores/plugin-code.ts). `manual` draws nothing by itself: its owner lets the firmware take a step
// and asks for a page's cards as the firmware drew them (capture), which is how the editor shows a card it cannot
// draw itself (GlassFaces.vue).
import { useDocumentVisibility, useElementVisibility, useRafFn, useTimeoutFn } from "@vueuse/core";
import age from "virtual:esp-screens-preview-age";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { FirmwarePreviewModule } from "../wasm/firmware_preview.js";
import { loadFirmware, startPlugins } from "../wasm/load";
import { t } from "../i18n";
import { api, getJson, send } from "../api";
import type { PageLayout, Screen } from "../types";
import type { Texts } from "../model/plugins";
import { useInventoryStore } from "../stores/inventory";
import { useDocumentStore } from "../stores/document";
import { usePluginCodeStore } from "../stores/plugin-code";
import type { GlassCard } from "../stores/faces";
import { allTiles } from "../model/page-tiles";

const inv = useInventoryStore();
const doc = useDocumentStore();
const code = usePluginCodeStore();

const props = withDefaults(defineProps<{
  width: number; height: number; dpi?: number; columns: number; rows: number;
  layout?: PageLayout | null; still?: boolean; controls?: boolean;
  // Whether the board draws pictures (stores/screen.ts drawsPictures): a CYD's preview has no square for an album cover.
  pictures?: boolean;
  // The screen's Dark mode (its settings), drawn as the firmware draws it.
  dark?: boolean;
  screen?: Screen;
  // The screen whose plugins draw their own tiles here (default: `screen`); the home page names it without binding the
  // screen's settings.
  pluginsOf?: Screen;
  // Its owner draws: no frames of its own, only what capture() is asked for.
  manual?: boolean;
  // The slots of the layout whose tile is shown with its type's own example (a plugin's example of its tile) instead
  // of what it reads now: a tile that is on no page yet has nothing of its own to show.
  examples?: number[];
}>(), { still: false, controls: true, pictures: true, dark: false, manual: false });
// `synced`: the firmware has the layout and its values as they are now. `changed`: the tiles (their indexes in the
// layout) whose values came in new this time, or null when the whole layout did.
// `failed` says with `final` whether that was the end: a refresh the add-on refused or did not answer is asked again
// by itself ten seconds on (final false), a firmware that did not load or that threw in a frame goes no further.
const emit = defineEmits<{ ready: []; failed: [message: string, final: boolean]; synced: [changed: number[] | null] }>();
const canvas = ref<HTMLCanvasElement | null>(null);
const error = ref("");
const actionError = ref("");
let module: FirmwarePreviewModule | null = null;
let disposed = false, generation = 0, pointer: number | null = null, synced = false, ready = false;
let lastLayout = "", lastMessages = new Map<string, string>();
let session = "", sequence = 0;
let sendingActions = false;
let events: EventSource | null = null;
let settingsEvents: EventSource | null = null;
let sendingSettings = false;
type Extra = { entity: string | null; label: Texts; available: boolean; [key: string]: unknown };
let extras: Extra[] = [];
let fetchingImage = false;
let lastDraw = 0;
// The draft changed and the firmware does not have it yet, or is being handed it now: what it shows is the layout
// before, so capture() gives nothing until it is in.
let behind = false, receiving = 0;
const downloads = new AbortController();
// A still screen redraws its clock and the states coming in, not a finger: four frames a second is enough.
const STILL_FRAME = 250;
// A draft that changes with every key typed (a tile's name, a title) goes to the add-on once the typing pauses this long.
const LAYOUT_PAUSE = 200;

const layout = () => props.layout === undefined ? doc.document : props.layout;
// The states again every ten seconds after the last time (a fallback for the live stream), soon after the stream says
// something changed, and once typing pauses; every wait goes with the preview.
// A hidden tab asks nothing: what came due meanwhile is asked for once the tab is shown again.
const sight = useDocumentVisibility();
let due = false;
const whenInSight = () => { if (sight.value === "hidden") due = true; else receive(); };
watch(sight, (now) => { if (now === "visible" && due) { due = false; receive(); } });
const refreshLater = useTimeoutFn(whenInSight, 10000, { immediate: false });
const refreshSoon = useTimeoutFn(whenInSight, 100, { immediate: false });
const layoutPause = useTimeoutFn(() => receive(), LAYOUT_PAUSE, { immediate: false });
// One frame each time the browser draws; a still screen only while it is in sight (useElementVisibility).
const frames = useRafFn(draw, { immediate: false });
const visible = useElementVisibility(canvas, { initialValue: true });
// The screens' language, in which ESP Screens builds them and writes the words it sends (Settings -> Language & region).
const language = () => inv.inventory.language?.effective || "en";

// The language and the look of the screen, as its own firmware draws them (a build from before has neither export).
// Each only when it changes: a new language draws every card again.
function speak() {
  if (module && !disposed && "_preview_language" in module) module.ccall("preview_language", "number", ["string"], [language()]);
}
function shade() {
  if (module && !disposed) module._preview_dark?.(props.dark ? 1 : 0);
}

// Bind HA values to the firmware's Settings rows. The canvas is still the only renderer.
function screenSettings() {
  if (!module?._preview_settings || disposed) return;
  const screen = props.screen;
  module.ccall('preview_settings', null, ['string'], [JSON.stringify({
    name: screen?.name || layout()?.title || '', firmware: screen?.firmware || '', online: screen?.online ?? false,
    values: screen?.settings?.values || {},
    dimmable: screen?.settings?.keys.includes('brightness'), standby: screen?.screensaver?.standby,
  })]);
}
function extraSettings() {
  if (module?._preview_extras && !disposed) module.ccall('preview_extras', null, ['string'], [JSON.stringify(
    extras.map(row => ({ ...row, label: row.label[language()] || row.label[language().split('-')[0]!] || row.label.en || '' })),
  )]);
}
function settingsControls() {
  module?._preview_settings_controls?.(props.controls && !props.still && !!props.screen && !props.screen.virtual ? 1 : 0);
}
function listenSettings() {
  settingsEvents?.close(); settingsEvents = null;
  extras = []; extraSettings();
  const screen = props.screen;
  if (!module?._preview_extras || disposed || props.still || !screen || screen.virtual ||
      sight.value === 'hidden' || typeof EventSource === 'undefined') return;
  const stream = new EventSource(`api/screens/${encodeURIComponent(screen.id)}/extras/events?language=${encodeURIComponent(language())}`);
  settingsEvents = stream;
  stream.onmessage = event => {
    if (settingsEvents !== stream) return;
    extras = JSON.parse(event.data); extraSettings();
  };
  stream.onerror = () => {
    if (settingsEvents !== stream) return;
    extras = extras.map(row => ({ ...row, available: false })); extraSettings();
  };
}
async function sendSettings() {
  if (sendingSettings || !module?._preview_next_setting || disposed) return;
  sendingSettings = true;
  try {
    while (!disposed && module) {
      const encoded = module.ccall('preview_next_setting', 'string', [], []);
      if (!encoded) break;
      const screen = props.screen;
      if (!props.controls || props.still || !screen || screen.virtual) continue;
      const request = JSON.parse(encoded), route = `screens/${encodeURIComponent(screen.id)}`;
      try {
        if (request.entity) await send(`${route}/extras`, 'POST', request);
        else {
          const view = await send<NonNullable<Screen['settings']>>(`${route}/settings`, 'PUT', { settings: { [request.key]: request.value } });
          const current = inv.inventory.screens.find(item => item.id === screen.id);
          if (current) current.settings = view;
        }
        actionError.value = '';
      } catch (e) {
        if (disposed || props.screen?.id !== screen.id) continue;
        actionError.value = t('editor.preview.action_error', { message: e instanceof Error ? e.message : String(e) });
        // Rejected writes may produce no state event. Restore once; successful writes arrive by SSE.
        if (request.entity) {
          try {
            const rows = await getJson<Extra[]>(`${route}/extras`);
            if (!disposed && props.screen?.id === screen.id) { extras = rows; extraSettings(); }
          } catch { /* The stream restores values when the connection returns. */ }
        } else screenSettings();
      }
    }
  } finally { sendingSettings = false; }
}

function time() {
  const now = new Date();
  module?._preview_time(Math.floor(performance.now()), Math.floor(now.getTime() / 1000), -now.getTimezoneOffset() * 60);
}

function fail(message: string, final = false) {
  error.value = message;
  emit("failed", message, final);
}

async function receive() {
  const document = layout();
  if (!module || disposed || !document) return;
  const revision = ++generation;
  refreshLater.stop();
  behind = false; receiving += 1;
  try {
    const result = await send<{ revision: string; configuration: Record<string, unknown>[]; values: Record<string, unknown>[] }>("firmware-preview", "POST", {
      shape: { width: props.width, height: props.height, columns: props.columns, rows: props.rows },
      layout: document,
      ...(props.examples?.length ? { examples: props.examples } : {}),
    });
    if (disposed || revision !== generation) return;
    time();
    const deliver = (packet: Record<string, unknown>) => {
      const status = module!.ccall("preview_receive", "string", ["string"], [JSON.stringify({
        ...packet, v: 2, session, seq: ++sequence, rev: result.revision,
      })]);
      if (status !== 'Synced' && status !== 'Loading tiles') throw new Error(t('editor.preview.packet_error', { message: status }));
    };
    const whole = result.revision !== lastLayout || !session, changed: number[] = [];
    if (whole) {
      const request = [...crypto.getRandomValues(new Uint8Array(8))].map(byte => byte.toString(16).padStart(2, '0')).join('');
      const answer = module.ccall('preview_receive', 'string', ['string'], [JSON.stringify({ v: 2, op: 'hello', request, features: ['pictures'] })]);
      if (!/^Session:[0-9a-f]{16}$/.test(answer)) throw new Error(t('editor.preview.packet_error', { message: answer }));
      session = answer.slice(8); sequence = 0;
      for (const packet of result.configuration) deliver(packet);
      lastLayout = result.revision; lastMessages.clear();
    }
    for (const packet of result.values) {
      const text = JSON.stringify(packet), key = `${packet.op}:${packet.i ?? packet.p ?? ''}`;
      if (lastMessages.get(key) === text) continue;
      deliver(packet);
      lastMessages.set(key, text);
      if (typeof packet.i === 'number') changed.push(packet.i);
    }
    deliver({ op: 'ping' });
    error.value = "";
    synced = true;
    emit("synced", whole ? null : changed);
  } catch (e) {
    if (!disposed && revision === generation) fail(e instanceof Error ? e.message : String(e));
  } finally {
    receiving -= 1;
    if (!disposed && revision === generation) refreshLater.start();
  }
}

// One step of the firmware: its clock, its frame, and what it asked for meanwhile on its way.
function step() {
  if (!module) return;
  time();
  module._preview_render();
  void sendActions();
  void sendSettings();
  void fetchImages();
}
// The firmware's frame onto the canvas.
function show() {
  if (!module || !canvas.value) return;
  const start = module._preview_frame();
  const pixels = module.HEAPU8.subarray(start, start + props.width * props.height * 4);
  canvas.value.getContext("2d")?.putImageData(new ImageData(new Uint8ClampedArray(pixels), props.width, props.height), 0, 0);
}
function paint() {
  if (!module || !canvas.value) return;
  step();
  show();
  if (synced && !ready) { ready = true; emit("ready"); }
}

function draw() {
  if (!module || disposed || !canvas.value) return;
  try {
    const now = performance.now();
    if (!props.still || (visible.value && now - lastDraw >= STILL_FRAME)) {
      lastDraw = now;
      paint();
    }
  } catch (e) {
    frames.pause();
    fail(t("editor.preview.stopped", { message: e instanceof Error ? e.message : String(e) }), true);
  }
}

// A step of the firmware with `page` on its glass, and that page's cards as it draws them now (preview_cards: each
// card's slot in the layout, its box, its corners, whether a plugin's own code drew it, and a count that moved when its
// pixels changed). The frame itself is copied onto the canvas only when the owner asks for it (`canvas()`), which it
// does for a card whose count moved: a step in which nothing changed costs no copy. Null until the layout is in, or
// when the firmware has no such page.
function capture(page: number): { cards: GlassCard[]; canvas: () => HTMLCanvasElement } | null {
  const element = canvas.value;
  if (!module || disposed || !element || !synced || behind || receiving || !module._preview_show || error.value) return null;
  try {
    const turned = module._preview_page() !== page;
    if (turned && !module._preview_show(page)) return null;
    // A page that just came is made in the first pass and drawn as its cards asked in the second.
    step();
    if (turned) step();
    let shown = false;
    return { cards: JSON.parse(module.ccall("preview_cards", "string", [], [])),
      canvas: () => { if (!shown) { shown = true; show(); } return element; } };
  } catch (e) {
    fail(t("editor.preview.stopped", { message: e instanceof Error ? e.message : String(e) }), true);
    return null;
  }
}
defineExpose({ capture });

async function sendActions() {
  if (sendingActions || !module || disposed) return;
  sendingActions = true;
  try {
    while (!disposed && module) {
      const encoded = module.ccall("preview_next_action", "string", [], []);
      if (!encoded) break;
      const request = JSON.parse(encoded);
      if (request.event && request.service === 'esphome.screen_camera') {
        void requestImage(request); // A slow artwork source must not block play/pause.
        continue;
      }
      let success = true, message = "";
      if (props.controls && !props.still) {
        try {
          await send("firmware-preview/action", "POST", request);
        } catch (e) {
          success = false;
          message = e instanceof Error ? e.message : String(e);
        }
      } else {
        // Nothing reached Home Assistant: send the states again so the tile drops what it expected.
        lastMessages.clear();
      }
      if (disposed || !module) break;
      time();
      module.ccall("preview_action_response", null, ["number", "number", "string"], [request.call_id, success ? 1 : 0, message]);
      actionError.value = success ? "" : t("editor.preview.action_error", { message });
      // Read HA's resulting state through the same packets as a physical device.
      // No browser code invents the result of a switch or thermostat command.
      await receive();
    }
  } finally { sendingActions = false; }
}

async function requestImage(request: Record<string, unknown>) {
  try {
    const packet = await send<Record<string, unknown>>('firmware-preview/image', 'POST', {
      request, shape: { width: props.width, height: props.height, ...(props.dpi ? { dpi: props.dpi } : {}) },
    }, { signal: downloads.signal });
    // The real decoder also guards the image view counter. Keep an old
    // layout/session response out of the current protocol sequence.
    if (!disposed && module && packet.session === session && packet.rev === lastLayout) {
      time();
      module.ccall('preview_receive', 'string', ['string'], [JSON.stringify({ ...packet, v: 2, seq: ++sequence })]);
    }
  } catch { /* Firmware image timeouts keep the placeholder and retry. */ }
}

async function fetchImages() {
  if (fetchingImage || !module || disposed) return;
  fetchingImage = true;
  try {
    while (!disposed && module) {
      const encoded = module.ccall('preview_next_image', 'string', [], []);
      if (!encoded) break;
      const request = JSON.parse(encoded);
      try {
        const path = /^http:\/\/firmware-preview\.invalid\/([A-Za-z0-9_-]{16,64}\.bmp)$/.exec(request.url);
        if (!path) throw new Error('Invalid preview image link');
        const response = await api(`firmware-preview/images/${path[1]}`, { signal: downloads.signal });
        const bytes = new Uint8Array(await response.arrayBuffer());
        if (disposed || !module) break;
        const buffer = module._preview_image_buffer(request.id, bytes.length);
        if (buffer) {
          module.HEAPU8.set(bytes, buffer);
          time(); module._preview_image_ready(request.id, 1);
        } else module._preview_image_ready(request.id, 0);
      } catch {
        if (!disposed && module) { time(); module._preview_image_ready(request.id, 0); }
      }
    }
  } finally { fetchingImage = false; }
}

function refreshLiveState() {
  refreshSoon.start();
}

function entityQuery() {
  const entities = new Set<string>();
  for (const page of layout()?.pages ?? []) {
    for (const tile of allTiles(page)) {
      if (tile.content.kind === 'entity') entities.add(tile.content.entityId);
      // A plugin's tile of an entity follows that entity too.
      else if (tile.content.kind === 'plugin' && tile.content.entityId) entities.add(tile.content.entityId);
    }
    for (const section of page.sections ?? []) if (section.summary) entities.add(section.summary);
    for (const item of page.topbar.trailing) if (item.entity) entities.add(item.entity);
  }
  return [...entities].sort().map(entity => `entity=${encodeURIComponent(entity)}`).join('&');
}

function listen() {
  events?.close(); events = null;
  const query = entityQuery();
  // A still screen (the overview's thumbnails) takes the ten-second refresh instead of a stream of its own: a browser
  // keeps six connections to one host over plain http, and an overview of six screens would hold them all. The one
  // preview behind the editor (`manual`) is a single connection, and follows its entities as they change.
  if (!module || disposed || !query || (props.still && !props.manual) || typeof EventSource === 'undefined') return;
  const stream = new EventSource(`api/firmware-preview/events?${query}`);
  events = stream;
  stream.onmessage = () => { if (events === stream) refreshLiveState(); };
  // EventSource reconnects itself. The normal ten-second refresh remains a fallback.
}

function contact(event: PointerEvent) {
  if (!module || !canvas.value || props.still) return;
  if (event.type === "pointerdown") {
    if (pointer !== null) return;
    pointer = event.pointerId;
    canvas.value.setPointerCapture(pointer);
  }
  if (event.pointerId !== pointer) return;
  time();
  const rect = canvas.value.getBoundingClientRect();
  module._preview_touch(Math.round((event.clientX - rect.left) * props.width / rect.width),
    Math.round((event.clientY - rect.top) * props.height / rect.height), event.type === "pointerup" ? 0 : 1);
  if (event.type === "pointerup") { canvas.value.releasePointerCapture(pointer); pointer = null; }
}
function cancel() {
  if (pointer !== null) module?._preview_cancel();
  pointer = null;
}

onMounted(async () => {
  try {
    // The plugins' code is waited for (stores/plugin-code.ts). A preview that left meanwhile makes no firmware: the
    // overview's previews do when the page opens on a screen, and each firmware is the whole binary made anew.
    const plugins = await code.codeFor(props.pluginsOf ?? props.screen);
    if (disposed) return;
    const loaded = await loadFirmware(plugins);
    if (disposed) return;
    module = loaded;
    if (!module._preview_init(props.width, props.height, props.dpi ?? 170, props.columns, props.rows)) {
      throw new Error(t("editor.preview.invalid_shape"));
    }
    // The plugins' own setup(), before the first frame (wasm/load.ts).
    startPlugins(module, language());
    // A board that draws no pictures (the CYD) has no square for an album cover, as on its glass (firmware 0.46.0).
    module._preview_pictures?.(props.pictures === false ? 0 : 1);
    speak(); shade();
    screenSettings(); settingsControls(); listenSettings();
    await receive();
    listen();
    // The first frame at once, then one each time the browser draws (a failing frame stops them).
    if (props.manual) return;
    frames.resume();
    draw();
  } catch (e) { if (!disposed) fail(e instanceof Error ? e.message : String(e), true); }
});
watch(layout, () => { behind = true; layoutPause.start(); }, { deep: true });
watch(language, speak);
watch(() => props.dark, shade);
watch(entityQuery, listen);
watch(() => [props.screen?.settings, props.screen?.online], screenSettings, { deep: true });
watch(() => [props.controls, props.still, props.screen?.id], settingsControls);
watch(() => [props.screen?.id, props.still, sight.value, language()], listenSettings);
onBeforeUnmount(() => {
  disposed = true; generation++;
  events?.close(); events = null;
  settingsEvents?.close(); settingsEvents = null;
  downloads.abort();
  frames.pause();
  cancel(); module = null;
});
// When the preview shipped here was built, in the person's own way of writing a date; empty where the build could not say.
const staleSince = age.preview ? new Date(age.preview).toLocaleDateString() : "";
</script>

<template>
  <div class="firmware-preview" :class="{ still }" :style="{ aspectRatio: `${width} / ${height}` }">
    <canvas ref="canvas" :width="width" :height="height" :aria-label="t('editor.preview.canvas')"
      @pointerdown.prevent="contact" @pointermove="contact" @pointerup="contact" @pointercancel="cancel" @lostpointercapture="cancel"></canvas>
  </div>
  <!-- The preview this editor ships is older than the firmware (web/preview-age.ts): said here, where it is looked at. -->
  <p v-if="age.stale && !still" class="firmware-preview-note" role="status">{{ t("editor.preview.stale", { date: staleSince }) }}</p>
  <p v-if="actionError && !still" class="firmware-preview-error" role="alert">{{ actionError }}</p>
  <p v-if="error && !still" class="firmware-preview-error" role="alert">{{ error }}</p>
</template>
