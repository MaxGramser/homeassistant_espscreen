<script setup lang="ts">
// The first layout (docs/AUTO_LAYOUT.md): the pages Tessera proposes for the open screen, drawn small as the screen will
// show them, before they go in as one edit. On a screen that has tiles it asks whether they replace its pages or come
// after them. The layout itself is model/auto-layout.ts, its glue editor/auto-layout.ts.
import { computed, onMounted, ref, watch } from "vue";
import { t } from "../i18n";
import type { AutoResult } from "../model/auto-layout";
import { placedTiles, sectionsOf, tilesIn, titleOf } from "../model/pages";
import { applyLayout, draftEmpty, proposeLayout, type AutoMode } from "../editor/auto-layout";
import { useDocumentStore } from "../stores/document";
import { useEntitiesStore } from "../stores/entities";
import { glyph } from "../model/topbar";
import Icon from "./ui/Icon.vue";
import UiChoiceCards from "./ui/UiChoiceCards.vue";

const emit = defineEmits<{ close: [] }>();
const doc = useDocumentStore();
const entities = useEntitiesStore();
const dialog = ref<HTMLDialogElement>();
const empty = draftEmpty();
const mode = ref<AutoMode>("replace");
const result = ref<AutoResult | null>(null), error = ref(""), busy = ref(false);
// Pages and tiles left for more after the ones the screen has.
const pagesLeft = computed(() => Math.min(doc.editorLayout.grid.pages - (doc.document?.pages.length ?? 0), doc.tileLimit - (doc.layout?.tiles.length ?? 0)));
const cards = computed(() => [
  { value: "replace", title: t("editor.auto.replace"), detail: t("editor.auto.replace_hint") },
  { value: "append", title: t("editor.auto.append"), detail: pagesLeft.value > 0 ? t("editor.auto.append_hint") : t("editor.auto.append_full") },
]);
const shown = computed(() => result.value?.layout.pages.filter((page) => page.tiles.length || page.sections?.length) ?? []);
const aspect = computed(() => `${doc.screenShape.width} / ${doc.screenShape.height}`);
const grid = computed(() => doc.documentGrid ?? { columns: 1, rows: 1 });
let asked = 0;
async function propose() {
  const ask = ++asked;
  busy.value = true; error.value = "";
  try {
    const made = await proposeLayout(mode.value);
    if (ask === asked) result.value = made;
  } catch (failure: any) {
    if (ask === asked) { result.value = null; error.value = t("editor.auto.failed", { error: failure?.message || String(failure) }); }
  } finally { if (ask === asked) busy.value = false; }
}
watch(mode, () => { if (mode.value !== "append" || pagesLeft.value > 0) propose(); else result.value = null; });
const ready = computed(() => !busy.value && Boolean(result.value?.tiles) && (mode.value === "replace" || pagesLeft.value > 0));
function make() {
  if (!ready.value || !result.value) return;
  if (applyLayout(result.value, mode.value)) emit("close");
}
const tileIcon = (entity: string) => glyph(entities.automaticIcon(entity));
const entityOf = (content: { kind: string; entityId?: string }) => content.entityId ?? "";
onMounted(() => { dialog.value?.showModal(); propose(); });
</script>

