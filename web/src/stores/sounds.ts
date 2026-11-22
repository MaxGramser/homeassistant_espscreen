// ---- Sounds: the library of what the screens play, and the one player of the page (docs/SOUNDS.md) ----
// The app keeps the sounds (sounds.py, api/sounds): the ones it comes with, the ones someone cut here, and per kind (a
// call's ring, a doorbell's chime, an alert's tone) the sound for every screen and a screen's own. Every part of Events
// that shows a kind reads it here (components/sounds/SoundPicker.vue), and a sound cut in one tab is in the others at once.
// One sound plays at a time on the whole page, looped as a call rings or once as a chime and an alert play.
import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { api, getJson, send } from "../api";
import { t } from "../i18n";
import { wav } from "../model/ringtone";
import { useUiStore } from "./ui";

export type SoundKind = "call" | "doorbell" | "alert";
export type Sound = { id: string; name?: string; built_in: boolean; file: string; seconds: number };
export type KindView = { default: string; max_seconds: number; loops: boolean; volume: number; screens: { id: string; name: string; sound: string }[] };
export type SoundsView = { rate: number; min_seconds: number; max_seconds: number; max_own: number; name_most: number;
  volume_range: [number, number]; sounds: Sound[];
  kinds: Record<SoundKind, KindView> };
export const NONE = "none";

export const useSoundsStore = defineStore("sounds", () => {
  const ui = useUiStore();
  const view = ref<SoundsView | null>(null);
  const busy = ref(false);
  let loading: Promise<void> | null = null;
  const load = () => (loading ??= getJson<SoundsView>("sounds").then((v) => { view.value = v; }).finally(() => { loading = null; }));

  const nameOf = (sound: string) => {
    if (sound === NONE) return t("editor.sounds.none");
    const found = view.value?.sounds.find((s) => s.id === sound);
    return !found ? sound : found.built_in ? t(`editor.sounds.builtin.${found.id}`) : found.name || found.id;
  };
  /** The sounds that can be chosen for `kind`: those no longer than it allows. */
  const fitting = (kind: SoundKind) => (view.value?.sounds ?? []).filter((s) => s.seconds <= (view.value?.kinds[kind].max_seconds ?? 0) + 0.01);
  const ownCount = computed(() => view.value?.sounds.filter((s) => !s.built_in).length ?? 0);

  async function run(work: () => Promise<SoundsView>, done?: string) {
    busy.value = true;
    try {
      view.value = await work();
      if (done) ui.toast(done);
      return true;
    } catch (error) {
      ui.toast((error as Error).message);
      return false;
    } finally {
      busy.value = false;
    }
  }
  const choose = (kind: SoundKind, screen: string, sound: string) =>
    run(() => send<SoundsView>("sounds/choice", "PUT", { kind, screen, sound }), t("editor.sounds.chosen"));
  /** How loud the screens play `kind`, in dB of full scale. */
  const setVolume = (kind: SoundKind, volume: number) =>
    run(() => send<SoundsView>("sounds/volume", "PUT", { kind, volume }), t("editor.sounds.volume_saved", { volume }));
  /** The screen plays its sound of `kind` now, as it would for real. */
  async function test(kind: SoundKind, screen: string) {
    try {
      await send("sounds/test", "POST", { kind, screen });
      ui.toast(t("editor.sounds.test_sent"));
    } catch (error) {
      ui.toast((error as Error).message);
    }
  }
  function remove(sound: Sound) {
    if (playing.value === sound.id) stop();
    return run(() => send<SoundsView>(`sounds/${sound.id}`, "DELETE"), t("editor.sounds.removed"));
  }
  /** Keeps a sound cut here (16 kHz mono samples), under `name`; its id, or "" when the app refused it. */
  async function add(name: string, samples: Float32Array): Promise<string> {
    let id = "";
    const body = wav(samples, view.value?.rate ?? 16000);
    await run(async () => {
      const answer = await api(`sounds?name=${encodeURIComponent(name)}`, { method: "POST", body: body.slice().buffer, headers: { "Content-Type": "audio/wav" } });
      const result = (await answer.json()) as SoundsView & { id: string };
      id = result.id;
      return result;
    }, t("editor.sounds.saved"));
    return id;
  }

  // ---- the player ----
  let audio: AudioContext | null = null;
  let source: AudioBufferSourceNode | null = null;
  const playing = ref("");
  // Where the sound that plays is: when it started on the context's clock, how long it is, and whether it loops.
  let startedAt = 0, playLength = 0, looping = false;
  const context = () => (audio ??= new AudioContext());
  /** Seconds into the sound that plays now (within one turn of a loop), or -1 when nothing plays. */
  function position() {
    if (!playing.value || !audio || !playLength) return -1;
    const elapsed = audio.currentTime - startedAt;
    return looping ? elapsed % playLength : Math.min(elapsed, playLength);
  }
  function stop() {
    try { source?.stop(); } catch { /* already stopped */ }
    source = null;
    playing.value = "";
  }
  /** Plays `buffer` under `key`, looped or once; a second play of the same key stops it. */
  function playBuffer(buffer: AudioBuffer, key: string, loop: boolean) {
    stop();
    const ctx = context();
    void ctx.resume();
    source = ctx.createBufferSource();
    source.buffer = buffer;
    source.loop = loop;
    source.connect(ctx.destination);
    const mine = source;
    source.onended = () => { if (source === mine) { source = null; playing.value = ""; } };
    source.start();
    startedAt = ctx.currentTime;
    playLength = buffer.duration;
    looping = loop;
    playing.value = key;
  }
  function playSamples(samples: Float32Array, key: string, loop: boolean) {
    const rate = view.value?.rate ?? 16000;
    const buffer = context().createBuffer(1, samples.length, rate);
    buffer.copyToChannel(new Float32Array(samples), 0);
    playBuffer(buffer, key, loop);
  }
  const buffers = new Map<string, AudioBuffer>();
  /** Plays `sound` here at `volume` dB, the way the screens get it (louder or softer than they sound, but in proportion). */
  async function play(sound: Sound, loop: boolean, key = sound.id, volume?: number) {
    if (playing.value === key) return stop();
    const cached = `${sound.file}@${volume ?? ""}`;
    let buffer = buffers.get(cached);
    if (!buffer) {
      buffer = await context().decodeAudioData(await (await api(`sounds/${sound.id}.wav${volume === undefined ? "" : `?volume=${volume}`}`)).arrayBuffer());
      buffers.set(cached, buffer);
    }
    playBuffer(buffer, key, loop);
  }
  /** A sound file of someone's, decoded and brought to the app's rate, both channels into one (Web Audio's resampler). */
  async function decode(file: File): Promise<Float32Array> {
    const rate = view.value?.rate ?? 16000;
    const decoded = await context().decodeAudioData(await file.arrayBuffer());
    const offline = new OfflineAudioContext(1, Math.max(1, Math.ceil(decoded.duration * rate)), rate);
    const node = offline.createBufferSource();
    node.buffer = decoded;
    node.connect(offline.destination);
    node.start();
    return (await offline.startRendering()).getChannelData(0).slice();
  }

  return { view, busy, load, nameOf, fitting, ownCount, choose, setVolume, test, remove, add, playing, position, stop, play, playSamples, decode };
});
