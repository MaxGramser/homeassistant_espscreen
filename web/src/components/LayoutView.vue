<script setup lang="ts">
// The pages side by side, like swiping on the screen, and the library on the right.
import { computed } from "vue";
import { entriesOf, hasGaps, MAX_PAGES, pageCount } from "../model/layout";
import { addPage, closeInspector, currentScreen, isGuition, pageReachWarning, pagesShown, state, supports, tileLimit } from "../store";
import DevicePage from "./DevicePage.vue";
import Library from "./Library.vue";

const layout = computed(() => state.layout!);
const entries = computed(() => state.drag.preview || entriesOf(layout.value));
const pages = computed(() => pageCount(entries.value, layout.value.pages));
const shown = computed(() => pagesShown());
const canAdd = computed(() => pages.value < MAX_PAGES);
const positionsHint = computed(() => hasGaps(layout.value.tiles) && !supports(0, 2, 26)
  ? `Empty slots and fixed positions work from firmware 0.2.26. This screen (firmware ${currentScreen.value?.firmware || "unknown"}) shifts the tiles up to the first free slot until that update.`
  : "");
// Page buttons and swiping off: a page no Go to page tile reaches, or one without a way back.
const reachHint = computed(() => pageReachWarning(entries.value, pages.value));
function onCanvasClick(e: MouseEvent) {
  // A click beside the pages closes the drawer; the cards and the bar handle their own clicks.
  if ((e.target as HTMLElement).closest(".device, .page-label, .canvas-head")) return;
  if (state.inspector) closeInspector();
}
</script>

<template>
  <div class="canvas" id="canvas" @click="onCanvasClick">
    <div class="canvas-head">
      <b id="count">{{ pages }} {{ pages === 1 ? "page" : "pages" }} · {{ layout.tiles.length }} / {{ tileLimit }} tiles</b>
      <span v-if="!layout.tiles.length" id="no-tiles">Add your first light, scene, or device from the library.</span>
      <span v-else>Tap the top bar or a tile to change it. Drag to move; drop on the next page for a new one.</span>
      <span v-if="positionsHint" id="positions-hint" class="warn">{{ positionsHint }}</span>
      <span v-if="reachHint" id="page-reach-hint" class="warn">{{ reachHint }}</span>
    </div>
    <div class="pages" id="layout-preview" aria-label="Screen layout">
      <DevicePage v-for="page in shown" :key="page" :page="page - 1" :entries="entries" :pages="pages" :moving="state.drag.moving" />
      <div class="page ghost" :class="{ disabled: !canAdd }">
        <div class="page-label"><span>Page {{ shown + 1 }}</span></div>
        <div class="device" :class="{ cyd: !isGuition }" id="add-page" role="button" :tabindex="canAdd ? 0 : -1" @click="canAdd && addPage()" @keydown.enter.prevent="canAdd && addPage()">
          {{ canAdd ? "+ Add page" : `${MAX_PAGES} pages is the most` }}
        </div>
      </div>
    </div>
  </div>
  <Library />
</template>
