<script setup lang="ts">
// The tip beside a sensor just added as a meter (model/sensor-look.ts): how it should look, the meter's ring, tape and
// bar, its graph or the plain value, as GrowTip offers a grown tile's controls. A look the pointer rests on is drawn on
// the tile at once (stores/inspector.ts optionPreview), a click keeps it, Done or a click elsewhere keeps what it has.
// Every look keeps the range the sensor started with, so trying them loses nothing. Only looks the screen draws for this
// sensor are offered: the graph where Home Assistant keeps its history as a line (the same test the meter passed).
import { useElementBounding, useEventListener, useTimeoutFn } from "@vueuse/core";
import { computed, nextTick, ref, shallowRef, watch } from "vue";
import { PopoverAnchor, PopoverContent, PopoverPortal, PopoverRoot } from "reka-ui";
import { t } from "../i18n";
import { LOOK_KEYS, lookOf, lookOptions, type LookKey } from "../model/sensor-look";
import { ownRange } from "../model/meter";
import { setTileOptions } from "../editor/tiles";
import { useDocumentStore } from "../stores/document";
import { useInspectorStore } from "../stores/inspector";
import { useScreenStore } from "../stores/screen";
import { useUiStore } from "../stores/ui";
import Icon from "./ui/Icon.vue";
import TileAnchor from "./TileAnchor.vue";

const ui = useUiStore();
const doc = useDocumentStore();
const insp = useInspectorStore();
const scr = useScreenStore();

// It comes once the tile landed and the page settled, as the grow tip waits for the hand to rest.
const WAIT = 500;
const tile = computed(() => ui.lookTip ? doc.layout?.tiles.find((item) => item.id === ui.lookTip!.tileId) : undefined);
const due = ref(false);
const rest = useTimeoutFn(() => { due.value = true; }, WAIT, { immediate: false });
watch(() => ui.lookTip, (tip) => { due.value = false; rest.stop(); if (tip && ui.lookTips) rest.start(); });
const open = computed(() => Boolean(due.value && ui.lookTips && tile.value));
// The range it started with, kept by every meter look; read once, when the tip opens.
const range = ref<[number, number] | null>(null);
watch(open, (on) => { if (on) range.value = ownRange(tile.value?.options); });
const now = computed(() => lookOf(tile.value?.options));
// Each look in small, as the page draws the tile with it: a copy without the tile's id, so the look pointed at
// (optionPreview) stays on the page's tile and never on the miniatures.
const miniature = (key: LookKey) => {
  const { id: _id, ...rest } = tile.value!;
  return { ...rest, options: { ...(rest.options || {}), meter: undefined, min: undefined, max: undefined, ...lookOptions(key, range.value) } } as typeof rest;
};

function preview(key: LookKey | null) {
  if (!tile.value?.id) return;
  if (key === null || key === now.value) { insp.optionPreview = null; return; }
  const { display, ...rest } = lookOptions(key, range.value);
  // What the look leaves out (the ring's own look, a range) is left out of the drawn tile too.
  insp.optionPreview = { tileId: tile.value.id, key: "display", value: display, with: { meter: undefined, min: undefined, max: undefined, ...rest } };
}
function pick(key: LookKey) {
  if (!tile.value) return;
  insp.optionPreview = null;
  if (key !== now.value) setTileOptions(tile.value, { meter: undefined, min: undefined, max: undefined, ...lookOptions(key, range.value) });
}
function close() {
  insp.optionPreview = null;
  ui.lookTip = null;
}
function never() {
  ui.lookTips = false;
  close();
}

// The tile on the page, followed as the page scrolls or the tile is drawn anew.
const element = () => tile.value?.id ? document.querySelector<HTMLElement>(`.pages [data-tile-id="${tile.value.id}"]`) : null;
const target = shallowRef<HTMLElement | null>(null);
watch([open, () => doc.layout], async () => { await nextTick(); target.value = open.value ? element() : null; }, { immediate: true });
const bounds = useElementBounding(target);
const reference = computed(() => {
  const rect = new DOMRect(bounds.left.value, bounds.top.value, bounds.width.value, bounds.height.value);
  return { getBoundingClientRect: () => rect, contextElement: target.value ?? undefined };
});

// Another screen, the tile gone or a drag on its way: the tip goes.
watch(() => scr.selected, close);
watch(() => tile.value, (found) => { if (ui.lookTip && !found) close(); });
useEventListener(window, "pointerdown", (event: PointerEvent) => {
  if (ui.lookTip && !(event.target as Element | null)?.closest?.(".look-tip")) close();
}, { capture: true });
useEventListener(window, "keydown", (event: KeyboardEvent) => { if (open.value && event.key === "Escape") close(); }, { capture: true });
</script>

<template>
  <PopoverRoot :open="open" @update:open="(on) => { if (!on) close(); }">
    <PopoverAnchor :reference="reference" />
    <PopoverPortal>
      <PopoverContent v-if="open" class="ui-popover grow-tip look-tip" side="right" align="start" :side-offset="16" :collision-padding="16"
        :aria-label="t('editor.tile.look.title')" @open-auto-focus.prevent @focus-outside.prevent>
        <header>
          <span class="grow-badge"><Icon name="palette-outline" /></span>
          <div>
            <h4>{{ t('editor.tile.look.title') }}</h4>
            <p>{{ t('editor.tile.look.text') }}</p>
          </div>
          <button type="button" class="icon-btn grow-close" :aria-label="t('editor.tile.look.done')" @click="close"><Icon name="close" /></button>
        </header>
        <div class="grow-sets" role="radiogroup" :aria-label="t('editor.tile.look.title')" @pointerleave="preview(null)">
          <button v-for="key in LOOK_KEYS" :key="key" type="button" role="radio" class="grow-set" :data-look="key"
            :aria-checked="key === now ? 'true' : 'false'" @pointerenter="preview(key)" @focus="preview(key)" @blur="preview(null)" @click="pick(key)">
            <span class="look-mini" aria-hidden="true"><TileAnchor :tile="miniature(key)" :fit="66" /></span>
            <span class="grow-name">{{ t(`editor.tile.look.${key}`) }}</span>
            <span class="grow-radio" aria-hidden="true"></span>
          </button>
        </div>
        <footer>
          <button type="button" class="grow-never" @click="never">{{ t('editor.tile.look.never') }}</button>
          <button type="button" class="btn primary mini" @click="close">{{ t('editor.tile.look.done') }}</button>
        </footer>
      </PopoverContent>
    </PopoverPortal>
  </PopoverRoot>
</template>

<style>
/* Each look in small beside its name (LookTip): the tile as the page draws it, never a thing to click inside. */
.look-tip { width: 344px; }
.look-tip .grow-set { min-height: 74px; padding: 5px 8px; }
.look-mini { flex: none; width: 124px; display: grid; place-items: center; pointer-events: none; }
.look-mini .tile-anchor { cursor: default; }
</style>
