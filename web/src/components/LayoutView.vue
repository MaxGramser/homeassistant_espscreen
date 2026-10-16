<script setup lang="ts">

// The pages side by side, like swiping on the screen, or as a map of where the page tiles lead; the library on the
// right. One toolbar above both views: the view, undo and redo, the preview, a new page, and the how-to in one place.
import { useElementSize, useSwipe } from "@vueuse/core";
import { computed, nextTick, onBeforeUnmount, ref, watch, watchEffect } from "vue";
import { useAtMost } from "../composables/useWidths";
import { useBandSelect } from "../composables/useBandSelect";
import { modifierKey, shortcut } from "../editor/clipboard";
import { PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger } from "reka-ui";
import { t } from "../i18n";
import { entriesOf } from "../model/layout";
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
import { titleOf } from '../model/pages';
import { useUiStore } from "../stores/ui";
import { useBuildsStore } from "../stores/builds";
import { useScreenStore } from "../stores/screen";
import { useDragStore } from "../stores/drag";
import { useCanvasStore } from "../stores/canvas";
import { pageReachWarning, pagesShown, pageTitleShown } from "../editor/pages";
import { useDocumentStore } from "../stores/document";
import { useInspectorStore } from "../stores/inspector";
import { useDraftsStore } from "../stores/drafts";
import GrowTip from "./GrowTip.vue";

const ui = useUiStore();
const builds = useBuildsStore();
const scr = useScreenStore();
const dragging = useDragStore();
const canvas = useCanvasStore();
const doc = useDocumentStore();
const insp = useInspectorStore();
const drafts = useDraftsStore();
const { grid, hasGaps, pageCount } = doc.editorLayout;
const droppedTiles = computed(() => scr.currentScreen?.page_document?.format === 'pages-v2'
  ? scr.currentScreen.page_document.migration?.droppedTiles || [] : []);
const adjustedFields = computed(() => scr.currentScreen?.page_document?.format === 'pages-v2'
  ? scr.currentScreen.page_document.migration?.adjustedFields || [] : []);
const recoveryField = (field: string) => t(({ title: 'editor.topbar.screen_name', pages: 'editor.pages.choose_page',
  page_titles: 'editor.pages.title', header: 'editor.topbar.title', settings: 'editor.screen_view.tabs.settings' } as Record<string, string>)[field] || 'editor.common.unknown');
// From 700 px down the pages stand one at a time (composables/useWidths.ts).
const narrow = useAtMost('narrow');
const simplePages = computed(() => narrow.value
  ? [Math.max(0, doc.document?.pages.findIndex((page) => page.id === doc.selectedPageId) ?? 0) + 1]
  : Array.from({ length: shown.value }, (_, index) => index + 1));

// On a phone (app 0.4.40) the pages stand one at a time, as on the glass: a swipe goes to the next, the page's name
// under it opens the list of pages, and the map is the full editor's.
const mode = computed(() => ui.phone ? "simple" : doc.editorMode);
const selectedIndex = computed(() => Math.max(0, doc.document?.pages.findIndex((page) => page.id === doc.selectedPageId) ?? 0));
function stepPage(step: number) {
  const list = doc.document?.pages || [];
  const next = list[selectedIndex.value + step];
  if (next) { doc.selectedPageId = next.id; insp.forgetCell(); }
}
// A swipe is a finger that went more than 48 px sideways, half again as far as up or down, within 700 ms.
const pagesView = ref<HTMLElement | null>(null);
let swipeAt = 0;
const swipe = useSwipe(pagesView, {
  threshold: 1,
  onSwipeStart: () => { swipeAt = Date.now(); },
  onSwipeEnd: () => {
    const dx = -swipe.lengthX.value, dy = -swipe.lengthY.value;
    if (!ui.phone || dragging.active) return;
    if (Math.abs(dx) > 48 && Math.abs(dx) > Math.abs(dy) * 1.5 && Date.now() - swipeAt < 700) stepPage(dx < 0 ? 1 : -1);
  },
});

