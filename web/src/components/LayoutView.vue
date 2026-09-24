<script setup lang="ts">
// The pages side by side, like swiping on the screen, and the library on the right.
import { computed, ref } from "vue";
import { t } from "../i18n";
import { entriesOf, grid, hasGaps, pageCount } from "../model/layout";
import { addPage, closeInspector, currentScreen, deviceStyle, isCompact, pageReachWarning, pagesShown, state, supports, tileLimit } from "../store";
import DevicePage from "./DevicePage.vue";
import FirmwarePreview from "./FirmwarePreview.vue";
import Library from "./Library.vue";

const layout = computed(() => state.layout!);
const entries = computed(() => state.drag.preview || entriesOf(layout.value));
const pages = computed(() => pageCount(entries.value, layout.value.pages));
const shown = computed(() => pagesShown());
const canAdd = computed(() => pages.value < grid.pages);
const positionsHint = computed(() => hasGaps(layout.value.tiles) && !supports(0, 2, 26)
  ? t("editor.layout.positions_hint", { firmware: currentScreen.value?.firmware || t("editor.common.unknown") })
  : "");
// Page buttons and swiping off: a page no Go to page tile reaches, or one without a way back.
const reachHint = computed(() => pageReachWarning(entries.value, pages.value));
const firmwarePreview = ref(false);
function onCanvasClick(e: MouseEvent) {
  // A click beside the pages closes the drawer; the cards and the bar handle their own clicks.
  if ((e.target as HTMLElement).closest(".device, .page-label, .canvas-head")) return;
  if (state.inspector) closeInspector();
}
</script>

<template>
  <div class="canvas" id="canvas" @click="onCanvasClick">
    <div class="canvas-head">
      <b id="count">{{ t("editor.layout.count", { tiles: layout.tiles.length, limit: tileLimit }, pages) }}</b>
      <span v-if="!layout.tiles.length" id="no-tiles">{{ t("editor.layout.no_tiles") }}</span>
      <span v-else>{{ t("editor.layout.how_to") }}</span>
      <span v-if="pages > 1" id="how-to-pages">{{ t("editor.layout.how_to_pages") }}</span>
      <span v-if="positionsHint" id="positions-hint" class="warn">{{ positionsHint }}</span>
      <span v-if="reachHint" id="page-reach-hint" class="warn">{{ reachHint }}</span>
      <button v-if="currentScreen?.virtual" type="button" class="btn mini" id="firmware-preview-toggle" @click="firmwarePreview = !firmwarePreview">
        {{ t(firmwarePreview ? "editor.preview.editor" : "editor.preview.firmware") }}
      </button>
    </div>
    <FirmwarePreview v-if="firmwarePreview && currentScreen?.virtual && currentScreen.shape" :width="currentScreen.shape.width" :height="currentScreen.shape.height"
      :key="`${currentScreen.id}:${JSON.stringify(currentScreen.shape)}`"
      :dpi="currentScreen.shape.dpi" :columns="currentScreen.shape.columns" :rows="currentScreen.shape.rows"
      :pages="pages"
      :tiles="entries.map((entry) => entry.tile)" />
    <div v-else class="pages" id="layout-preview" :aria-label="t('editor.layout.aria')">
      <DevicePage v-for="page in shown" :key="page" :page="page - 1" :entries="entries" :pages="pages" :moving="state.drag.moving" />
      <div class="page ghost" :style="deviceStyle" :class="{ disabled: !canAdd }">
        <div class="page-label"><span>{{ t("editor.page.label", { page: shown + 1 }) }}</span></div>
        <div class="device" :class="{ compact: isCompact }" :style="deviceStyle" id="add-page" role="button" :tabindex="canAdd ? 0 : -1" @click="canAdd && addPage()" @keydown.enter.prevent="canAdd && addPage()">
          {{ canAdd ? t("editor.layout.add_page") : t("editor.layout.max_pages", grid.pages) }}
        </div>
      </div>
    </div>
  </div>
  <Library />
</template>
