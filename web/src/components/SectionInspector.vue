<script setup lang="ts">
// A section's drawer (docs/PAGES.md "Sections"): its title, its icon, the entity whose state its band sums up, its size
// in cells, and taking it away with or without its tiles. What changes here shows on the section at once, as the glass
// will draw it. Under it the two notes a section may need: loose tiles beside it that would read better as a row of
// their own, and a grid of three rows or fewer, where the band costs a lot of each tile's height.
import { computed, nextTick, watch } from "vue";
import { t } from "../i18n";
import { useTextDraft } from "../composables/useTextDraft";
import { looseRowAbove, removeSection, resizeSection, setSectionFields } from "../editor/sections";
import { blockOf, insideMargins, looseBeside, sectionMetrics } from "../model/sections";
import { cardHeight } from "../model/ui-scale";
import { useDocumentStore } from "../stores/document";
import { useEntitiesStore } from "../stores/entities";
import { useInspectorStore } from "../stores/inspector";
import { useInventoryStore } from "../stores/inventory";
import { useScreenStore } from "../stores/screen";
import { useCanvasStore } from "../stores/canvas";
import IconPicker from "./IconPicker.vue";
import Icon from "./ui/Icon.vue";
import InspectorHead from "./ui/InspectorHead.vue";
import Section from "./ui/Section.vue";
import UiPicker from "./ui/UiPicker.vue";
import SwitchRow from "./ui/SwitchRow.vue";

const props = defineProps<{ id: string }>();
const doc = useDocumentStore();
const insp = useInspectorStore();
const entities = useEntitiesStore();
const inv = useInventoryStore();
const scr = useScreenStore();
const canvas = useCanvasStore();

const block = computed(() => doc.layout?.sections?.find((b) => b.id === props.id));
const grid = computed(() => (doc.documentGrid ? doc.screenGridOf(doc.documentGrid) : null));
const titleDraft = useTextDraft(() => block.value?.title ?? "", (value) => setSectionFields(props.id, { title: value }, `section:${props.id}`), true);
// Asked to rename this section (its menu): the title field takes the focus, selected.
watch(() => insp.naming, async (asked) => {
  if (!asked || asked.kind !== "section" || asked.id !== props.id) return;
  insp.naming = null;
  await nextTick();
  const field = document.querySelector<HTMLInputElement>("#section-title");
  field?.focus();
  field?.select();
}, { immediate: true });

// The summary: one entity's state at the band's right end. The section's own tiles come first in the list.
const own = computed(() => {
  const g = grid.value, layout = doc.layout;
  if (!g || !layout) return new Set<string>();
  return new Set(layout.tiles.filter((tile) => blockOf(layout, tile, g)?.id === props.id).map((tile) => tile.entity));
});
const summaryItems = computed(() => {
  const all = inv.inventory.entities.map((e) => ({ id: e.id, name: e.name || e.id, hint: own.value.has(e.id) ? t("editor.sections.in_section") : e.area || undefined }));
  return [...all.filter((item) => own.value.has(item.id)), ...all.filter((item) => !own.value.has(item.id))];
});
const summaryName = computed(() => (block.value?.summary ? entities.entityName(block.value.summary) : t("editor.sections.summary_none")));

// A tile's height in this section and beside it, for the note on a grid of three rows or fewer: the section's header and
// padding come out of its own tiles (insideMargins), loose tiles keep their height.
const short = computed(() => (grid.value?.rows ?? 9) <= 3);
const heights = computed(() => {
  const shape = doc.screenShape, rows = grid.value?.rows ?? 3, m = sectionMetrics(shape as Parameters<typeof sectionMetrics>[0]);
  const dpi = (shape as { dpi?: number }).dpi || 170, mm = (px: number) => Math.round((px * 25.4) / dpi);
  const cell = cardHeight(shape, rows, 1, 0, canvas.pageBarShown), room = insideMargins(m, block.value?.rows ?? 1, 0, 0);
  return { without: mm(cell), with: mm(cell - room.top - room.bottom) };
});
const loose = computed(() => (block.value && grid.value && doc.layout ? looseBeside(doc.layout, grid.value, block.value.page).length : 0));
// A screen online whose firmware draws no sections yet gets the tiles without them until it is updated.
const needsUpdate = computed(() => Boolean(scr.currentScreen?.online) && scr.currentScreen?.sections_drawn === false);
</script>

