<script setup lang="ts">
// The entities a tile can show, in a drawer along the bottom of the pages (app 0.4.32): the inspector keeps the right
// side to itself. Folded it is one bar with the search. Typing anywhere on the page starts a search there and opens
// the drawer; the arrow keys walk the results and Enter adds the one in focus. Open, the rooms and the kinds of
// entity stand in a column on the left and the entities beside them, grouped by room until a search ranks them.
// Its top edge drags it taller or lower, and both are remembered.
// A click adds the entity to the marked empty cell or the first free one; a drag puts it exactly where it lands.
// Two views of the same results (docs/PAGES.md "The library"): Tiles, the default, draws every entity as the tiles it can
// be at its sizes (LibraryShelf.vue), List the rows it always had. A room's extras (Home Assistant's settings, diagnosis
// and hidden entities) stand folded under the rest in both.
import { useElementSize, useEventListener, useInfiniteScroll, useTimeoutFn } from "@vueuse/core";
import { computed, nextTick, ref, watch } from "vue";
import { vDrag } from "../drag";
import { t } from "../i18n";
import { domainInfo } from "../model/layout";
import { glyph } from "../model/topbar";
import { isExtra, entryDetail, entryTone as tone, kindCounts, libraryBase, libraryGroups, libraryMatches, libraryWindow, markOf, roomCounts, ROWS_AT_ONCE, shortName as short, tileCounts,
  type Entry, type LibraryFilter } from "../model/library";
import { tilePalette } from "../model/tile-palette";
import { usePreference } from "../composables/usePreference";
import { useResizeHandle } from "../composables/useResizeHandle";
import { useListNavigation } from "../composables/useListNavigation";
import { isEditableTarget } from "../composables/isEditableTarget";
import { question } from "../composables/useConfirm";
import Icon from "./ui/Icon.vue";
import LibraryShelf from "./LibraryShelf.vue";
import UiSegmented from "./ui/UiSegmented.vue";
import { cardContent, cardHeight, frameOf } from "../model/ui-scale";
import { useCanvasStore } from "../stores/canvas";
import UiSwitch from "./ui/UiSwitch.vue";
import { useUiStore } from "../stores/ui";
import { useEntitiesStore } from "../stores/entities";
import { usePluginsStore } from "../stores/plugins";
import { useScreenStore } from "../stores/screen";
import { useInventoryStore } from "../stores/inventory";
import { addTile } from "../editor/tiles";
import { addSection, sectionsOffered } from "../editor/sections";
import { pageTitleShown } from "../editor/pages";
import { useDocumentStore } from "../stores/document";
import { useInspectorStore } from "../stores/inspector";

const ui = useUiStore();
const entities = useEntitiesStore();
const plugins = usePluginsStore();
const scr = useScreenStore();
const inv = useInventoryStore();
const doc = useDocumentStore();
const insp = useInspectorStore();
const canvas = useCanvasStore();