<template>
  <dialog ref="dialog" class="auto-layout" aria-labelledby="auto-layout-title" @cancel.prevent="emit('close')">
    <header>
      <span class="auto-mark"><Icon name="auto-fix" /></span>
      <h2 id="auto-layout-title">{{ t("editor.auto.title") }}</h2>
      <button class="icon-btn" type="button" :aria-label="t('editor.common.close')" @click="emit('close')"><Icon name="close" /></button>
    </header>
    <p class="intro">{{ t("editor.auto.intro") }}</p>
    <UiChoiceCards v-if="!empty" v-model="mode" class="modes" :cards="cards" :label="t('editor.auto.title')" />
    <p v-if="mode === 'append' && pagesLeft <= 0" class="notice" role="status"><Icon name="information-outline" /><span class="notice-text">{{ t("editor.auto.append_full") }}</span></p>
    <div v-else-if="busy" class="status" role="status"><span class="spin"></span>{{ t("editor.auto.reading") }}</div>
    <div v-else-if="error" class="notice warn" role="alert"><Icon name="alert-circle-outline" /><span class="notice-text">{{ error }}</span></div>
    <template v-else-if="result">
      <p v-if="!result.tiles" class="notice" role="status"><Icon name="information-outline" /><span class="notice-text">{{ t(mode === "append" ? "editor.auto.nothing_new" : "editor.auto.nothing") }}</span></p>
      <template v-else>
        <p class="summary" role="status">
          <b>{{ t("editor.auto.summary", { pages: shown.length, tiles: result.tiles }, shown.length) }}</b>
          <span v-if="result.sections"> · {{ t("editor.auto.summary_sections", { n: result.sections }, result.sections) }}</span>
          <span v-if="result.rooms"> · {{ t("editor.auto.from_rooms", { n: result.rooms }, result.rooms) }}</span>
        </p>
        <ol class="thumbs" :aria-label="t('editor.auto.title')">
          <li v-for="(page, index) in shown" :key="page.id" class="thumb">
            <span class="thumb-title"><b>{{ index + 1 }}</b> {{ titleOf(result.layout, page) }}</span>
            <div class="thumb-page" :style="{ aspectRatio: aspect, gridTemplateColumns: `repeat(${grid.columns}, 1fr)`, gridTemplateRows: `repeat(${grid.rows}, 1fr)` }">
              <div v-for="section in sectionsOf(page)" :key="section.id" class="thumb-section"
                :style="{ gridColumn: `${section.placement.column + 1} / span ${section.placement.columns}`, gridRow: `${section.placement.row + 1} / span ${section.placement.rows}` }">
                <span class="thumb-head">{{ section.title }}</span>
                <div class="thumb-inner" :style="{ gridTemplateColumns: `repeat(${section.placement.columns}, 1fr)`, gridTemplateRows: `repeat(${section.placement.rows}, 1fr)` }">
                  <div v-for="tile in tilesIn(page, section)" :key="tile.id" class="thumb-tile" :title="tile.appearance.label"
                    :style="{ gridColumn: `${tile.placement.column - section.placement.column + 1} / span ${tile.placement.columns}`, gridRow: `${tile.placement.row - section.placement.row + 1} / span ${tile.placement.rows}` }">
                    <span class="mdi">{{ tileIcon(entityOf(tile.content)) }}</span><span class="thumb-label">{{ tile.appearance.label }}</span>
                  </div>
                </div>
              </div>
              <div v-for="{ tile, row, column } in placedTiles(page).filter((placed) => !placed.section)" :key="tile.id" class="thumb-tile" :title="tile.appearance.label"
                :style="{ gridColumn: `${column + 1} / span ${tile.placement.columns}`, gridRow: `${row + 1} / span ${tile.placement.rows}` }">
                <span class="mdi">{{ tileIcon(entityOf(tile.content)) }}</span><span class="thumb-label">{{ tile.appearance.label }}</span>
              </div>
            </div>
          </li>
        </ol>
        <p v-if="result.leftOut" class="help">{{ t("editor.auto.left_out", { n: result.leftOut }, result.leftOut) }}</p>
      </template>
    </template>
    <footer>
      <button type="button" class="btn quiet" @click="emit('close')">{{ t("editor.common.cancel") }}</button>
      <button type="button" id="auto-layout-make" class="btn primary" :disabled="!ready" @click="make"><Icon name="auto-fix" />{{ t("editor.auto.make") }}</button>
    </footer>
  </dialog>
</template>

<style scoped>
.auto-layout { width: 760px; max-width: calc(100vw - 24px); max-height: calc(100dvh - 24px); overflow: auto; padding: 22px 24px; border: 1px solid var(--line); border-radius: 16px; background: var(--surface); color: var(--ink); box-shadow: var(--shadow); }
.auto-layout::backdrop { background: rgb(10 12 18 / .45); }
header { display: flex; align-items: center; gap: 10px; }
header h2 { margin: 0; font-size: 18px; flex: 1; }
.auto-mark { display: grid; place-items: center; width: 32px; height: 32px; border-radius: 50%; background: var(--accent-soft); color: var(--accent); font-size: 18px; }
.intro { margin: 10px 0 16px; color: var(--ink-2); font-size: 13px; line-height: 1.45; }
.modes { margin-bottom: 16px; grid-template-columns: repeat(2, minmax(0, 1fr)); }
.modes :deep(.choice-card) { min-width: 0; height: 100%; }
.status { display: flex; align-items: center; gap: 10px; color: var(--muted); font-size: 13px; padding: 28px 0; justify-content: center; }
.summary { margin: 0 0 10px; font-size: 13px; color: var(--ink-2); }
.summary b { color: var(--ink); font-weight: 600; }
.thumbs { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 14px; }
.thumb { display: grid; gap: 6px; min-width: 0; }
.thumb-title { font-size: 12px; color: var(--ink-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.thumb-title b { color: var(--muted); font-weight: 600; margin-right: 4px; }
.thumb-page { display: grid; gap: 3px; padding: 4px; border-radius: 10px; background: var(--surface-2); border: 1px solid var(--line); }
.thumb-section { display: grid; grid-template-rows: auto 1fr; min-width: 0; min-height: 0; padding: 2px 3px 3px; border-radius: 7px; background: color-mix(in srgb, var(--accent) 9%, var(--surface)); }
.thumb-head { font-size: 8.5px; font-weight: 650; color: var(--ink-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding: 0 2px 2px; }
.thumb-inner { display: grid; gap: 2px; min-height: 0; }
.thumb-tile { display: flex; align-items: center; gap: 2px; min-width: 0; min-height: 0; overflow: hidden; padding: 1px 3px; border-radius: 4px; background: var(--surface); box-shadow: 0 0 0 1px var(--line); font-size: 8px; color: var(--ink-2); }
.thumb-tile .mdi { font-size: 9px; color: var(--accent); flex: none; }
.thumb-label { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.help { margin: 12px 0 0; font-size: 12px; color: var(--muted); }
footer { display: flex; justify-content: flex-end; gap: 10px; margin-top: 18px; }
@media (max-width: 560px) { .modes { grid-template-columns: 1fr; } }
</style>
