<script setup lang="ts">
// What the screens play for one kind of sound (docs/SOUNDS.md): a call's ring, a doorbell's chime or an alert's tone,
// in that kind's own part of Events (CallsView, DoorbellView, AlertsView). One card: the sound for every screen with a
// key to hear each, how loud the screens play it (Volume, -20 dB unless changed), a sound of one's own made from a file
// (AudioEditor), and each screen that can play this kind with a sound of its own and a Test key that plays it there as it
// would for real. Only screens with a speaker are listed; the library is the app's, the same in every kind
// (stores/sounds.ts), and a kind offers what fits its length.
import { computed, nextTick, onMounted, ref } from "vue";
import { editorLanguage, t } from "../../i18n";
import { glyph } from "../../model/topbar";
import { NONE, useSoundsStore, type Sound, type SoundKind } from "../../stores/sounds";
import Icon from "../ui/Icon.vue";
import UiSelect from "../ui/UiSelect.vue";
import UiSlider from "../ui/UiSlider.vue";
import AudioEditor from "./AudioEditor.vue";

const props = defineProps<{ kind: SoundKind }>();
const sounds = useSoundsStore();
const PLAY = glyph("F040A"), STOP = glyph("F04DB"), REMOVE = glyph("F09E7"), TEST = glyph("F057E");
// An app that does not answer leaves the card as it is: it loads again when it is opened next.
onMounted(() => { sounds.load().catch((error: unknown) => console.error("The sounds could not be read:", error)); });

