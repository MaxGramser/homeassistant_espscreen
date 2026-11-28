<script setup lang="ts">
// A screen's miniature in the sidebar (model/miniature.ts): its glass in its own proportions and the tiles of its home
// page, drawn as a picture beside its name; a screen that is away is a dark glass. It says nothing a reader of the row
// does not hear from the row itself, so it is hidden from a screen reader.
import { computed } from "vue";
import { miniatureOf } from "../model/miniature";
import type { Screen } from "../types";

const props = defineProps<{ screen: Screen }>();
const mini = computed(() => miniatureOf(props.screen));
</script>

<template>
  <svg class="screen-mini" :class="{ off: !mini.lit }" :viewBox="`0 0 ${mini.width} ${mini.height}`" :width="mini.width" :height="mini.height" aria-hidden="true">
    <rect class="mini-frame" :width="mini.width" :height="mini.height" rx="3.6" />
    <rect class="mini-glass" :x="mini.bezel" :y="mini.bezel" :width="mini.width - 2 * mini.bezel" :height="mini.height - 2 * mini.bezel" rx="2.3" />
    <rect v-for="(tile, index) in mini.tiles" :key="index" class="mini-tile" :x="tile.x" :y="tile.y" :width="tile.width" :height="tile.height" rx="0.8" />
  </svg>
</template>
