<script setup lang="ts">
// A sound of one's own, cut from a file (docs/SOUNDS.md): choose a sound file, see it as a waveform and pick the part to
// keep, at most `most` seconds (a call's ring with the pause it wants before it rings again). Play plays that part the
// way the screen will, looped for a ring (`loops`), after the bass is filtered out and the level raised
// (model/ringtone.ts); Save keeps it in the app's library (stores/sounds.ts), where every kind it fits can choose it.
// The waveform shows the sound without its bass, so the part is picked on what will be heard. Used by every kind of sound
// (SoundPicker.vue): only the length and the loop differ.
import { computed, onBeforeUnmount, ref } from "vue";
import { t } from "../../i18n";
import { firstPart, highPass, movePart, peaks, ringtone } from "../../model/ringtone";
import { glyph } from "../../model/topbar";
import { useSoundsStore } from "../../stores/sounds";
import { useUiStore } from "../../stores/ui";

const props = defineProps<{ most: number; loops: boolean; idPrefix: string }>();
const emit = defineEmits<{ saved: [id: string]; cancel: [] }>();
const ui = useUiStore();
const sounds = useSoundsStore();
const PLAY = glyph("F040A"), STOP = glyph("F04DB");
const KEY = `cut-${props.idPrefix}`;
const COLUMNS = 480;

const picker = ref<HTMLInputElement | null>(null);
const sound = ref<Float32Array | null>(null);
const heard = computed(() => (sound.value ? highPass(sound.value, rate.value) : null));
const part = ref<{ start: number; end: number }>({ start: 0, end: 0 });
const name = ref("");
const reading = ref(false);
const rate = computed(() => sounds.view?.rate ?? 16000);
const least = computed(() => sounds.view?.min_seconds ?? 0.25);
const length = computed(() => (sound.value ? sound.value.length / rate.value : 0));
const bars = computed(() => (heard.value ? peaks(heard.value, COLUMNS) : []));
const wave = computed(() => bars.value.map((p, i) => `M${i + 0.5} ${50 - Math.max(0.5, p * 48)}V${50 + Math.max(0.5, p * 48)}`).join(""));
const at = (seconds: number) => `${(100 * seconds) / (length.value || 1)}%`;
const fixed = (value: number) => value.toFixed(1);
const playing = computed(() => sounds.playing === KEY);

onBeforeUnmount(() => { if (playing.value) sounds.stop(); });

/** Opens the system's file chooser. */
const choose = () => picker.value?.click();
defineExpose({ choose });

async function read(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  (event.target as HTMLInputElement).value = "";
  if (!file) return;
  if (playing.value) sounds.stop();
  reading.value = true;
  try {
    sound.value = await sounds.decode(file);
    part.value = firstPart(heard.value!, rate.value, props.most);
    name.value = file.name.replace(/\.[^.]+$/, "").slice(0, sounds.view?.name_most ?? 40);
  } catch {
    sound.value = null;
    ui.toast(t("editor.sounds.own_unreadable"));
  } finally {
    reading.value = false;
  }
}
const made = () => ringtone(sound.value!, rate.value, part.value.start, part.value.end);
const play = () => (playing.value ? sounds.stop() : sounds.playSamples(made(), KEY, props.loops));
function cancel() {
  if (playing.value) sounds.stop();
  sound.value = null;
  emit("cancel");
}
async function save() {
  if (playing.value) sounds.stop();
  const id = await sounds.add(name.value, made());
  if (id) {
    sound.value = null;
    emit("saved", id);
  }
}

// The part on the waveform: drag it to move it, its edges to stretch it, a tap beside it to move it there.
const strip = ref<HTMLElement | null>(null);
let dragging: { edge: "start" | "end" | "whole"; from: number; part: { start: number; end: number } } | null = null;
const timeAt = (event: PointerEvent) => {
  const box = strip.value!.getBoundingClientRect();
  return (Math.max(0, Math.min(box.width, event.clientX - box.left)) / (box.width || 1)) * length.value;
};
function down(event: PointerEvent) {
  const edge = ((event.target as HTMLElement).dataset.edge as "start" | "end" | "whole" | undefined) ?? null;
  const time = timeAt(event);
  if (!edge) {
    const span = part.value.end - part.value.start;
    part.value = movePart(part.value, "whole", time - span / 2, length.value, least.value, props.most);
  }
  dragging = { edge: edge ?? "whole", from: time, part: { ...part.value } };
  strip.value!.setPointerCapture(event.pointerId);
}
function move(event: PointerEvent) {
  if (!dragging) return;
  const time = timeAt(event);
  const to = dragging.edge === "whole" ? dragging.part.start + time - dragging.from : time;
  part.value = movePart(dragging.edge === "whole" ? dragging.part : part.value, dragging.edge, to, length.value, least.value, props.most);
}
function up() {
  if (!dragging) return;
  dragging = null;
  if (playing.value) { sounds.stop(); play(); }  // what plays follows the part at once
}
</script>

