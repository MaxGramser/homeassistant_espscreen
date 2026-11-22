<script setup lang="ts">
// Calls, a part of Events (EventsView, docs/CALLS.md "Ringtone"): what rings on a screen when another screen calls it.
// The app keeps the choice (ringtones.py, api/ringtones): one tone for every screen and, where someone set one, a
// screen's own. Four tones come with the app; someone can add their own here: a sound file is decoded and brought to
// 16 kHz mono by the browser, drawn as a waveform, and the part that rings is picked on it, at most `max_seconds`, with
// the pause it wants before it rings again. Play loops that part as the screen will, after the bass is filtered out and
// the level raised (model/ringtone.ts); Save sends the finished WAV, which a screen downloads with its next ring.
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { api, getJson, send } from "../api";
import { t } from "../i18n";
import { firstPart, highPass, movePart, peaks, ringtone, wav } from "../model/ringtone";
import { glyph } from "../model/topbar";
import { useUiStore } from "../stores/ui";
import Icon from "./ui/Icon.vue";
import UiSelect from "./ui/UiSelect.vue";

type Tone = { id: string; name?: string; built_in: boolean; file: string };
type View = { rate: number; max_seconds: number; min_seconds: number; max_own: number; name_most: number; default: string; tones: Tone[];
  screens: { id: string; name: string; tone: string }[] };
type Part = { start: number; end: number };

const ui = useUiStore();
const view = ref<View | null>(null);
const busy = ref(false);
const PLAY = glyph("F040A"), STOP = glyph("F04DB"), RING = glyph("F11AB"), REMOVE = glyph("F09E7");

onMounted(async () => { view.value = await getJson<View>("ringtones"); });
onBeforeUnmount(() => { stop(); void audio?.close(); });

const nameOf = (tone: Tone) => (tone.built_in ? t(`editor.calls.tones.${tone.id}`) : tone.name || tone.id);
const ownCount = computed(() => view.value?.tones.filter((tone) => !tone.built_in).length ?? 0);
const screenChoices = computed(() => [["", t("editor.calls.screens_same")] as const,
  ...(view.value?.tones ?? []).map((tone) => [tone.id, nameOf(tone)] as const)]);

async function run(work: () => Promise<View>, done?: string) {
  busy.value = true;
  try {
    view.value = await work();
    if (done) ui.toast(done);
  } catch (error) {
    ui.toast((error as Error).message);
  } finally {
    busy.value = false;
  }
}
const choose = (screen: string, tone: string) => run(() => send<View>("ringtones/choice", "PUT", { screen, tone }), t("editor.calls.chosen"));
const remove = (tone: Tone) => { if (playing.value === tone.id) stop(); return run(() => send<View>(`ringtones/${tone.id}`, "DELETE"), t("editor.calls.removed")); };

// ---- playing: one sound at a time, looped as a screen rings ----
let audio: AudioContext | null = null;
let source: AudioBufferSourceNode | null = null;
const playing = ref("");
const context = () => (audio ??= new AudioContext());
function stop() {
  try { source?.stop(); } catch { /* already stopped */ }
  source = null;
  playing.value = "";
}
function loop(buffer: AudioBuffer, key: string) {
  stop();
  const ctx = context();
  void ctx.resume();
  source = ctx.createBufferSource();
  source.buffer = buffer;
  source.loop = true;
  source.connect(ctx.destination);
  source.start();
  playing.value = key;
}
const sounds = new Map<string, AudioBuffer>();
async function playTone(tone: Tone) {
  if (playing.value === tone.id) return stop();
  let buffer = sounds.get(tone.file);
  if (!buffer) {
    const bytes = await (await api(`ringtones/${tone.id}.wav`)).arrayBuffer();
    buffer = await context().decodeAudioData(bytes);
    sounds.set(tone.file, buffer);
  }
  loop(buffer, tone.id);
}

