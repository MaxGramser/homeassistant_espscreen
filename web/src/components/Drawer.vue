<script setup lang="ts">
// The inspector: a column of its own on the right (app 0.4.32), there only while something is selected, so it never
// covers the pages or the library. Its content follows what is selected. It glides open and shut (app 0.4.32): the
// column grows while its content keeps its own width, so the pages beside it make room once instead of reflowing.
import { computed, ref } from "vue";
import { t } from "../i18n";
import { useResizeHandle } from "../composables/useResizeHandle";
import { DRAWER_MAX, DRAWER_MIN, useDrawerStore } from "../stores/drawer";
import TileInspector from "./TileInspector.vue";
import TopbarInspector from "./TopbarInspector.vue";
import SaverClock from "./SaverClock.vue";
import SaverInspector from "./SaverInspector.vue";
import InspectPanel from "./InspectPanel.vue";
import PageInspector from "./PageInspector.vue";
import SelectionInspector from "./SelectionInspector.vue";
import { useUiStore } from "../stores/ui";
import { useDocumentStore } from "../stores/document";
import { useInspectorStore } from "../stores/inspector";

const ui = useUiStore();
const doc = useDocumentStore();
const insp = useInspectorStore();

const open = computed(() => Boolean(insp.inspector && (insp.inspector.kind !== "tile" || doc.currentTile)));
// Its left edge (app dev): dragged wider or narrower as the sidebar's edge is, by the arrow keys (Shift for bigger
// steps), or back to its width with a double click (stores/drawer.ts).
const drawer = useDrawerStore();
const aside = ref<HTMLElement | null>(null);
let right = 0;
const edge = useResizeHandle({
  onStart: () => { right = aside.value?.getBoundingClientRect().right || window.innerWidth; drawer.resizing = true; },
  onMove: (e) => drawer.drag(right - e.clientX),
  onEnd: () => { drawer.resizing = false; },
  selectNothing: true,
});
function resizeKey(event: KeyboardEvent) {
  const by = event.shiftKey ? 48 : 16;
  if (event.key === "ArrowLeft") drawer.drag(drawer.width + by);
  else if (event.key === "ArrowRight") drawer.drag(drawer.width - by);
  else if (event.key === "Home") drawer.reset();
  else return;
  event.preventDefault();
}
</script>

<template>
  <!-- On a phone (app 0.4.40) the inspector is a sheet from the bottom over a dimmed page; a tap beside it closes it. -->
  <Transition name="dim"><div v-if="open && ui.phone" class="sheet-dim" @click="insp.closeInspector"></div></Transition>
  <Transition name="drawer">
  <aside v-if="open" ref="aside" class="drawer open" :class="{ resizing: drawer.resizing }" id="tile-sheet"
    :style="ui.phone ? undefined : { '--drawer-w': `${drawer.width}px` }" @click.stop>
    <div v-if="!ui.phone" class="drawer-resize" role="separator" aria-orientation="vertical" tabindex="0" :aria-label="t('editor.drawer.resize')"
      :aria-valuenow="drawer.width" :aria-valuemin="DRAWER_MIN" :aria-valuemax="DRAWER_MAX" :title="t('editor.drawer.resize')"
      @pointerdown="edge.start" @dblclick="drawer.reset()" @keydown="resizeKey"></div>
    <div v-if="insp.inspector" class="drawer-inner">
      <!-- Keyed by the tile: another tile's settings start as a tile's settings start, with More settings and every chooser closed. -->
      <TileInspector v-if="insp.inspector.kind === 'tile' && doc.currentTile" :key="doc.currentTile.id" :tile="doc.currentTile" />
      <SelectionInspector v-else-if="insp.inspector.kind === 'tiles'" />
      <!-- The bar and its +: one inspector, so the bar at its head stays where it is. -->
      <TopbarInspector v-else-if="insp.inspector.kind === 'bar' || insp.inspector.kind === 'bar-add'" :index="insp.inspector.kind === 'bar' ? insp.inspector.index : -1" :adding="insp.inspector.kind === 'bar-add'" />
      <!-- The screensaver's clock, its entities and its +: one inspector, so the clock's row at its head stays where it is. -->
      <SaverClock v-else-if="insp.inspector.kind === 'saver-item' || insp.inspector.kind === 'saver-add' || (insp.inspector.kind === 'saver' && insp.inspector.step === 'clock')"
        :index="insp.inspector.kind === 'saver-item' ? insp.inspector.index : -1" :adding="insp.inspector.kind === 'saver-add'" />
      <SaverInspector v-else-if="insp.inspector.kind === 'saver'" :key="insp.inspector.step" :step="insp.inspector.step" />
      <PageInspector v-else-if="insp.inspector.kind === 'page'" :id="insp.inspector.id" />
      <InspectPanel v-else-if="insp.inspector.kind === 'inspect'" :entity="insp.inspector.entity" :at="insp.inspector.slot" :tile-key="insp.inspector.key" />
    </div>
  </aside>
  </Transition>
</template>
