<script setup lang="ts">
// All the tiles an entity can be (editor/library-tiles.ts samplesOf), in a card that opens over the one tile the shelf
// shows of it (Library.vue, docs/PAGES.md "The library"): its name in full, where it is, and every size side by side at
// one scale, each with its cells and its controls under it. A click or a drag places the one that is taken. The card
// stands above the tile it belongs to, under it where there is no room above, and never past the window's edge.
import { computed, ref } from "vue";
import { useElementSize, useWindowSize } from "@vueuse/core";
import { t } from "../i18n";
import { glyph } from "../model/topbar";
import { entryTone, type Entry } from "../model/library";
import { tilePalette } from "../model/tile-palette";
import { samplesOf } from "../editor/library-tiles";
import { useEntitiesStore } from "../stores/entities";
import LibrarySample from "./LibrarySample.vue";
import type { Tile } from "../types";

export type Anchor = { left: number; top: number; bottom: number };
const props = defineProps<{ entity: Entry; name: string; detail: string; mark: string; disabled: boolean; glass: number; zoom: number; maxHeight: number; anchor: Anchor }>();
const emit = defineEmits<{ add: [tile: Tile] }>();
const entities = useEntitiesStore();

const samples = computed(() => { void entities.capabilities[props.entity.id]; void entities.liveOf(props.entity.id); return samplesOf(props.entity.id); });
const palette = computed(() => tilePalette(props.entity.id, entities.liveOf(props.entity.id)));
const box = ref<HTMLElement | null>(null);
const { width, height } = useElementSize(box, undefined, { box: "border-box" });
const win = useWindowSize();
const GAP = 10, EDGE = 8;
const place = computed(() => {
  const left = Math.max(EDGE, Math.min(props.anchor.left - 12, win.width.value - width.value - EDGE));
  const above = props.anchor.top - GAP - height.value;
  const below = win.height.value - props.anchor.bottom - GAP - height.value;
  const top = above >= EDGE || above >= below ? Math.max(EDGE, above) : props.anchor.bottom + GAP;
  // Placed once it is measured: a card drawn first and moved after would be seen to jump.
  return { left: `${left}px`, top: `${top}px`, visibility: height.value ? "visible" as const : "hidden" as const };
});
</script>

<template>
  <div ref="box" class="ui-popover lib-sizes" role="group" :aria-label="name" :style="place">
    <header class="sizes-head">
      <span class="av mdi" :class="entryTone(entity)" :style="{ color: palette.icon, background: palette.circle }">{{ glyph(entities.automaticIcon(entity.id)) }}</span>
      <span class="sizes-name" :title="entity.id"><b>{{ name }}</b><small v-if="detail">{{ detail }}</small></span>
      <span v-if="mark !== '+'" class="sizes-mark">{{ mark === "✓" ? t("editor.library.tiles.placed") : mark }}</span>
    </header>
    <div class="sizes-row">
      <LibrarySample v-for="sample in samples" :key="sample.size" :sample="sample" :name="name" :disabled="disabled" :glass="glass" :zoom="zoom" :max-height="maxHeight" foot @add="(tile) => emit('add', tile)" />
    </div>
  </div>
</template>

<style scoped>
.lib-sizes { position: fixed; display: grid; gap: 10px; padding: 12px; max-width: calc(100vw - 16px); animation: none; }
.sizes-head { display: flex; align-items: center; gap: 10px; min-width: 0; }
.sizes-head .av { width: 26px; height: 26px; border-radius: 7px; display: grid; place-items: center; font-size: 15px; flex: none; }
.sizes-name { display: grid; min-width: 0; flex: 1; }
.sizes-name b { font-weight: 600; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sizes-name small { font-size: 11.5px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sizes-mark { font-size: 11px; color: var(--muted); background: var(--seg); border-radius: 999px; padding: 2px 8px; flex: none; }
/* The strip of glass the tiles stand on: the screen's own page and words, as the mockup draws them (model/glass-colours.ts). */
.sizes-row { display: flex; align-items: flex-end; flex-wrap: wrap; gap: 14px 18px; padding: 14px 14px 10px; border-radius: 10px; background: var(--glass-page); }
</style>
