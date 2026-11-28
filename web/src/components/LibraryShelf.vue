<script setup lang="ts">
// One entity on the library's shelf (Library.vue, docs/PAGES.md "The library"): one tile, the size that suits its type
// best or the size the person chose for the whole shelf (editor/library-tiles.ts shelfSample), standing in the shelf's
// grid on the cells it takes, as on a page. A click or a drag places that tile. Pointing at it tells the library, which
// opens the card with all of the entity's sizes over it (LibrarySizes.vue). Under the tile stands the entity's name on a
// line of its own, as under a widget in a gallery: a tile's own name shares its room with a slider or a curve, and on
// the shelf the name is what a thing is found by.
import { computed } from "vue";
import { samplesOf, shelfSample } from "../editor/library-tiles";
import { startTile } from "../editor/tiles";
import type { Entry, ShelfView } from "../model/library";
import type { Size } from "../model/sizes";
import { useEntitiesStore } from "../stores/entities";
import LibrarySample from "./LibrarySample.vue";
import type { Tile } from "../types";

const props = defineProps<{ entity: Entry; name: string; mark: string; view: ShelfView; disabled: boolean; glass: number; zoom: number; maxHeight: number; maxWidth: number; columns: number; active?: boolean }>();
const emit = defineEmits<{ add: [tile: Tile]; point: [el: HTMLElement]; leave: [] }>();
const entities = useEntitiesStore();

// Read again when what decides it is known: what Home Assistant says the entity can do, and what it reports.
const sample = computed(() => {
  void entities.capabilities[props.entity.id]; void entities.liveOf(props.entity.id);
  return shelfSample(samplesOf(props.entity.id), props.view, props.entity.id, startTile(props.entity.id).options?.size as Size | undefined);
});
</script>

<template>
  <div v-if="sample" :id="`lib-${entity.id}`" class="shelf" :class="{ active, disabled }" role="option" :aria-selected="active ? 'true' : 'false'"
    :style="{ gridColumn: `span ${Math.max(1, Math.min(sample.columns, columns))}`, gridRow: `span ${Math.min(sample.rows, 2)}` }"
    @pointerenter="(e) => e.pointerType === 'mouse' && emit('point', e.currentTarget as HTMLElement)" @pointerleave="emit('leave')">
    <LibrarySample :sample="sample" :name="name" :disabled="disabled" :glass="glass" :zoom="zoom" :max-height="maxHeight" :max-width="maxWidth" @add="(tile) => emit('add', tile)" />
    <span class="shelf-name" :title="`${name} · ${entity.id}`">{{ name }}</span>
    <span v-if="mark !== '+'" class="shelf-mark" aria-hidden="true">{{ mark }}</span>
  </div>
</template>

<style scoped>
.shelf { position: relative; display: block; min-width: 0; border-radius: 12px; }
.shelf.active { box-shadow: 0 0 0 2px var(--glass-page), 0 0 0 4px var(--accent); }
/* The name under the tile: one line, the strip's own soft ink, as wide as the tile (Library.vue counts its height in a line). */
.shelf-name { display: block; height: 14px; margin-top: 4px; padding: 0 3px; font-size: 11px; line-height: 14px; font-weight: 500; color: var(--glass-ink-soft); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.shelf.disabled { opacity: 0.5; }
/* On the screen already: a small mark on the tile's corner, the count where it stands there more than once. */
.shelf-mark { position: absolute; left: -5px; top: -5px; min-width: 18px; height: 18px; padding: 0 5px; border-radius: 999px; display: grid; place-items: center; font-size: 10.5px; font-weight: 600;
  color: var(--surface); background: var(--ink-2); pointer-events: none; }
</style>
