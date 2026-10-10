<script setup lang="ts">
// A card on the mockup, drawn with what Home Assistant reports right now. A placeholder is the tile being dragged, drawn
// where it will land. What the card is and writes comes from useTileCard (model/tile-face.ts, model/tile-text.ts); this
// is the card itself, where it stands, what a click and the keys do to it, and the face the screen gives it
// (components/tile/).
import { computed, nextTick } from "vue";
import { vDrag } from "../drag";
import { t } from "../i18n";
import { useTileCard, type TileCardProps } from "../composables/useTileCard";
import TileResize from "./TileResize.vue";
import TileBedside from "./tile/TileBedside.vue";
import TileClockFace from "./tile/TileClockFace.vue";
import TileEnergy from "./tile/TileEnergy.vue";
import TileLine from "./tile/TileLine.vue";
import TilePicture from "./tile/TilePicture.vue";
import TilePlugin from "./tile/TilePlugin.vue";
import TileRoundKey from "./tile/TileRoundKey.vue";
import TileTall from "./tile/TileTall.vue";
import TileWatch from "./tile/TileWatch.vue";
import { useUiStore } from "../stores/ui";
import { placeTile, removeTile } from "../editor/tiles";
import { useDocumentStore } from "../stores/document";
import { useInspectorStore } from "../stores/inspector";

const ui = useUiStore();
const doc = useDocumentStore();
const insp = useInspectorStore();

const props = defineProps<TileCardProps>();
const emit = defineEmits<{ navigate: [tileId: string] }>();
const card = useTileCard(props);
const kind = computed(() => card.face.kind);
const CLOCKS = ["analog", "dial", "flip-wide", "flip", "digital"];

function activate() {
  if (props.preview) { if (card.goesTo && props.tile.id) emit("navigate", props.tile.id); }
  else if (card.live) insp.openTile(props.tile);
}
const label = computed(() => t("editor.tile_card.label", { name: card.texts.name, slot: (props.slot % card.grid.slots) + 1, page: Math.floor(props.slot / card.grid.slots) + 1 }));
// Focus, a tap and a drag: a card of the editor's own layout; in the preview a tile that opens a page.
const reachable = computed(() => !card.foreign && (props.preview ? Boolean(card.goesTo) : card.live));
const classes = computed(() => {
  const face = card.face;
  return { wide: face.wide, full: face.full, tall: face.tall, "watch-card": kind.value === "watch", "tall-action": face.tallAction || face.tallStack, "big-key": face.bigKey,
    photo: card.loaded.artwork && !!card.artwork, camera: (kind.value === "camera" && card.loaded.camera) || (kind.value === "favorite" && card.loaded.favorite),
    bare: props.tile.options?.background === "none", placeholder: props.placeholder || (!card.live && !card.foreign), chosen: card.chosen,
    "just-added": !props.preview && !!props.tile.id && doc.justAdded === props.tile.id };
});
const style = computed(() => {
  const background = card.background;
  return { gridColumn: `${props.slot % card.grid.columns + 1} / span ${card.shape.columns}`, gridRow: `${Math.floor(props.slot % card.grid.slots / card.grid.columns) + 1} / span ${card.shape.rows}`,
    ...(background && props.tile.options?.background !== "none" ? { backgroundColor: background } : {}),
    "--tile-icon": card.palette.icon, "--tile-circle": card.palette.circle, "--tile-accent": card.palette.accent, ...(card.watchStyle?.pad ?? {}) };
});

async function onKey(e: KeyboardEvent) {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); activate(); return; }
  if (props.preview) return;
  // Delete or Backspace removes the focused card (app 0.4.32); Undo brings it back.
  if ((e.key === "Delete" || e.key === "Backspace") && card.live) { e.preventDefault(); removeTile(props.tile); return; }
  // Up and down are a row of the screen's grid, whatever its columns; left and right one cell.
  const grid = card.grid;
  const step = ({ ArrowLeft: -1, ArrowRight: 1, ArrowUp: -grid.columns, ArrowDown: grid.columns } as Record<string, number>)[e.key];
  if (!step) return;
  e.preventDefault();
  // A wide card owns its row: every arrow means the row above or below. A full card moves by the page.
  const to = props.tile.slot + (card.face.full ? Math.sign(step) * grid.slots : step);
  if (!placeTile(props.tile, to)) {
    // Nowhere to go without pushing a tile off its page (app 0.4.2): say so instead of doing nothing.
    if (to >= 0 && to < grid.slots * 8) ui.toast(t("editor.layout.no_room", { page: Math.floor(to / grid.slots) + 1 }));
    return;
  }
  // The card that moved, found by its id: the cards are keyed by their place, so the one under the old place is
  // another tile now, and focusing that sent the next arrow key to the neighbour (app 0.4.1).
  await nextTick();
  document.querySelector<HTMLElement>(`.pages [data-tile-id="${props.tile.id}"]`)?.focus();
}
</script>

<template>
  <TileRoundKey v-if="round" :card="card" @activate="activate" />
  <div v-else class="tile" :class="classes" :data-slot="slot" :data-tile-id="tile.id" :data-columns="card.shape.columns" :data-rows="card.shape.rows" :style="style"
    :tabindex="reachable ? 0 : -1" :role="reachable ? 'button' : undefined" :aria-label="card.live ? label : undefined"
    v-drag="preview || card.foreign ? null : { kind: 'tile', tile }" @click="activate" @keydown="card.live && onKey($event)">
    <TileBedside v-if="kind === 'bedside'" :card="card" />
    <TilePlugin v-else-if="kind === 'plugin-live' || kind === 'plugin'" :card="card" />
    <TileEnergy v-else-if="kind === 'energy'" :card="card" />
    <TileClockFace v-else-if="CLOCKS.includes(kind)" :card="card" />
    <TilePicture v-else-if="kind === 'favorite' || kind === 'camera'" :card="card" />
    <TileWatch v-else-if="kind === 'watch'" :card="card" />
    <TileTall v-else-if="kind === 'tall' || kind === 'big-key'" :card="card" />
    <TileLine v-else :card="card" />
    <TileResize v-if="card.live && !preview && !placeholder" :tile="tile" />
    <button v-if="card.live && !preview" type="button" class="remove" :title="t('editor.tile_card.remove')" :aria-label="t('editor.tile_card.remove_named', { name: card.texts.name })" @click.stop="removeTile(tile)">✕</button>
  </div>
</template>

<style scoped>
/* The card itself, by its face; what stands on it is styled with its face (components/tile/). */
/* A Big number card: its content box is the glass's (the board's TILE_PAD), and its parts stand where watchCard puts them. */
.tile.watch-card { padding-inline: var(--frame-pad, 8px); }
.tile.tall.big-key { flex-direction: column; justify-content: center; align-items: center; text-align: center; gap: 4px; container-type: size; }
/* Additional rows extend the existing header and controls. All single-row selectors remain unchanged. */
.tile.tall { flex-direction: column; align-items: stretch; justify-content: start; container-type: size; }
.tile.full.tall { justify-content: start; text-align: left; }
.tile.tall.tall-action { justify-content: center; }
.tile.tall.photo { color: white; }
.tile.camera { justify-content: end; }
</style>
