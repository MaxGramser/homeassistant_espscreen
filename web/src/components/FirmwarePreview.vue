<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import createModule, { type FirmwarePreviewModule } from "../wasm/firmware_preview.js";
import wasmUrl from "../wasm/firmware_preview.wasm?url";
import { state } from "../store";
import { t } from "../i18n";
import { send } from "../api";
import type { Tile } from "../types";

const props = defineProps<{ width: number; height: number; dpi?: number; columns: number; rows: number; pages?: number; tiles?: Tile[] }>();
const canvas = ref<HTMLCanvasElement | null>(null);
const error = ref("");
const actionError = ref("");
let module: FirmwarePreviewModule | null = null;
let raf: number | null = null, refreshTimer: ReturnType<typeof setTimeout> | undefined;
let disposed = false, generation = 0, pointer: number | null = null;
let lastLayout = "", lastMessages = new Map<string, string>();
let sendingActions = false;
let liveRefresh: ReturnType<typeof setTimeout> | undefined;

function time() {
  const now = new Date();
  module?._preview_time(Math.floor(performance.now()), Math.floor(now.getTime() / 1000), -now.getTimezoneOffset() * 60);
}

async function receive() {
  if (!module || disposed) return;
  const revision = ++generation;
  clearTimeout(refreshTimer);
  try {
    const result = await send<{ messages: Record<string, unknown>[] }>("firmware-preview", "POST", {
      shape: { width: props.width, height: props.height, columns: props.columns, rows: props.rows },
      layout: { ...state.layout, tiles: props.tiles ?? state.layout?.tiles ?? [], pages: props.pages ?? 1 },
    });
    if (disposed || revision !== generation) return;
    time();
    for (const packet of result.messages) {
      const text = JSON.stringify(packet), key = `${packet.op}:${packet.i ?? ""}`;
      if (packet.op === "layout") {
        if (text === lastLayout) {
          // The firmware's normal keepalive preserves the current page and cards.
          module.ccall("preview_receive", "string", ["string"], [JSON.stringify({ v: 1, op: "ping", rev: packet.rev })]);
          continue;
        }
        lastLayout = text; lastMessages.clear();
      } else if (lastMessages.get(key) === text) continue;
      const status = module.ccall("preview_receive", "string", ["string"], [text]);
      if (status.startsWith("Error:")) throw new Error(t("editor.preview.packet_error", { message: status }));
      lastMessages.set(key, text);
    }
    error.value = "";
  } catch (e) {
    if (!disposed && revision === generation) error.value = e instanceof Error ? e.message : String(e);
  } finally {
    if (!disposed && revision === generation) refreshTimer = setTimeout(receive, 10000);
  }
}

function draw() {
  raf = null;
  if (!module || disposed || !canvas.value) return;
  try {
    time();
    module._preview_render();
    void sendActions();
    const start = module._preview_frame();
    const pixels = module.HEAPU8.subarray(start, start + props.width * props.height * 4);
    canvas.value.getContext("2d")?.putImageData(new ImageData(new Uint8ClampedArray(pixels), props.width, props.height), 0, 0);
    raf = requestAnimationFrame(draw);
  } catch (e) {
    error.value = t("editor.preview.stopped", { message: e instanceof Error ? e.message : String(e) });
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
      let success = true, message = "";
      try {
        await send("firmware-preview/action", "POST", request);
      } catch (e) {
        success = false;
        message = e instanceof Error ? e.message : String(e);
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

function refreshLiveState() {
  clearTimeout(liveRefresh);
  liveRefresh = setTimeout(receive, 100);
}

function contact(event: PointerEvent) {
  if (!module || !canvas.value) return;
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
    const loaded = await createModule({ locateFile: () => wasmUrl });
    if (disposed) return;
    module = loaded;
    if (!module._preview_init(props.width, props.height, props.dpi ?? 170, props.columns, props.rows)) {
      throw new Error(t("editor.preview.invalid_shape"));
    }
    await receive();
    draw();
  } catch (e) { if (!disposed) error.value = e instanceof Error ? e.message : String(e); }
});
watch(() => [props.tiles, props.pages, state.layout?.title, state.layout?.settings, state.layout?.header], receive, { deep: true });
watch(() => (props.tiles ?? state.layout?.tiles ?? []).map(tile => state.liveStates[tile.entity]), refreshLiveState, { deep: true });
onBeforeUnmount(() => {
  disposed = true; generation++;
  if (raf !== null) cancelAnimationFrame(raf);
  raf = null;
  clearTimeout(refreshTimer); clearTimeout(liveRefresh); cancel(); module = null;
});
</script>

<template>
  <p class="hint">{{ t("editor.preview.controls", { width, height }) }}</p>
  <div class="firmware-preview" :style="{ aspectRatio: `${width} / ${height}` }">
    <canvas ref="canvas" :width="width" :height="height" :aria-label="t('editor.preview.canvas')"
      @pointerdown.prevent="contact" @pointermove="contact" @pointerup="contact" @pointercancel="cancel" @lostpointercapture="cancel"></canvas>
  </div>
  <p v-if="actionError" role="alert">{{ actionError }}</p>
  <p v-if="error" role="alert">{{ error }}</p>
</template>
