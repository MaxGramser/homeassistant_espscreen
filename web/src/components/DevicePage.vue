<script setup lang="ts">
import { editorLayout } from "../store";
const { cellsOf, grid, pageOf, spanOf } = editorLayout;

// One page of the screen as the mockup draws it: the top bar and the screen's own grid of cells.
import { computed, nextTick, onBeforeUnmount } from "vue";
import { vDrag } from "../drag";
import { t } from "../i18n";
import { sizeOf } from "../model/layout";
import { closeInspector, deviceStyle, homeKeyShown, isCompact, movePage, navigationSettings, openBar, openPage, pageAt, pageReady, pageTitleShown, phone, previewed, roomyNames, screenText, setHomePage, state, topbarItems } from "../store";
import type { Tile } from "../types";
import TileCard from "./TileCard.vue";
import TopbarSvg from "./TopbarSvg.vue";
import PageNavigation from './PageNavigation.vue';
import PageMenu from './PageMenu.vue';
import Icon from './ui/Icon.vue';
import type { NavigationIntent } from '../model/pages';

const props = defineProps<{ page: number; entries: { tile: Tile; slot: number }[]; pages: number; moving: Tile | null; map?: boolean; preview?: boolean; canGoBack?: boolean }>();
const emit = defineEmits<{ navigate: [intent: NavigationIntent] }>();
const owned = computed(() => pageAt(props.page));
// A click on the page itself opens its settings: its head ("Page 3"), the room around the tiles and its dots. A tile, an
// empty cell, the screen's top bar and the menus keep their own click (app 0.4.32).
function pageClick(event: MouseEvent) {
  if (props.preview || !owned.value) return;
  const target = event.target as HTMLElement;
  if (target.closest(".tile, .cell, .bar-wrap, .home-chip, a, input, [role='menu'], [role='menuitem'], button:not(.grab)")) return;
  openPage(owned.value.id);
}
const isHome = computed(() => owned.value?.id === state.document?.homePageId);
const backInHeader = computed(() => !navigationSettings().pageButtons && Boolean(owned.value?.navigation.excludeFromPagination));
const bySlot = computed(() => new Map(props.entries.map((e) => [e.slot, e])));
const covered = computed(() => new Set(props.entries.flatMap((e) => cellsOf(e.slot, sizeOf(e.tile)).slice(1))));
const cells = computed(() => Array.from({ length: grid.slots }, (_, cell) => props.page * grid.slots + cell).filter((slot) => !covered.value.has(slot)));
const barSelected = computed(() => state.barPage === props.page && (state.inspector?.kind === "bar" || state.inspector?.kind === "bar-add"));
const filled = computed(() => props.entries.filter((e) => pageOf(e.slot) === props.page).reduce((n, e) => n + spanOf(sizeOf(e.tile)), 0));
const cellStyle = (slot: number) => ({ gridColumn: slot % grid.columns + 1, gridRow: Math.floor(slot % grid.slots / grid.columns) + 1 });
function pickCell(slot: number) {
  state.selectedPageId = owned.value?.id || state.selectedPageId;
  const marked = state.insertAt === slot && !phone.value;
  state.insertAt = marked ? -1 : slot;
  // On a phone the empty cell opens the sheet to add a tile there (app 0.4.40), without a keyboard over the list.
  if (state.insertAt >= 0 && phone.value) { closeInspector(); state.addSheet = true; }
  else if (state.insertAt >= 0) document.querySelector<HTMLInputElement>("#search")?.focus();
}
// A whole page moves by its label (app 0.2.121) and leaves by the button beside its cell count (app 0.2.123). One
// page has nowhere to go and cannot leave either, and the page a tile can start behind the last one isn't a page yet.
const movable = computed(() => !props.preview && !props.map && props.pages > 1 && props.page < props.pages);
let cancelHome = () => {};
onBeforeUnmount(() => cancelHome());
function dragHome(event: PointerEvent) {
  if (!isHome.value || !pageReady.value || event.button !== 0) return;
  cancelHome();
  const start = { x: event.clientX, y: event.clientY };
  const finish = (end: PointerEvent) => {
    window.removeEventListener('pointerup', finish); window.removeEventListener('pointercancel', cancel);
    if (Math.hypot(end.clientX - start.x, end.clientY - start.y) < 8) return;
    const id = document.elementFromPoint(end.clientX, end.clientY)?.closest<HTMLElement>('[data-page-id]')?.dataset.pageId;
    if (id) setHomePage(id);
  };
  const cancel = () => { window.removeEventListener('pointerup', finish); window.removeEventListener('pointercancel', cancel); };
  cancelHome = cancel;
  window.addEventListener('pointerup', finish); window.addEventListener('pointercancel', cancel);
}
// This is the page being carried, drawn in the place it would land.
const carried = computed(() => state.drag.page?.to === props.page);
// Left and right move the page a place along, for a finger on a phone and for anyone who can't drag.
async function onKey(e: KeyboardEvent) {
  const step = ({ ArrowLeft: -1, ArrowRight: 1 } as Record<string, number>)[e.key];
  if (!step) return;
  e.preventDefault();
  const to = props.page + step;
  if (movePage(props.page, to)) {
    await nextTick();
    document.querySelector<HTMLElement>(`.pages [data-page="${to}"]`)?.focus();
  }
}
</script>