const kind = computed(() => sounds.view?.kinds[props.kind]);
const secondsText = (value: number) => new Intl.NumberFormat(editorLanguage(), { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(value);
const choices = computed(() => [...sounds.fitting(props.kind), null]);  // null: no sound
const screenChoices = computed(() => [["", t("editor.sounds.screens_same")] as const,
  ...sounds.fitting(props.kind).map((s) => [s.id, sounds.nameOf(s.id)] as const), [NONE, t("editor.sounds.none")] as const]);
const key = (sound: Sound) => `${props.kind}-${sound.id}`;
const cutting = ref(false);
const cutter = ref<InstanceType<typeof AudioEditor> | null>(null);
const full = computed(() => sounds.ownCount >= (sounds.view?.max_own ?? 12));
function startCut() {
  cutting.value = true;
  // The file chooser at once, from the same tap (a browser opens it only from one).
  void nextTick(() => cutter.value?.choose());
}
// The volume follows the slider at once and is kept when the hand lets go.
const volume = ref<number | null>(null);
const shown = computed(() => volume.value ?? kind.value?.volume ?? -20);
async function keepVolume(value: number) {
  await sounds.setVolume(props.kind, value);
  volume.value = null;
}
const soundOf = (screen: { sound: string }) => screen.sound || kind.value?.default || NONE;
async function save(name: string, samples: Float32Array) {
  const id = await sounds.add(name, samples);
  if (!id) return;
  cutting.value = false;
  await sounds.choose(props.kind, "", id);
}
</script>

<template>
  <section class="card sound-picker" :id="`sounds-${kind ? props.kind : 'loading'}`" :aria-busy="sounds.busy">
    <h2>{{ t(`editor.sounds.kinds.${props.kind}.title`) }}</h2>
    <p class="hint">{{ t(`editor.sounds.kinds.${props.kind}.text`) }}</p>
    <template v-if="kind">
      <div class="sound-list" role="radiogroup" :aria-label="t(`editor.sounds.kinds.${props.kind}.title`)">
        <div v-for="sound in choices" :key="sound?.id ?? NONE" class="sound-row" :class="{ chosen: kind.default === (sound?.id ?? NONE) }"
          :data-sound="sound?.id ?? NONE">
          <button v-if="sound" type="button" class="sound-play" :class="{ on: sounds.playing === key(sound) }"
            :aria-label="sounds.playing === key(sound) ? t('editor.sounds.stop') : t('editor.sounds.play')"
            @click="sounds.play(sound, kind.loops, key(sound), kind.volume)"><span class="mdi">{{ sounds.playing === key(sound) ? STOP : PLAY }}</span></button>
          <span v-else class="sound-play-space" />
          <button type="button" role="radio" class="sound-pick" :aria-checked="kind.default === (sound?.id ?? NONE)" :disabled="sounds.busy"
            @click="sounds.choose(props.kind, '', sound?.id ?? NONE)">
            <span>{{ sounds.nameOf(sound?.id ?? NONE) }}</span>
            <small v-if="sound && !sound.built_in">{{ t("editor.sounds.seconds", { seconds: secondsText(sound.seconds) }) }}</small>
            <Icon v-if="kind.default === (sound?.id ?? NONE)" name="check" />
          </button>
          <button v-if="sound && !sound.built_in" type="button" class="btn quiet mini" :aria-label="t('editor.common.remove')" :disabled="sounds.busy"
            @click="sounds.remove(sound)"><span class="mdi">{{ REMOVE }}</span></button>
        </div>
      </div>

      <div class="sound-volume">
        <span>{{ t("editor.sounds.volume") }}</span>
        <UiSlider :id="`sounds-${props.kind}-volume`" :model-value="shown" :min="sounds.view?.volume_range[0] ?? -40" :max="sounds.view?.volume_range[1] ?? 0"
          :step="1" :label="t('editor.sounds.volume')" @update:model-value="(v) => (volume = v)" @commit="keepVolume" />
        <strong>{{ t("editor.sounds.volume_db", { volume: shown }) }}</strong>
      </div>

      <div class="sound-own">
        <p v-if="full && !cutting" class="hint">{{ t("editor.sounds.own_full", { most: sounds.view?.max_own ?? 12 }) }}</p>
        <button v-else-if="!cutting" type="button" class="btn" :id="`sounds-${props.kind}-own`" @click="startCut">
          <Icon name="plus" />{{ t("editor.sounds.own_add") }}
        </button>
        <AudioEditor v-if="cutting" ref="cutter" :most="kind.max_seconds" :loops="kind.loops" :id-prefix="`sounds-${props.kind}`"
          :busy="sounds.busy" @save="save" @cancel="cutting = false" />
      </div>

      <div v-if="kind.screens.length" class="sound-screens">
        <h3>{{ t("editor.sounds.screens_title") }}</h3>
        <div v-for="screen in kind.screens" :key="screen.id" class="sound-screen" :data-screen="screen.id">
          <span>{{ screen.name }}</span>
          <UiSelect :model-value="screen.sound" :options="screenChoices" :disabled="sounds.busy" :aria-label="screen.name"
            @update:model-value="(sound) => sounds.choose(props.kind, screen.id, String(sound))" />
          <button type="button" class="btn quiet sound-test" :disabled="sounds.busy || soundOf(screen) === NONE"
            :title="t('editor.sounds.test_hint')" @click="sounds.test(props.kind, screen.id)"><span class="mdi">{{ TEST }}</span>{{ t("editor.sounds.test") }}</button>
        </div>
      </div>
      <p v-else class="hint">{{ t("editor.sounds.screens_none") }}</p>
    </template>
  </section>
</template>

<style scoped>
.sound-picker { display: grid; gap: 12px; }
.sound-picker h2 { font-size: 15px; margin: 0; }
.sound-picker h3 { font-size: 13px; margin: 0 0 4px; color: var(--muted); font-weight: 600; }
.sound-picker .hint { margin: 0; }
.sound-list { display: grid; gap: 4px; }
.sound-row { display: flex; align-items: center; gap: 8px; }
.sound-play, .sound-play-space { flex: none; width: 34px; height: 34px; }
.sound-play { display: grid; place-items: center; border-radius: 50%; border: 0; background: var(--surface-2); color: var(--ink); font-size: 18px; cursor: pointer; }
.sound-play.on { background: var(--accent); color: var(--accent-ink); }
.sound-pick { flex: 1; display: flex; align-items: center; gap: 8px; min-height: 38px; padding: 0 12px; border-radius: 10px; border: 0; background: transparent; color: inherit; font: inherit; text-align: left; cursor: pointer; }
.sound-pick > span { flex: 1; }
.sound-pick small { color: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; }
.sound-pick:hover { background: var(--surface-2); }
.sound-row.chosen .sound-pick { background: var(--surface-2); font-weight: 600; }
.sound-pick .ui-icon { color: var(--accent); }
.sound-own { display: grid; }
.sound-own > .btn { justify-self: start; }
.sound-screens { display: grid; gap: 2px; }
.sound-screen { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 42px; }
.sound-screen > span { min-width: 0; overflow-wrap: anywhere; }
.sound-screen :deep(.ui-select) { min-width: 200px; margin-left: auto; }
.sound-test { flex: none; }
.sound-test .mdi { font-size: 16px; }
.sound-volume { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 12px; max-width: 520px; }
.sound-volume > span { font-size: 13px; color: var(--muted); }
.sound-volume strong { font-variant-numeric: tabular-nums; min-width: 56px; text-align: right; }
</style>
