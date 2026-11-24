<script setup lang="ts">
// A plugin's tile (design). Where the editor's preview has the plugin's own code, the card is the one the firmware drew
// with it, cut from the firmware's frame (stores/faces.ts useFace, GlassFaces.vue): the plugin's own drawing, at this
// size, on this board. A tile on a page shows what it reads now; a tile that is on no page yet (the library's tiles of
// a plugin) has nothing of its own to read and shows the plugin's own example. Until that picture is there, and for a
// plugin without code for the preview, the editor draws what it can know: with the add-on's preview of its data a
// line's number, where it goes and the minutes to go, counted down on the editor's clock; without, a placeholder with
// the tile's icon, its name, one line of what it shows, and the plugin it comes from.
import { computed, ref, watchEffect } from "vue";
import { text as pluginText } from "../../model/plugins";
import { glyph } from "../../model/topbar";
import { useFace } from "../../stores/faces";
import { usePluginCodeStore } from "../../stores/plugin-code";
import { useScreenStore } from "../../stores/screen";
import type { TileCardView } from "../../composables/useTileCard";

const props = defineProps<{ card: TileCardView }>();
// The same card for as long as this face stands (useTileCard): read without going through the props each time.
const card = props.card;
const code = usePluginCodeStore();
const scr = useScreenStore();
// The firmware's card for this tile at the cells it covers now, asked for while this card stands. Not for the tile
// being carried: that one is drawn where it will land, as the editor marks a landing place.
const drawn = useFace(() => {
  const by = card.placeholder ? null : code.drawnBy(scr.currentScreen, card.tile.entity);
  return by ? { tile: card.tile, columns: card.shape.columns, rows: card.shape.rows, example: !card.tile.id, by } : null;
});
const face = computed(() => {
  const found = drawn.value;
  return found && found.columns === card.shape.columns && found.rows === card.shape.rows ? found : undefined;
});
const glass = ref<HTMLCanvasElement | null>(null);
watchEffect(() => {
  const found = face.value, canvas = glass.value;
  if (!found || !canvas) return;
  // Read the count so a card drawn again is copied again.
  void found.stamp;
  if (canvas.width !== found.width) canvas.width = found.width;
  if (canvas.height !== found.height) canvas.height = found.height;
  const paint = canvas.getContext("2d");
  paint?.clearRect(0, 0, found.width, found.height);
  paint?.drawImage(found.canvas, 0, 0);
});
</script>

<template>
  <canvas v-if="face" ref="glass" class="plugin-glass" :class="{ kept: face.kept }" :aria-label="card.texts.name" role="img"></canvas>
  <span v-else-if="card.pluginRow" class="plugin-live" :class="{ compact: card.shape.columns === 1 && card.shape.rows === 1 }">
    <span class="plugin-live-head"><b v-if="card.pluginRow.badge" class="plugin-live-badge">{{ card.pluginRow.badge }}</b><span class="plugin-live-title">{{ card.pluginRow.title || card.texts.name }}</span></span>
    <span class="plugin-live-value">{{ card.texts.pluginValue }}</span>
  </span>
  <span v-else-if="card.pluginTile" class="plugin-face" :class="{ compact: card.shape.columns === 1 && card.shape.rows === 1 }">
    <span class="plugin-face-icon mdi">{{ glyph(card.pluginTile.tile.icon || card.pluginTile.plugin.icon) }}</span>
    <span class="plugin-face-words"><b>{{ card.texts.name }}</b><small v-if="card.pluginTile.tile.example">{{ pluginText(card.pluginTile.tile.example) }}</small></span>
    <span class="plugin-face-tag"><span class="mdi">{{ glyph("F0A66") }}</span>{{ pluginText(card.pluginTile.plugin.name) }}</span>
  </span>
</template>