<template>
  <div class="page" :class="{ carried, refused: state.drag.refused === page, chosen: !preview && !!owned && state.selectedPageId === owned.id && state.inspector?.kind === 'page' }" :style="deviceStyle" :data-page-id="owned?.id" @click="pageClick">
    <div v-if="!preview" class="page-head" :class="{ selected: state.selectedPageId === owned?.id && state.inspector?.kind === 'page' }">
      <button v-if="movable" type="button" class="grab" :data-page="page" v-drag="{ kind: 'page', page }"
        :title="t('editor.page.move_title')" :aria-label="t('editor.page.move_aria', { page: page + 1 })" @keydown="onKey">
        <Icon name="drag-vertical" class="grip" />{{ t("editor.page.label", { page: page + 1 }) }}
      </button>
      <slot v-else name="handle"><span class="page-name">{{ t("editor.page.label", { page: page + 1 }) }}</span></slot>
      <span v-if="owned" class="page-title" :title="pageTitleShown(page)">{{ pageTitleShown(page) }}</span>
      <span v-if="isHome" class="home-chip" :class="{ movable: pageReady }" role="img" :aria-label="t('editor.pages.drag_home')" :title="t('editor.pages.drag_home')"
        @pointerdown.stop="dragHome"><Icon name="home" />{{ t('editor.pages.home_chip') }}</span>
      <span v-if="owned?.navigation.excludeFromPagination" class="detail-chip" :title="t('editor.pages.include_navigation_hint')"><Icon name="link-variant" />{{ t('editor.pages.detail_chip') }}</span>
      <span class="page-side">
        <span class="page-count" :title="t('editor.pages.cells_used')">{{ filled }}/{{ grid.slots }}</span>
        <slot name="actions" />
        <PageMenu v-if="owned" :id="owned.id" />
      </span>
    </div>
    <div class="device" :class="{ compact: isCompact, roomy: roomyNames }">
      <div class="bar-wrap" :class="{ selected: !preview && barSelected }" :title="preview ? undefined : t('editor.page.edit_bar')" :role="preview ? undefined : 'button'" :tabindex="preview ? undefined : 0"
        @click="!preview && openBar(0, page)" @keydown.enter.prevent="!preview && openBar(0, page)">
        <TopbarSvg :items="topbarItems(page)" :name-text="pageTitleShown(page)" :home="homeKeyShown(page)" :back="backInHeader" />
        <button v-if="preview && (backInHeader || homeKeyShown(page))" type="button" class="preview-home" :aria-label="backInHeader ? screenText('screen.navigation.back') : t('editor.pages.go_home')" @click.stop="emit('navigate', { kind: backInHeader ? 'back' : 'home' })"></button>
      </div>
      <div class="tiles">
        <template v-for="slot in cells" :key="slot">
          <TileCard v-if="bySlot.get(slot)" :tile="preview ? bySlot.get(slot)!.tile : previewed(bySlot.get(slot)!.tile)" :slot="slot" :placeholder="bySlot.get(slot)!.tile === moving" :preview="preview" @navigate="emit('navigate', { kind: 'tile', tileId: $event })" />
          <span v-else-if="preview" class="cell preview-empty" :style="cellStyle(slot)"></span>
          <button v-else type="button" class="cell" :style="cellStyle(slot)" :class="{ 'insert-here': state.insertAt === slot }" :data-slot="slot"
            :title="t('editor.page.cell.title')"
            :aria-label="t('editor.page.cell.aria', { slot: (slot % grid.slots) + 1, page: page + 1 })" @click="pickCell(slot)">
            <span>+</span><small>{{ state.insertAt === slot ? t("editor.page.cell.next") : t("editor.page.cell.empty") }}</small>
          </button>
        </template>
      </div>
      <PageNavigation v-if="owned" :page-id="owned.id" :interactive="preview" :can-go-back="canGoBack" @navigate="emit('navigate', { kind: $event })" />
    </div>
  </div>
</template>

<style scoped>
.page { min-width: 0; }
/* The page in the glass's proportions (store deviceStyle, app 0.4.74): the top bar from the top edge of the glass down
   to where the tiles start, the grid's margins and gaps, and the page bar at its own height, so every card is as high
   against its page as the screen draws it. */
.device { padding: 0 var(--frame-side, 10px) var(--frame-bottom, 10px); gap: 0; grid-template-rows: var(--frame-top, 48px) minmax(0, 1fr); }
.device:has(.page-navigation) { grid-template-rows: var(--frame-top, 48px) minmax(0, 1fr) var(--frame-bar, 32px); }
.tiles { gap: var(--frame-gap-y, 8px) var(--frame-gap-x, 8px); }
.bar-wrap { position: relative; min-height: 0; }
.preview-home { position: absolute; inset: 0 auto 0 0; width: 30px; border: 0; background: transparent; }
.preview-empty { visibility: hidden; }
</style>
