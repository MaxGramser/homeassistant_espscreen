<script setup lang="ts">
// The shared firmware and LVGL in WebAssembly, fed the same packets a screen gets. `still` shows a layout without
// touch at a few frames a second (the home page); otherwise it takes taps and swipes, and `controls` decides whether
// a tap on a tile reaches Home Assistant.
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { FirmwarePreviewModule } from "../wasm/firmware_preview.js";
import { loadFirmware } from "../wasm/load";
import { state } from "../store";
import { t } from "../i18n";
import { api, send } from "../api";
import type { PageLayout } from "../types";

const props = withDefaults(defineProps<{
  width: number; height: number; dpi?: number; columns: number; rows: number;
  layout?: PageLayout | null; still?: boolean; controls?: boolean;
}>(), { still: false, controls: true });
const emit = defineEmits<{ ready: []; failed: [message: string] }>();
const canvas = ref<HTMLCanvasElement | null>(null);
const error = ref("");
const actionError = ref("");
let module: FirmwarePreviewModule | null = null;
let raf: number | null = null, refreshTimer: ReturnType<typeof setTimeout> | undefined;
let disposed = false, generation = 0, pointer: number | null = null, synced = false, ready = false;
let lastLayout = "", lastMessages = new Map<string, string>();
let session = "", sequence = 0;
let sendingActions = false;
let liveRefresh: ReturnType<typeof setTimeout> | undefined;
let events: EventSource | null = null;
let fetchingImage = false;
let visible = true, lastDraw = 0;
let observer: IntersectionObserver | null = null;
const downloads = new AbortController();
// A still screen redraws its clock and the states coming in, not a finger: four frames a second is enough.
const STILL_FRAME = 250;

const layout = () => props.layout === undefined ? state.document : props.layout;

function time() {
  const now = new Date();
  module?._preview_time(Math.floor(performance.now()), Math.floor(now.getTime() / 1000), -now.getTimezoneOffset() * 60);
}

function fail(message: string) {
  error.value = message;
  emit("failed", message);
}

async function receive() {
  const document = layout();
  if (!module || disposed || !document) return;
  const revision = ++generation;
  clearTimeout(refreshTimer);
  try {
    const result = await send<{ revision: string; configuration: Record<string, unknown>[]; values: Record<string, unknown>[] }>("firmware-preview", "POST", {
      shape: { width: props.width, height: props.height, columns: props.columns, rows: props.rows },
      layout: document,
    });
    if (disposed || revision !== generation) return;
    time();
    const deliver = (packet: Record<string, unknown>) => {
      const status = module!.ccall("preview_receive", "string", ["string"], [JSON.stringify({
        ...packet, v: 2, session, seq: ++sequence, rev: result.revision,
      })]);
      if (status !== 'Synced' && status !== 'Loading tiles') throw new Error(t('editor.preview.packet_error', { message: status }));
    };
    if (result.revision !== lastLayout || !session) {
      const request = [...crypto.getRandomValues(new Uint8Array(8))].map(byte => byte.toString(16).padStart(2, '0')).join('');
      const answer = module.ccall('preview_receive', 'string', ['string'], [JSON.stringify({ v: 2, op: 'hello', request })]);
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
    }
    deliver({ op: 'ping' });
    error.value = "";
    synced = true;
  } catch (e) {
    if (!disposed && revision === generation) fail(e instanceof Error ? e.message : String(e));
  } finally {
    if (!disposed && revision === generation) refreshTimer = setTimeout(receive, 10000);
  }
}

function draw() {
  raf = null;
  if (!module || disposed || !canvas.value) return;
  try {
    const now = performance.now();
    if (!props.still || (visible && now - lastDraw >= STILL_FRAME)) {
      lastDraw = now;
      time();
      module._preview_render();
      void sendActions();
      void fetchImages();
      const start = module._preview_frame();
      const pixels = module.HEAPU8.subarray(start, start + props.width * props.height * 4);
      canvas.value.getContext("2d")?.putImageData(new ImageData(new Uint8ClampedArray(pixels), props.width, props.height), 0, 0);
      if (synced && !ready) { ready = true; emit("ready"); }
    }
    raf = requestAnimationFrame(draw);
  } catch (e) {
    fail(t("editor.preview.stopped", { message: e instanceof Error ? e.message : String(e) }));
  }
}

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
      request, shape: { width: props.width, height: props.height },
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
  clearTimeout(liveRefresh);
  liveRefresh = setTimeout(receive, 100);
}

function entityQuery() {
  const entities = new Set<string>();
  for (const page of layout()?.pages ?? []) {
    for (const tile of page.tiles) if (tile.content.kind === 'entity') entities.add(tile.content.entityId);
    for (const item of page.topbar.trailing) if (item.entity) entities.add(item.entity);
  }
  return [...entities].sort().map(entity => `entity=${encodeURIComponent(entity)}`).join('&');
}

function listen() {
  events?.close(); events = null;
  const query = entityQuery();
  if (!module || disposed || !query || typeof EventSource === 'undefined') return;
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
  if (props.still && canvas.value && typeof IntersectionObserver !== "undefined") {
    observer = new IntersectionObserver((entries) => { visible = entries.some((entry) => entry.isIntersecting); });
    observer.observe(canvas.value);
  }
  try {
    const loaded = await loadFirmware();
    if (disposed) return;
    module = loaded;
    if (!module._preview_init(props.width, props.height, props.dpi ?? 170, props.columns, props.rows)) {
      throw new Error(t("editor.preview.invalid_shape"));
    }
    await receive();
    listen();
    draw();
  } catch (e) { if (!disposed) fail(e instanceof Error ? e.message : String(e)); }
});
watch(layout, receive, { deep: true });
watch(entityQuery, listen);
onBeforeUnmount(() => {
  disposed = true; generation++;
  events?.close(); events = null;
  observer?.disconnect();
  downloads.abort();
  if (raf !== null) cancelAnimationFrame(raf);
  raf = null;
  clearTimeout(refreshTimer); clearTimeout(liveRefresh); cancel(); module = null;
});
</script>

<template>
  <div class="firmware-preview" :class="{ still }" :style="{ aspectRatio: `${width} / ${height}` }">
    <canvas ref="canvas" :width="width" :height="height" :aria-label="t('editor.preview.canvas')"
      @pointerdown.prevent="contact" @pointermove="contact" @pointerup="contact" @pointercancel="cancel" @lostpointercapture="cancel"></canvas>
  </div>
  <p v-if="actionError && !still" class="firmware-preview-error" role="alert">{{ actionError }}</p>
  <p v-if="error && !still" class="firmware-preview-error" role="alert">{{ error }}</p>
</template>