// ---- a tone of one's own ----
const picker = ref<HTMLInputElement | null>(null);
const sound = ref<Float32Array | null>(null);  // the whole file at the app's rate, mono
// What of it the speakers play, without the bass: the waveform shows this, so a part is picked on what will be heard.
const heard = computed(() => (sound.value ? highPass(sound.value, rate.value) : null));
const part = ref<Part>({ start: 0, end: 0 });
const ownName = ref("");
const reading = ref(false);
const COLUMNS = 480;
const rate = computed(() => view.value?.rate ?? 16000);
const most = computed(() => view.value?.max_seconds ?? 3);
const least = computed(() => view.value?.min_seconds ?? 0.25);
const length = computed(() => (sound.value ? sound.value.length / rate.value : 0));
const bars = computed(() => (heard.value ? peaks(heard.value, COLUMNS) : []));
const wave = computed(() => bars.value.map((p, i) => `M${i + 0.5} ${50 - Math.max(0.5, p * 48)}V${50 + Math.max(0.5, p * 48)}`).join(""));
const at = (seconds: number) => `${(100 * seconds) / (length.value || 1)}%`;
const seconds = (value: number) => value.toFixed(1);

async function read(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  (event.target as HTMLInputElement).value = "";
  if (!file) return;
  stop();
  reading.value = true;
  try {
    const decoded = await context().decodeAudioData(await file.arrayBuffer());
    // The browser's own resampler down to the app's rate, both channels into one.
    const frames = Math.max(1, Math.ceil(decoded.duration * rate.value));
    const offline = new OfflineAudioContext(1, frames, rate.value);
    const node = offline.createBufferSource();
    node.buffer = decoded;
    node.connect(offline.destination);
    node.start();
    sound.value = (await offline.startRendering()).getChannelData(0).slice();
    part.value = firstPart(heard.value!, rate.value, most.value);
    ownName.value = file.name.replace(/\.[^.]+$/, "").slice(0, view.value?.name_most ?? 40);
  } catch {
    sound.value = null;
    ui.toast(t("editor.calls.own_unreadable"));
  } finally {
    reading.value = false;
  }
}
const made = () => ringtone(sound.value!, rate.value, part.value.start, part.value.end);
function playOwn() {
  if (playing.value === "own") return stop();
  const samples = made();
  const buffer = context().createBuffer(1, samples.length, rate.value);
  buffer.copyToChannel(new Float32Array(samples), 0);
  loop(buffer, "own");
}
function cancelOwn() {
  if (playing.value === "own") stop();
  sound.value = null;
}
async function saveOwn() {
  if (playing.value === "own") stop();
  const body = wav(made(), rate.value);
  await run(async () => {
    const answer = await api(`ringtones?name=${encodeURIComponent(ownName.value)}`, { method: "POST", body: body.slice().buffer, headers: { "Content-Type": "audio/wav" } });
    const result = (await answer.json()) as View & { id: string };
    sound.value = null;
    return result;
  }, t("editor.calls.saved"));
}

// The part on the waveform: drag it to move it, its edges to stretch it, a tap beside it to move it there.
const strip = ref<HTMLElement | null>(null);
let dragging: { edge: "start" | "end" | "whole"; from: number; part: Part } | null = null;
const timeAt = (event: PointerEvent) => {
  const box = strip.value!.getBoundingClientRect();
  return (Math.max(0, Math.min(box.width, event.clientX - box.left)) / (box.width || 1)) * length.value;
};
function down(event: PointerEvent) {
  const edge = ((event.target as HTMLElement).dataset.edge as "start" | "end" | "whole" | undefined) ?? null;
  const time = timeAt(event);
  if (!edge) {
    const span = part.value.end - part.value.start;
    part.value = movePart(part.value, "whole", time - span / 2, length.value, least.value, most.value);
  }
  dragging = { edge: edge ?? "whole", from: time, part: { ...part.value } };
  strip.value!.setPointerCapture(event.pointerId);
}
function move(event: PointerEvent) {
  if (!dragging) return;
  const time = timeAt(event);
  const to = dragging.edge === "whole" ? dragging.part.start + time - dragging.from : time;
  part.value = movePart(dragging.edge === "whole" ? dragging.part : part.value, dragging.edge, to, length.value, least.value, most.value);
}
function up() {
  if (!dragging) return;
  dragging = null;
  // What plays follows the part at once.
  if (playing.value === "own") { stop(); playOwn(); }
}
</script>

