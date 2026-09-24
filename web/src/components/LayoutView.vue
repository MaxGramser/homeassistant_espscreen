<script setup lang="ts">
import { editorLayout } from "../store";
const { grid, hasGaps, pageCount } = editorLayout;

// The pages side by side, like swiping on the screen, or as a map of where the page tiles lead; the library on the
// right. One toolbar above both views: the view, undo and redo, the preview, a new page, and the how-to in one place.
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger } from "reka-ui";
import { t } from "../i18n";
import { entriesOf } from "../model/layout";
import { closeInspector, currentScreen, deviceStyle, gridChanged, isCompact, pageReachWarning, pagesShown, redo, reviewScreenGrid, setEditorMode, startUpdate, state, supports, tileLimit, undo } from "../store";
import PageWizard from "./PageWizard.vue";
import DevicePage from "./DevicePage.vue";
import FirmwarePreview from "./FirmwarePreview.vue";
import Library from "./Library.vue";
import PageMap from "./PageMap.vue";
import NavigationPreview from './NavigationPreview.vue';
import GridReview from './GridReview.vue';
import Icon from './ui/Icon.vue';
import type { IconName } from '../model/ui-icons';
import { dismissMigrationNote, resolveLayoutConflict, startFreshLayout } from '../store';
import { titleOf } from '../model/pages';
const preview = ref(false);
const firmwarePreview = ref(false);
const pageWizard = ref(false);
const droppedTiles = computed(() => currentScreen.value?.page_document?.format === 'pages-v2'
  ? currentScreen.value.page_document.migration?.droppedTiles || [] : []);
const adjustedFields = computed(() => currentScreen.value?.page_document?.format === 'pages-v2'
  ? currentScreen.value.page_document.migration?.adjustedFields || [] : []);
const recoveryField = (field: string) => t(({ title: 'editor.topbar.screen_name', pages: 'editor.pages.choose_page',
  page_titles: 'editor.pages.title', header: 'editor.topbar.title', settings: 'editor.screen_view.tabs.settings' } as Record<string, string>)[field] || 'editor.common.unknown');
const narrow = ref(window.innerWidth <= 700);
const resize = () => { narrow.value = window.innerWidth <= 700; };
onMounted(() => window.addEventListener('resize', resize));
onBeforeUnmount(() => window.removeEventListener('resize', resize));
const simplePages = computed(() => narrow.value
  ? [Math.max(0, state.document?.pages.findIndex((page) => page.id === state.selectedPageId) ?? 0) + 1]
  : Array.from({ length: shown.value }, (_, index) => index + 1));

const layout = computed(() => state.layout!);
const entries = computed(() => state.drag.preview || entriesOf(layout.value));
const pages = computed(() => pageCount(entries.value, layout.value.pages));
const shown = computed(() => pagesShown());
const canAdd = computed(() => pages.value < grid.pages);
const focused = computed(() => state.document?.pages.findIndex((page) => page.id === state.focusedPageId) ?? -1);
const positionsHint = computed(() => hasGaps(layout.value.tiles) && !supports(0, 2, 26)
  ? t("editor.layout.positions_hint", { firmware: currentScreen.value?.firmware || t("editor.common.unknown") })
  : "");
// Page buttons and swiping off: a page no Go to page tile reaches, or one without a way back.
const reachHint = computed(() => pageReachWarning());
// Everything the page used to explain in small (i) buttons beside the count, now behind one ? in the toolbar.
const tips: [IconName, string][] = [["pencil-outline", "change"], ["plus", "add"], ["drag", "move"], ["view-column-outline", "pages"], ["sitemap-outline", "map"], ["play", "preview"]];
function onCanvasClick(e: MouseEvent) {
  // A click beside the pages closes the drawer; the cards and the bar handle their own clicks.
  if ((e.target as HTMLElement).closest(".device, .page-label, .page-head, .editor-toolbar, .map-node, .map-links, button, select, input")) return;
  if (state.inspector) closeInspector();
}
</script>