<template>
  <template v-if="block">
    <InspectorHead :title="block.title" icon="view-grid-outline"
      :crumbs="[{ text: t('editor.page.label', { page: block.page + 1 }), open: () => insp.openPage(doc.document!.pages[block!.page].id) }, { text: t('editor.sections.kind') }]" />
    <div class="dr-body section-body">
      <p v-if="needsUpdate" class="notice warn section-update"><Icon name="alert-circle-outline" />{{ t("editor.sections.update_screen") }}</p>
      <Section :title="t('editor.sections.head')" icon="format-title">
        <div class="f">
          <span class="f-label"><label for="section-title">{{ t("editor.sections.title") }}</label></span>
          <input id="section-title" :value="titleDraft.value.value" maxlength="48" :placeholder="t('editor.sections.name_placeholder')"
            @focus="doc.beginFieldEdit(`section:${id}`); titleDraft.focus()" @blur="doc.endFieldEdit(); titleDraft.blur()"
            @input="titleDraft.input(($event.target as HTMLInputElement).value)" />
        </div>
        <IconPicker :selected="block.icon || 'auto'" automatic="" :auto-label="t('editor.sections.no_icon')"
          @pick="(name: string) => setSectionFields(id, { icon: name === 'auto' || name === 'none' ? undefined : name })" />
        <div class="f">
          <span class="f-label"><span id="section-summary-label">{{ t("editor.sections.summary") }}</span></span>
          <div class="section-summary">
            <UiPicker id="section-summary" :items="summaryItems" :placeholder="t('editor.sections.summary_search')" :empty="t('editor.sections.summary_none_found')"
              @pick="(entity: string) => setSectionFields(id, { summary: entity })">
              <template #trigger>
                <button type="button" class="ghost-btn" aria-labelledby="section-summary-label"><Icon name="magnify" />{{ summaryName }}</button>
              </template>
            </UiPicker>
            <button v-if="block.summary" type="button" class="btn quiet mini" :aria-label="t('editor.sections.summary_clear')" :title="t('editor.sections.summary_clear')"
              @click="setSectionFields(id, { summary: undefined })"><Icon name="close" /></button>
          </div>
          <small class="help">{{ t("editor.sections.summary_hint") }}</small>
        </div>
        <SwitchRow class="section-contrast" :label="t('editor.sections.contrast')" :description="t('editor.sections.contrast_hint')"
          :model-value="Boolean(block.contrast)" @update:model-value="(on: boolean) => setSectionFields(id, { contrast: on || undefined, ...(on ? {} : { contrastTiles: undefined }) })" />
        <SwitchRow v-if="block.contrast" class="section-contrast-tiles" :label="t('editor.sections.contrast_tiles')" :description="t('editor.sections.contrast_tiles_hint')"
          :model-value="Boolean(block.contrastTiles)" @update:model-value="(on: boolean) => setSectionFields(id, { contrastTiles: on || undefined })" />
      </Section>
      <Section :title="t('editor.sections.size')" icon="view-grid-outline">
        <div class="section-size">
          <span class="section-size-label">{{ t("editor.sections.columns") }}</span>
          <button type="button" class="btn quiet mini" :aria-label="t('editor.sections.narrower')" :disabled="block.columns <= 1" @click="resizeSection(id, block.columns - 1, block.rows)"><Icon name="minus" /></button>
          <b>{{ block.columns }}</b>
          <button type="button" class="btn quiet mini" :aria-label="t('editor.sections.wider')" @click="resizeSection(id, block.columns + 1, block.rows)"><Icon name="plus" /></button>
          <span class="section-size-label">{{ t("editor.sections.rows") }}</span>
          <button type="button" class="btn quiet mini" :aria-label="t('editor.sections.lower')" :disabled="block.rows <= 1" @click="resizeSection(id, block.columns, block.rows - 1)"><Icon name="minus" /></button>
          <b>{{ block.rows }}</b>
          <button type="button" class="btn quiet mini" :aria-label="t('editor.sections.taller')" @click="resizeSection(id, block.columns, block.rows + 1)"><Icon name="plus" /></button>
        </div>
        <small class="help">{{ t("editor.sections.size_hint") }}</small>
      </Section>
      <p v-if="loose" class="notice section-loose"><Icon name="information-outline" /><span>{{ t("editor.sections.loose_hint", { n: loose }, loose) }}</span>
        <button type="button" class="btn quiet mini" @click="looseRowAbove(block.page)">{{ t("editor.sections.loose_row") }}</button></p>
      <p v-if="short" class="notice section-short"><Icon name="information-outline" />{{ t("editor.sections.short_grid", { rows: grid?.rows ?? 3, with: heights.with, without: heights.without }) }}</p>
    </div>
    <div class="dr-foot section-foot">
      <button type="button" class="btn quiet" id="section-remove" @click="removeSection(id)"><Icon name="view-grid-outline" />{{ t("editor.sections.remove") }}</button>
      <button type="button" class="btn danger" id="section-remove-tiles" @click="removeSection(id, true)"><Icon name="delete-outline" />{{ t("editor.sections.remove_with_tiles") }}</button>
    </div>
  </template>
</template>

<style scoped>
.section-body { padding-bottom: 12px; }
.section-summary { display: flex; align-items: center; gap: 6px; }
.section-size { display: grid; grid-template-columns: auto auto 2.2em auto; align-items: center; gap: 6px 8px; padding: 4px 0; }
.section-size b { text-align: center; font-variant-numeric: tabular-nums; }
.section-size-label { color: var(--muted); }
.notice { display: flex; gap: 8px; align-items: flex-start; margin: 10px 16px 0; padding: 10px 12px; border-radius: 10px; background: var(--surface-2, #f4f4f4); font-size: 13px; line-height: 1.4; }
.notice .btn { margin-left: auto; flex: none; }
.section-foot { display: flex; gap: 8px; flex-wrap: wrap; }
</style>
