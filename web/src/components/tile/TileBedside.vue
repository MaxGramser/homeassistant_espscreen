<script setup lang="ts">
// The bedside clock (app 0.4.12): big digits over its key places, as the screen draws it. A place without a key is marked
// for the next tile from the library; a key is a card of its own in its round form.
import { t } from "../../i18n";
import TileCard from "../TileCard.vue";
import type { TileCardView } from "../../composables/useTileCard";
import { useCanvasStore } from "../../stores/canvas";
import { useDragStore } from "../../stores/drag";
import { useInspectorStore } from "../../stores/inspector";
import { useRegionStore } from "../../stores/region";
import { useScreenStore } from "../../stores/screen";

const canvas = useCanvasStore();
const dragging = useDragStore();
const insp = useInspectorStore();
const region = useRegionStore();
const scr = useScreenStore();
const props = defineProps<{ card: TileCardView }>();

function markKey(key: number) {
  const holder = props.card.tile.id!, marked = insp.insertKey?.holder === holder && insp.insertKey?.key === key;
  insp.insert = marked ? null : { kind: "key", holder, key };
  if (insp.insertKey) document.querySelector<HTMLInputElement>("#search")?.focus();
}
</script>

<template>
  <span class="bedside-clock" :class="{ compact: canvas.isCompact }">
    <span class="time"><span class="bedside-time">{{ card.clock.digits }}</span><small v-if="!region.clock24 && scr.supports(0, 17, 0)" class="am-pm">{{ card.clock.amPm }}</small></span>
    <span v-if="card.keyPlaces.length" class="keys">
      <span v-for="place in card.keyPlaces" :key="place.key" class="key-place" :data-key="card.preview || card.placeholder ? undefined : place.key" :data-holder="card.preview || card.placeholder ? undefined : card.tile.id"
        :class="{ 'insert-here': insp.insertKey?.holder === card.tile.id && insp.insertKey?.key === place.key, over: dragging.key?.holder === card.tile.id && dragging.key?.key === place.key }">
        <TileCard v-if="place.tile" :tile="place.tile" :slot="-1" round :preview="card.preview" />
        <button v-else type="button" class="key-empty" :title="t('editor.page.cell.title')" @click.stop="markKey(place.key)"><span>+</span></button>
      </span>
    </span>
  </span>
</template>

<style scoped>
.bedside-clock { display: flex; flex-direction: column; align-items: center; justify-content: space-evenly; width: 100%; height: 100%; min-width: 0; container-type: inline-size; }
/* As the screen draws it: the time about as wide as the card, the keys a quarter of its height. */
.bedside-clock .bedside-time { font-size: 32cqw; font-weight: 400; line-height: 1; letter-spacing: -1px; }
/* The compact look (a CYD) draws its display step smaller against the card. */
.bedside-clock.compact .bedside-time { font-size: 24cqw; }
.bedside-clock .key-place { width: auto; min-width: min(20cqw, 64px); }
.bedside-clock .time { display: grid; justify-items: end; }
.bedside-clock .am-pm { font-size: min(4cqw, 12px); opacity: .6; margin-top: 4px; }
.bedside-clock .keys { display: flex; gap: 14px; }
.key-place { display: grid; place-items: center; width: 64px; min-height: 52px; border-radius: 12px; }
.key-place.over, .key-place.insert-here { outline: 2px dashed var(--accent, #2196f3); outline-offset: 2px; }
.key-empty { width: 36px; height: 36px; border-radius: 50%; border: 1px dashed currentColor; background: transparent; color: inherit; opacity: .45; cursor: pointer; }
</style>