// The room for one page (stores/canvas.ts deviceStyle): the canvas less its padding, and its height less the toolbar
// and the page's head above the glass, so a large screen opens as large as fits without scrolling.
const canvasView = ref<HTMLElement | null>(null);
const { band } = useBandSelect(canvasView);
const canvasSize = useElementSize(canvasView);
watchEffect(() => {
  const width = canvasSize.width.value, height = canvasSize.height.value;
  // A phone fills its width with the page (stores/canvas.ts); a narrow page that is not a phone keeps the sizes above.
  canvas.room = width <= 0 || height <= 0 || (narrow.value && !ui.phone) ? null
    : ui.phone ? { width, height } : { width: width - 10, height: height - 110 };
});
onBeforeUnmount(() => { canvas.room = null; });
const zoomPercent = computed(() => `${Math.round(canvas.zoom * 100)}%`);
// The page to add at the end of the row, in pixels: on its proportions alone (aspect-ratio) it kept the size of a zoom
// after the zoom went back, while the pages beside it followed.
const ghostSize = computed(() => {
  const width = parseFloat(canvas.deviceStyle["--mockup-width"]), shape = doc.screenShape;
  return { width: `${width}px`, height: `${((width * shape.height) / shape.width).toFixed(2)}px` };
});
// A zoom keeps the part of the row that is in view: the row scrolls along with its pages, instead of standing on a page
// further along when they shrink.
watch(() => canvas.zoom, (zoom, before) => {
  const row = pagesView.value;
  if (!row || !before) return;
  const middle = (row.scrollLeft + row.clientWidth / 2) / before;
  nextTick(() => { row.scrollLeft = Math.max(0, middle * zoom - row.clientWidth / 2); });
});

const layout = computed(() => doc.layout!);
const entries = computed(() => dragging.preview || entriesOf(layout.value));
const pages = computed(() => pageCount(entries.value, layout.value.pages));
const shown = computed(() => pagesShown());
const canAdd = computed(() => pages.value < grid.pages);
const focused = computed(() => doc.document?.pages.findIndex((page) => page.id === doc.focusedPageId) ?? -1);
const positionsHint = computed(() => hasGaps(layout.value.tiles) && !scr.supports(0, 2, 26)
  ? t("editor.layout.positions_hint", { firmware: scr.currentScreen?.firmware || t("editor.common.unknown") })
  : "");
// Undo and redo say what they do ("Undo: Kitchen light moved to page 2"), and only their name when there is nothing to do.
const undoText = computed(() => doc.undoWhat ? t("editor.undo.undo", { what: doc.undoWhat }) : t("editor.common.undo"));
const redoText = computed(() => doc.redoWhat ? t("editor.undo.redo", { what: doc.redoWhat }) : t("editor.pages.redo"));
// Page buttons and swiping off: a page no Go to page tile reaches, or one without a way back.
const reachHint = computed(() => pageReachWarning());
// Everything the page used to explain in small (i) buttons beside the count, now behind one ? in the toolbar.
const tips: [IconName, string][] = [["pencil-outline", "change"], ["plus", "add"], ["drag", "move"], ["content-copy", "copy"], ["view-column-outline", "pages"], ["sitemap-outline", "map"], ["play", "preview"]];
// The keys of copy and paste as this computer writes them (editor/clipboard.ts).
const keys = { mod: modifierKey(), copy: shortcut("C"), paste: shortcut("V") };
// A band dragged from beside the tiles chooses the tiles it touches (composables/useBandSelect.ts), on the canvas above.
function onCanvasClick(e: MouseEvent) {
  // A click beside the pages closes the drawer; the cards and the bar handle their own clicks.
  if ((e.target as HTMLElement).closest(".device, .page-label, .page-head, .editor-toolbar, .map-node, .map-links, button, select, input")) return;
  if (insp.inspector) insp.closeInspector();
}
</script>

