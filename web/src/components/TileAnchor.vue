<script setup lang="ts">
// The tile in small at the head of its inspector (app 0.4.89): the card as its page draws it, at the size of its cells
// on the page (stores/canvas.ts deviceStyle) and scaled down only where the column is narrower, so every choice made or
// pointed at under it (stores/inspector.ts previewed) shows here too. Its icon is the way to the icons and its name to
// the Name field. A bedside clock's key is drawn as its round key.
import { useResizeObserver } from "@vueuse/core";
import { computed, ref } from "vue";
import { t } from "../i18n";
import { dimensions, sizeOf } from "../model/layout";
import type { Tile } from "../types";
import TileCard from "./TileCard.vue";
import { useCanvasStore } from "../stores/canvas";
import { useDocumentStore } from "../stores/document";
import { useInspectorStore } from "../stores/inspector";

const canvas = useCanvasStore();
const doc = useDocumentStore();
const insp = useInspectorStore();

const props = defineProps<{ tile: Tile; icon?: boolean }>();
const emit = defineEmits<{ icon: []; name: [] }>();
const key = computed(() => props.tile.in !== undefined);
const shape = computed(() => dimensions(sizeOf(props.tile), doc.editorLayout.grid));
// One cell of the page in editor pixels: the glass less its frame, its page bar and the gaps, as DevicePage lays it out.
const size = computed(() => {
  const style = canvas.deviceStyle as Record<string, string>, px = (name: string) => parseFloat(style[name]) || 0;
  const glass = doc.screenShape, grid = doc.editorLayout.grid;
  const width = px("--mockup-width"), height = (width * glass.height) / glass.width;
  const across = width - 2 * px("--frame-side"), down = height - px("--frame-top") - px("--frame-bottom") - (canvas.pageBarShown ? px("--frame-bar") : 0);
  const gapX = px("--frame-gap-x"), gapY = px("--frame-gap-y");
  const cell = { width: (across - (grid.columns - 1) * gapX) / grid.columns, height: (down - (grid.rows - 1) * gapY) / grid.rows };
  const { columns, rows } = shape.value;
  return { width: columns * cell.width + (columns - 1) * gapX, height: rows * cell.height + (rows - 1) * gapY, cell, columns, rows };
});
// Scaled to the column, and kept low enough that the settings under it have room.
const box = ref<HTMLElement | null>(null);
const room = ref(0);
useResizeObserver(box, (entries) => { room.value = entries[0]?.contentRect.width || 0; });
const zoom = computed(() => (key.value ? 1 : Math.min(1, (room.value || size.value.width) / size.value.width, 170 / size.value.height)));
const grid = computed(() => ({ gridTemplateColumns: `repeat(${size.value.columns}, ${size.value.cell.width}px)`, gridTemplateRows: `repeat(${size.value.rows}, ${size.value.cell.height}px)` }));
function click(e: MouseEvent) {
  const at = e.target as HTMLElement;
  if (props.icon && at.closest(".ic, .disc, .tile-icon")) emit("icon");
  else if (at.closest(".nm, .round-name, .camera-name")) emit("name");
}
</script>

<template>
  <div ref="box" class="tile-anchor" :title="t('editor.tile.anchor_hint')" @click.capture.stop="click">
    <div class="tile-anchor-glass" :style="[canvas.deviceStyle, { zoom }]">
      <div class="device tile-anchor-device" :class="{ compact: canvas.isCompact, roomy: canvas.roomyNames, key }">
        <TileCard v-if="key" :tile="insp.previewed(tile)" :slot="-1" round preview />
        <div v-else class="tiles" :style="grid">
          <TileCard :tile="insp.previewed(tile)" :slot="0" preview />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tile-anchor { display: grid; justify-items: center; min-width: 0; }
.tile-anchor-glass { max-width: 100%; }
.tile-anchor-device { display: block; aspect-ratio: auto; padding: 6px; border-radius: 14px; }
.tile-anchor-device.key { padding: 8px 14px; }
/* The card is shown, not chosen or worked: no ring of the chosen tile, no hand of a drag, no slider or key that takes a
   finger. Only its icon and its name answer, as the way to them. */
.tile-anchor :deep(.tile), .tile-anchor :deep(.tile *), .tile-anchor :deep(.round-tile), .tile-anchor :deep(.round-tile *) { pointer-events: none; cursor: default; }
.tile-anchor :deep(.tile.chosen), .tile-anchor :deep(.round-tile.chosen) { outline: none; }
.tile-anchor :deep(.ic), .tile-anchor :deep(.disc), .tile-anchor :deep(.nm), .tile-anchor :deep(.round-name) { pointer-events: auto; cursor: pointer; }
.tile-anchor :deep(.ic:hover), .tile-anchor :deep(.disc:hover), .tile-anchor :deep(.nm:hover) { opacity: 0.7; }
</style>