// Open: on a wider page the drawer along the bottom, remembered; on a phone (app 0.4.40) a sheet that opens for a tile
// and goes once it is added, closed or swiped away. Closing it there forgets the cell it was opened for.
const open = computed({
  get: () => ui.phone ? ui.addSheet : ui.libraryOpen,
  set: (value: boolean) => {
    if (!ui.phone) { ui.libraryOpen = value; return; }
    ui.addSheet = value;
    if (!value) { insp.forgetCell(); ui.search = ""; }
  },
});
// Where the tile goes, said at the top of the phone's sheet.
const destination = computed(() => {
  const pages = doc.document?.pages || [];
  const page = insp.insertAt >= 0 ? Math.floor(insp.insertAt / doc.editorLayout.grid.slots) : Math.max(0, pages.findIndex((item) => item.id === doc.selectedPageId));
  // The page's number always: its title alone is often the screen's name, and reads as the whole screen.
  const number = t("editor.page.label", { page: page + 1 }), title = pageTitleShown(page);
  const name = title && title !== number ? `${number} · ${title}` : number;
  return insp.insertAt >= 0 ? t("editor.phone.add_to_cell", { cell: insp.insertAt % doc.editorLayout.grid.slots + 1, page: name }) : t("editor.phone.add_to_page", { page: name });
});
// How many tiles each entity has on the screen. One that is there stays addable when the firmware takes an entity on
// several tiles (a page tile from 0.2.65, any entity but the bedside clock from 0.16.0): its mark says how often.
const chosen = computed(() => tileCounts(doc.layout?.tiles || []));
const onScreen = (id: string) => chosen.value.has(id);
const placed = (id: string) => onScreen(id) && !scr.repeatable(id);
const mark = (id: string) => markOf(id, chosen.value);
// A plugin's tile type (design): listed under Plugins, only for a screen that runs that plugin.
const pluginEntries = computed<(Entry & { plugin: string })[]>(() => (plugins.pluginsEnabled ? plugins.tilesOn(scr.currentScreen) : []));
const pluginOf = (id: string) => pluginEntries.value.find((e) => e.id === id)?.plugin || "";
// Go to page tiles for the pages there are and the next one, at least the eight every screen has and at most what this
// screen takes: a board with 24 pages (firmware 0.34.0+) would otherwise list 24 of them.
// A section is added from here too (docs/PAGES.md "Sections"): on a screen that draws them, at the marked empty cell
// (one outside a section; a section never holds another) or on the chosen page's first free cells, so a tile or a
// section is one choice in one place. A search finds it by its name.
const sectionOffered = computed(() => {
  if (!sectionsOffered() || ui.filter || ui.room) return false;
  const query = ui.search.trim().toLowerCase();
  if (query && ![t("editor.sections.add"), t("editor.sections.untitled")].some((word) => word.toLowerCase().includes(query))) return false;
  const grid = doc.editorLayout.grid, slot = insp.insertAt;
  if (slot < 0) return true;
  const page = Math.floor(slot / grid.slots), local = slot % grid.slots, row = Math.floor(local / grid.columns), column = local % grid.columns;
  return !(doc.layout?.sections ?? []).some((b) => b.page === page && column >= b.column && column < b.column + b.columns && row >= b.row && row < b.row + b.rows);
});
function addSectionHere() {
  const pages = doc.document?.pages || [], slot = insp.insertAt;
  const page = slot >= 0 ? Math.floor(slot / doc.editorLayout.grid.slots) : Math.max(0, pages.findIndex((item) => item.id === doc.selectedPageId));
  if (addSection(page, slot) && ui.phone) open.value = false;
}
const pagesOffered = computed(() => Math.min(doc.editorLayout.grid.pages, Math.max(8, (doc.document?.pages.length || 0) + 1)));
const query = computed(() => ui.search.trim().toLocaleLowerCase());
// What the search and the hide switch leave over (model/library.ts). The picker offers what a tile can show; camera and
// image tiles need a board that draws pictures (app 0.2.66).
const entries = computed(() => [...pluginEntries.value, ...(inv.inventory.builtin || []), ...inv.inventory.entities]);
const filterNow = computed<LibraryFilter>(() => ({ query: query.value, pages: pagesOffered.value, pictures: scr.pictures, textTiles: Boolean(scr.currentScreen?.text_tiles), callTiles: Boolean(scr.currentScreen?.call_tiles), todoLists: Boolean(scr.currentScreen?.todo_lists), hidePlaced: ui.hidePlaced, counts: chosen.value }));
const base = computed(() => libraryBase(entries.value, filterNow.value));
const pool = computed(() => base.value.filter((e) => !ui.room || e.area === ui.room));
const matches = computed(() => libraryMatches(pool.value, ui.filter, query.value));
// Nothing here for what is typed, because of a kind, a room or the hide switch: how many the whole library has for it.
const elsewhere = computed(() => query.value && !matches.value.length && (ui.filter || ui.room || ui.hidePlaced)
  ? libraryBase(entries.value, { ...filterNow.value, hidePlaced: false }).length : 0);
