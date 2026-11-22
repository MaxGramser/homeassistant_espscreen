<script setup lang="ts">
// The audio editor (docs/SOUNDS.md, "A sound of your own"): a sound file made into a sound the screens play, wherever one
// is chosen (SoundPicker, in Calls, Doorbell and Alerts). Drop or choose a file; the browser decodes it and brings it to
// the app's rate (stores/sounds.ts). Above, the whole file with the chosen part in it, to move through a long song; below
// it the part large, with room around it (viewAround), a grip at either end with its time, a ruler, and a playhead while
// it plays. The part is at most `most` seconds; Play plays it as the screen will, after the bass is filtered out, the ends
// faded and the level evened (model/ringtone.ts), looped for a ring (`loops`). The waveform shows the sound without its
// bass, so the part is picked on what will be heard. Arrow keys move a grip or the part (Shift: ten times as far), the
// space bar plays. Save hands the finished samples and a name to its owner (`save`); nothing here talks to the app.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { editorLanguage, t } from "../../i18n";
import { firstPart, highPass, movePart, peaks, ringtone, rulerTicks, viewAround } from "../../model/ringtone";
import { glyph } from "../../model/topbar";
import { useSoundsStore } from "../../stores/sounds";
import { useUiStore } from "../../stores/ui";
import Icon from "../ui/Icon.vue";

const props = defineProps<{ most: number; loops: boolean; idPrefix: string; busy?: boolean }>();
const emit = defineEmits<{ save: [name: string, samples: Float32Array]; cancel: [] }>();
const ui = useUiStore();
const sounds = useSoundsStore();
const PLAY = glyph("F040A"), STOP = glyph("F04DB"), MUSIC = glyph("F0E2A");
const KEY = `editor-${props.idPrefix}`;

type Span = { start: number; end: number };
const picker = ref<HTMLInputElement | null>(null);
const sound = ref<Float32Array | null>(null);
const fileName = ref("");
const name = ref("");
const reading = ref(false);
const dropping = ref(false);
const part = ref<Span>({ start: 0, end: 0 });
const view = ref<Span>({ start: 0, end: 0 });
const rate = computed(() => sounds.view?.rate ?? 16000);
const least = computed(() => sounds.view?.min_seconds ?? 0.25);
const heard = computed(() => (sound.value ? highPass(sound.value, rate.value) : null));
const length = computed(() => (sound.value ? sound.value.length / rate.value : 0));
const span = computed(() => part.value.end - part.value.start);
const playing = computed(() => sounds.playing === KEY);

