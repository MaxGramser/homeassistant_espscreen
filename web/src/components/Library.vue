<script setup lang="ts">
// The entities a tile can show, in a drawer along the bottom of the pages (app 0.4.32): the inspector keeps the right
// side to itself. Folded it is one bar with the search. Typing anywhere on the page starts a search there and opens
// the drawer; the arrow keys walk the results and Enter adds the one in focus. Open, the rooms and the kinds of
// entity stand in a column on the left and the entities beside them, grouped by room until a search ranks them.
// Its top edge drags it taller or lower, and both are remembered.
// A click adds the entity to the marked empty cell or the first free one; a drag puts it exactly where it lands.
import { useEventListener, useTimeoutFn } from "@vueuse/core";
import { computed, nextTick, ref, watch } from "vue";
import { vDrag } from "../drag";
import { t } from "../i18n";
import { domainInfo } from "../model/layout";
import { glyph } from "../model/topbar";
import { entryDetail, entryTone as tone, kindCounts, libraryBase, libraryGroups, libraryMatches, markOf, roomCounts, shortName as short, SHOWN, tileCounts,
  type Entry } from "../model/library";
import { tilePalette } from "../model/tile-palette";
import { usePreference } from "../composables/usePreference";
import { useResizeHandle } from "../composables/useResizeHandle";
import { useListNavigation } from "../composables/useListNavigation";
import { isEditableTarget } from "../composables/isEditableTarget";
import { question } from "../composables/useConfirm";
import Icon from "./ui/Icon.vue";
import UiSwitch from "./ui/UiSwitch.vue";
import { useUiStore } from "../stores/ui";
import { useEntitiesStore } from "../stores/entities";
import { usePluginsStore } from "../stores/plugins";
import { useScreenStore } from "../stores/screen";
import { useInventoryStore } from "../stores/inventory";
import { addTile } from "../editor/tiles";
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
  const name = pageTitleShown(page) || t("editor.page.label", { page: page + 1 });
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
const pagesOffered = computed(() => Math.min(doc.editorLayout.grid.pages, Math.max(8, (doc.document?.pages.length || 0) + 1)));
const query = computed(() => ui.search.trim().toLocaleLowerCase());
// What the search and the hide switch leave over (model/library.ts). The picker offers what a tile can show; camera and
// image tiles need a board that draws pictures (app 0.2.66). The screen's own cards and plugin tiles first: the list
// shows the first 80, and these are few.
const base = computed(() => libraryBase([...pluginEntries.value, ...(inv.inventory.builtin || []), ...inv.inventory.entities],
  { query: query.value, pages: pagesOffered.value, pictures: scr.pictures, hidePlaced: ui.hidePlaced, counts: chosen.value }));
const pool = computed(() => base.value.filter((e) => !ui.room || e.area === ui.room));
const matches = computed(() => libraryMatches(pool.value, ui.filter, query.value));
const shownList = computed(() => matches.value.slice(0, SHOWN));
// Browsing, the entities stand under their room, and the screen's own cards last; a search or a room is one list.
const grouped = computed(() => !query.value && !ui.room);
const groups = computed(() => libraryGroups(shownList.value, grouped.value));
// The order the arrow keys walk: the groups as they stand.
const flat = computed(() => groups.value.flatMap((group) => group.entities));
// The states of what is shown, asked once the list has stood still a moment (180 ms), again every minute, and never for a
// folded drawer; the wait goes with the drawer.
const loadSoon = useTimeoutFn(() => entities.loadLibraryStates(shownList.value.map((entity) => entity.id), doc.stillSelected()), 180, { immediate: false });
watch(() => [open.value, shownList.value.map((entity) => entity.id).join('|'), Math.floor(ui.now / 60000)],
  () => (open.value ? loadSoon.start() : loadSoon.stop()), { immediate: true });
// The kinds and rooms the results hold, each with its count, so searching narrows the column the way it narrows the
// entities.
const offered = computed(() => kindCounts(pool.value, ui.filter));
const rooms = computed(() => roomCounts(base.value, ui.room));
const full = computed(() => (doc.layout?.tiles.length || 0) >= doc.tileLimit);
const memoryFull = computed(() => doc.memory?.level === "full" || doc.memory?.level === "over");
const count = computed(() => inv.inventory.entities.length);
const detail = (e: Entry) => entryDetail(e, grouped.value, pluginOf(e.id));

// ---- Keyboard: type anywhere to search, arrows to walk, Enter to add ----
const search = ref<HTMLInputElement | null>(null);
const list = ref<HTMLElement | null>(null);
const searching = ref(false);
const addable = (e: Entry) => !placed(e.id) && !full.value;
// The arrows walk the results round, the one in focus scrolled into view; Enter adds it; a new search starts at the first.
const results = useListNavigation(flat, {
  wrap: true,
  onPick: (entity) => (addable(entity) ? (addTile(entity.id), true) : false),
  resetOn: () => [ui.search, ui.filter, ui.room],
  onMove: () => nextTick(() => (list.value?.querySelector(".ent.active") as HTMLElement | null)?.scrollIntoView?.({ block: "nearest" })),
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
const height = ref(keptHeight.value);
const maxHeight = () => Math.max(MIN, Math.round(window.innerHeight * 0.7));
function toggle() { open.value = !open.value; }
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
  <aside class="library" id="library" :class="{ open, resizing }" :style="ui.phone ? undefined : { height: `${open ? height : HEAD}px` }">
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
    </div>
    <div class="lib-body" id="library-body" :inert="!open || undefined">
      <div class="lib-rail">
        <nav class="lib-domains" id="filters" :aria-label="t('editor.library.filter_label')">
          <button v-for="[value, n] in offered" :key="value" type="button" :aria-pressed="ui.filter === value ? 'true' : 'false'" @click="ui.filter = value">
            <span v-if="value" class="domain-icon mdi" :style="{ color: domainInfo(value + '.')[2], background: domainInfo(value + '.')[3] }" aria-hidden="true">{{ glyph(entities.automaticIcon(value + ".")) }}</span>
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
      <div ref="list" class="lib-list" id="results" role="listbox" aria-live="polite" :aria-label="t('editor.library.title')">
        <section v-for="group in groups" :key="group.key" class="lib-group">
          <h4 v-if="group.title" class="lib-group-title">{{ group.title }} <small>{{ group.entities.length }}</small></h4>
          <div class="lib-grid">
            <button v-for="entity in group.entities" :id="`lib-${entity.id}`" :key="entity.id" type="button" class="ent" role="option"
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
        </section>
        <p v-if="!matches.length" class="hint lib-empty">{{ ui.hidePlaced && !ui.search && !ui.filter && !ui.room ? t("editor.library.all_placed") : t("editor.library.none_found") }}</p>
        <p v-else-if="matches.length > SHOWN" class="hint">{{ t("editor.common.results", matches.length) }}</p>
        <div v-if="full" class="lib-foot">{{ t(doc.tileLimit < 48 ? "editor.library.full_update" : "editor.library.full", doc.tileLimit) }}</div>
        <div v-else-if="memoryFull" class="lib-foot">{{ t("editor.memory.full_library") }}</div>
      </div>
    </div>
  </aside>
</template>
