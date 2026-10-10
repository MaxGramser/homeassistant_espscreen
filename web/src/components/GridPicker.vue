<script setup lang="ts">
// The screen's columns and rows, beside the mockup (app 0.4.85, firmware 0.53.0+). A change lays the draft out on the new
// grid at once (stores/document.ts chooseGrid): what no longer fits moves on to a new page after its own, and the screen gets the
// grid with the next save. A screen whose firmware keeps the grid it was built with says so instead; a preview screen
// without its board's grids (the custom glass) has no button.
import { computed } from "vue";
import { PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger } from "reka-ui";
import { t } from "../i18n";
import Icon from "./ui/Icon.vue";
import { useScreenStore } from "../stores/screen";
import { useDocumentStore } from "../stores/document";

const scr = useScreenStore();
const doc = useDocumentStore();

const grid = computed(() => doc.documentGrid);
const axes = [["columns", 0], ["rows", 1]] as const;
const value = (axis: "columns" | "rows") => grid.value?.[axis] ?? 0;
const can = (axis: "columns" | "rows", index: 0 | 1, by: number) => {
  const way = doc.gridWay, next = value(axis) + by;
  return !!way && next >= way.min[index] && next <= way.max[index];
};
function step(axis: "columns" | "rows", index: 0 | 1, by: number) {
  if (!grid.value || !can(axis, index, by)) return;
  doc.chooseGrid(axis === "columns" ? grid.value.columns + by : grid.value.columns, axis === "rows" ? grid.value.rows + by : grid.value.rows);
}
const cells = computed(() => (grid.value ? grid.value.columns * grid.value.rows : 0));
// Standing up or lying down, on glass that turns (the add-on says which way it is to hang; null on square glass).
const turns = computed(() => !!scr.currentScreen?.hang && doc.documentUpright !== null);
const ways = [[false, "landscape", "crop-landscape"], [true, "portrait", "crop-portrait"]] as const;
</script>

<template>
  <PopoverRoot v-if="grid && (doc.gridWay || !scr.currentScreen?.virtual)">
    <PopoverTrigger as-child>
      <button type="button" id="toolbar-grid" class="btn quiet" :title="t('editor.grid.title')">
        <Icon name="view-grid-outline" />{{ grid.columns }} × {{ grid.rows }}
      </button>
    </PopoverTrigger>
    <PopoverPortal>
      <PopoverContent class="ui-popover grid-pop" align="start" :side-offset="8" :collision-padding="12">
        <h4>{{ t("editor.grid.title") }}</h4>
        <template v-if="doc.gridWay">
          <div v-if="turns" class="seg grid-ways" role="group" :aria-label="t('editor.grid.way')">
            <button v-for="[upright, word, icon] in ways" :key="word" type="button" :id="`grid-${word}`"
              :aria-pressed="doc.documentUpright === upright ? 'true' : 'false'" @click="doc.chooseHang(upright)">
              <Icon :name="icon" />{{ t(`editor.grid.${word}`) }}
            </button>
          </div>
          <div class="grid-body">
            <div class="grid-steps">
              <div v-for="[axis, index] in axes" :key="axis" class="grid-step">
                <span>{{ t(`editor.grid.${axis}`) }}</span>
                <button type="button" class="icon-btn" :id="`grid-${axis}-less`" :disabled="!can(axis, index, -1)"
                  :aria-label="t(`editor.grid.${axis}_less`)" @click="step(axis, index, -1)"><Icon name="minus" /></button>
                <b>{{ value(axis) }}</b>
                <button type="button" class="icon-btn" :id="`grid-${axis}-more`" :disabled="!can(axis, index, 1)"
                  :aria-label="t(`editor.grid.${axis}_more`)" @click="step(axis, index, 1)"><Icon name="plus" /></button>
              </div>
            </div>
            <div class="grid-sketch" aria-hidden="true"
              :style="{ aspectRatio: `${doc.screenShape.width} / ${doc.screenShape.height}`, gridTemplateColumns: `repeat(${grid.columns}, 1fr)`, gridTemplateRows: `repeat(${grid.rows}, 1fr)` }">
              <i v-for="cell in cells" :key="cell"></i>
            </div>
          </div>
          <p class="grid-hint">{{ t("editor.grid.hint") + (turns ? " " + t("editor.grid.turn_hint") : "") }}</p>
        </template>
        <p v-else class="grid-hint">{{ t("editor.grid.update_first") }}</p>
      </PopoverContent>
    </PopoverPortal>
  </PopoverRoot>
</template>

<style>
/* Not scoped: the popover is drawn in a portal, outside this component's elements (as .help-pop in app.css). */
.grid-pop { width: 300px; padding: 14px 16px; display: grid; gap: 12px; }
.grid-pop h4 { font-size: 13.5px; }
.grid-pop .grid-ways { display: flex; }
.grid-pop .grid-ways button { flex: 1; justify-content: center; }
.grid-pop .grid-body { display: flex; gap: 16px; align-items: center; }
.grid-pop .grid-steps { display: grid; gap: 8px; flex: 1; min-width: 0; }
.grid-pop .grid-step { display: grid; grid-template-columns: 1fr auto 26px auto; align-items: center; gap: 6px; font-size: 13px; color: var(--ink-2); }
.grid-pop .grid-step b { text-align: center; font-variant-numeric: tabular-nums; color: var(--ink); font-weight: 600; }
.grid-pop .grid-sketch { width: 72px; max-height: 96px; display: grid; gap: 3px; padding: 4px; border: 1px solid var(--line); border-radius: 8px; flex: none; }
.grid-pop .grid-sketch i { background: var(--seg); border-radius: 3px; }
.grid-pop .grid-hint { font-size: 12.5px; line-height: 1.45; color: var(--muted); }
</style>