<template>
  <div class="calls" id="calls-part">
    <section class="card event-create" id="calls-hero">
      <div class="event-create-text">
        <h2>{{ t("editor.calls.hero_title") }}</h2>
        <p>{{ t("editor.calls.hero_text") }}</p>
      </div>
      <span class="mdi calls-mark" aria-hidden="true">{{ RING }}</span>
    </section>

    <section class="card" id="calls-tones" :aria-busy="busy">
      <h2>{{ t("editor.calls.every_title") }}</h2>
      <div class="calls-tones" role="radiogroup" :aria-label="t('editor.calls.every_title')">
        <div v-for="tone in view?.tones ?? []" :key="tone.id" class="calls-tone" :class="{ chosen: view?.default === tone.id }" :data-tone="tone.id">
          <button type="button" class="calls-play" :aria-label="playing === tone.id ? t('editor.calls.stop') : t('editor.calls.play')"
            :class="{ on: playing === tone.id }" @click="playTone(tone)"><span class="mdi">{{ playing === tone.id ? STOP : PLAY }}</span></button>
          <button type="button" role="radio" class="calls-pick" :aria-checked="view?.default === tone.id" :disabled="busy" @click="choose('', tone.id)">
            <span>{{ nameOf(tone) }}</span><Icon v-if="view?.default === tone.id" name="check" />
          </button>
          <button v-if="!tone.built_in" type="button" class="btn quiet mini calls-remove" :aria-label="t('editor.common.remove')" :disabled="busy"
            @click="remove(tone)"><span class="mdi">{{ REMOVE }}</span></button>
        </div>
      </div>
    </section>

    <section class="card" id="calls-own">
      <h2>{{ t("editor.calls.own_title") }}</h2>
      <p class="hint">{{ t("editor.calls.own_text", { seconds: most }) }}</p>
      <input ref="picker" type="file" accept="audio/*,.wav,.mp3,.m4a,.ogg,.flac" hidden @change="read" />
      <template v-if="!sound">
        <p v-if="ownCount >= (view?.max_own ?? 12)" class="hint">{{ t("editor.calls.own_full", { most: view?.max_own ?? 12 }) }}</p>
        <button v-else type="button" class="btn primary" id="calls-own-choose" :disabled="reading" @click="picker?.click()">
          <Icon name="tray-arrow-up" />{{ reading ? t("editor.common.loading") : t("editor.calls.own_choose") }}
        </button>
      </template>
      <div v-else class="calls-editor">
        <div ref="strip" class="calls-strip" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up">
          <svg class="calls-wave" :viewBox="`0 0 ${COLUMNS} 100`" preserveAspectRatio="none" aria-hidden="true"><path :d="wave" /></svg>
          <div class="calls-part" data-edge="whole" :style="{ left: at(part.start), width: `calc(${at(part.end)} - ${at(part.start)})` }">
            <span class="calls-edge start" data-edge="start" /><span class="calls-edge end" data-edge="end" />
          </div>
        </div>
        <p class="calls-times" id="calls-own-times">{{ t("editor.calls.own_part", { start: seconds(part.start), end: seconds(part.end), length: seconds(part.end - part.start) }) }}</p>
        <p class="hint">{{ t("editor.calls.own_drag") }}</p>
        <label class="calls-name">
          <span>{{ t("editor.calls.own_name") }}</span>
          <input v-model="ownName" type="text" :maxlength="view?.name_most ?? 40" id="calls-own-name" />
        </label>
        <div class="calls-actions">
          <button type="button" class="btn" id="calls-own-play" @click="playOwn"><span class="mdi">{{ playing === "own" ? STOP : PLAY }}</span>
            {{ playing === "own" ? t("editor.calls.stop") : t("editor.calls.play") }}</button>
          <button type="button" class="btn quiet" @click="cancelOwn">{{ t("editor.common.cancel") }}</button>
          <button type="button" class="btn primary" id="calls-own-save" :disabled="busy || !ownName.trim()" @click="saveOwn">{{ t("editor.calls.own_save") }}</button>
        </div>
      </div>
    </section>

    <section class="card" id="calls-screens">
      <h2>{{ t("editor.calls.screens_title") }}</h2>
      <p v-if="view && !view.screens.length" class="hint">{{ t("editor.calls.screens_none") }}</p>
      <div v-for="screen in view?.screens ?? []" :key="screen.id" class="calls-screen" :data-screen="screen.id">
        <span>{{ screen.name }}</span>
        <UiSelect :model-value="screen.tone" :options="screenChoices" :disabled="busy" :aria-label="screen.name"
          @update:model-value="(tone) => choose(screen.id, String(tone))" />
      </div>
    </section>
  </div>