<template>
  <div ref="canvasView" class="canvas" id="canvas" @click="onCanvasClick">
    <div v-if="!doc.layout" class="notice" role="status">
      <Icon name="information-outline" />
      <span class="notice-text">{{ scr.currentScreen?.page_document?.format === 'legacy-v1' ? scr.currentScreen.page_document.migrationError : t('editor.pages.wait_grid') }}</span>
      <button v-if="scr.currentScreen?.page_document?.format === 'legacy-v1' && scr.currentScreen.source_grid" type="button" class="btn quiet mini" @click="doc.startFreshLayout">{{ t('editor.pages.start_fresh') }}</button>
    </div>
    <template v-else>
    <div v-if="!ui.phone" class="editor-toolbar">
      <div class="seg views" role="group" :aria-label="t('editor.pages.mode')">
        <button type="button" :aria-pressed="doc.editorMode === 'simple'" @click="doc.setEditorMode('simple')"><Icon name="view-column-outline" />{{ t('editor.pages.view_row') }}</button>
        <button type="button" :aria-pressed="doc.editorMode === 'advanced'" @click="doc.setEditorMode('advanced')"><Icon name="sitemap-outline" />{{ t('editor.pages.view_map') }}</button>
      </div>
      <div class="tool-group" role="group">
        <button type="button" id="undo" class="icon-btn" :disabled="!doc.undoCount" :aria-label="undoText" :title="`${undoText} · ⌘Z`" @click="doc.undo"><Icon name="undo" /></button>
        <button type="button" id="redo" class="icon-btn" :disabled="!doc.redoCount" :aria-label="redoText" :title="`${redoText} · ⇧⌘Z`" @click="doc.redo"><Icon name="redo" /></button>
      </div>
      <button type="button" class="btn quiet" :title="t('editor.pages.try_navigation')" @click="ui.previewOpen = true"><Icon name="play" />{{ t('editor.pages.preview') }}</button>
      <button type="button" id="toolbar-add-page" class="btn quiet" :disabled="!canAdd" :title="canAdd ? '' : t('editor.layout.max_pages', grid.pages)" @click="ui.pageWizardOpen = true"><Icon name="plus" />{{ t('editor.layout.add_page') }}</button>
      <span class="spacer"></span>
      <span id="count" class="toolbar-count">{{ t("editor.layout.count", { tiles: layout.tiles.length, limit: doc.tileLimit }, pages) }}</span>
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
              <span><b>{{ t(`editor.layout.help.${key}_label`) }}</b> {{ t(`editor.layout.help.${key}`, keys) }}</span>
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
      <button type="button" class="btn quiet mini" @click="doc.dismissMigrationNote">{{ t('editor.pages.dismiss_migration') }}</button>
    </div>
    <!-- Home Assistant ignores this screen's taps until it may perform actions (app 0.4.63, its own repair issue). -->
    <div v-if="scr.currentScreen?.actions_blocked" id="actions-blocked" class="notice warn" role="status">
      <Icon name="alert-circle-outline" /><span class="notice-text">{{ t('editor.pages.actions_blocked') }}</span>
      <!-- One click instead of Home Assistant's Configure dialog (app 0.4.73). -->
      <button type="button" class="btn primary mini" id="allow-actions" :disabled="Boolean(scr.allowing)" @click="scr.allowActions(scr.currentScreen)"><span v-if="scr.allowing === scr.currentScreen.id" class="spin small"></span>{{ t('editor.pages.allow_actions') }}</button>
    </div>
    <div v-if="scr.currentScreen?.page_capability === 'offline'" class="notice" role="status"><Icon name="information-outline" /><span class="notice-text">{{ t('editor.pages.offline_notice') }}</span></div>
    <div v-if="scr.currentScreen?.page_capability === 'update_screen'" class="notice" role="status">
      <Icon name="update" /><span class="notice-text">{{ t('editor.pages.update_notice') }}</span>
      <button v-if="scr.currentScreen?.online && scr.currentScreen.update?.profile" type="button" class="btn primary mini" @click="builds.startUpdate(scr.currentScreen)">{{ t('editor.screen_view.menu.update') }}</button>
    </div>
    <!-- Another tab of this browser changes this screen too (app 0.4.x): said before either saves. -->
    <div v-if="drafts.elsewhere" id="other-tab" class="notice choice" role="status">
      <Icon name="content-duplicate" /><span class="notice-text"><strong>{{ t('editor.tabs.elsewhere') }}</strong>{{ t('editor.tabs.elsewhere_hint') }}</span>
      <button type="button" id="keep-mine" class="btn quiet mini" @click="drafts.keepMine()">{{ t('editor.tabs.keep_mine') }}</button>
      <button type="button" id="take-over" class="btn primary mini" @click="drafts.takeOver()">{{ t('editor.tabs.take_over') }}</button>
    </div>
    <!-- Unsaved changes this browser kept when the page closed (app 0.4.x): the work comes back with one click. -->
    <div v-if="drafts.offer" id="kept-draft" class="notice choice" role="status">
      <Icon name="clock-outline" /><span class="notice-text"><strong>{{ drafts.offerText }}</strong>{{ t('editor.draft.kept_hint') }}</span>
      <button type="button" id="kept-discard" class="btn quiet mini" @click="drafts.discard()">{{ t('editor.draft.discard') }}</button>
      <button type="button" id="kept-restore" class="btn primary mini" @click="drafts.restore()">{{ t('editor.draft.restore') }}</button>
    </div>
    <div v-if="doc.conflict" class="notice warn" role="alert">
      <Icon name="alert-circle-outline" /><span class="notice-text">{{ t('editor.pages.conflict') }}</span>
      <button type="button" class="btn quiet mini" :disabled="doc.busy" @click="doc.resolveLayoutConflict('reload')">{{ t('editor.pages.reload_saved') }}</button>
      <button type="button" class="btn primary mini" :disabled="doc.busy" @click="doc.resolveLayoutConflict('keep')">{{ t('editor.pages.keep_mine') }}</button>
    </div>
    <div v-if="doc.gridChanged" class="notice warn" role="status"><Icon name="resize" /><span class="notice-text">{{ t('editor.pages.grid_changed') }}</span><button class="btn quiet mini" @click="doc.reviewScreenGrid">{{ t('editor.pages.grid_review') }}</button></div>
    <div v-if="positionsHint" id="positions-hint" class="notice warn" role="status"><Icon name="alert-circle-outline" /><span class="notice-text">{{ positionsHint }}</span></div>
    <div v-if="reachHint" id="page-reach-hint" class="notice warn" role="status"><Icon name="alert-circle-outline" /><span class="notice-text">{{ reachHint }}</span></div>
    <div v-if="!layout.tiles.length" id="no-tiles" class="notice" role="status"><Icon name="plus" /><span class="notice-text">{{ t("editor.layout.no_tiles") }}</span></div>
    <template v-if="mode === 'advanced' && focused >= 0">
      <button type="button" class="btn quiet back-map" @click="doc.focusedPageId = null"><Icon name="arrow-left" />{{ t('editor.pages.back_map') }}</button>
      <div class="pages focused-page"><DevicePage :page="focused" :entries="entries" :pages="pages" :moving="dragging.moving" map /></div>
    </template>
    <PageMap v-else-if="mode === 'advanced'" :key="String(narrow)" :compact="narrow" />
    <div v-else ref="pagesView" class="pages" id="layout-preview" :aria-label="t('editor.layout.aria')">
      <div v-if="narrow && !ui.phone" class="page-pills" role="group" :aria-label="t('editor.pages.choose_page')">
        <button v-for="(page, index) in doc.document!.pages" :key="page.id" type="button" :aria-pressed="doc.selectedPageId === page.id ? 'true' : 'false'"
          @click="doc.selectedPageId = page.id"><b>{{ index + 1 }}</b> {{ titleOf(doc.document!, page) }}</button>
      </div>
      <DevicePage v-for="page in simplePages" :key="doc.document?.pages[page - 1]?.id || page" :page="page - 1" :entries="entries" :pages="pages" :moving="dragging.moving" />
      <div v-if="ui.phone && doc.document" class="phone-pager">
        <button type="button" class="phone-page-name" id="phone-pages" @click="ui.pagesSheet = true">
          {{ pageTitleShown(selectedIndex) || t("editor.page.label", { page: selectedIndex + 1 }) }}
          <small>{{ t("editor.phone.page_of", { n: selectedIndex + 1, total: doc.document.pages.length }) }}</small><Icon name="chevron-down" />
        </button>
        <span v-if="doc.document.pages.length > 1" class="phone-dots" aria-hidden="true">
          <i v-for="(page, index) in doc.document.pages" :key="page.id" :class="{ on: index === selectedIndex }"></i>
        </span>
        <p class="phone-hint">{{ t(doc.document.pages.length > 1 ? "editor.phone.hint_pages" : "editor.phone.hint") }}</p>
      </div>
      <div v-if="!narrow" class="page ghost" :style="{ ...canvas.deviceStyle, flexBasis: ghostSize.width }" :class="{ disabled: !canAdd }">
        <div class="page-head"><span class="page-name muted">{{ t("editor.page.label", { page: shown + 1 }) }}</span></div>
        <div class="device" :class="{ compact: canvas.isCompact }" :style="{ ...canvas.deviceStyle, ...ghostSize, aspectRatio: 'auto' }" id="add-page" role="button" :tabindex="canAdd ? 0 : -1" @click="canAdd && (ui.pageWizardOpen = true)" @keydown.enter.prevent="canAdd && (ui.pageWizardOpen = true)">
          <span class="ghost-plus"><Icon name="plus" /></span>
          <span>{{ canAdd ? t("editor.layout.add_page") : t("editor.layout.max_pages", grid.pages) }}</span>
        </div>
      </div>
    </div>
    <!-- The size of the pages (stores/canvas.ts zoom): out of the toolbar, in the corner, as on a map. -->
    <div v-if="!ui.phone && mode === 'simple'" class="zoom-dock"><div class="zoom-pill" role="group" :aria-label="t('editor.pages.zoom')">
      <button type="button" class="icon-btn" id="zoom-out" :aria-label="t('editor.pages.zoom_out')" :disabled="canvas.zoom <= 0.5" @click="canvas.zoomBy(-1)"><Icon name="magnify-minus-outline" /></button>
      <button type="button" class="zoom-value" id="zoom-reset" :title="t('editor.pages.zoom_reset')" @click="canvas.zoom = 1">{{ zoomPercent }}</button>
      <button type="button" class="icon-btn" id="zoom-in" :aria-label="t('editor.pages.zoom_in')" :disabled="canvas.zoom >= 2" @click="canvas.zoomBy(1)"><Icon name="magnify-plus-outline" /></button>
    </div></div>
    </template>
  </div>
  <Teleport to="body"><div v-if="band" class="select-band" :style="{ left: `${band.left}px`, top: `${band.top}px`, width: `${band.width}px`, height: `${band.height}px` }"></div></Teleport>
  <Library v-if="doc.layout" />
  <GrowTip v-if="!ui.previewOpen" />
  <NavigationPreview v-if="ui.previewOpen && doc.document" :key="scr.selected || ''" @close="ui.previewOpen = false" />
  <PageWizard v-if="ui.pageWizardOpen" :key="scr.selected || ''" @close="ui.pageWizardOpen = false" />
  <PhonePages v-if="ui.phone && ui.pagesSheet && doc.document" @add="ui.pagesSheet = false; ui.pageWizardOpen = true" />
  <GridReview v-if="doc.gridReview" />
