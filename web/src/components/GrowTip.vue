<script setup lang="ts">
// The tip beside a tile that grew (app 0.4.89): the tile lit up on a dimmed page, and beside it what its new room offers,
// the set its growing put on it first. A choice the pointer rests on is drawn on the tile at once (stores/inspector.ts
// optionPreview), a click keeps it, Done or a click elsewhere lets the tip go with what the tile has. The same sets the
// inspector's Controls offers (model/tile-options.ts controlSets), so the tip never offers what the panel would not.
//
// It never stands in the way of sizing: it comes when the hand rests, WAIT after the release (the tile already shows its
// new controls meanwhile), and a press or a key before then means the user is on to the next thing, so it stays away.
// Taking a handle again puts it aside at once (a press outside it), and the next size brings it back for that size.
import { useElementBounding, useEventListener, useTimeoutFn } from "@vueuse/core";
import { computed, nextTick, ref, shallowRef, watch } from "vue";
import { PopoverAnchor, PopoverContent, PopoverPortal, PopoverRoot } from "reka-ui";
import { t } from "../i18n";
import { dimensions } from "../model/layout";
import { controlSets } from "../model/tile-options";
import { growOrder, resolveControls } from "../model/catalogue";
import { setTileOption, tilePanel } from "../editor/tiles";
import { useDocumentStore } from "../stores/document";
import { useInspectorStore } from "../stores/inspector";
import { useInventoryStore } from "../stores/inventory";
import { useScreenStore } from "../stores/screen";
import { useUiStore } from "../stores/ui";
import Icon from "./ui/Icon.vue";

const ui = useUiStore();
const doc = useDocumentStore();
const insp = useInspectorStore();
const inv = useInventoryStore();
const scr = useScreenStore();

const WAIT = 800;
const tile = computed(() => ui.growTip ? doc.layout?.tiles.find((item) => item.id === ui.growTip!.tileId) : undefined);
// Due once the hand has rested after a release; each new size starts the wait again.
const due = ref(false);
const rest = useTimeoutFn(() => { due.value = true; }, WAIT, { immediate: false });
watch(() => ui.growTip, (tip) => { due.value = false; rest.stop(); if (tip && ui.growTips) rest.start(); });
const open = computed(() => Boolean(due.value && ui.growTips && tile.value));
const domain = computed(() => tile.value?.entity.split(".")[0] ?? "");
const labels = computed(() => Object.fromEntries((inv.inventory.controls?.[domain.value]?.choices ?? []).map((choice) => [choice.key, choice.label])));
// What the tile draws now, and the sets its size offers, the one its growing chose first.
const now = computed(() => (tile.value && resolveControls(tile.value)) || "none");
const sets = computed(() => {
  if (!tile.value || !ui.growTip) return [];
  const offered = controlSets(tile.value, tilePanel(tile.value), ui.growTip.size), first = ui.growTip.applied;
  // The richest first (catalogue `grow`), so the list reads from most to least.
  const ranked = growOrder(domain.value).filter((key) => offered.includes(key) && key !== first);
  return [...(first && offered.includes(first) ? [first] : []), ...ranked, "none"];
});
const shape = computed(() => ui.growTip ? dimensions(ui.growTip.size as never, doc.editorLayout.grid) : { columns: 1, rows: 1 });

// The tile on the page, followed as the page scrolls, the window resizes or the tile is drawn anew (an edit, a size).
const element = () => tile.value?.id ? document.querySelector<HTMLElement>(`.pages [data-tile-id="${tile.value.id}"]`) : null;
const target = shallowRef<HTMLElement | null>(null);
watch([open, () => doc.layout], async () => { await nextTick(); target.value = open.value ? element() : null; }, { immediate: true });
const bounds = useElementBounding(target);
// A new anchor each time the tile moves, so the tip moves along with it.
const reference = computed(() => {
  const rect = new DOMRect(bounds.left.value, bounds.top.value, bounds.width.value, bounds.height.value);
  return { getBoundingClientRect: () => rect, contextElement: target.value ?? undefined };
});
// Wide enough around the tile that its edge grips stand in the light, ready to take again.
const PAD = 10;
const spot = computed(() => target.value && bounds.width.value ? { left: `${bounds.left.value - PAD}px`, top: `${bounds.top.value - PAD}px`,
  width: `${bounds.width.value + 2 * PAD}px`, height: `${bounds.height.value + 2 * PAD}px` } : null);

function preview(key: string | null) {
  if (!tile.value?.id) return;
  insp.optionPreview = key === null || key === now.value ? null : { tileId: tile.value.id, key: "controls", value: key };
}
function pick(key: string) {
  if (!tile.value) return;
  insp.optionPreview = null;
  if (key !== now.value) setTileOption(tile.value, "controls", key);
}
function close() {
  insp.optionPreview = null;
  ui.growTip = null;
}
function never() {
  ui.growTips = false;
  close();
}
// Another screen, another page shown, the tile gone or grown again elsewhere: the tip goes.
watch(() => scr.selected, close);
watch(() => tile.value, (found) => { if (ui.growTip && !found) close(); });
// Undone or sized again by another route: the tile no longer has the size the tip speaks of.
watch(() => tile.value?.options?.size ?? "single", (size) => { if (ui.growTip && tile.value && size !== ui.growTip.size) close(); });
// While it waits, a press or a key is the user moving on (a key that sizes again brings a new wait with its size).
const moveOn = () => { if (ui.growTip && !due.value) close(); };
// Open, a press anywhere but on the tip puts it aside, before the page sees it: a grip stops its own press from
// reaching the document, so Reka's outside press would never hear of it.
useEventListener(window, "pointerdown", (event: PointerEvent) => {
  if (open.value && !(event.target as Element | null)?.closest?.(".grow-tip")) close();
  else moveOn();
}, { capture: true });
useEventListener(window, "keydown", (event: KeyboardEvent) => {
  if (open.value && event.key === "Escape") close();
  else moveOn();
}, { capture: true });
</script>