function searchEverything() { ui.filter = ""; ui.room = ""; ui.hidePlaced = false; }
// Browsing, the entities stand under their room, and the screen's own cards last; a search or a room is one list.
const grouped = computed(() => !query.value && !ui.room);
const allGroups = computed(() => libraryGroups(matches.value, grouped.value));
// The order the arrow keys walk: the groups as they stand, also what the list has not come to yet.
const flat = computed(() => allGroups.value.flatMap((group) => group.entities));
// Everything is listed, but a home's thousand entities don't stand on the page at once: the rows come as the list is
// scrolled towards them, and a new search or kind starts at the top again.
const list = ref<HTMLElement | null>(null);
const tilesView = computed(() => ui.libraryView === "tiles" && !ui.phone);
// The Tiles view draws three cards an entity: a screenful of shelves and two more ahead come at once (shelvesInView,
// below), more as the list is scrolled.
const step = computed(() => (tilesView.value ? shelvesInView.value * 3 : ROWS_AT_ONCE));
const rows = ref(ROWS_AT_ONCE);
// While browsing a room's extras stand folded apart and are left out of the window: they come whole when unfolded.
const groups = computed(() => {
  if (!grouped.value) return libraryWindow(allGroups.value, rows.value).map((group) => ({ ...group, extras: [] as Entry[] }));
  let left = rows.value;
  return allGroups.value.flatMap((group) => {
    const main = group.entities.filter((e) => !isExtra(e)), extras = group.entities.filter(isExtra);
    if (left <= 0) return [];
    const shown = main.slice(0, left);
    left -= shown.length;
    // A room is shown once its turn comes; its fold after the last of its own entities.
    const done = shown.length === main.length;
    return shown.length || (done && extras.length) ? [{ ...group, entities: shown, count: group.entities.length, extras: done ? extras : [] }] : [];
  });
});
useInfiniteScroll(list, () => { rows.value += step.value; }, { distance: 400, canLoadMore: () => open.value && rows.value < flat.value.length });
watch(() => [ui.search, ui.filter, ui.room, ui.hidePlaced, ui.libraryView], () => { rows.value = step.value; list.value?.scrollTo?.({ top: 0 }); });
// The rows the list shows now.
function rowsInView() {
  const box = list.value?.getBoundingClientRect();
  if (!box) return [];
  return [...list.value!.querySelectorAll<HTMLElement>(".ent, .shelf")].filter((row) => { const place = row.getBoundingClientRect(); return place.bottom >= box.top && place.top <= box.bottom; })
    .map((row) => row.id.slice("lib-".length));
}
// The states of the rows in view, asked once the list has stood still a moment (180 ms), again every minute, and never for
// a folded drawer; the wait goes with the drawer.
// The Tiles view also asks what each can do, which decides the controls its larger tiles get.
const loadSoon = useTimeoutFn(() => { const ids = rowsInView(); void entities.loadLibraryStates(ids, doc.stillSelected()); if (tilesView.value) void entities.loadCapabilities(ids); }, 180, { immediate: false });
watch(() => [open.value, groups.value, Math.floor(ui.now / 60000)],
  () => (open.value ? loadSoon.start() : loadSoon.stop()), { immediate: true });
