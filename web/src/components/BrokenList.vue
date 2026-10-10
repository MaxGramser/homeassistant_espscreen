<script setup lang="ts">
// The tiles whose entity is gone or has been away for a while (stores/broken.ts), each with where it stands and what is
// wrong: the overview's notice, the sidebar's list and a screen's details show it. A row opens that tile in the inspector
// with the entity picker ready.
import { healthText, whereText, type BrokenTile } from "../model/broken-tiles";
import { glyph } from "../model/topbar";
import { revealTile } from "../composables/revealTile";
import { useBrokenStore } from "../stores/broken";
import { useEntitiesStore } from "../stores/entities";
import { useUiStore } from "../stores/ui";

withDefaults(defineProps<{ tiles: readonly BrokenTile[]; withScreen?: boolean }>(), { withScreen: true });
const emit = defineEmits<{ done: [] }>();
const broken = useBrokenStore();
const entities = useEntitiesStore();
const ui = useUiStore();
async function open(tile: BrokenTile) {
  emit("done");
  if (await broken.show(tile)) void revealTile(tile.tileId);
}
</script>

<template>
  <div class="broken-list">
    <button v-for="tile in tiles" :key="`${tile.screen.id}:${tile.tileId}`" type="button" class="broken-row" :data-tile="tile.tileId" @click="open(tile)">
      <span class="mdi">{{ glyph(entities.automaticIcon(tile.entity)) }}</span>
      <span class="tx">
        <strong>{{ tile.label || entities.entityName(tile.entity) }}</strong>
        <small>{{ [whereText(tile, withScreen), healthText(tile.health, ui.now)].join(" · ") }}</small>
      </span>
    </button>
  </div>
</template>
