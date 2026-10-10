<script setup lang="ts">
// A plugin's tile (design): the editor cannot draw what the plugin draws on the glass. With the add-on's preview of its
// data it looks like the glass (a line's number, where it goes, the minutes to go, counted down on the editor's clock);
// without, a placeholder with the tile's icon, its name, one line of what it shows, and the plugin it comes from.
import { text as pluginText } from "../../model/plugins";
import { glyph } from "../../model/topbar";
import type { TileCardView } from "../../composables/useTileCard";

defineProps<{ card: TileCardView }>();
</script>

<template>
  <span v-if="card.pluginRow" class="plugin-live" :class="{ compact: card.shape.columns === 1 && card.shape.rows === 1 }">
    <span class="plugin-live-head"><b v-if="card.pluginRow.badge" class="plugin-live-badge">{{ card.pluginRow.badge }}</b><span class="plugin-live-title">{{ card.pluginRow.title || card.texts.name }}</span></span>
    <span class="plugin-live-value">{{ card.texts.pluginValue }}</span>
  </span>
  <span v-else-if="card.pluginTile" class="plugin-face" :class="{ compact: card.shape.columns === 1 && card.shape.rows === 1 }">
    <span class="plugin-face-icon mdi">{{ glyph(card.pluginTile.tile.icon || card.pluginTile.plugin.icon) }}</span>
    <span class="plugin-face-words"><b>{{ card.texts.name }}</b><small v-if="card.pluginTile.tile.example">{{ pluginText(card.pluginTile.tile.example) }}</small></span>
    <span class="plugin-face-tag"><span class="mdi">{{ glyph("F0A66") }}</span>{{ pluginText(card.pluginTile.plugin.name) }}</span>
  </span>
</template>
