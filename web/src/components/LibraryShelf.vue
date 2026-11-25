<script setup lang="ts">
// One entity in the library's Tiles view (Library.vue): its name over the tiles it can be on this screen, each the real
// card the mockup draws (TileCard), at the size it lands, on a patch of the screen's glass, all at the same scale so the
// sizes compare. A click puts that tile on the marked cell or the first free one; a drag puts it where it lands.
import { computed } from "vue";
import { vDrag } from "../drag";
import { t } from "../i18n";
import { glyph } from "../model/topbar";
import { entryTone, type Entry } from "../model/library";
import { tilePalette } from "../model/tile-palette";
import { cardContent, cardHeight, frameOf } from "../model/ui-scale";
import { samplesOf, type Sample } from "../editor/library-tiles";
import { useCanvasStore } from "../stores/canvas";
import { useDocumentStore } from "../stores/document";
import { useEntitiesStore } from "../stores/entities";
import { useInventoryStore } from "../stores/inventory";
import TileCard from "./TileCard.vue";
import type { Tile } from "../types";

const props = defineProps<{ entity: Entry; name: string; detail: string; mark: string; disabled: boolean; zoom: number; maxHeight: number; active?: boolean }>();
const emit = defineEmits<{ add: [tile: Tile] }>();
const canvas = useCanvasStore();
const doc = useDocumentStore();
const entities = useEntitiesStore();
const inv = useInventoryStore();

// Read again when what decides them is known: what Home Assistant says the entity can do, and what it reports.
const samples = computed(() => { void entities.capabilities[props.entity.id]; void entities.liveOf(props.entity.id); return samplesOf(props.entity.id); });
const glass = computed(() => Number(canvas.deviceStyle["--glass"]) || 1);
// A card's size on the glass, the way the screen lays out its grid (model/ui-scale.ts), in the mockup's pixels.
function box(sample: Sample) {
  const shape = doc.screenShape as Parameters<typeof frameOf>[0], grid = doc.editorLayout.grid, frame = frameOf(shape);
  const width = cardContent(shape, grid.columns, sample.columns) + 2 * frame.tile_pad + 2;
  const height = cardHeight(shape, grid.rows, sample.rows, 0, canvas.pageBarShown);
  return { width: width * glass.value, height: height * glass.value };
}
// One scale for every size, so they compare; a tile higher than two rows (the energy card's diagram) is drawn smaller
// to stand as high as the rest.
const zoomOf = (sample: Sample) => Math.min(props.zoom, props.maxHeight / Math.max(1, box(sample).height));
const labels = computed(() => Object.fromEntries((inv.inventory.controls?.[props.entity.id.split(".")[0]]?.choices ?? []).map((choice) => [choice.key, choice.label])));
// Under a tile: its face where it has another than the plain card, and its controls.
const controlsOf = (sample: Sample) => {
  const display = String(sample.tile.options?.display ?? "standard");
  const face = !["standard", "digital"].includes(display) && sample.tile.entity.split(".")[0] !== "screen" ? t(`editor.tile.display.${display}`) : "";
  return [face, sample.controls === "none" ? "" : labels.value[sample.controls] ?? ""].filter(Boolean).join(" · ");
};
const palette = computed(() => tilePalette(props.entity.id, entities.liveOf(props.entity.id)));
</script>

<template>
  <article :id="`lib-${entity.id}`" class="shelf" :class="{ active, disabled }" role="option" :aria-selected="active ? 'true' : 'false'">
    <header class="shelf-head">
      <span class="av mdi" :class="entryTone(entity)" :style="{ color: palette.icon, background: palette.circle }">{{ glyph(entities.automaticIcon(entity.id)) }}</span>
      <span class="shelf-name"><b>{{ name }}</b><small v-if="detail">{{ detail }}</small></span>
      <span v-if="mark !== '+'" class="shelf-mark">{{ mark === "✓" ? t("editor.library.tiles.placed") : mark }}</span>
    </header>
    <div class="shelf-row">
      <button v-for="sample in samples" :key="sample.size" type="button" class="sample" :style="{ width: `${box(sample).width * zoomOf(sample)}px` }"
        :title="controlsOf(sample) || undefined" :disabled="disabled" :aria-label="t('editor.library.tiles.add_size', { name, columns: sample.columns, rows: sample.rows })"
        v-drag="disabled ? null : { kind: 'entity', id: entity.id, tile: sample.tile }" @click="emit('add', sample.tile)">
        <span class="sample-glass" :style="{ width: `${box(sample).width * zoomOf(sample)}px`, height: `${box(sample).height * zoomOf(sample)}px` }">
          <span class="sample-zoom" :style="{ transform: `scale(${zoomOf(sample)})` }">
            <span class="page sample-page" :style="canvas.deviceStyle">
              <span class="device" :class="{ compact: canvas.isCompact, roomy: canvas.roomyNames }">
                <span class="tiles" :style="{ '--screen-columns': sample.columns, '--screen-rows': sample.rows, width: `${box(sample).width}px`, height: `${box(sample).height}px` }">
                  <TileCard :tile="sample.tile" :at="0" :grid="doc.editorLayout.grid" preview />
                </span>
              </span>
            </span>
          </span>
          <span class="sample-add" aria-hidden="true">+</span>
        </span>
        <span class="sample-foot">
          <i class="sample-shape" aria-hidden="true" :style="{ width: `${4 + sample.columns * 5}px`, height: `${4 + sample.rows * 5}px` }"></i>
          <span>{{ sample.columns }} × {{ sample.rows }}</span>
          <small v-if="controlsOf(sample)">{{ controlsOf(sample) }}</small>
        </span>
      </button>
    </div>
  </article>