<template>
  <Teleport to="body">
    <Transition name="grow-spot">
      <div v-if="open && spot" class="grow-spot" :style="spot" aria-hidden="true"></div>
    </Transition>
  </Teleport>
  <PopoverRoot :open="open" @update:open="(on) => { if (!on) close(); }">
    <PopoverAnchor :reference="reference" />
    <!-- Focus moving on (the tile chosen again after its edit) leaves it open; a click elsewhere, Escape or Done closes it. -->
    <PopoverPortal>
      <PopoverContent v-if="open" class="ui-popover grow-tip" side="right" align="start" :side-offset="22" :collision-padding="16"
        :aria-label="t('editor.tile.grow.title')" @open-auto-focus.prevent @focus-outside.prevent>
        <header>
          <span class="grow-badge"><Icon name="resize" /></span>
          <div>
            <h4>{{ t('editor.tile.grow.title') }}</h4>
            <p>{{ ui.growTip?.applied ? t('editor.tile.grow.applied', { columns: shape.columns, rows: shape.rows }) : t('editor.tile.grow.offered', { columns: shape.columns, rows: shape.rows }) }}</p>
          </div>
          <button type="button" class="icon-btn grow-close" :aria-label="t('editor.tile.grow.done')" @click="close"><Icon name="close" /></button>
        </header>
        <div class="grow-sets" role="radiogroup" :aria-label="t('editor.tile.controls.label')" @pointerleave="preview(null)">
          <button v-for="key in sets" :key="key" type="button" role="radio" class="grow-set" :class="{ none: key === 'none' }"
            :aria-checked="key === now ? 'true' : 'false'" @pointerenter="preview(key)" @focus="preview(key)" @blur="preview(null)" @click="pick(key)">
            <span class="grow-radio" aria-hidden="true"></span>
            <span class="grow-name">{{ key === 'none' ? t('editor.tile.grow.none') : labels[key] ?? key }}</span>
            <span v-if="key === ui.growTip?.applied" class="grow-tag">{{ t('editor.tile.grow.suggested') }}</span>
          </button>
        </div>
        <footer>
          <button type="button" class="grow-never" @click="never">{{ t('editor.tile.grow.never') }}</button>
          <button type="button" class="btn primary mini" @click="close">{{ t('editor.tile.grow.done') }}</button>
        </footer>
      </PopoverContent>
    </PopoverPortal>
  </PopoverRoot>
</template>

<style>
/* The tile lit on a dimmed page, as a tour does it: one ring with a shadow that covers everything around it. */
.grow-spot { position: fixed; z-index: 70; border-radius: 20px; pointer-events: none; box-shadow: 0 0 0 2px var(--accent), 0 0 0 9999px rgb(15 23 42 / .26);
  transition: left .18s ease-out, top .18s ease-out, width .18s ease-out, height .18s ease-out; }
.grow-spot-enter-active, .grow-spot-leave-active { transition: opacity .16s ease-out; }
.grow-spot-enter-from, .grow-spot-leave-to { opacity: 0; }
.grow-tip { width: 300px; padding: 14px; display: grid; gap: 12px; animation: grow-in .2s ease-out; }
@keyframes grow-in { from { opacity: 0; transform: translateX(-6px); } }
.grow-tip header { display: grid; grid-template-columns: auto 1fr auto; gap: 10px; align-items: start; }
.grow-tip h4 { font-size: 13.5px; margin: 1px 0 3px; }
.grow-tip p { margin: 0; color: var(--muted); font-size: 12.5px; line-height: 1.4; }
.grow-badge { display: grid; place-items: center; width: 28px; height: 28px; border-radius: 8px; background: var(--accent-soft); color: var(--accent); font-size: 16px; }
.grow-close { margin: -4px -4px 0 0; }
.grow-sets { display: grid; gap: 2px; }
.grow-set { display: flex; align-items: center; gap: 10px; min-height: 34px; padding: 6px 8px; border: 0; border-radius: 8px; background: transparent; color: var(--ink); font: inherit; text-align: left; cursor: pointer; }
.grow-set:hover, .grow-set:focus-visible { background: var(--hover, rgb(0 0 0 / .04)); outline: none; }
.grow-set[aria-checked="true"] { background: var(--accent-soft); }
.grow-set.none .grow-name { color: var(--muted); }
.grow-radio { flex: none; width: 14px; height: 14px; border-radius: 50%; border: 1.5px solid var(--line-strong, var(--muted)); transition: border-width .12s ease-out, border-color .12s ease-out; }
.grow-set[aria-checked="true"] .grow-radio { border: 4.5px solid var(--accent); }
.grow-name { flex: 1; }
.grow-tag { flex: none; padding: 2px 7px; border-radius: 999px; background: var(--surface); color: var(--accent); font-size: 11px; font-weight: 600; }
.grow-tip footer { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.grow-never { padding: 4px 0; border: 0; background: none; color: var(--muted); font: inherit; font-size: 12px; cursor: pointer; }
.grow-never:hover { color: var(--ink); text-decoration: underline; }
@media (prefers-reduced-motion: reduce) { .grow-spot, .grow-radio { transition: none; } .grow-tip { animation: none; } }
</style>