</template>

<style scoped>
.calls { display: grid; gap: 14px; }
.calls h2 { font-size: 15px; margin: 0 0 10px; }
.calls-mark { display: grid; place-items: center; width: 96px; height: 96px; border-radius: 50%; background: var(--surface-2); font-size: 48px; color: var(--accent); }
.calls-tones { display: grid; gap: 6px; }
.calls-tone { display: flex; align-items: center; gap: 8px; }
.calls-play { flex: none; display: grid; place-items: center; width: 34px; height: 34px; border-radius: 50%; border: 0; background: var(--surface-2); color: var(--ink); font-size: 18px; cursor: pointer; }
.calls-play.on { background: var(--accent); color: var(--accent-ink); }
.calls-pick { flex: 1; display: flex; align-items: center; justify-content: space-between; gap: 8px; min-height: 38px; padding: 0 12px; border-radius: 10px; border: 0; background: transparent; color: inherit; font: inherit; text-align: left; cursor: pointer; }
.calls-pick:hover { background: var(--surface-2); }
.calls-tone.chosen .calls-pick { background: var(--surface-2); font-weight: 600; }
.calls-pick .ui-icon { color: var(--accent); }
#calls-own-choose { justify-self: start; }
.calls-editor { display: grid; gap: 10px; }
.calls-strip { position: relative; height: 96px; border-radius: 10px; background: var(--surface-2); overflow: hidden; touch-action: none; cursor: pointer; user-select: none; }
.calls-wave { position: absolute; inset: 0; width: 100%; height: 100%; }
.calls-wave path { stroke: var(--muted); stroke-width: 1; vector-effect: non-scaling-stroke; }
.calls-part { position: absolute; top: 0; bottom: 0; background: color-mix(in srgb, var(--accent) 22%, transparent); box-shadow: inset 0 0 0 2px var(--accent); border-radius: 8px; cursor: grab; }
.calls-edge { position: absolute; top: 0; bottom: 0; width: 14px; cursor: ew-resize; }
.calls-edge::after { content: ""; position: absolute; top: 30%; bottom: 30%; left: 5px; width: 4px; border-radius: 2px; background: var(--accent); }
.calls-edge.start { left: -2px; }
.calls-edge.end { right: -2px; }
.calls-times { margin: 0; font-variant-numeric: tabular-nums; font-weight: 600; }
.calls-name { display: grid; gap: 4px; max-width: 360px; }
.calls-name span { font-size: 13px; color: var(--muted); }
.calls-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.calls-actions .mdi { font-size: 16px; }
.calls-screen { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 42px; }
.calls-screen > span { min-width: 0; overflow-wrap: anywhere; }
.calls-screen :deep(.ui-select) { min-width: 200px; }
</style>
