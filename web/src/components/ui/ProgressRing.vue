<script setup lang="ts">
// How far a build is, as a ring the size of a letter (the sidebar's rows, the overview's cards, the header): the arc
// fills as the build goes, an empty ring waits its turn, and without a number the arc turns, as the spinner did.
import { computed } from "vue";

const props = withDefaults(defineProps<{ percent: number | null; label: string; size?: number }>(), { size: 14 });
// A circle of radius 6 in a box of 16, its stroke 2 wide: the same weight as the spinner it stands in for.
const LENGTH = 2 * Math.PI * 6;
const offset = computed(() => props.percent === null ? LENGTH * 0.72 : LENGTH * (1 - Math.min(100, Math.max(0, props.percent)) / 100));
</script>

<template>
  <svg class="ring" :class="{ 'ring-turning': percent === null, 'ring-waiting': percent === 0 }" :width="size" :height="size" viewBox="0 0 16 16" role="progressbar" :aria-label="label"
    aria-valuemin="0" aria-valuemax="100" :aria-valuenow="percent ?? undefined">
    <circle class="ring-track" cx="8" cy="8" r="6" />
    <circle class="ring-arc" cx="8" cy="8" r="6" :stroke-dasharray="LENGTH" :stroke-dashoffset="offset" />
  </svg>
</template>
