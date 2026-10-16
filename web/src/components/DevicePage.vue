<script setup lang="ts">

// One page of the screen as the mockup draws it: the top bar and the screen's own grid of cells.
import { useEventListener } from "@vueuse/core";
import { computed, nextTick, ref, shallowRef } from "vue";
import { useGesture } from "../composables/useGesture";
import { vDrag } from "../drag";
import { t } from "../i18n";
import { sizeOf } from "../model/layout";
import type { Tile } from "../types";
import TileCard from "./TileCard.vue";
import TopbarSvg from "./TopbarSvg.vue";
import PageNavigation from './PageNavigation.vue';
import PageMenu from './PageMenu.vue';
import PageMenuItems from './PageMenuItems.vue';
import UiContextMenu from './ui/UiContextMenu.vue';
import UiMenuItem from './ui/UiMenuItem.vue';
import UiMenuSeparator from './ui/UiMenuSeparator.vue';
import TileMenuItems from './TileMenuItems.vue';
import Icon from './ui/Icon.vue';
import type { NavigationIntent } from '../model/pages';
import { useUiStore } from "../stores/ui";
import { useRegionStore } from "../stores/region";
import { useSettingsStore } from "../stores/settings";
import { useScreenStore } from "../stores/screen";
import { useTopbarStore } from "../stores/topbar";
import { useDragStore } from "../stores/drag";
import { useCanvasStore } from "../stores/canvas";
import { copiedTiles, copyChosen, cutChosen, pasteCopied, removeTiles, shortcut } from "../editor/clipboard";
import { movePage, pageTitleShown, setHomePage } from "../editor/pages";
import { useDocumentStore } from "../stores/document";
import { useInspectorStore } from "../stores/inspector";

const ui = useUiStore();
const region = useRegionStore();
const settings = useSettingsStore();
const scr = useScreenStore();
const topbar = useTopbarStore();
const dragging = useDragStore();
const canvas = useCanvasStore();
const doc = useDocumentStore();
const insp = useInspectorStore();
const { cellsOf, grid, pageOf, spanOf } = doc.editorLayout;