<template>
  <div class="canvas" id="canvas" @click="onCanvasClick">
    <div v-if="!state.layout" class="notice" role="status">
      <Icon name="information-outline" />
      <span class="notice-text">{{ currentScreen?.page_document?.format === 'legacy-v1' ? currentScreen.page_document.migrationError : t('editor.pages.wait_grid') }}</span>
      <button v-if="currentScreen?.page_document?.format === 'legacy-v1' && currentScreen.source_grid" type="button" class="btn quiet mini" @click="startFreshLayout">{{ t('editor.pages.start_fresh') }}</button>
    </div>
    <template v-else>
    <div class="editor-toolbar">
      <div class="seg views" role="group" :aria-label="t('editor.pages.mode')">
        <button type="button" :aria-pressed="state.editorMode === 'simple'" @click="setEditorMode('simple')"><Icon name="view-column-outline" />{{ t('editor.pages.view_row') }}</button>
        <button type="button" :aria-pressed="state.editorMode === 'advanced'" @click="setEditorMode('advanced')"><Icon name="sitemap-outline" />{{ t('editor.pages.view_map') }}</button>
      </div>
      <div class="tool-group" role="group">
        <button type="button" class="icon-btn" :disabled="!state.undoCount" :aria-label="t('editor.common.undo')" :title="`${t('editor.common.undo')} · ⌘Z`" @click="undo"><Icon name="undo" /></button>
        <button type="button" class="icon-btn" :disabled="!state.redoCount" :aria-label="t('editor.pages.redo')" :title="`${t('editor.pages.redo')} · ⇧⌘Z`" @click="redo"><Icon name="redo" /></button>
      </div>
      <button type="button" class="btn quiet" :title="t('editor.pages.try_navigation')" @click="preview = true"><Icon name="play" />{{ t('editor.pages.preview') }}</button>
      <button v-if="currentScreen?.virtual" type="button" class="btn quiet" id="firmware-preview-toggle" @click="firmwarePreview = !firmwarePreview">
        {{ t(firmwarePreview ? 'editor.preview.editor' : 'editor.preview.firmware') }}
      </button>
      <button type="button" id="toolbar-add-page" class="btn quiet" :disabled="!canAdd" :title="canAdd ? '' : t('editor.layout.max_pages', grid.pages)" @click="pageWizard = true"><Icon name="plus" />{{ t('editor.layout.add_page') }}</button>
      <span class="spacer"></span>
      <span id="count" class="toolbar-count">{{ t("editor.layout.count", { tiles: layout.tiles.length, limit: tileLimit }, pages) }}</span>
      <PopoverRoot>
        <PopoverTrigger as-child>
          <button type="button" id="layout-help" class="icon-btn" :aria-label="t('editor.layout.help.title')" :title="t('editor.layout.help.title')"><Icon name="help-circle-outline" /></button>
        </PopoverTrigger>
        <PopoverPortal>
          <PopoverContent class="ui-popover help-pop" align="end" :side-offset="8" :collision-padding="12">
            <h4>{{ t('editor.layout.help.title') }}</h4>
            <div v-for="[icon, key] in tips" :key="key" class="help-tip-row">
              <span class="help-tip-icon"><Icon :name="icon" /></span>
              <span><b>{{ t(`editor.layout.help.${key}_label`) }}</b> {{ t(`editor.layout.help.${key}`) }}</span>
            </div>
          </PopoverContent>
        </PopoverPortal>
      </PopoverRoot>
    </div>
    <div v-if="droppedTiles.length || adjustedFields.length" class="notice" role="status">
      <Icon name="alert-circle-outline" />
      <span class="notice-text">
        <span v-if="droppedTiles.length">{{ t('editor.pages.migration_dropped', { count: droppedTiles.length, names: droppedTiles.map(tile => tile.name || tile.entity || t('editor.common.unknown')).join(', ') }) }}</span>
        <span v-if="adjustedFields.length"> {{ t('editor.pages.migration_adjusted', { fields: adjustedFields.map(recoveryField).join(', ') }) }}</span>
      </span>
      <button type="button" class="btn quiet mini" @click="dismissMigrationNote">{{ t('editor.pages.dismiss_migration') }}</button>
    </div>
    <div v-if="currentScreen?.page_capability === 'offline'" class="notice" role="status"><Icon name="information-outline" /><span class="notice-text">{{ t('editor.pages.offline_notice') }}</span></div>
    <div v-if="currentScreen?.page_capability === 'update_screen'" class="notice" role="status">
      <Icon name="update" /><span class="notice-text">{{ t('editor.pages.update_notice') }}</span>
      <button v-if="currentScreen?.online && currentScreen.update?.profile" type="button" class="btn primary mini" @click="startUpdate(currentScreen)">{{ t('editor.screen_view.menu.update') }}</button>
    </div>
    <div v-if="state.conflict" class="notice warn" role="alert">
      <Icon name="alert-circle-outline" /><span class="notice-text">{{ t('editor.pages.conflict') }}</span>
      <button type="button" class="btn quiet mini" :disabled="state.busy" @click="resolveLayoutConflict('reload')">{{ t('editor.pages.reload_saved') }}</button>
      <button type="button" class="btn primary mini" :disabled="state.busy" @click="resolveLayoutConflict('keep')">{{ t('editor.pages.keep_mine') }}</button>
    </div>
    <div v-if="gridChanged" class="notice warn" role="status"><Icon name="resize" /><span class="notice-text">{{ t('editor.pages.grid_changed') }}</span><button class="btn quiet mini" @click="reviewScreenGrid">{{ t('editor.pages.grid_review') }}</button></div>
    <div v-if="positionsHint" id="positions-hint" class="notice warn" role="status"><Icon name="alert-circle-outline" /><span class="notice-text">{{ positionsHint }}</span></div>
    <div v-if="reachHint" id="page-reach-hint" class="notice warn" role="status"><Icon name="alert-circle-outline" /><span class="notice-text">{{ reachHint }}</span></div>
    <div v-if="!layout.tiles.length" id="no-tiles" class="notice" role="status"><Icon name="plus" /><span class="notice-text">{{ t("editor.layout.no_tiles") }}</span></div>
    <FirmwarePreview v-if="firmwarePreview && currentScreen?.virtual && currentScreen.shape" :width="currentScreen.shape.width" :height="currentScreen.shape.height"
      :key="`${currentScreen.id}:${JSON.stringify(currentScreen.shape)}`"
      :dpi="currentScreen.shape.dpi" :columns="currentScreen.shape.columns" :rows="currentScreen.shape.rows"
      :pages="pages" :tiles="entries.map(entry => entry.tile)" />
    <template v-else-if="state.editorMode === 'advanced' && focused >= 0">
      <button type="button" class="btn quiet back-map" @click="state.focusedPageId = null"><Icon name="arrow-left" />{{ t('editor.pages.back_map') }}</button>
      <div class="pages focused-page"><DevicePage :page="focused" :entries="entries" :pages="pages" :moving="state.drag.moving" map /></div>
    </template>
    <PageMap v-else-if="state.editorMode === 'advanced'" :key="String(narrow)" :compact="narrow" />
    <div v-else class="pages" id="layout-preview" :aria-label="t('editor.layout.aria')">
      <div v-if="narrow" class="page-pills" role="group" :aria-label="t('editor.pages.choose_page')">
        <button v-for="(page, index) in state.document!.pages" :key="page.id" type="button" :aria-pressed="state.selectedPageId === page.id ? 'true' : 'false'"
          @click="state.selectedPageId = page.id"><b>{{ index + 1 }}</b> {{ titleOf(state.document!, page) }}</button>
      </div>
      <DevicePage v-for="page in simplePages" :key="state.document?.pages[page - 1]?.id || page" :page="page - 1" :entries="entries" :pages="pages" :moving="state.drag.moving" />
      <div v-if="!narrow" class="page ghost" :style="deviceStyle" :class="{ disabled: !canAdd }">
        <div class="page-head"><span class="page-name muted">{{ t("editor.page.label", { page: shown + 1 }) }}</span></div>
        <div class="device" :class="{ compact: isCompact }" :style="deviceStyle" id="add-page" role="button" :tabindex="canAdd ? 0 : -1" @click="canAdd && (pageWizard = true)" @keydown.enter.prevent="canAdd && (pageWizard = true)">
          <span class="ghost-plus"><Icon name="plus" /></span>
          <span>{{ canAdd ? t("editor.layout.add_page") : t("editor.layout.max_pages", grid.pages) }}</span>
        </div>
      </div>
    </div>
    </template>
  </div>
  <Library v-if="state.layout" />
  <NavigationPreview v-if="preview && state.document" :key="state.selected || ''" @close="preview = false" />
  <PageWizard v-if="pageWizard" :key="state.selected || ''" @close="pageWizard = false" />
  <GridReview v-if="state.gridReview" />
</template>

<style scoped>
.focused-page { padding: 18px 0; justify-content: center; }
.back-map { align-self: flex-start; }
.page-pills { display: flex; gap: 6px; overflow-x: auto; width: 100%; padding-bottom: 4px; }
.page-pills button { flex: none; display: inline-flex; gap: 6px; align-items: center; padding: 6px 12px; border-radius: 999px; border: 1px solid var(--line); background: var(--surface); color: var(--ink-2); font-size: 12.5px; white-space: nowrap; }
.page-pills button b { font-weight: 650; color: var(--muted); }
.page-pills button[aria-pressed="true"] { background: var(--ink); border-color: var(--ink); color: var(--surface); }
.page-pills button[aria-pressed="true"] b { color: inherit; opacity: .7; }
@media (max-width: 700px) { #layout-preview { flex-direction: column; align-items: center; overflow: visible; } }
</style>