</template>

<style scoped>
/* One entity a row: its name on the left, its tiles side by side on a strip of glass, as on a shelf. Narrow, the name
   goes above. */
.shelf { display: grid; grid-template-columns: 190px minmax(0, 1fr); align-items: center; gap: 8px 16px; padding: 10px; border: 1px solid var(--line); border-radius: 14px; background: var(--surface); container-type: inline-size; }
@container (max-width: 560px) { .shelf { grid-template-columns: minmax(0, 1fr); } }
.shelf.active { border-color: var(--accent); box-shadow: var(--focus); }
.shelf.disabled { opacity: 0.55; }
.shelf-head { display: flex; align-items: center; gap: 10px; min-width: 0; padding-left: 4px; flex-wrap: wrap; }
.shelf-head .av { width: 26px; height: 26px; border-radius: 7px; display: grid; place-items: center; font-size: 15px; flex: none; }
.shelf-name { display: grid; min-width: 0; flex: 1; }
.shelf-name b { font-weight: 500; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.shelf-name small { font-size: 11px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.shelf-mark { font-size: 11px; color: var(--muted); background: var(--seg); border-radius: 999px; padding: 2px 8px; flex: none; }
/* The strip of glass the tiles stand on: the screen's own page and words, as the mockup draws them (model/glass-colours.ts). */
.shelf-row { display: flex; align-items: flex-end; gap: 16px 18px; flex-wrap: wrap; padding: 14px 14px 10px; border-radius: 10px; background: var(--glass-page); }
.sample { display: grid; gap: 6px; justify-items: start; padding: 0; border: 0; background: none; font: inherit; text-align: left; cursor: grab; border-radius: 10px; outline: none; touch-action: manipulation; }
.sample:disabled { cursor: default; }
/* The patch of glass the card stands on: the screen's own background, as on the mockup. */
.sample-glass { position: relative; display: block; border-radius: 12px; outline: 2px solid transparent; outline-offset: 3px; transition: outline-color 0.12s, transform 0.12s; }
.sample:not(:disabled):hover .sample-glass, .sample:focus-visible .sample-glass { outline-color: var(--accent); }
.sample:not(:disabled):active .sample-glass { transform: scale(0.98); }
/* Scaled, not zoomed: the card is laid out at its own size, as its faces measure it (a zoom made them measure it small). */
.sample-zoom { display: block; pointer-events: none; transform-origin: 0 0; width: max-content; }
.sample-page { display: block; }
.sample-page .device { display: block; padding: 0; background: transparent; aspect-ratio: auto; border-radius: 0; }
.sample-page .tiles { display: grid; gap: var(--frame-gap-y) var(--frame-gap-x); }
.sample-add { position: absolute; right: -6px; top: -6px; width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center; background: var(--accent); color: var(--accent-ink);
  font-weight: 600; font-size: 15px; opacity: 0; transform: scale(0.8); transition: opacity 0.12s, transform 0.12s; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2); }
.sample:not(:disabled):hover .sample-add, .sample:focus-visible .sample-add { opacity: 1; transform: none; }
.sample-foot { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--glass-muted); padding-left: 2px; width: 100%; min-width: 0; white-space: nowrap; }
.sample-foot > * { flex: none; }
.sample-foot > small { flex: 1 1 auto; min-width: 0; }
.sample-foot span { font-weight: 600; color: var(--glass-ink-soft); }
.sample-foot small { font-size: 11px; overflow: hidden; text-overflow: ellipsis; }
.sample-shape { display: inline-block; border: 1.5px solid currentColor; border-radius: 2px; opacity: 0.7; }
</style>
