<script setup lang="ts">
// The screensaver's clock in miniature, in the glass's own proportions: the time large in the middle, the date under it
// and the bottom line with the temperature and the entities, white on black as the screen draws it. A line wider than
// the glass loses its last entities until it fits, as on the screen, so the temperature always stays.
import { useResizeObserver } from "@vueuse/core";
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { glyph } from "../model/topbar";
import { useTopbarStore } from "../stores/topbar";
import { useScreensaverStore } from "../stores/screensaver";

const topbar = useTopbarStore();
const screensaver = useScreensaverStore();

defineProps<{ height: number }>();
const line = ref<HTMLElement | null>(null);
const items = computed(() => screensaver.saverItems.map((it) => {
  const view = topbar.topbarView(it);
  return { key: it.entity, icon: view.icon && it.icon !== "none" ? glyph(view.icon) : "", text: it.content === "icon" ? "" : view.text };
}));
const temperature = computed(() => ((screensaver.saver?.weather ?? "auto") === "" ? null : screensaver.clockPreview.temperature));
const fit = ref(items.value.length);
async function measure() {
  fit.value = items.value.length;
  await nextTick();
  while (line.value && fit.value > 0 && line.value.scrollWidth > line.value.clientWidth + 1) {
    fit.value -= 1;
    await nextTick();
  }
}
watch([items, temperature], measure, { deep: true });
onMounted(measure);
useResizeObserver(line, () => measure());
</script>

<template>
  <div class="saver-glass" aria-hidden="true" :style="{ aspectRatio: screensaver.glassRatio, height: `${height}px`, '--glass-h': `${height}px` }">
    <span class="saver-glass-time">{{ screensaver.clockPreview.time }}</span>
    <span class="saver-glass-date">{{ screensaver.clockPreview.date }}</span>
    <span ref="line" class="saver-glass-line">
      <span v-if="temperature">{{ temperature }}</span>
      <span v-for="it in items.slice(0, fit)" :key="it.key"><span v-if="it.icon" class="mdi">{{ it.icon }}</span>{{ it.text }}</span>
    </span>
  </div>
</template>

<style scoped>
.saver-glass { display: grid; justify-items: center; align-content: center; gap: 2px; width: auto; max-width: 100%; justify-self: center; position: relative;
  border-radius: calc(var(--glass-h) * 0.07); background: #000; color: #fff; padding: 0 10px; }
.saver-glass-time { font-size: calc(var(--glass-h) * 0.25); font-weight: 300; line-height: 1; letter-spacing: -0.01em; font-variant-numeric: tabular-nums; }
.saver-glass-date { font-size: max(10px, calc(var(--glass-h) * 0.07)); opacity: 0.8; }
.saver-glass-line { position: absolute; left: 8px; right: 8px; bottom: calc(var(--glass-h) * 0.06); display: flex; justify-content: safe center; gap: 4px;
  font-size: max(10px, calc(var(--glass-h) * 0.064)); opacity: 0.85; white-space: nowrap; overflow: hidden; }
.saver-glass-line > span + span::before { content: "·"; margin-right: 4px; opacity: 0.7; }
.saver-glass-line .mdi { margin-right: 3px; }
</style>