<template>
  <div class="cutter" :id="`${idPrefix}-cutter`">
    <input ref="picker" type="file" accept="audio/*,.wav,.mp3,.m4a,.ogg,.flac" hidden @change="read" />
    <p v-if="reading" class="hint">{{ t("editor.common.loading") }}</p>
    <div v-else-if="!sound" class="cutter-actions">
      <button type="button" class="btn primary" :id="`${idPrefix}-choose`" @click="choose">{{ t("editor.sounds.own_choose") }}</button>
      <button type="button" class="btn quiet" @click="cancel">{{ t("editor.common.cancel") }}</button>
    </div>
    <template v-else>
      <p class="hint">{{ t(loops ? "editor.sounds.own_text_loop" : "editor.sounds.own_text_once", { seconds: most }) }}</p>
      <div ref="strip" class="cutter-strip" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up">
        <svg class="cutter-wave" :viewBox="`0 0 ${COLUMNS} 100`" preserveAspectRatio="none" aria-hidden="true"><path :d="wave" /></svg>
        <div class="cutter-part" data-edge="whole" :style="{ left: at(part.start), width: `calc(${at(part.end)} - ${at(part.start)})` }">
          <span class="cutter-edge start" data-edge="start" /><span class="cutter-edge end" data-edge="end" />
        </div>
      </div>
      <p class="cutter-times" :id="`${idPrefix}-times`">{{ t("editor.sounds.own_part", { start: fixed(part.start), end: fixed(part.end), length: fixed(part.end - part.start) }) }}</p>
      <p class="hint">{{ t(loops ? "editor.sounds.own_drag_loop" : "editor.sounds.own_drag_once") }}</p>
      <label class="cutter-name">
        <span>{{ t("editor.sounds.own_name") }}</span>
        <input v-model="name" type="text" :maxlength="sounds.view?.name_most ?? 40" :id="`${idPrefix}-name`" />
      </label>
      <div class="cutter-actions">
        <button type="button" class="btn" :id="`${idPrefix}-play`" @click="play"><span class="mdi">{{ playing ? STOP : PLAY }}</span>
          {{ playing ? t("editor.sounds.stop") : t("editor.sounds.play") }}</button>
        <button type="button" class="btn quiet" @click="cancel">{{ t("editor.common.cancel") }}</button>
        <button type="button" class="btn primary" :id="`${idPrefix}-save`" :disabled="sounds.busy || !name.trim()" @click="save">{{ t("editor.sounds.own_save") }}</button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.cutter { display: grid; gap: 10px; }
.cutter .hint { margin: 0; }
.cutter-strip { position: relative; height: 96px; border-radius: 10px; background: var(--surface-2); overflow: hidden; touch-action: none; cursor: pointer; user-select: none; }
.cutter-wave { position: absolute; inset: 0; width: 100%; height: 100%; }
.cutter-wave path { stroke: var(--muted); stroke-width: 1; vector-effect: non-scaling-stroke; }
.cutter-part { position: absolute; top: 0; bottom: 0; background: color-mix(in srgb, var(--accent) 22%, transparent); box-shadow: inset 0 0 0 2px var(--accent); border-radius: 8px; cursor: grab; }
.cutter-edge { position: absolute; top: 0; bottom: 0; width: 14px; cursor: ew-resize; }
.cutter-edge::after { content: ""; position: absolute; top: 30%; bottom: 30%; left: 5px; width: 4px; border-radius: 2px; background: var(--accent); }
.cutter-edge.start { left: -2px; }
.cutter-edge.end { right: -2px; }
.cutter-times { margin: 0; font-variant-numeric: tabular-nums; font-weight: 600; }
.cutter-name { display: grid; gap: 4px; max-width: 360px; }
.cutter-name span { font-size: 13px; color: var(--muted); }
.cutter-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.cutter-actions .mdi { font-size: 16px; }
</style>
