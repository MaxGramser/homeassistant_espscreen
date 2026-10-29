<script setup lang="ts">
// One value along a track (Reka UI's Slider): a light preset's brightness, white shade, hue and saturation. The track
// may be painted (`track`, a CSS background such as the warm-to-cool gradient of a light's whites) and then shows no fill
// of its own; the knob takes the value's colour where one is given. `commit` comes when a drag or a key press ends, so a
// drag is one step of undo (stores/document.ts beginFieldEdit).
import { SliderRange, SliderRoot, SliderThumb, SliderTrack } from "reka-ui";

const props = defineProps<{ modelValue: number; min: number; max: number; step?: number; track?: string; knob?: string; label: string; id?: string }>();
const emit = defineEmits<{ "update:modelValue": [value: number]; start: []; commit: [value: number] }>();
const update = (values: number[] | undefined) => { if (values?.length && values[0] !== props.modelValue) emit("update:modelValue", values[0]); };
</script>

<template>
  <SliderRoot :id="id" class="ui-slider" :class="{ painted: !!track }" :model-value="[modelValue]" :min="min" :max="max" :step="step ?? 1"
    @update:model-value="update" @pointerdown="emit('start')" @value-commit="(v: number[]) => emit('commit', v[0])">
    <SliderTrack class="ui-slider-track" :style="track ? { background: track } : undefined">
      <SliderRange v-if="!track" class="ui-slider-range" />
    </SliderTrack>
    <SliderThumb class="ui-slider-thumb" :aria-label="label" :style="knob ? { background: knob } : undefined" />
  </SliderRoot>
</template>

<style scoped>
.ui-slider { position: relative; display: flex; align-items: center; width: 100%; height: 22px; touch-action: none; user-select: none; }
.ui-slider-track { position: relative; flex: 1; height: 10px; border-radius: 999px; background: var(--seg); overflow: hidden; }
.ui-slider.painted .ui-slider-track { height: 12px; box-shadow: inset 0 0 0 1px var(--line); }
.ui-slider-range { position: absolute; height: 100%; background: var(--accent); border-radius: inherit; }
.ui-slider-thumb { display: block; width: 18px; height: 18px; border-radius: 50%; background: var(--surface); box-shadow: 0 0 0 2px var(--surface), 0 0 0 3px var(--line-strong), var(--shadow); cursor: grab; }
.ui-slider-thumb:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
</style>
