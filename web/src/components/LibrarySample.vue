<script setup lang="ts">
// One tile the library offers (editor/library-tiles.ts Sample): the real card the mockup draws (TileCard), at the size
// it lands, on a patch of the screen's glass, scaled as the shelf says. A click puts that very tile on the marked cell
// or the first free one; a drag puts it where it lands. The shelf shows it bare (LibraryShelf.vue); the card with all
// of an entity's sizes writes its cells and its controls under it (LibrarySizes.vue).
import { computed } from "vue";
import { vDrag } from "../drag";
import { t } from "../i18n";
import { cardContent, cardHeight, frameOf } from "../model/ui-scale";
import type { Sample } from "../editor/library-tiles";
import { useCanvasStore } from "../stores/canvas";
import { useDocumentStore } from "../stores/document";
import { useInventoryStore } from "../stores/inventory";
import TileCard from "./TileCard.vue";
import type { Tile } from "../types";

const props = defineProps<{ sample: Sample; name: string; disabled: boolean; zoom: number; maxHeight?: number; maxWidth?: number; foot?: boolean }>();
const emit = defineEmits<{ add: [tile: Tile] }>();
const canvas = useCanvasStore();
const doc = useDocumentStore();
const inv = useInventoryStore();

const glass = computed(() => Number(canvas.deviceStyle["--glass"]) || 1);
// A card's size on the glass, the way the screen lays out its grid (model/ui-scale.ts), in the mockup's pixels.
const box = computed(() => {
  const shape = doc.screenShape as Parameters<typeof frameOf>[0], grid = doc.editorLayout.grid, frame = frameOf(shape);
  const width = cardContent(shape, grid.columns, props.sample.columns) + 2 * frame.tile_pad + 2;
  const height = cardHeight(shape, grid.rows, props.sample.rows, 0, canvas.pageBarShown);
  return { width: width * glass.value, height: height * glass.value };
});
// One scale for every tile, so they compare; a tile higher or wider than its room (the energy card's diagram, a
// calendar on a narrow shelf) is drawn smaller to stand in it.
const scale = computed(() => Math.min(props.zoom, (props.maxHeight ?? Infinity) / Math.max(1, box.value.height), (props.maxWidth ?? Infinity) / Math.max(1, box.value.width)));
const labels = computed(() => Object.fromEntries((inv.inventory.controls?.[props.sample.tile.entity.split(".")[0]]?.choices ?? []).map((choice) => [choice.key, choice.label])));
// Under a tile: its face where it has another than the plain card, and its controls.
const controls = computed(() => {
  const display = String(props.sample.tile.options?.display ?? "standard");
  const face = !["standard", "digital"].includes(display) && props.sample.tile.entity.split(".")[0] !== "screen" ? t(`editor.tile.display.${display}`) : "";
  return [face, props.sample.controls === "none" ? "" : labels.value[props.sample.controls] ?? ""].filter(Boolean).join(" · ");
});
</script>

<template>
  <button type="button" class="sample" :style="{ width: `${box.width * scale}px` }" :title="foot ? controls || undefined : undefined" :disabled="disabled"
    :aria-label="t('editor.library.tiles.add_size', { name, columns: sample.columns, rows: sample.rows })"
    v-drag="disabled ? null : { kind: 'entity', id: sample.tile.entity, tile: sample.tile }" @click="emit('add', sample.tile)">
    <span class="sample-glass" :style="{ width: `${box.width * scale}px`, height: `${box.height * scale}px` }">
      <span class="sample-zoom" :style="{ transform: `scale(${scale})` }">
        <span class="page sample-page" :style="canvas.deviceStyle">
          <span class="device" :class="{ compact: canvas.isCompact, roomy: canvas.roomyNames }">
            <span class="tiles" :style="{ '--screen-columns': sample.columns, '--screen-rows': sample.rows, width: `${box.width}px`, height: `${box.height}px` }">
              <TileCard :tile="sample.tile" :at="0" :grid="doc.editorLayout.grid" preview />
            </span>
          </span>
        </span>
      </span>
      <span class="sample-add" aria-hidden="true">+</span>
    </span>
    <span v-if="foot" class="sample-foot">
      <i class="sample-shape" aria-hidden="true" :style="{ width: `${4 + sample.columns * 5}px`, height: `${4 + sample.rows * 5}px` }"></i>
      <span>{{ sample.columns }} × {{ sample.rows }}</span>
      <small v-if="controls">{{ controls }}</small>
    </span>
  </button>
</template>

<style scoped>
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
  font-weight: 600; font-size: 15px; opacity: 0; transform: scale(0.8); transition: opacity 0.12s, transform 0.12s; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2); z-index: 1; }
.sample:not(:disabled):hover .sample-add, .sample:focus-visible .sample-add { opacity: 1; transform: none; }
.sample-foot { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--glass-muted); padding-left: 2px; width: 100%; min-width: 0; white-space: nowrap; }
.sample-foot > * { flex: none; }
.sample-foot > small { flex: 1 1 auto; min-width: 0; }
.sample-foot span { font-weight: 600; color: var(--glass-ink-soft); }
.sample-foot small { font-size: 11px; overflow: hidden; text-overflow: ellipsis; }
.sample-shape { display: inline-block; border: 1.5px solid currentColor; border-radius: 2px; opacity: 0.7; }
</style>