// The kinds and rooms the results hold, each with its count, so searching narrows the column the way it narrows the
// entities.
const offered = computed(() => kindCounts(pool.value, ui.filter));
const rooms = computed(() => roomCounts(base.value, ui.room));
const full = computed(() => (doc.layout?.tiles.length || 0) >= doc.tileLimit);
const memoryFull = computed(() => doc.memory?.level === "full" || doc.memory?.level === "over");
const count = computed(() => inv.inventory.entities.length);
const detail = (e: Entry) => entryDetail(e, grouped.value, pluginOf(e.id));
// A room's extras (Home Assistant's settings, diagnosis and hidden entities) stand folded under the rest while browsing;
// a search lists them where they rank, and the room's fold is opened by a click.
const unfolded = ref(new Set<string>());
const mainOf = (group: { entities: Entry[] }) => group.entities;
const extrasOf = (group: { extras: Entry[] }) => group.extras;
function unfold(key: string) { const next = new Set(unfolded.value); if (next.has(key)) next.delete(key); else next.add(key); unfolded.value = next; }
const extraKinds = (list: Entry[]) => [...new Set(list.map((e) => (e.category ?? "hidden")))].map((kind) => t(`editor.library.extras.${kind}`)).join(", ");
// ---- The Tiles view's scale (docs/PAGES.md "The library") ----
// Every card at one scale, so the sizes compare. The sizes of a shelf stand on one line in the strip's width, and the
// tallest, a card of two rows as the page draws it, fills the height the list has under a shelf's own name and sizes;
// never larger than on the page, and for the height never smaller than LEAST_SCALE of it, under which its words stop
// being readable (the drawer opens that high instead).
// What a shelf and the drawer take beside the cards is measured from what they draw (their CSS), not counted here.
const LEAST_SCALE = 0.5;
// The list's height with its padding: what a shelf has to stand in.
const { height: listHeight } = useElementSize(list, undefined, { box: "border-box" });
const shelfChrome = ref(0), drawerChrome = ref(0), strip = ref({ width: 0, gap: 0 });
// A measure is taken a frame after the drawing it reads, and kept only when it moved by more than a pixel: what it
// changes is drawn again and measured once more, and that settles instead of going round. The frame is what keeps the
// page alive: a measure in the same tick as the drawing (nextTick) chains every pass into one microtask queue, and a
// scale that flips between two values then never lets the browser draw again (it froze the page at 1440 x 1000).
const settle = (target: { value: number }, next: number) => { if (Math.abs(target.value - next) > 1) target.value = next; };
function measureShelves() {
  const shelf = list.value?.querySelector<HTMLElement>(".shelf"), row = shelf?.querySelector<HTMLElement>(".shelf-row");
  if (row) {
    const css = getComputedStyle(row);
    const width = row.clientWidth - parseFloat(css.paddingLeft) - parseFloat(css.paddingRight), gap = parseFloat(css.columnGap) || 0;
    if (Math.abs(strip.value.width - width) > 1 || strip.value.gap !== gap) strip.value = { width, gap };
  }
  // What the first shelf takes beside its cards, from the top of the list: the room's title above it, its name, the
  // strip's padding and the sizes' words, on a shelf whose cards stand on one line.
  const tallest = Math.max(0, ...[...(shelf?.querySelectorAll<HTMLElement>(".sample-glass") ?? [])].map((glass) => glass.offsetHeight));
  // The cards stand on the strip's floor: on one line they all end at the same height.
  const oneLine = row && new Set([...row.querySelectorAll<HTMLElement>(".sample")].map((sample) => Math.round(sample.offsetTop + sample.offsetHeight))).size <= 1;
  if (shelf && tallest && oneLine) {
    const bottom = shelf.getBoundingClientRect().bottom - list.value!.getBoundingClientRect().top + list.value!.scrollTop;
    settle(shelfChrome, bottom + parseFloat(getComputedStyle(list.value!).paddingBottom) - tallest);
  }
  const aside = list.value?.closest<HTMLElement>(".library");
  if (aside && open.value && list.value!.clientHeight) settle(drawerChrome, aside.offsetHeight - list.value!.clientHeight);
}
const shelfTwoRows = computed(() => {
  const shape = doc.screenShape as Parameters<typeof cardHeight>[0], grid = doc.editorLayout.grid, glass = Number(canvas.deviceStyle["--glass"]) || 1;
  return cardHeight(shape, grid.rows, Math.min(2, grid.rows), 0, canvas.pageBarShown) * glass;
});
// The widest shelf the screen offers: one cell, a row of two and two rows of two side by side (library-tiles.ts SHOWN).
const shelfWidth = computed(() => {
  const shape = doc.screenShape as Parameters<typeof cardContent>[0], grid = doc.editorLayout.grid, glass = Number(canvas.deviceStyle["--glass"]) || 1;
  const card = (columns: number) => (cardContent(shape, grid.columns, Math.min(columns, grid.columns)) + 2 * frameOf(shape).tile_pad + 2) * glass;
  return card(1) + 2 * card(2);
});
const shelfZoom = computed(() => {
  const byHeight = (listHeight.value - shelfChrome.value) / Math.max(1, shelfTwoRows.value);
  const byWidth = strip.value.width ? (strip.value.width - 2 * strip.value.gap) / Math.max(1, shelfWidth.value) : 1;
  // One line comes first: a narrow list makes the cards smaller still, rather than break a shelf in two.
  return Math.min(1, byWidth, Math.max(LEAST_SCALE, byHeight));
});
// How many shelves a screenful of the list holds.
const shelvesInView = computed(() => Math.max(1, Math.ceil(listHeight.value / Math.max(1, shelfTwoRows.value * shelfZoom.value + shelfChrome.value))));

