<script setup lang="ts">
import { editorLayout } from "../store";
const { grid, hasGaps, pageCount } = editorLayout;

// The pages side by side, like swiping on the screen, or as a map of where the page tiles lead; the library on the
// right. One toolbar above both views: the view, undo and redo, the preview, a new page, and the how-to in one place.
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger } from "reka-ui";
import { t } from "../i18n";
import { entriesOf } from "../model/layout";
import { closeInspector, currentScreen, deviceStyle, gridChanged, isCompact, pageReachWarning, pagesShown, pageTitleShown, phone, redo, reviewScreenGrid, setEditorMode, startUpdate, state, supports, tileLimit, undo } from "../store";
import PhonePages from "./PhonePages.vue";
import PageWizard from "./PageWizard.vue";
import DevicePage from "./DevicePage.vue";
import Library from "./Library.vue";
import PageMap from "./PageMap.vue";
import NavigationPreview from './NavigationPreview.vue';
import GridReview from './GridReview.vue';
import MemoryMeter from './MemoryMeter.vue';
import Icon from './ui/Icon.vue';
import type { IconName } from '../model/ui-icons';
import { allowActions, dismissMigrationNote, resolveLayoutConflict, startFreshLayout } from '../store';
import { titleOf } from '../model/pages';
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

