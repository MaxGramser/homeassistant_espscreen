<script setup lang="ts">
import { useResizeObserver } from '@vueuse/core';
import { computed, nextTick, onMounted, ref, watch } from 'vue';

// Measure the actual rendered text and viewport, including font and tile changes.
// A fitting title stays still. The duplicate is visual only, never read twice.
const props = defineProps<{ text: string }>();
const viewport = ref<HTMLElement>();
const content = ref<HTMLElement>();
const distance = ref(0);
function measure() {
  const width = content.value?.scrollWidth || 0;
  const available = viewport.value?.clientWidth || 0;
  distance.value = available > 0 && width > available + 1 ? width + 32 : 0;
}
const style = computed(() => ({
  '--marquee-distance': `${distance.value}px`,
  '--marquee-duration': `${Math.max(6, distance.value / 24 / .85)}s`,
}));
watch(() => props.text, async () => { await nextTick(); measure(); });
useResizeObserver([viewport, content], measure);
onMounted(measure);
</script>

<template>
  <span ref="viewport" class="marquee" :class="{ scrolling: distance > 0 }" :style="style" :title="text">
    <span :key="text" class="marquee-track"><span ref="content" class="marquee-text">{{ text }}</span><span v-if="distance" class="marquee-copy" aria-hidden="true">{{ text }}</span></span>
  </span>
</template>

<style scoped>
.marquee { display: block; min-width: 0; overflow: hidden; white-space: nowrap; }
.marquee-track { display: flex; width: max-content; }
.marquee-text, .marquee-copy { flex: none; }
.marquee-copy { padding-left: 32px; }
.scrolling .marquee-track { animation: media-title var(--marquee-duration) linear 1.4s infinite; }
@keyframes media-title { 0%, 15% { transform: translateX(0); } 100% { transform: translateX(calc(-1 * var(--marquee-distance))); } }
@media (prefers-reduced-motion: reduce) {
  .scrolling .marquee-track { animation: none; }
  .marquee-text { overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
  .marquee-track { width: 100%; }
  .marquee-copy { display: none; }
}
</style>