const props = defineProps<{ page: number; entries: { tile: Tile; slot: number }[]; pages: number; moving: Tile | null; map?: boolean; preview?: boolean; canGoBack?: boolean }>();
const emit = defineEmits<{ navigate: [intent: NavigationIntent] }>();
const owned = computed(() => doc.pageAt(props.page));
// A click on the page itself opens its settings: its head ("Page 3"), the room around the tiles and its dots. A tile, an
// empty cell, the screen's top bar and the menus keep their own click (app 0.4.32).
function pageClick(event: MouseEvent) {
  if (props.preview || !owned.value) return;
  const target = event.target as HTMLElement;
  if (target.closest(".tile, .cell, .bar-wrap, .home-chip, a, input, [role='menu'], [role='menuitem'], button:not(.grab)")) return;
  insp.openPage(owned.value.id);
}
const isHome = computed(() => owned.value?.id === doc.document?.homePageId);
const backInHeader = computed(() => !settings.navigationSettings().pageButtons && Boolean(owned.value?.navigation.excludeFromPagination));
const bySlot = computed(() => new Map(props.entries.map((e) => [e.slot, e])));
const covered = computed(() => new Set(props.entries.flatMap((e) => cellsOf(e.slot, sizeOf(e.tile)).slice(1))));
const cells = computed(() => Array.from({ length: grid.slots }, (_, cell) => props.page * grid.slots + cell).filter((slot) => !covered.value.has(slot)));
const barSelected = computed(() => doc.barPage === props.page && (insp.inspector?.kind === "bar" || insp.inspector?.kind === "bar-add"));
const filled = computed(() => props.entries.filter((e) => pageOf(e.slot) === props.page).reduce((n, e) => n + spanOf(sizeOf(e.tile)), 0));
const cellStyle = (slot: number) => ({ gridColumn: slot % grid.columns + 1, gridRow: Math.floor(slot % grid.slots / grid.columns) + 1 });
function pickCell(slot: number) {
  doc.selectedPageId = owned.value?.id || doc.selectedPageId;
  const marked = insp.insertAt === slot && !ui.phone;
  insp.insert = marked ? null : { kind: "cell", slot };
  // On a phone the empty cell opens the sheet to add a tile there (app 0.4.40), without a keyboard over the list.
  if (insp.insertAt >= 0 && ui.phone) { insp.closeInspector(); ui.addSheet = true; }
  else if (insp.insertAt >= 0) document.querySelector<HTMLInputElement>("#search")?.focus();
}
// The right mouse button on the page (docs/PAGES.md, "Menus"): one menu for the whole page, with the items of what is
// under the pointer. A tile gets its own, the ones behind its inspector's ···, and is chosen first, as a file manager
// does: one of the tiles chosen together keeps them all and gets what goes for all of them. An empty cell offers to be
// filled, from the library or with what was copied; it shows as marked while its menu is open and is marked only by
// what is chosen there, since a marked cell opens the library's search (Library.vue), which would take the menu's
// focus. Anywhere else the page gets its own menu, its ···, and its settings open.
type MenuFor = { kind: "tile"; tile: Tile; several: boolean } | { kind: "cell"; slot: number } | { kind: "page" };
const menuFor = shallowRef<MenuFor>({ kind: "page" });
function aim(e: MouseEvent) {
  const under = e.target as HTMLElement;
  const card = under.closest<HTMLElement>("[data-tile-id]:not(.placeholder)");
  const tile = card ? doc.layout?.tiles.find((item) => item.id === card.dataset.tileId) : undefined;
  const cell = under.closest<HTMLElement>(".cell[data-slot]");
  menuFor.value = tile ? { kind: "tile", tile, several: insp.isPicked(tile) && insp.chosenTiles.length > 1 }
    : cell ? { kind: "cell", slot: Number(cell.dataset.slot) } : { kind: "page" };
}
function menuOpened(open: boolean) {
  const aimed = menuFor.value;
  if (!open || !owned.value) return;
  if (aimed.kind === "tile" && !aimed.several && !doc.isSelected(aimed.tile)) insp.openTile(aimed.tile);
  else if (aimed.kind === "page") insp.openPage(owned.value.id);
}
const menuOpen = ref(false);
const menuCell = computed(() => (menuOpen.value && menuFor.value.kind === "cell" ? menuFor.value.slot : -1));
function markCell(slot: number) {
  doc.selectedPageId = owned.value?.id || doc.selectedPageId;
  insp.insert = { kind: "cell", slot };
}
function addHere(slot: number) {
  markCell(slot);
  if (ui.phone) { insp.closeInspector(); ui.addSheet = true; }
}
function pasteHere(slot: number) { markCell(slot); void pasteCopied(); }
// A whole page moves by its label (app 0.2.121) and leaves by the button beside its cell count (app 0.2.123). One
// page has nowhere to go and cannot leave either, and the page a tile can start behind the last one isn't a page yet.
const movable = computed(() => !props.preview && !props.map && props.pages > 1 && props.page < props.pages);
// The home mark carried to another page: where the pointer is let go names the new home page.
const homeDrag = useGesture();
function dragHome(event: PointerEvent) {
  if (!isHome.value || !scr.pageReady || event.button !== 0) return;
  const start = { x: event.clientX, y: event.clientY };
  homeDrag.begin(() => {
    useEventListener(window, 'pointerup', (end: PointerEvent) => {
      homeDrag.end();
      if (Math.hypot(end.clientX - start.x, end.clientY - start.y) < 8) return;
      const id = document.elementFromPoint(end.clientX, end.clientY)?.closest<HTMLElement>('[data-page-id]')?.dataset.pageId;
      if (id) setHomePage(id);
    });
    useEventListener(window, 'pointercancel', () => homeDrag.end());
  });
}
// This is the page being carried, drawn in the place it would land.
const carried = computed(() => dragging.page?.to === props.page);
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
  <UiContextMenu v-model:open="menuOpen" width="248px" :disabled="preview || !owned" @update:open="menuOpened">
  <div class="page" :class="{ carried, refused: dragging.refused === page, chosen: !preview && !!owned && doc.selectedPageId === owned.id && insp.inspector?.kind === 'page' }" :style="canvas.deviceStyle" :data-page-id="owned?.id" @click="pageClick" @contextmenu="aim">
    <div v-if="!preview" class="page-head" :class="{ selected: doc.selectedPageId === owned?.id && insp.inspector?.kind === 'page' }">
      <button v-if="movable" type="button" class="grab" :data-page="page" v-drag="{ kind: 'page', page }"
        :title="t('editor.page.move_title')" :aria-label="t('editor.page.move_aria', { page: page + 1 })" @keydown="onKey">
        <Icon name="drag-vertical" class="grip" />{{ t("editor.page.label", { page: page + 1 }) }}
      </button>
      <slot v-else name="handle"><span class="page-name">{{ t("editor.page.label", { page: page + 1 }) }}</span></slot>
      <span v-if="owned" class="page-title" :title="pageTitleShown(page)" @dblclick.stop="insp.renamePage(owned.id)">{{ pageTitleShown(page) }}</span>
      <span v-if="isHome" class="home-chip" :class="{ movable: scr.pageReady }" role="img" :aria-label="t('editor.pages.drag_home')" :title="t('editor.pages.drag_home')"
        @pointerdown.stop="dragHome"><Icon name="home" />{{ t('editor.pages.home_chip') }}</span>
      <span v-if="owned?.navigation.excludeFromPagination" class="detail-chip" :title="t('editor.pages.include_navigation_hint')"><Icon name="link-variant" />{{ t('editor.pages.detail_chip') }}</span>
      <span class="page-side">
        <span class="page-count" :title="t('editor.pages.cells_used')">{{ filled }}/{{ grid.slots }}</span>
        <slot name="actions" />
        <PageMenu v-if="owned" :id="owned.id" />
      </span>
    </div>
    <div class="device" :class="{ compact: canvas.isCompact, roomy: canvas.roomyNames }">
      <div class="bar-wrap" :class="{ selected: !preview && barSelected }" :title="preview ? undefined : t('editor.page.edit_bar')" :role="preview ? undefined : 'button'" :tabindex="preview ? undefined : 0"
        @click="!preview && insp.openBar(0, page)" @keydown.enter.prevent="!preview && insp.openBar(0, page)">
        <TopbarSvg :items="topbar.topbarItems(page)" :name-text="pageTitleShown(page)" :home="topbar.homeKeyShown(page)" :back="backInHeader" />
        <button v-if="preview && (backInHeader || topbar.homeKeyShown(page))" type="button" class="preview-home" :aria-label="backInHeader ? region.screenText('screen.navigation.back') : t('editor.pages.go_home')" @click.stop="emit('navigate', { kind: backInHeader ? 'back' : 'home' })"></button>
      </div>
      <div class="tiles">
        <template v-for="slot in cells" :key="slot">
          <TileCard v-if="bySlot.get(slot)" :tile="preview ? bySlot.get(slot)!.tile : insp.previewed(bySlot.get(slot)!.tile)" :slot="slot" :placeholder="bySlot.get(slot)!.tile === moving" :preview="preview" @navigate="emit('navigate', { kind: 'tile', tileId: $event })" />
          <span v-else-if="preview" class="cell preview-empty" :style="cellStyle(slot)"></span>
          <button v-else type="button" class="cell" :style="cellStyle(slot)" :class="{ 'insert-here': insp.insertAt === slot || menuCell === slot }" :data-slot="slot"
            :title="t('editor.page.cell.title')"
            :aria-label="t('editor.page.cell.aria', { slot: (slot % grid.slots) + 1, page: page + 1 })" @click="pickCell(slot)">
            <span>+</span><small>{{ insp.insertAt === slot ? t("editor.page.cell.next") : t("editor.page.cell.empty") }}</small>
          </button>
        </template>
      </div>
      <PageNavigation v-if="owned" :page-id="owned.id" :interactive="preview" :can-go-back="canGoBack" @navigate="emit('navigate', { kind: $event })" />
    </div>
  </div>
  <template #menu>
    <template v-if="menuFor.kind === 'tile' && menuFor.several">
      <UiMenuItem class="tiles-copy" icon="content-copy" :hint="shortcut('C')" @select="copyChosen">{{ t("editor.selection.copy") }}</UiMenuItem>
      <UiMenuItem class="tiles-cut" icon="content-cut" :hint="shortcut('X')" @select="cutChosen">{{ t("editor.menu.cut") }}</UiMenuItem>
      <UiMenuSeparator />
      <UiMenuItem class="tiles-remove" icon="delete-outline" danger hint="⌫" @select="removeTiles(insp.chosenTiles)">{{ t("editor.selection.remove", { n: insp.chosenTiles.length }, insp.chosenTiles.length) }}</UiMenuItem>
    </template>
    <TileMenuItems v-else-if="menuFor.kind === 'tile'" :tile="menuFor.tile" />
    <template v-else-if="menuFor.kind === 'cell'">
      <UiMenuItem class="cell-add" icon="plus" @select="addHere(menuFor.slot)">{{ t("editor.menu.add_here") }}</UiMenuItem>
      <UiMenuItem class="cell-paste" icon="content-paste" :hint="shortcut('V')" :disabled="!copiedTiles()" @select="pasteHere(menuFor.slot)">{{ t("editor.menu.paste_here") }}</UiMenuItem>
    </template>
    <PageMenuItems v-else-if="owned" :id="owned.id" />
  </template>
  </UiContextMenu>
</template>

<style scoped>
.page { min-width: 0; }
/* The page in the glass's proportions (stores/canvas.ts deviceStyle, app 0.4.74): the top bar from the top edge of the glass down
   to where the tiles start, the grid's margins and gaps, and the page bar at its own height, so every card is as high
   against its page as the screen draws it. */
.device { padding: 0 var(--frame-side, 10px) var(--frame-bottom, 10px); gap: 0; grid-template-rows: var(--frame-top, 48px) minmax(0, 1fr); }
.device:has(.page-navigation) { grid-template-rows: var(--frame-top, 48px) minmax(0, 1fr) var(--frame-bar, 32px); }
.tiles { gap: var(--frame-gap-y, 8px) var(--frame-gap-x, 8px); }
.bar-wrap { position: relative; min-height: 0; }
.preview-home { position: absolute; inset: 0 auto 0 0; width: 30px; border: 0; background: transparent; }
.preview-empty { visibility: hidden; }
</style>
