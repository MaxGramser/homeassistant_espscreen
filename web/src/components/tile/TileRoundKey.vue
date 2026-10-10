<script setup lang="ts">
// A key of a bedside clock (app 0.4.12): the card in its round form, its value or its icon in the circle and its name under
// it (firmware 0.17.0: the name can be left off), with the same remove key as a tile at the circle's corner.
import { vDrag } from "../../drag";
import { t } from "../../i18n";
import { glyph } from "../../model/topbar";
import type { TileCardView } from "../../composables/useTileCard";
import { removeTile } from "../../editor/tiles";
import { useCanvasStore } from "../../stores/canvas";
import { useDocumentStore } from "../../stores/document";

const canvas = useCanvasStore();
const doc = useDocumentStore();
defineProps<{ card: TileCardView }>();
defineEmits<{ activate: [] }>();
</script>

<template>
  <span class="round-tile" :class="{ chosen: card.chosen, placeholder: card.placeholder || (!card.live && !card.foreign), 'just-added': !card.preview && !!card.tile.id && doc.justAdded === card.tile.id }"
    :data-tile-id="card.tile.id" :style="{ '--tile-icon': card.palette.icon, '--tile-circle': card.palette.circle }">
    <button type="button" class="round-key" :aria-label="card.texts.name" :disabled="card.preview && !card.live"
      v-drag="card.preview || card.foreign ? null : { kind: 'tile', tile: card.tile }" @click.stop="$emit('activate')">
      <span class="disc" :class="{ lit: card.lit }"><span v-if="card.texts.roundValue" class="value">{{ card.texts.roundValue }}</span><span v-else class="mdi">{{ glyph(card.icon) }}</span></span>
      <span v-if="card.tile.options?.overlay !== 'none' && !canvas.isCompact" class="kn">{{ card.texts.name }}</span>
    </button>
    <!-- The same remove key as on a tile, at the circle's corner. -->
    <button v-if="card.live && !card.preview" type="button" class="remove" :title="t('editor.tile_card.remove')" :aria-label="t('editor.tile_card.remove_named', { name: card.texts.name })" @click.stop="removeTile(card.tile)">✕</button>
  </span>
</template>

<style scoped>
.bedside-clock .round-tile .disc { width: 16cqw; height: 16cqw; font-size: 8cqw; }
.bedside-clock .round-tile .disc .value { font-size: 4cqw; }
.bedside-clock .round-tile, .bedside-clock .round-key { max-width: none; }
.round-tile { position: relative; display: grid; justify-items: center; min-width: 0; max-width: 64px; }
.round-key { display: flex; flex-direction: column; align-items: center; gap: 4px; min-width: 0; max-width: 64px; padding: 0; border: 0; background: transparent; color: inherit; cursor: pointer; font: inherit; }
.round-tile .remove { top: -6px; right: 4px; }
.round-tile .disc { display: grid; place-items: center; width: 36px; height: 36px; border-radius: 50%; background: var(--tile-circle); color: var(--tile-icon); font-size: 19px; }
.round-tile .disc .value { font-size: 10px; color: var(--ink, inherit); }
.round-tile .kn { font-size: 9px; opacity: .7; max-width: 64px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.round-tile.chosen .disc { outline: 2px solid var(--accent, #2196f3); outline-offset: 2px; }
.round-tile.placeholder { opacity: .4; }
</style>
