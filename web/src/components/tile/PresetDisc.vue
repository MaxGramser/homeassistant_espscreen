<script setup lang="ts">
// One of a light's presets as the screen draws its key (light_presets::key): a disc in its colour, a hairline round a pale
// one, its brightness small and quiet in the middle where the tile shows it, and Home Assistant's focus ring a little way
// round the one the light shows. A brightness alone stands on the light's pale amber; a preset without a colour of its own
// (an effect, the lamp's own preset) is a plain grey key with the first two characters of its name. Used on the mockup's
// cards and in the inspector's presets, so both look like the glass.
import { computed } from "vue";
import theme from "virtual:esp-screens-theme";
import { darkInk, hex, neutral, pale, presetLabel, presetRgb, type Preset } from "../../model/light-presets";

const props = defineProps<{ preset: Preset; lit?: boolean; level?: boolean }>();
const role = (name: string) => hex(theme.roles[name].light);
const plain = computed(() => neutral(props.preset));
const look = computed(() => {
  const c = presetRgb(props.preset);
  return { background: plain.value ? role("TRACK") : c === null ? role("AMBER_TRACK") : hex(c), borderColor: pale(props.preset) ? role("LINE") : "transparent",
    color: role(plain.value ? "INK" : darkInk(props.preset) ? "PRESET_INK_DARK" : "PRESET_INK_LIGHT"), outlineColor: role("INK") };
});
// A plain key always writes its name; any other its brightness where asked (Presets::label).
const text = computed(() => (plain.value ? presetLabel(props.preset, false) : props.level && props.preset.b !== undefined ? String(props.preset.b) : ""));
</script>

<template>
  <span class="preset-disc" :class="{ lit, plain }" :style="look"><span v-if="text" class="preset-level">{{ text }}</span></span>
</template>

<style scoped>
.preset-disc { box-sizing: border-box; display: grid; place-items: center; border-radius: 50%; border: 1px solid; line-height: 1; outline: 0 solid; outline-offset: var(--ring-pad, 3px); }
.preset-disc.lit { outline-width: var(--ring-w, 2px); }
/* Quiet: the colour is the key, its brightness a whisper on it (LV_OPA_40); a plain key's name a little stronger (LV_OPA_70). */
.preset-level { opacity: .4; font-variant-numeric: tabular-nums; }
.preset-disc.plain .preset-level { opacity: .7; }
</style>
