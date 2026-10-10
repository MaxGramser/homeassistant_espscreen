<script setup lang="ts">
// A Big number card as the glass lays it out in this card's room on this grid (ui-scale watchCard, app 0.4.74): the icon
// and the name above the number in the largest face that fits, or in a low cell the name small in the corner and the
// number under it, each part where the glass puts it.
import { glyph } from "../../model/topbar";
import type { TileCardView } from "../../composables/useTileCard";

const props = defineProps<{ card: TileCardView }>();
// The same card for as long as this face stands (useTileCard): read without going through the props each time.
const card = props.card;
</script>

<template>
  <span v-if="card.watchFace && card.watchStyle" class="watch" :class="{ stacked: card.watchFace.stacked }">
    <span v-if="card.watchFace.stacked" class="ic mdi" :class="{ lit: card.lit }" :style="card.watchStyle.circle">{{ glyph(card.icon) }}</span>
    <span class="nm" :style="card.watchStyle.title">{{ card.texts.name }}</span>
    <template v-if="card.watchFace.stacked">
      <span class="big" :style="card.watchStyle.value">{{ card.texts.value }}</span>
      <span v-if="card.watchStyle.unit" class="unit" :style="card.watchStyle.unit">{{ card.texts.unit }}</span>
    </template>
    <span v-else class="alone" :style="card.watchStyle.row">
      <span class="big" :style="card.watchStyle.value">{{ card.texts.value }}</span>
      <span v-if="card.watchStyle.unit" class="unit" :style="card.watchStyle.unit">{{ card.texts.unit }}</span>
    </span>
  </span>
</template>

<style scoped src="./parts.css"></style>
<style scoped>
.tile .watch { position: relative; flex: 1; align-self: stretch; min-width: 0; min-height: 0; }
.tile .watch > * { position: absolute; margin: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tile .watch .alone { left: 0; right: 0; display: flex; justify-content: center; align-items: flex-end; }
.tile .watch .alone > * { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.tile .watch .alone .unit { flex: none; }
.tile .watch .ic:not(.thumb) { display: grid; place-items: center; padding: 0; line-height: 1; }
.tile .watch .big { font-weight: 500; letter-spacing: 0; }
.tile .watch .unit { color: #5a5f66; font-weight: 400; overflow: visible; }
</style>