// ---- numbers as the editor's language writes them ----
const number = (value: number, digits = 1) => new Intl.NumberFormat(editorLanguage(), { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
const clock = (seconds: number) => (seconds < 60 ? `${number(seconds)} s` : `${Math.floor(seconds / 60)}:${number(seconds % 60, 1).padStart(4, "0")}`);
const mark = (seconds: number, step: number) => (step < 1 ? number(seconds, step < 0.5 ? 2 : 1) : seconds < 60 ? `${Math.round(seconds)}` : `${Math.floor(seconds / 60)}:${String(Math.round(seconds % 60)).padStart(2, "0")}`);

// ---- the two waveforms: their width follows the page ----
const overview = ref<HTMLElement | null>(null);
const stage = ref<HTMLElement | null>(null);
const overviewWidth = ref(600), stageWidth = ref(600);
let watcher: ResizeObserver | null = null;
onMounted(() => {
  watcher = new ResizeObserver(() => {
    overviewWidth.value = overview.value?.clientWidth || overviewWidth.value;
    stageWidth.value = stage.value?.clientWidth || stageWidth.value;
  });
});
watch([overview, stage], ([a, b]) => { if (a) watcher?.observe(a); if (b) watcher?.observe(b); });
onBeforeUnmount(() => { watcher?.disconnect(); if (playing.value) sounds.stop(); cancelAnimationFrame(frame); });

const overviewBars = computed(() => (heard.value ? peaks(heard.value, Math.max(40, Math.floor(overviewWidth.value / 3))) : []));
const stageBars = computed(() => {
  if (!heard.value) return [];
  const from = Math.floor(view.value.start * rate.value), to = Math.ceil(view.value.end * rate.value);
  const columns = Math.max(40, Math.floor(stageWidth.value / 4));
  const bars = peaks(heard.value.subarray(from, to), columns);
  const top = Math.max(1e-6, ...(overviewBars.value.length ? overviewBars.value : bars));
  return bars.map((p, i) => {
    const t = view.value.start + ((i + 0.5) / columns) * (view.value.end - view.value.start);
    return { h: Math.max(2, (p / top) * 92), in: t >= part.value.start && t <= part.value.end };
  });
});
const overviewTop = computed(() => Math.max(1e-6, ...overviewBars.value));
const ruler = computed(() => rulerTicks(view.value.start, view.value.end, Math.max(4, Math.floor(stageWidth.value / 70))));
const inView = (seconds: number) => `${(100 * (seconds - view.value.start)) / Math.max(1e-6, view.value.end - view.value.start)}%`;
const inFile = (seconds: number) => `${(100 * seconds) / Math.max(1e-6, length.value)}%`;

// ---- a file ----
const choose = () => picker.value?.click();
defineExpose({ choose });
async function open(file: File | undefined) {
  if (!file) return;
  if (playing.value) sounds.stop();
  reading.value = true;
  try {
    sound.value = await sounds.decode(file);
    part.value = firstPart(heard.value!, rate.value, props.most);
    view.value = viewAround(part.value, length.value);
    fileName.value = file.name;
    name.value = file.name.replace(/\.[^.]+$/, "").slice(0, sounds.view?.name_most ?? 40);
    await nextTick();
    overviewWidth.value = overview.value?.clientWidth || overviewWidth.value;
    stageWidth.value = stage.value?.clientWidth || stageWidth.value;
  } catch {
    ui.toast(t("editor.sounds.own_unreadable"));
  } finally {
    reading.value = false;
  }
}
function picked(event: Event) {
  const input = event.target as HTMLInputElement;
  void open(input.files?.[0]);
  input.value = "";
}
function dropped(event: DragEvent) {
  dropping.value = false;
  void open(event.dataTransfer?.files?.[0]);
}

// ---- playing, with the playhead ----
const made = () => ringtone(sound.value!, rate.value, part.value.start, part.value.end);
const head = ref(-1);
let frame = 0;
function follow() {
  head.value = playing.value ? sounds.position() : -1;
  if (playing.value) frame = requestAnimationFrame(follow);
}
function play() {
  if (playing.value) { sounds.stop(); head.value = -1; return; }
  sounds.playSamples(made(), KEY, props.loops);
  cancelAnimationFrame(frame);
  frame = requestAnimationFrame(follow);
}
function replay() { if (playing.value) { sounds.stop(); play(); } }  // what plays follows the part at once

// ---- the part: dragged on either waveform, or moved by keys ----
type Edge = "start" | "end" | "whole";
let dragging: { edge: Edge; from: number; part: Span; on: "stage" | "overview" } | null = null;
function timeAt(event: PointerEvent, on: "stage" | "overview") {
  const box = (on === "stage" ? stage.value : overview.value)!.getBoundingClientRect();
  const frac = Math.max(0, Math.min(1, (event.clientX - box.left) / (box.width || 1)));
  return on === "stage" ? view.value.start + frac * (view.value.end - view.value.start) : frac * length.value;
}
function down(event: PointerEvent, on: "stage" | "overview") {
  const edge = (on === "stage" ? ((event.target as HTMLElement).closest("[data-edge]") as HTMLElement | null)?.dataset.edge : "whole") as Edge | undefined;
  const time = timeAt(event, on);
  if (!edge || (on === "overview" && (time < part.value.start || time > part.value.end))) {
    part.value = movePart(part.value, "whole", time - span.value / 2, length.value, least.value, props.most);
  }
  dragging = { edge: edge ?? "whole", from: time, part: { ...part.value }, on };
  (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
}
function move(event: PointerEvent) {
  if (!dragging) return;
  const time = timeAt(event, dragging.on);
  const to = dragging.edge === "whole" ? dragging.part.start + time - dragging.from : time;
  part.value = movePart(dragging.edge === "whole" ? dragging.part : part.value, dragging.edge, to, length.value, least.value, props.most);
  if (dragging.on === "overview") view.value = viewAround(part.value, length.value);
}
function up() {
  if (!dragging) return;
  dragging = null;
  view.value = viewAround(part.value, length.value);
  replay();
}
function key(event: KeyboardEvent, edge: Edge) {
  const by = event.key === "ArrowLeft" ? -1 : event.key === "ArrowRight" ? 1 : 0;
  if (!by) return;
  event.preventDefault();
  const step = (event.shiftKey ? 0.5 : 0.05) * by;
  const to = edge === "start" ? part.value.start + step : edge === "end" ? part.value.end + step : part.value.start + step;
  part.value = movePart(part.value, edge, to, length.value, least.value, props.most);
  view.value = viewAround(part.value, length.value);
  replay();
}
function space(event: KeyboardEvent) {
  if (!sound.value || (event.target as HTMLElement).closest("input, button")) return;
  event.preventDefault();
  play();
}
function cancel() {
  if (playing.value) sounds.stop();
  sound.value = null;
  emit("cancel");
}
function save() {
  if (playing.value) sounds.stop();
  emit("save", name.value.trim(), made());
}
</script>

<template>
  <div class="ae" :id="`${idPrefix}-editor`" @keydown.space="space">
    <input ref="picker" type="file" accept="audio/*,.wav,.mp3,.m4a,.ogg,.flac" hidden @change="picked" />

    <!-- No file yet: a place to drop one. -->
    <div v-if="!sound" class="ae-drop" :class="{ over: dropping }" :id="`${idPrefix}-drop`"
      @dragover.prevent="dropping = true" @dragleave="dropping = false" @drop.prevent="dropped">
      <span class="mdi ae-drop-mark" aria-hidden="true">{{ MUSIC }}</span>
      <strong>{{ reading ? t("editor.common.loading") : t("editor.sounds.editor.drop") }}</strong>
      <span class="ae-drop-note">{{ t(loops ? "editor.sounds.editor.drop_loop" : "editor.sounds.editor.drop_once", { seconds: number(most, 0) }) }}</span>
      <div class="ae-drop-keys">
        <button type="button" class="btn primary" :id="`${idPrefix}-choose`" :disabled="reading" @click="choose">{{ t("editor.sounds.own_choose") }}</button>
        <button type="button" class="btn quiet" @click="cancel">{{ t("editor.common.cancel") }}</button>
      </div>
    </div>

    <template v-else>
      <header class="ae-head">
        <label class="ae-name">
          <span>{{ t("editor.sounds.own_name") }}</span>
          <input v-model="name" type="text" :maxlength="sounds.view?.name_most ?? 40" :id="`${idPrefix}-name`" />
        </label>
        <span class="ae-file" :title="fileName">{{ fileName }} · {{ t("editor.sounds.editor.total", { time: clock(length) }) }}</span>
        <button type="button" class="btn quiet mini" @click="choose">{{ t("editor.sounds.editor.other_file") }}</button>
      </header>

      <!-- The whole file, the part in it. -->
      <div ref="overview" class="ae-overview" :aria-label="t('editor.sounds.editor.whole')" role="group"
        @pointerdown="(e) => down(e, 'overview')" @pointermove="move" @pointerup="up" @pointercancel="up">
        <svg :viewBox="`0 0 ${overviewBars.length * 3} 40`" preserveAspectRatio="none" aria-hidden="true">
          <rect v-for="(p, i) in overviewBars" :key="i" :x="i * 3" :y="20 - Math.max(1, (p / overviewTop) * 18)" width="2"
            :height="Math.max(2, (p / overviewTop) * 36)" rx="1" />
        </svg>
        <span class="ae-window" :style="{ left: inFile(view.start), width: `calc(${inFile(view.end)} - ${inFile(view.start)})` }" />
        <span class="ae-overview-part" :style="{ left: inFile(part.start), width: `calc(${inFile(part.end)} - ${inFile(part.start)})` }" />
      </div>

      <!-- The part, large. -->
      <div ref="stage" class="ae-stage" @pointerdown="(e) => down(e, 'stage')" @pointermove="move" @pointerup="up" @pointercancel="up">
        <svg class="ae-wave" :viewBox="`0 0 ${stageBars.length * 4} 100`" preserveAspectRatio="none" aria-hidden="true">
          <rect v-for="(b, i) in stageBars" :key="i" :class="{ in: b.in }" :x="i * 4 + 1" :y="50 - b.h / 2" width="2.4" :height="b.h" rx="1.2" />
        </svg>
        <div class="ae-part" data-edge="whole" tabindex="0" role="group" :aria-label="t('editor.sounds.editor.part')"
          :style="{ left: inView(part.start), width: `calc(${inView(part.end)} - ${inView(part.start)})` }" @keydown="(e) => key(e, 'whole')">
          <span class="ae-grip start" data-edge="start" tabindex="0" role="slider" :aria-label="t('editor.sounds.editor.start')"
            :aria-valuemin="0" :aria-valuemax="length" :aria-valuenow="part.start" :aria-valuetext="clock(part.start)" @keydown.stop="(e) => key(e, 'start')">
            <span class="ae-tag">{{ clock(part.start) }}</span>
          </span>
          <span class="ae-grip end" data-edge="end" tabindex="0" role="slider" :aria-label="t('editor.sounds.editor.end')"
            :aria-valuemin="0" :aria-valuemax="length" :aria-valuenow="part.end" :aria-valuetext="clock(part.end)" @keydown.stop="(e) => key(e, 'end')">
            <span class="ae-tag">{{ clock(part.end) }}</span>
          </span>
        </div>
        <span v-if="head >= 0" class="ae-head-line" :style="{ left: inView(part.start + head) }" />
      </div>
      <div class="ae-ruler" aria-hidden="true">
        <span v-for="tick in ruler.ticks" :key="tick" :style="{ left: inView(tick) }">{{ mark(tick, ruler.step) }}</span>
      </div>

      <div class="ae-bar">
        <button type="button" class="ae-play" :class="{ on: playing }" :id="`${idPrefix}-play`"
          :aria-label="playing ? t('editor.sounds.stop') : t('editor.sounds.play')" @click="play">
          <span class="mdi">{{ playing ? STOP : PLAY }}</span>
        </button>
        <div class="ae-length" :id="`${idPrefix}-times`">
          <strong>{{ clock(span) }}</strong>
          <span>{{ t("editor.sounds.editor.of_most", { most: number(most, 0) }) }}</span>
          <span class="ae-meter"><i :style="{ width: `${Math.min(100, (100 * span) / most)}%` }" /></span>
        </div>
        <ul class="ae-chips" :aria-label="t('editor.sounds.editor.made')">
          <li>{{ t("editor.sounds.editor.no_bass") }}</li>
          <li>{{ t("editor.sounds.editor.soft_ends") }}</li>
          <li>{{ t("editor.sounds.editor.even_level") }}</li>
          <li v-if="loops"><Icon name="repeat" />{{ t("editor.sounds.editor.repeats") }}</li>
        </ul>
      </div>
      <p class="hint ae-hint">{{ t(loops ? "editor.sounds.own_drag_loop" : "editor.sounds.own_drag_once") }}</p>

      <footer class="ae-foot">
        <button type="button" class="btn quiet" @click="cancel">{{ t("editor.common.cancel") }}</button>
        <button type="button" class="btn primary" :id="`${idPrefix}-save`" :disabled="busy || !name.trim()" @click="save">{{ t("editor.sounds.own_save") }}</button>
      </footer>
    </template>
  </div>
</template>

<style scoped>
.ae { display: grid; gap: 12px; padding: 16px; border-radius: 14px; background: var(--surface-2); }
.ae .hint { margin: 0; }

.ae-drop { display: grid; justify-items: center; gap: 6px; padding: 28px 16px; border-radius: 12px; border: 2px dashed var(--line-strong); text-align: center; transition: border-color 0.12s, background 0.12s; }
.ae-drop.over { border-color: var(--accent); background: var(--accent-soft); }
.ae-drop-mark { font-size: 34px; color: var(--accent); line-height: 1; }
.ae-drop-note { color: var(--muted); font-size: 13px; max-width: 46ch; }
.ae-drop-keys { display: flex; gap: 8px; margin-top: 8px; }

.ae-head { display: flex; align-items: flex-end; gap: 12px; flex-wrap: wrap; }
.ae-name { display: grid; gap: 4px; flex: 1 1 220px; max-width: 360px; }
.ae-name span { font-size: 12px; color: var(--muted); }
.ae-name input { font-size: 15px; font-weight: 600; }
.ae-file { flex: 1 1 160px; color: var(--muted); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding-bottom: 8px; }
.ae-head .btn { margin-bottom: 4px; }

.ae-overview { position: relative; height: 40px; border-radius: 8px; background: var(--surface); cursor: pointer; touch-action: none; user-select: none; overflow: hidden; }
.ae-overview svg { position: absolute; inset: 0; width: 100%; height: 100%; }
.ae-overview rect { fill: var(--muted); opacity: 0.55; }
.ae-window { position: absolute; top: 0; bottom: 0; background: color-mix(in srgb, var(--ink) 6%, transparent); pointer-events: none; }
.ae-overview-part { position: absolute; top: 3px; bottom: 3px; border-radius: 5px; background: color-mix(in srgb, var(--accent) 28%, transparent); box-shadow: inset 0 0 0 1.5px var(--accent); pointer-events: none; }

.ae-stage { position: relative; height: 150px; margin-top: 16px; border-radius: 10px; background: var(--surface); touch-action: none; user-select: none; overflow: visible; cursor: pointer; }
.ae-wave { position: absolute; inset: 10px 0; width: 100%; height: calc(100% - 20px); }
.ae-wave rect { fill: var(--muted); opacity: 0.35; transition: opacity 0.1s; }
.ae-wave rect.in { fill: var(--accent); opacity: 1; }
.ae-part { position: absolute; top: 0; bottom: 0; background: color-mix(in srgb, var(--accent) 10%, transparent); border-top: 2px solid var(--accent); border-bottom: 2px solid var(--accent); cursor: grab; outline: none; }
.ae-part:focus-visible { box-shadow: 0 0 0 2px var(--focus, var(--accent)); }
.ae-part:active { cursor: grabbing; }
.ae-grip { position: absolute; top: -2px; bottom: -2px; width: 18px; cursor: ew-resize; outline: none; }
.ae-grip.start { left: -9px; }
.ae-grip.end { right: -9px; }
.ae-grip::before { content: ""; position: absolute; left: 7px; top: 0; bottom: 0; width: 4px; border-radius: 2px; background: var(--accent); }
.ae-grip::after { content: ""; position: absolute; left: 3px; top: 50%; width: 12px; height: 28px; margin-top: -14px; border-radius: 6px; background: var(--accent); box-shadow: var(--shadow); }
.ae-grip:focus-visible::after { box-shadow: 0 0 0 3px var(--surface), 0 0 0 5px var(--accent); }
.ae-tag { position: absolute; bottom: calc(100% + 4px); left: 50%; transform: translateX(-50%); padding: 2px 6px; border-radius: 6px; background: var(--accent); color: var(--accent-ink); font-size: 11px; font-weight: 600; font-variant-numeric: tabular-nums; white-space: nowrap; pointer-events: none; }
.ae-head-line { position: absolute; top: 6px; bottom: 6px; width: 2px; margin-left: -1px; border-radius: 1px; background: var(--ink); pointer-events: none; }

.ae-ruler { position: relative; height: 16px; margin-top: -6px; }
.ae-ruler span { position: absolute; transform: translateX(-50%); font-size: 11px; color: var(--muted); font-variant-numeric: tabular-nums; }
.ae-ruler span::before { content: ""; position: absolute; left: 50%; top: -5px; width: 1px; height: 4px; background: var(--line-strong); }

.ae-bar { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.ae-play { flex: none; display: grid; place-items: center; width: 48px; height: 48px; border-radius: 50%; border: 0; background: var(--accent); color: var(--accent-ink); font-size: 26px; cursor: pointer; box-shadow: var(--shadow); }
.ae-play.on { background: var(--ink); color: var(--surface); }
.ae-length { display: grid; grid-template-columns: auto auto; align-items: baseline; column-gap: 6px; row-gap: 4px; min-width: 150px; }
.ae-length strong { font-size: 18px; font-variant-numeric: tabular-nums; }
.ae-length > span:not(.ae-meter) { color: var(--muted); font-size: 12px; }
.ae-meter { grid-column: 1 / -1; height: 4px; border-radius: 2px; background: var(--seg); overflow: hidden; }
.ae-meter i { display: block; height: 100%; border-radius: 2px; background: var(--accent); }
.ae-chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 0 auto; padding: 0; list-style: none; }
.ae-chips li { display: inline-flex; align-items: center; gap: 4px; padding: 3px 9px; border-radius: 999px; background: var(--surface); color: var(--muted); font-size: 12px; }
.ae-hint { font-size: 12px; }
.ae-foot { display: flex; justify-content: flex-end; gap: 8px; }
</style>