</template>

<style scoped>
.select-band { position: fixed; z-index: 40; pointer-events: none; border: 1px solid var(--accent); background: color-mix(in srgb, var(--accent) 12%, transparent); border-radius: 3px; }
.focused-page { padding: 18px 0; justify-content: center; }
.back-map { align-self: flex-start; }
.page-pills { display: flex; gap: 6px; overflow-x: auto; width: 100%; padding-bottom: 4px; }
.page-pills button { flex: none; display: inline-flex; gap: 6px; align-items: center; padding: 6px 12px; border-radius: 999px; border: 1px solid var(--line); background: var(--surface); color: var(--ink-2); font-size: 12.5px; white-space: nowrap; }
.page-pills button b { font-weight: 650; color: var(--muted); }
.page-pills button[aria-pressed="true"] { background: var(--ink); border-color: var(--ink); color: var(--surface); }
.page-pills button[aria-pressed="true"] b { color: inherit; opacity: .7; }
/* No room of its own in the column: it stands over the corner of the pages, at the foot of what is in view. */
.zoom-dock { position: sticky; bottom: 0; align-self: flex-end; margin-top: auto; height: 0; z-index: 2; }
.zoom-pill { position: absolute; right: 0; bottom: 0; display: flex; align-items: center; gap: 2px; padding: 3px; border-radius: 999px; background: var(--surface); border: 1px solid var(--line); box-shadow: 0 2px 8px rgba(20, 24, 40, 0.08); }
.zoom-pill .icon-btn { width: 28px; height: 28px; border-radius: 50%; }
.zoom-value { min-width: 46px; height: 28px; border: 0; border-radius: 999px; background: transparent; color: var(--ink-2); font-size: 12px; font-variant-numeric: tabular-nums; cursor: pointer; }
.zoom-value:hover { background: var(--seg); }
@media (max-width: 700px) { #layout-preview { flex-direction: column; align-items: center; overflow: visible; } }
</style>
