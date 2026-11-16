<script setup lang="ts">
// "Make a section" beside the tiles chosen together on a page (docs/PAGES.md "Sections", "Making a section"): a small
// action at the top right of what is chosen. A click opens a name field there, focused at once, and the page shows the
// section the tiles will make while the name is typed: in place where they fill a rectangle, else a block at the first
// tile with its tiles in reading order and the loose tiles in its way moved aside. Enter makes it, as one step of undo;
// Escape leaves everything as it was. Icon and summary come after, in the section's drawer that opens.
import { computed, nextTick, ref, watch } from "vue";
import { t } from "../i18n";
import { makeSection, proposedSection, sectionsOffered, showEdit } from "../editor/sections";
import { isKey, sizeOf, dimensions } from "../model/layout";
import { blockOf } from "../model/sections";
import { useDocumentStore } from "../stores/document";
import { useInspectorStore } from "../stores/inspector";
import Icon from "./ui/Icon.vue";

const props = defineProps<{ page: number }>();
const doc = useDocumentStore();
const insp = useInspectorStore();
const { grid } = doc.editorLayout;

// The chosen tiles of this page, when they are all loose there: what a section can be made of.
const chosen = computed(() => {
  const tiles = insp.chosenTiles.filter((tile) => !isKey(tile) && tile.slot >= 0);
  if (!tiles.length || !doc.layout || !doc.documentGrid) return [];
  if (tiles.some((tile) => Math.floor(tile.slot / grid.slots) !== props.page)) return [];
  const g = doc.screenGridOf(doc.documentGrid);
  return tiles.some((tile) => blockOf(doc.layout!, tile, g) || sizeOf(tile) === "full") ? [] : tiles;
});
// Two or more chosen together, or one in its own drawer once the name is asked for (its menu, the selection's drawer).
const shown = computed(() => sectionsOffered() && (chosen.value.length > 1 || (chosen.value.length === 1 && insp.makingSection)));
// Where the action stands: the top right corner of the chosen tiles' cells.
// Where the action stands: above the top right corner of the chosen tiles' cells, or under their bottom right corner when
// they start on the page's first row, so it never covers the top bar.
const anchor = computed(() => {
  let top = Infinity, bottom = 0, right = 0;
  for (const tile of chosen.value) {
    const local = tile.slot % grid.slots, row = Math.floor(local / grid.columns), column = local % grid.columns, d = dimensions(sizeOf(tile), grid);
    top = Math.min(top, row);
    bottom = Math.max(bottom, row + d.rows - 1);
    right = Math.max(right, column + d.columns);
  }
  const line = (row: number) => row + 1;
  return top === 0 ? { gridColumn: `${right} / span 1`, gridRow: `${line(bottom)} / span 1`, alignSelf: "end" }
    : { gridColumn: `${right} / span 1`, gridRow: `${line(top)} / span 1` };
});
const below = computed(() => anchor.value.alignSelf === "end");
const name = ref("");
const field = ref<HTMLInputElement | null>(null);
async function ask() {
  insp.makingSection = true;
  name.value = "";
  await nextTick();
  field.value?.focus();
}
function preview() {
  const edit = proposedSection(name.value);
  showEdit(edit && !("refused" in edit) ? edit : null);
}
function make() {
  if (makeSection(name.value)) name.value = "";
}
function leave() {
  insp.makingSection = false;
  showEdit(null);
}
watch(() => insp.makingSection, async (open) => {
  if (open && shown.value) { await nextTick(); field.value?.focus(); preview(); }
  if (!open) showEdit(null);
});
watch(() => chosen.value.map((tile) => tile.id).join(), () => { if (insp.makingSection) preview(); });
</script>

<template>
  <div v-if="shown" class="section-maker" :class="{ below }" :style="anchor" @click.stop @pointerdown.stop>
    <button v-if="!insp.makingSection" type="button" class="section-maker-key" @click="ask">
      <Icon name="view-grid-outline" />{{ t("editor.sections.make") }}
    </button>
    <form v-else class="section-maker-field" @submit.prevent="make">
      <Icon name="view-grid-outline" />
      <input ref="field" v-model="name" maxlength="48" :placeholder="t('editor.sections.name_placeholder')" :aria-label="t('editor.sections.title')"
        @input="preview" @keydown.esc.prevent.stop="leave" />
      <button type="submit" class="section-maker-ok" :title="t('editor.sections.make_now')" :aria-label="t('editor.sections.make_now')"><Icon name="check" /></button>
    </form>
  </div>
</template>

<style>
.section-maker { position: relative; z-index: 6; justify-self: end; align-self: start; width: 0; height: 0; }
.section-maker > * { position: absolute; right: 0; bottom: 6px; white-space: nowrap; }
.section-maker.below > * { bottom: auto; top: 6px; }
.section-maker-key { display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border: 0; border-radius: 999px; background: var(--accent); color: #fff;
  font: 600 13px var(--ui-font); box-shadow: 0 4px 14px rgb(0 0 0 / .22); cursor: pointer; animation: section-maker-in .14s ease-out; }
.section-maker-key:hover { filter: brightness(1.06); }
.section-maker-field { display: inline-flex; align-items: center; gap: 6px; padding: 4px 4px 4px 10px; border-radius: 999px; background: var(--surface);
  border: 1px solid var(--accent); box-shadow: 0 6px 20px rgb(0 0 0 / .22); animation: section-maker-in .14s ease-out; }
.section-maker-field input { width: 14em; border: 0; outline: none; background: transparent; font: 500 14px var(--ui-font); color: var(--ink); }
.section-maker-ok { display: grid; place-items: center; width: 28px; height: 28px; border: 0; border-radius: 50%; background: var(--accent); color: #fff; cursor: pointer; }
@keyframes section-maker-in { from { opacity: 0; transform: translateY(4px); } }
</style>
