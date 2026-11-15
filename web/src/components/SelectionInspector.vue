<script setup lang="ts">
// Several tiles chosen together (⌘ or Shift and a click, or a band dragged over them): which ones, and what can be done
// to them all at once. Copy takes every setting along, to paste with ⌘V on another page or another screen; a tile in the
// list opens on its own.
import { computed } from "vue";
import { t } from "../i18n";
import { domainInfo } from "../model/layout";
import { glyph } from "../model/topbar";
import { copyChosen, removeTiles, shortcut as key } from "../editor/clipboard";
import Icon from "./ui/Icon.vue";
import InspectorHead from "./ui/InspectorHead.vue";
import { useDocumentStore } from "../stores/document";
import { useEntitiesStore } from "../stores/entities";
import { useInspectorStore } from "../stores/inspector";
import { useScreenStore } from "../stores/screen";
import { pageTitleShown } from "../editor/pages";

const doc = useDocumentStore();
const entities = useEntitiesStore();
const insp = useInspectorStore();
const scr = useScreenStore();

const tiles = computed(() => insp.selectedTiles);
const { pageOf } = doc.editorLayout;
// The pages they stand on, in the order of the row: "Page 2" for one, the screen for several.
const pagesOf = computed(() => [...new Set(tiles.value.map((tile) => pageOf(tile.slot)))].sort((a, b) => a - b));
const crumbs = computed(() => [{ text: scr.currentScreen?.name || "" },
  ...(pagesOf.value.length === 1 ? [{ text: pageTitleShown(pagesOf.value[0]) || t("editor.page.label", { page: pagesOf.value[0] + 1 }) }] : [])]);
const name = (entity: string, own: string) => own || entities.entityName(entity);
import { canMakeSection } from "../editor/sections";
</script>

<template>
  <InspectorHead kind="tile" icon="view-dashboard-outline" :title="t('editor.selection.title', { n: tiles.length }, tiles.length)" :crumbs="crumbs" />
  <div class="dr-body">
    <div class="items selection-list" role="list" :aria-label="t('editor.selection.title', { n: tiles.length }, tiles.length)">
      <div v-for="tile in tiles" :key="tile.id" class="item" role="listitem" tabindex="0" @click="insp.openTile(tile)" @keydown.enter.prevent="insp.openTile(tile)">
        <span class="av mdi" :style="{ color: domainInfo(tile.entity)[2], background: domainInfo(tile.entity)[3] }">{{ glyph(entities.tileIconCp(tile)) }}</span>
        <span class="tx"><b>{{ name(tile.entity, tile.name) }}</b><small v-if="pagesOf.length > 1">{{ t("editor.page.label", { page: pageOf(tile.slot) + 1 }) }}</small></span>
        <button type="button" class="x" :aria-label="t('editor.selection.leave', { name: name(tile.entity, tile.name) })" :title="t('editor.selection.leave', { name: name(tile.entity, tile.name) })"
          @click.stop="insp.toggleTile(tile)"><Icon name="close" /></button>
      </div>
    </div>
    <div class="insp-actions">
      <button type="button" class="btn quiet" id="selection-copy" :title="key('C')" @click="copyChosen"><Icon name="content-copy" />{{ t("editor.selection.copy") }}</button>
      <button v-if="canMakeSection()" type="button" class="btn quiet" id="selection-section" @click="insp.makingSection = true"><Icon name="view-grid-outline" />{{ t("editor.sections.make") }}</button>
    </div>
    <p class="help selection-hint">{{ t("editor.selection.hint", { copy: key("C"), paste: key("V") }) }}</p>
  </div>
  <div class="dr-foot">
    <button type="button" class="btn danger" id="selection-remove" @click="removeTiles(tiles)"><Icon name="delete-outline" />{{ t("editor.selection.remove", { n: tiles.length }, tiles.length) }}</button>
  </div>
</template>

<style scoped>
.selection-list { padding: 12px 16px 4px; }
.selection-hint { padding: 4px 16px 12px; margin: 0; }
</style>