// ---- Keyboard: type anywhere to search, arrows to walk, Enter to add ----
const search = ref<HTMLInputElement | null>(null);
const searching = ref(false);
const addable = (e: Entry) => !placed(e.id) && !full.value;
// The arrows walk the results round, the one in focus scrolled into view; Enter adds it; a new search starts at the first.
const results = useListNavigation(flat, {
  wrap: true,
  onPick: (entity) => (addable(entity) ? (addTile(entity.id), true) : false),
  resetOn: () => [ui.search, ui.filter, ui.room],
  onMove: (index) => { if (index >= rows.value) rows.value = index + step.value; nextTick(() => (list.value?.querySelector(".ent.active, .shelf.active") as HTMLElement | null)?.scrollIntoView?.({ block: "nearest" })); },
});
const active = results.active;
function onSearchKey(e: KeyboardEvent) {
  if (e.key === "ArrowDown" || e.key === "ArrowUp") open.value = true;
  if (results.onKey(e)) return;
  if (e.key === "Escape") {
    // First Escape clears the search, the next one folds the drawer and hands the keys back to the page.
    e.stopPropagation();
    if (ui.search) ui.search = "";
    else { open.value = false; search.value?.blur(); }
  }
}
// A key typed where nothing takes text is the start of a search: the drawer opens on it (Notion's and Apple's way of
// letting a person just start typing). "/" only puts the cursor there. A dialog, a menu or a field keeps its keys.
function onPageKey(e: KeyboardEvent) {
  if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey || e.isComposing || ui.tab !== "layout" || ui.palette || question.value) return;
  const target = e.target as HTMLElement | null;
  if (isEditableTarget(target) || target?.closest?.("select, dialog, [role='dialog'], [role='menu'], [role='listbox']")) return;
  if (document.querySelector("dialog[open], [role='dialog'], [role='menu']")) return;
  if (e.key === "/") { e.preventDefault(); openSearch(); return; }
  if (e.key.length !== 1 || !/\S/.test(e.key)) return;
  e.preventDefault();
  ui.search += e.key;
  openSearch();
}
function openSearch() {
  open.value = true;
  // A phone's keyboard would cover the list it opens on: there the field waits for a tap.
  if (ui.phone) return;
  nextTick(() => { const input = search.value; if (!input) return; input.focus(); input.setSelectionRange(input.value.length, input.value.length); });
}
useEventListener(document, "keydown", onPageKey);

// ---- Open or folded, and how tall, remembered in this browser ----
const MIN = 180;
const HEAD = 49;
// The height this browser keeps, written when the edge is let go or a key moved it; `height` follows the pointer.
const keptHeight = usePreference("esp-screens.library-height", 300,
  { serializer: { read: (raw) => Math.max(MIN, Number(raw) || 300), write: (px) => String(Math.round(px)) } });
// Until the person drags it to a height of their own, it takes 30 % of the window, at most 300 px: on a laptop's 720 px
// the pages keep room for their rows instead of being cut off after two.
const heightChosen = (() => { try { return localStorage.getItem("esp-screens.library-height") !== null; } catch { return false; } })();
const height = ref(heightChosen ? keptHeight.value : Math.min(300, Math.max(MIN, Math.round(window.innerHeight * 0.3))));
const maxHeight = () => Math.max(MIN, Math.round(window.innerHeight * 0.7));
function toggle() { open.value = !open.value; }
function showView(view: string) { ui.libraryView = view === "list" ? "list" : "tiles"; open.value = true; }

