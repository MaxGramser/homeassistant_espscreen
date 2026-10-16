<script setup lang="ts">
// A cover's card of one cell with its control chosen (firmware 0.57.0, render_tall): its head on top and its controls
// under it, or, on a card at least twice as wide as high whose name fits the left half whole, the head at the left and the
// controls at the right where that gives them a richer layout (cover_tile.h's tiers, model/cover-tile.ts). Where nothing
// fits, the card is the one it is without them (CoverTilePreview draws nothing).
import { useElementSize } from "@vueuse/core";
import { computed, ref } from "vue";
import { glyph } from "../../model/topbar";
import { coverLayout } from "../../model/cover-tile";
import { lineOf, tallKeys, textWidth, uiScale } from "../../model/ui-scale";
import { controlKeys, coverTiltKeys, coverTiltKind } from "../../model/tall-controls";
import type { TileCardView } from "../../composables/useTileCard";
import { useCanvasStore } from "../../stores/canvas";
import { useDocumentStore } from "../../stores/document";
import CoverTilePreview from "../CoverTilePreview.vue";

const props = defineProps<{ card: TileCardView }>();
const card = props.card;
const canvas = useCanvasStore();
const doc = useDocumentStore();
const root = ref<HTMLElement>();
const { width, height } = useElementSize(root);
type Fonts = { label?: number; sublabel?: number };
const shape = computed(() => ({ ...doc.screenShape, look: canvas.isCompact ? "compact" : "standard" }) as
  { dpi?: number; look: string; width: number; fonts?: Fonts; spacing?: { margin: number; gap: number; tile_pad: number; circle?: number } });
const beside = computed(() => {
  const s = parseFloat(canvas.deviceStyle["--mockup-width"]) / doc.screenShape.width || 1;
  const w = Math.floor(width.value / s), h = Math.floor(height.value / s);
  if (w < 2 * h || !w) return false;
  const fonts = shape.value.fonts || {}, { large, px } = uiScale(shape.value), gap = px(large ? 8 : 4), { touch } = tallKeys(shape.value);
  const circle = Math.min(shape.value.spacing?.circle ?? px(large ? 54 : 36), Math.trunc(w / 6));
  if (textWidth(card.texts.name, fonts.label ?? 16) > Math.trunc(w / 2) - circle - gap) return false;
  const a = card.current?.a || {}, state = card.current?.state || "", primary = card.face.coverPrimary;
  const tilt = card.face.coverRow && /tilt/.test(String(card.tile.options?.controls || "")) ? coverTiltKind(state, a) : "";
  const keys = primary === "buttons" ? controlKeys("cover", "buttons", state, a).length : 0, tiltKeys = tilt === "buttons" ? coverTiltKeys(a).length : 0;
  const lines = lineOf(fonts.label ?? 16) + lineOf(fonts.sublabel ?? 14);
  const head = Math.max(lines, Math.min(circle, Math.trunc(h / 3)));
  const lay = (x: number, y: number, bw: number, bh: number) => coverLayout({ x, y, w: bw, h: bh }, touch, gap, lineOf(fonts.sublabel ?? 14), 2 * touch,
    primary === "position", keys, tilt === "position", tiltKeys, 0, false);
  const stacked = lay(0, head + gap, w, h - head - gap), side = lay(Math.trunc(w / 2) + gap, 0, w - Math.trunc(w / 2) - gap, h);
  return side.fits && (!stacked.fits || side.tier > stacked.tier);
});
</script>

<template>
  <span ref="root" class="cover-cell" :class="{ beside }">
    <span class="head">
      <span class="ic mdi" :class="{ lit: card.lit }">{{ glyph(card.icon) }}</span>
      <span class="tx"><span class="nm">{{ card.texts.name }}</span><span v-if="card.texts.line" class="st" :class="{ off: card.gone }">{{ card.texts.line }}</span></span>
    </span>
    <CoverTilePreview :standing="false" :tilt="/tilt/.test(String(card.tile.options?.controls || ''))" :primary="card.face.coverPrimary"
      :entity-state="card.current?.state || ''" :attributes="card.current?.a || {}" />
  </span>
</template>

<style scoped src="./parts.css"></style>
<style scoped>
.cover-cell { flex: 1; align-self: stretch; min-height: 0; display: flex; flex-direction: column; gap: 6px; }
.cover-cell .head { flex: none; }
.cover-cell.beside { flex-direction: row; align-items: center; }
.cover-cell.beside .head { width: 50%; }
</style>