// On a phone (app 0.4.40) the pages stand one at a time, as on the glass: a swipe goes to the next, the page's name
// under it opens the list of pages, and the map is the full editor's.
const mode = computed(() => phone.value ? "simple" : state.editorMode);
const selectedIndex = computed(() => Math.max(0, state.document?.pages.findIndex((page) => page.id === state.selectedPageId) ?? 0));
function stepPage(step: number) {
  const list = state.document?.pages || [];
  const next = list[selectedIndex.value + step];
  if (next) { state.selectedPageId = next.id; state.insertAt = -1; }
}
let swipe: { x: number; y: number; at: number } | null = null;
function swipeStart(e: TouchEvent) {
  const touch = e.touches[0];
  swipe = e.touches.length === 1 && touch ? { x: touch.clientX, y: touch.clientY, at: Date.now() } : null;
}
function swipeEnd(e: TouchEvent) {
  const touch = e.changedTouches[0], from = swipe;
  swipe = null;
  if (!from || !touch || state.drag.active) return;
  const dx = touch.clientX - from.x, dy = touch.clientY - from.y;
  if (Math.abs(dx) > 48 && Math.abs(dx) > Math.abs(dy) * 1.5 && Date.now() - from.at < 700) stepPage(dx < 0 ? 1 : -1);
}

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
    <div v-if="!phone" class="editor-toolbar">
      <div class="seg views" role="group" :aria-label="t('editor.pages.mode')">
        <button type="button" :aria-pressed="state.editorMode === 'simple'" @click="setEditorMode('simple')"><Icon name="view-column-outline" />{{ t('editor.pages.view_row') }}</button>
        <button type="button" :aria-pressed="state.editorMode === 'advanced'" @click="setEditorMode('advanced')"><Icon name="sitemap-outline" />{{ t('editor.pages.view_map') }}</button>
      </div>
      <div class="tool-group" role="group">
        <button type="button" class="icon-btn" :disabled="!state.undoCount" :aria-label="t('editor.common.undo')" :title="`${t('editor.common.undo')} · ⌘Z`" @click="undo"><Icon name="undo" /></button>
        <button type="button" class="icon-btn" :disabled="!state.redoCount" :aria-label="t('editor.pages.redo')" :title="`${t('editor.pages.redo')} · ⇧⌘Z`" @click="redo"><Icon name="redo" /></button>
      </div>
      <button type="button" class="btn quiet" :title="t('editor.pages.try_navigation')" @click="state.previewOpen = true"><Icon name="play" />{{ t('editor.pages.preview') }}</button>
      <button type="button" id="toolbar-add-page" class="btn quiet" :disabled="!canAdd" :title="canAdd ? '' : t('editor.layout.max_pages', grid.pages)" @click="state.pageWizardOpen = true"><Icon name="plus" />{{ t('editor.layout.add_page') }}</button>
      <span class="spacer"></span>
      <span id="count" class="toolbar-count">{{ t("editor.layout.count", { tiles: layout.tiles.length, limit: tileLimit }, pages) }}</span>
      <MemoryMeter />
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
    <!-- Home Assistant ignores this screen's taps until it may perform actions (app 0.4.63, its own repair issue). -->
    <div v-if="currentScreen?.actions_blocked" id="actions-blocked" class="notice warn" role="status">
      <Icon name="alert-circle-outline" /><span class="notice-text">{{ t('editor.pages.actions_blocked') }}</span>
      <!-- One click instead of Home Assistant's Configure dialog (app 0.4.73). -->
      <button type="button" class="btn primary mini" id="allow-actions" :disabled="Boolean(state.allowing)" @click="allowActions(currentScreen)"><span v-if="state.allowing === currentScreen.id" class="spin small"></span>{{ t('editor.pages.allow_actions') }}</button>
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
    <template v-if="mode === 'advanced' && focused >= 0">
      <button type="button" class="btn quiet back-map" @click="state.focusedPageId = null"><Icon name="arrow-left" />{{ t('editor.pages.back_map') }}</button>
      <div class="pages focused-page"><DevicePage :page="focused" :entries="entries" :pages="pages" :moving="state.drag.moving" map /></div>
    </template>
    <PageMap v-else-if="mode === 'advanced'" :key="String(narrow)" :compact="narrow" />
    <div v-else class="pages" id="layout-preview" :aria-label="t('editor.layout.aria')"
      @touchstart.passive="phone && swipeStart($event)" @touchend.passive="phone && swipeEnd($event)">
      <div v-if="narrow && !phone" class="page-pills" role="group" :aria-label="t('editor.pages.choose_page')">
        <button v-for="(page, index) in state.document!.pages" :key="page.id" type="button" :aria-pressed="state.selectedPageId === page.id ? 'true' : 'false'"
          @click="state.selectedPageId = page.id"><b>{{ index + 1 }}</b> {{ titleOf(state.document!, page) }}</button>
      </div>
      <DevicePage v-for="page in simplePages" :key="state.document?.pages[page - 1]?.id || page" :page="page - 1" :entries="entries" :pages="pages" :moving="state.drag.moving" />
      <div v-if="phone && state.document" class="phone-pager">
        <button type="button" class="phone-page-name" id="phone-pages" @click="state.pagesSheet = true">
          {{ pageTitleShown(selectedIndex) || t("editor.page.label", { page: selectedIndex + 1 }) }}
          <small>{{ t("editor.phone.page_of", { n: selectedIndex + 1, total: state.document.pages.length }) }}</small><Icon name="chevron-down" />
        </button>
        <span v-if="state.document.pages.length > 1" class="phone-dots" aria-hidden="true">
          <i v-for="(page, index) in state.document.pages" :key="page.id" :class="{ on: index === selectedIndex }"></i>
        </span>
        <p class="phone-hint">{{ t(state.document.pages.length > 1 ? "editor.phone.hint_pages" : "editor.phone.hint") }}</p>
      </div>
      <div v-if="!narrow" class="page ghost" :style="deviceStyle" :class="{ disabled: !canAdd }">
        <div class="page-head"><span class="page-name muted">{{ t("editor.page.label", { page: shown + 1 }) }}</span></div>
        <div class="device" :class="{ compact: isCompact }" :style="deviceStyle" id="add-page" role="button" :tabindex="canAdd ? 0 : -1" @click="canAdd && (state.pageWizardOpen = true)" @keydown.enter.prevent="canAdd && (state.pageWizardOpen = true)">
          <span class="ghost-plus"><Icon name="plus" /></span>
          <span>{{ canAdd ? t("editor.layout.add_page") : t("editor.layout.max_pages", grid.pages) }}</span>
        </div>
      </div>
    </div>
    </template>
  </div>
  <Library v-if="state.layout" />
  <NavigationPreview v-if="state.previewOpen && state.document" :key="state.selected || ''" @close="state.previewOpen = false" />
  <PageWizard v-if="state.pageWizardOpen" :key="state.selected || ''" @close="state.pageWizardOpen = false" />
  <PhonePages v-if="phone && state.pagesSheet && state.document" @add="state.pagesSheet = false; state.pageWizardOpen = true" />
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