// Typing in the folded bar opens the drawer on what it finds.
watch(() => ui.search, (q) => { if (q) open.value = true; });
// An empty cell or a clock's key marked for the next entity opens the drawer and puts the cursor in the search.
watch(() => insp.insert, (marked) => { if (marked) openSearch(); });
// While the top edge is held the drawer follows the pointer at once; otherwise it glides. Dragging the edge selects
// nothing on the page it passes over, and the height is kept when it is let go (also when the drawer goes first).
let from = { y: 0, h: 0 };
const edge = useResizeHandle({
  selectNothing: true,
  onStart: (e) => { from = { y: e.clientY, h: open.value ? height.value : HEAD }; },
  onMove: (e) => {
    const next = from.h + from.y - e.clientY;
    // Dragged below its least height it folds; dragged up from folded it opens.
    if (next < MIN * 0.6) { open.value = false; return; }
    open.value = true;
    height.value = Math.min(maxHeight(), Math.max(MIN, next));
  },
  onEnd: () => { keptHeight.value = height.value; },
});
const resizing = edge.resizing;
// The Tiles view opens at least as high as one shelf at its least scale: the drawer's own head and the shelf around a
// card of two rows.
const shownHeight = computed(() => (tilesView.value
  ? Math.max(height.value, Math.min(maxHeight(), drawerChrome.value + shelfChrome.value + shelfTwoRows.value * LEAST_SCALE)) : height.value));
// Measured again whenever what they draw changes: the shelves, the view, the drawer, and the scale itself, after which
// a shelf that wrapped stands on one line and can be measured.
watch([() => groups.value, tilesView, open, listHeight, shelfZoom], () => requestAnimationFrame(measureShelves), { immediate: true });
// The first window is the view's own, and a screenful more measured than the list holds gets its shelves at once.
watch(step, (next, before) => { if (before === undefined || rows.value < next) rows.value = next; }, { immediate: true });
function onResizeKey(e: KeyboardEvent) {
  if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
  e.preventDefault();
  open.value = true;
  height.value = Math.min(maxHeight(), Math.max(MIN, height.value + (e.key === "ArrowUp" ? 40 : -40)));
  keptHeight.value = height.value;
}
</script>

