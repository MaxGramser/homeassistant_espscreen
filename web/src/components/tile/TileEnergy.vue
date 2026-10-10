<script setup lang="ts">
// The energy card (app 0.4.77): the screen draws the house live from Home Assistant's Energy settings, as its own live view
// does; the mockup shows the diagram's shape, the sources around the house, in their paints.
import { glyph } from "../../model/topbar";
import type { TileCardView } from "../../composables/useTileCard";

const props = defineProps<{ card: TileCardView }>();
// The same card for as long as this face stands (useTileCard): read without going through the props each time.
const card = props.card;
</script>

<template>
  <svg class="energy-diagram" viewBox="0 0 200 100" aria-hidden="true">
    <g fill="none" stroke-width="1.5">
      <path d="M100 32 V40 Q100 46 106 46 H161" :stroke="card.energy.solar" />
      <path d="M39 50 H161" :stroke="card.energy.grid" />
      <path d="M100 68 V60 Q100 54 106 54 H161" :stroke="card.energy.battery" />
    </g>
    <g fill="#fff" stroke-width="1.5">
      <circle cx="100" cy="18" r="14" :stroke="card.energy.solar" />
      <circle cx="25" cy="50" r="14" :stroke="card.energy.grid" />
      <circle cx="100" cy="82" r="14" :stroke="card.energy.battery" />
      <circle cx="175" cy="50" r="14" :stroke="card.energy.ink" stroke-width="2" />
    </g>
    <g class="mdi" text-anchor="middle" dominant-baseline="central" font-size="13" :fill="card.energy.ink">
      <text x="100" y="18">{{ glyph("F0A72") }}</text>
      <text x="25" y="50">{{ glyph("F0D3E") }}</text>
      <text x="100" y="82">{{ glyph("F007F") }}</text>
      <text x="175" y="50">{{ glyph("F02DC") }}</text>
    </g>
  </svg>
</template>
