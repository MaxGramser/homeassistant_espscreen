<script setup lang="ts">
// A thermostat's range as the screen draws it between its -/+ (firmware 0.19.0, runtime_tiles range_chip): the end they
// move as a chip, its number as large as the widest temperature allows on its own, and its heat or cool icon beside it
// only where that fits at the same size; otherwise the number alone in its end's colour. A wide card's chip is worked
// out as the glass works it out (`wide`, ui-scale wideChip); any other is measured whenever it changes size or text.
import { useResizeObserver } from "@vueuse/core";
import { computed, onMounted, onUpdated, ref } from "vue";
import type { RangeChip } from "../../model/tile-text";

const props = defineProps<{ chip: RangeChip; icon: string; wide?: { face: number; icon: boolean } | null; glass?: number }>();
const root = ref<HTMLElement | null>(null);
const measuredLone = ref(false);
// The glass's rule in the mockup's pixels: icon + half a gap + the widest number + a gap within the chip.
function fit() {
  const el = root.value, number = el?.querySelector("b");
  if (props.wide !== undefined || !el || !number || !el.clientWidth) return;
  const style = getComputedStyle(el), icon = parseFloat(style.getPropertyValue("--chip-icon")) || 0;
  const pad = parseFloat(style.getPropertyValue("--chip-pad")) || 0, ems = props.chip.ems || 2;
  measuredLone.value = icon + 1.5 * pad + ems * parseFloat(getComputedStyle(number).fontSize) > el.clientWidth;
}
onMounted(fit);
onUpdated(fit);
useResizeObserver(root, fit);
const lone = computed(() => (props.wide !== undefined ? Boolean(props.wide && !props.wide.icon) : measuredLone.value));
const style = computed(() => ({ "--end": props.chip.color, "--chip-ems": props.chip.ems,
  ...(props.wide ? { "--chip-face": `${(props.wide.face * (props.glass ?? 1)).toFixed(2)}px` } : {}) }));
</script>

<template>
  <span ref="root" class="range-chip" :class="{ lone }" :style="style"><span class="mdi end-icon">{{ icon }}</span><b>{{ chip.text }}</b></span>
</template>

<style scoped>
.range-chip { container-type: inline-size; flex: 1; min-width: 0; align-self: stretch; display: flex; align-items: center; justify-content: center; gap: 3px; margin: 2px 0; padding: 0 6px; border-radius: 999px; }
.range-chip .end-icon { color: var(--end); font-size: 12px; }
.range-chip b { font-weight: 600; white-space: nowrap; }
.target .range-chip { margin: 0; }
/* Under a tall card's head its number is as large as the target's own (.target b, TileTall). */
.target .range-chip b { font-size: clamp(16px, 18cqh, 42px); font-weight: 400; text-align: center; }
.target .range-chip .end-icon { font-size: clamp(12px, 10cqh, 24px); }
/* No room for the icon beside the widest number: the number alone, in its end's colour. */
.range-chip.lone .end-icon { display: none; }
.range-chip.lone b { color: var(--end); }
</style>