<template>
  <div v-if="ui.phone && open" class="sheet-dim" @click="open = false"></div>
  <aside class="library" id="library" :class="{ open, resizing, 'tiles-view': tilesView }" :style="ui.phone ? undefined : { height: `${open ? shownHeight : HEAD}px` }">
    <div v-if="ui.phone" class="sheet-head">
      <span class="sheet-title"><b>{{ t("editor.phone.add_tile") }}</b><small>{{ destination }}</small></span>
      <button type="button" class="icon-btn sheet-close" :aria-label="t('editor.common.close')" @click="open = false"><Icon name="close" /></button>
    </div>
    <div v-else class="lib-grip" role="separator" aria-orientation="horizontal" tabindex="0" :aria-label="t('editor.library.resize')"
      @pointerdown="edge.start" @keydown="onResizeKey"><i></i></div>
    <div class="lib-head">
      <button v-if="!ui.phone" type="button" class="lib-title" id="library-toggle" :aria-expanded="open ? 'true' : 'false'" aria-controls="library-body" :title="t('editor.library.hint')" @click="toggle">
        <Icon name="chevron-down" class="lib-chevron" />
        <span>{{ t("editor.library.title") }}</span>
      </button>
      <label class="lib-search" :class="{ focused: searching }">
        <Icon name="magnify" />
        <input id="search" ref="search" v-model="ui.search" type="search" :placeholder="t('editor.library.search')" autocomplete="off" spellcheck="false"
          :aria-label="t('editor.library.search_label')" aria-controls="results" :aria-activedescendant="ui.search && flat[active] ? `lib-${flat[active].id}` : undefined"
          @focus="searching = true" @blur="searching = false" @keydown="onSearchKey" />
        <kbd v-if="!ui.search && !searching" aria-hidden="true">/</kbd>
      </label>
      <span v-if="!open" class="lib-count">{{ t("editor.library.entities", count) }}</span>
      <UiSegmented v-if="!ui.phone" class="lib-view" :label="t('editor.library.tiles.view')" :model-value="ui.libraryView" :segments="[
        { value: 'tiles', label: t('editor.library.tiles.tiles'), icon: 'view-grid-outline', title: t('editor.library.tiles.tiles_title') },
        { value: 'list', label: t('editor.library.tiles.list'), icon: 'format-list-bulleted', title: t('editor.library.tiles.list_title') }]"
        @update:model-value="showView" />
    </div>
    <div class="lib-body" id="library-body" :inert="!open || undefined">
      <div class="lib-rail">
        <nav class="lib-domains" id="filters" :aria-label="t('editor.library.filter_label')">
          <button v-for="[value, n] in offered" :key="value" type="button" :aria-pressed="ui.filter === value ? 'true' : 'false'" @click="ui.filter = value">
            <span v-if="value === 'plugin'" class="domain-icon plugin" aria-hidden="true"><Icon name="puzzle-outline" /></span>
            <span v-else-if="value" class="domain-icon mdi" :style="{ color: domainInfo(value + '.')[2], background: domainInfo(value + '.')[3] }" aria-hidden="true">{{ glyph(entities.automaticIcon(value + ".")) }}</span>
            <span v-else class="domain-icon all" aria-hidden="true"><Icon name="view-dashboard-outline" /></span>
            <span class="dn">{{ t(`editor.library.filters.${value || "all"}`) }}</span>
            <small>{{ n }}</small>
          </button>
        </nav>
        <nav v-if="rooms.length" class="lib-domains lib-rooms" id="room" :aria-label="t('editor.library.room')">
          <span class="lib-rail-title">{{ t("editor.library.room") }}</span>
          <button v-for="[room, n] in rooms" :key="room" type="button" :aria-pressed="ui.room === room ? 'true' : 'false'" @click="ui.room = ui.room === room ? '' : room">
            <span class="dn">{{ room }}</span>
            <small>{{ n }}</small>
          </button>
        </nav>
        <div class="lib-hide">
          <label for="hide-placed" :title="t('editor.library.hide_placed_title')">{{ t("editor.library.hide_placed") }}</label>
          <UiSwitch id="hide-placed" :model-value="ui.hidePlaced" @update:model-value="(on: boolean) => (ui.hidePlaced = on)" />
        </div>
      </div>
      <div ref="list" class="lib-list" id="results" role="listbox" aria-live="polite" :aria-label="t('editor.library.title')" @scroll.passive="loadSoon.start()">
        <section v-if="sectionOffered" class="lib-group lib-layout">
          <div class="lib-grid">
            <button type="button" class="ent ent-section" id="lib-section" @click="addSectionHere">
              <span class="av"><Icon name="view-grid-outline" /></span>
              <span class="tx"><b>{{ t("editor.sections.add") }}</b><small>{{ t("editor.sections.library_hint") }}</small></span>
              <span class="add">+</span>
            </button>
          </div>
        </section>
        <section v-for="group in groups" :key="group.key" class="lib-group">
          <h4 v-if="group.title" class="lib-group-title">{{ group.title }} <small>{{ group.count }}</small></h4>
          <div v-if="tilesView" class="lib-shelves">
            <LibraryShelf v-for="entity in mainOf(group)" :key="entity.id" :entity="entity" :name="short(entity)" :detail="detail(entity)" :mark="mark(entity.id)"
              :disabled="placed(entity.id) || full" :zoom="shelfZoom" :max-height="shelfZoom * shelfTwoRows" :active="!!ui.search && flat[active]?.id === entity.id" @add="(tile) => addTile(entity.id, tile)" />
          </div>
          <div v-else class="lib-grid">
            <button v-for="entity in mainOf(group)" :id="`lib-${entity.id}`" :key="entity.id" type="button" class="ent" role="option"
              :class="{ active: ui.search && flat[active]?.id === entity.id }" :aria-selected="ui.search && flat[active]?.id === entity.id ? 'true' : 'false'"
              :title="onScreen(entity.id) && !placed(entity.id) ? `${entity.id} · ${t('editor.library.again')}` : entity.id"
              :disabled="placed(entity.id) || full" v-drag="{ kind: 'entity', id: entity.id }" @click="addTile(entity.id)">
              <span class="av mdi" :class="tone(entity)" :style="{ color: tilePalette(entity.id, entities.liveOf(entity.id)).icon, background: tilePalette(entity.id, entities.liveOf(entity.id)).circle }">{{ glyph(entities.automaticIcon(entity.id)) }}</span>
              <span class="tx">
                <b>{{ short(entity) }}</b>
                <small v-if="detail(entity)">{{ detail(entity) }}</small>
              </span>
              <span class="add" :class="{ done: onScreen(entity.id) }">{{ mark(entity.id) }}</span>
            </button>
          </div>
          <template v-if="extrasOf(group).length">
            <button type="button" class="lib-extras" :aria-expanded="unfolded.has(group.key) ? 'true' : 'false'" @click="unfold(group.key)">
              <Icon name="chevron-down" class="lib-extras-chevron" />
              <span>{{ t("editor.library.extras.title", extrasOf(group).length) }}</span>
              <small>{{ extraKinds(extrasOf(group)) }}</small>
            </button>
            <div v-if="unfolded.has(group.key)" class="lib-grid lib-extras-list">
              <button v-for="entity in extrasOf(group)" :id="`lib-${entity.id}`" :key="entity.id" type="button" class="ent ent-extra" role="option"
                :title="entity.id" :disabled="placed(entity.id) || full" v-drag="{ kind: 'entity', id: entity.id }" @click="addTile(entity.id)">
                <span class="av mdi" :class="tone(entity)" :style="{ color: tilePalette(entity.id, entities.liveOf(entity.id)).icon, background: tilePalette(entity.id, entities.liveOf(entity.id)).circle }">{{ glyph(entities.automaticIcon(entity.id)) }}</span>
                <span class="tx"><b>{{ short(entity) }}</b><small>{{ [detail(entity), t(`editor.library.extras.${entity.category ?? "hidden"}`)].filter(Boolean).join(" · ") }}</small></span>
                <span class="add" :class="{ done: onScreen(entity.id) }">{{ mark(entity.id) }}</span>
              </button>
            </div>
          </template>
        </section>
        <p v-if="elsewhere" class="hint lib-empty">{{ t("editor.library.found_elsewhere", elsewhere) }} <button type="button" class="lib-everything" @click="searchEverything">{{ t("editor.library.search_everything") }}</button></p>
        <p v-else-if="!matches.length" class="hint lib-empty">{{ ui.hidePlaced && !ui.search && !ui.filter && !ui.room ? t("editor.library.all_placed") : t("editor.library.none_found") }}</p>
        <div v-if="full" class="lib-foot">{{ t(doc.tileLimit < 48 ? "editor.library.full_update" : "editor.library.full", doc.tileLimit) }}</div>
        <div v-else-if="memoryFull" class="lib-foot">{{ t("editor.memory.full_library") }}</div>
      </div>
    </div>
  </aside>
</template>

<style scoped>
/* The scrollbar's room is kept, so the shelves' width does not change as the list comes to need one (Library.vue scale). */
#results:has(.lib-shelves) { scrollbar-gutter: stable; }
.lib-shelves { display: grid; grid-template-columns: minmax(0, 1fr); gap: 10px; align-items: start; }
.lib-extras { display: flex; align-items: center; gap: 8px; margin-top: 10px; padding: 6px 8px; border-radius: 8px; color: var(--muted); font-size: 12px; width: 100%; text-align: left; }
.lib-extras:hover { background: var(--surface-2); color: var(--ink-2); }
.lib-extras span { font-weight: 500; }
.lib-extras small { font-size: 11px; opacity: 0.8; }
.lib-extras-chevron { transform: rotate(-90deg); transition: transform 0.12s; }
.lib-extras[aria-expanded="true"] .lib-extras-chevron { transform: none; }
.lib-extras-list { margin-top: 6px; }
.ent-extra .av { opacity: 0.75; }
.lib-view { flex: none; margin-left: auto; }
</style>
