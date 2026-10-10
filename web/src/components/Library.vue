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
import { domainInfo, pageTarget } from "../model/layout";
import { glyph } from "../model/topbar";
import { matchesQuery, prefixRank } from "../model/search";
import { tilePalette } from "../model/tile-palette";
import { isPluginTile } from "../model/plugins";
import { pluginsEnabled, tilesOn } from "../plugin-state";
import { currentScreen, stillSelected } from "../store";
import { usePreference } from "../composables/usePreference";
import { useResizeHandle } from "../composables/useResizeHandle";
import { useListNavigation } from "../composables/useListNavigation";
import { isEditableTarget } from "../composables/isEditableTarget";
import { question } from "../composables/useConfirm";
import { addTile, editorLayout, memory, pageTitleShown, pictures, repeatable, state, tileLimit } from "../store";
import Icon from "./ui/Icon.vue";
import UiSwitch from "./ui/UiSwitch.vue";
import { useUiStore } from "../stores/ui";
import { useEntitiesStore } from "../stores/entities";

const ui = useUiStore();
const entities = useEntitiesStore();

// The domains to filter on; the label of each is editor.library.filters.<domain>, "all" for no filter.
const FILTERS = [
  "", "light", "climate", "humidifier", "switch", "binary_sensor", "button", "script", "automation", "fan", "cover", "scene", "vacuum", "sensor",
  "media_player", "remote", "weather", "number", "select", "person", "timer", "screen", "alarm_control_panel", "lock",
];
const ALIAS: Record<string, string> = { switch: "input_boolean", number: "input_number", select: "input_select", weather: "sun", button: "input_button" };
const SHOWN = 80;
// Open: on a wider page the drawer along the bottom, remembered; on a phone (app 0.4.40) a sheet that opens for a tile
// and goes once it is added, closed or swiped away. Closing it there forgets the cell it was opened for.
const open = computed({
  get: () => ui.phone ? ui.addSheet : ui.libraryOpen,
  set: (value: boolean) => {
    if (!ui.phone) { ui.libraryOpen = value; return; }
    ui.addSheet = value;
    if (!value) { state.insertAt = -1; ui.search = ""; }
  },
});
// Where the tile goes, said at the top of the phone's sheet.
const destination = computed(() => {
  const pages = state.document?.pages || [];
  const page = state.insertAt >= 0 ? Math.floor(state.insertAt / editorLayout.grid.slots) : Math.max(0, pages.findIndex((item) => item.id === state.selectedPageId));
  const name = pageTitleShown(page) || t("editor.page.label", { page: page + 1 });
  return state.insertAt >= 0 ? t("editor.phone.add_to_cell", { cell: state.insertAt % editorLayout.grid.slots + 1, page: name }) : t("editor.phone.add_to_page", { page: name });
});
type Entry = { id: string; name: string; area?: string; device?: string; state?: string; tile?: boolean };
// How many tiles each entity has on the screen. One that is there stays addable when the firmware takes an entity on
// several tiles (a page tile from 0.2.65, any entity but the bedside clock from 0.16.0): its mark says how often.
const chosen = computed(() => {
  const counts = new Map<string, number>();
  for (const tile of state.layout?.tiles || []) counts.set(tile.entity, (counts.get(tile.entity) || 0) + 1);
  return counts;
});
const onScreen = (id: string) => chosen.value.has(id);
const placed = (id: string) => onScreen(id) && !repeatable(id);
const mark = (id: string) => (chosen.value.get(id) || 0) > 1 ? `×${chosen.value.get(id)}` : onScreen(id) ? "✓" : "+";
const builtin = (id: string) => id.startsWith("screen.");
// A plugin's tile type (design): listed under Plugins, only for a screen that runs that plugin.
const pluginEntries = computed<(Entry & { plugin: string })[]>(() => (pluginsEnabled.value ? tilesOn(currentScreen.value) : []));
const pluginOf = (id: string) => pluginEntries.value.find((e) => e.id === id)?.plugin || "";
// Go to page tiles for the pages there are and the next one, at least the eight every screen has and at most what this
// screen takes: a board with 24 pages (firmware 0.34.0+) would otherwise list 24 of them.
const pagesOffered = computed(() => Math.min(editorLayout.grid.pages, Math.max(8, (state.document?.pages.length || 0) + 1)));
const query = computed(() => ui.search.trim().toLocaleLowerCase());
// What the search and the hide switch leave over. The rooms are counted off this, the kinds off it narrowed to the
// room, and neither off the finished list: picking one would take every other one away with it.
const base = computed<Entry[]>(() => {
  const q = query.value;
  // The picker offers what a tile can show; camera and image tiles need a board that draws pictures (app 0.2.66).
  // The screen's own cards and plugin tiles first: the list shows the first 80, and these are few.
  return [...pluginEntries.value, ...(state.inventory.builtin || []), ...state.inventory.entities].filter((e) =>
    e.tile !== false && pageTarget(e.id) <= pagesOffered.value &&
    (pictures.value || (!["camera", "image"].includes(e.id.split(".")[0]) && e.id !== "screen.map")) &&
    (!ui.hidePlaced || !onScreen(e.id)) &&
    matchesQuery(q, e.name, e.id, e.device, e.area));
});
const pool = computed(() => base.value.filter((e) => !ui.room || e.area === ui.room));
const inDomain = (id: string, filter: string) => !filter || id.startsWith(filter + ".") || ALIAS[filter] === id.split(".")[0];
// A search ranks what it finds, the way Spotlight does: a name that starts with the words first, then one with a word
// that does, then the rest. Without one the list keeps Home Assistant's order.
const rank = (e: Entry) => prefixRank(e.name, query.value);
const matches = computed(() => {
  const found = pool.value.filter((e) => inDomain(e.id, ui.filter));
  return query.value ? [...found].sort((a, b) => rank(a) - rank(b)) : found;
});
const shownList = computed(() => matches.value.slice(0, SHOWN));
// Browsing, the entities stand under their room, and the screen's own cards last; a search or a room is one list.
const grouped = computed(() => !query.value && !ui.room);
const groups = computed(() => {
  if (!grouped.value) return [{ key: "", title: "", entities: shownList.value }];
  const byRoom = new Map<string, Entry[]>();
  for (const e of shownList.value) {
    const key = isPluginTile(e.id) ? "\u0002plugins" : builtin(e.id) ? "\u0001screen" : e.area || "\u0000none";
    byRoom.set(key, [...(byRoom.get(key) || []), e]);
  }
  const order = (key: string) => key === "\u0002plugins" ? 3 : key === "\u0001screen" ? 2 : key === "\u0000none" ? 1 : 0;
  return [...byRoom.keys()].sort((a, b) => order(a) - order(b) || a.localeCompare(b)).map((key) => ({
    key, entities: byRoom.get(key)!,
    title: key === "\u0002plugins" ? t("editor.library.plugins") : key === "\u0001screen" ? t("editor.library.filters.screen") : key === "\u0000none" ? t("editor.library.no_room") : key,
  }));
});
// The order the arrow keys walk: the groups as they stand.
const flat = computed(() => groups.value.flatMap((group) => group.entities));
// The states of what is shown, asked once the list has stood still a moment (180 ms), again every minute, and never for a
// folded drawer; the wait goes with the drawer.
const loadSoon = useTimeoutFn(() => entities.loadLibraryStates(shownList.value.map((entity) => entity.id), stillSelected()), 180, { immediate: false });
watch(() => [open.value, shownList.value.map((entity) => entity.id).join('|'), Math.floor(ui.now / 60000)],
  () => (open.value ? loadSoon.start() : loadSoon.stop()), { immediate: true });
// The kinds and rooms the results hold, each with its count, so searching narrows the column the way it narrows the
// entities. The chosen one stays even when nothing matches it any more, otherwise an empty list would have nothing to
// explain it.
const offered = computed(() => {
  const counts = new Map<string, number>();
  for (const e of pool.value) for (const d of FILTERS) if (d && inDomain(e.id, d)) counts.set(d, (counts.get(d) || 0) + 1);
  return FILTERS.filter((d) => !d || d === ui.filter || counts.has(d)).map((d) => [d, d ? counts.get(d) || 0 : pool.value.length] as [string, number]);
});
const rooms = computed(() => {
  const counts = new Map<string, number>();
  for (const e of base.value) if (e.area) counts.set(e.area, (counts.get(e.area) || 0) + 1);
  if (ui.room && !counts.has(ui.room)) counts.set(ui.room, 0);
  return [...counts.entries()].sort(([a], [b]) => a.localeCompare(b));
});
const full = computed(() => (state.layout?.tiles.length || 0) >= tileLimit.value);
const memoryFull = computed(() => memory.value?.level === "full" || memory.value?.level === "over");
const count = computed(() => state.inventory.entities.length);
// The avatar shows the state at a glance: lit for on, grey for an entity Home Assistant can't reach.
const tone = (e: { id: string; state?: string }) => {
  const domain = e.id.split(".")[0];
  if (e.state === "unavailable" || e.state === "unknown") return "gone";
  if (["light", "switch", "input_boolean", "automation", "remote", "fan", "humidifier"].includes(domain) && e.state === "on") return "on";
  return "";
};
// The name without its device's name in front, the way Home Assistant shows an entity on its device's card:
// "Bedroom screen Night mode" is "Night mode" under "Bedroom screen". A name that is only the device's stays whole.
const short = (e: Entry) => {
  const device = e.device?.trim();
  if (!device || !e.name.toLocaleLowerCase().startsWith(device.toLocaleLowerCase() + " ")) return e.name;
  const rest = e.name.slice(device.length).trim();
  return rest.charAt(0).toLocaleUpperCase() + rest.slice(1);
};
// Under the name: the device it was shortened by, else what it is, and its room where the list doesn't already stand
// under it.
const detail = (e: Entry) => isPluginTile(e.id) ? pluginOf(e.id) : builtin(e.id) ? "" : [short(e) !== e.name ? e.device : domainInfo(e.id)[0], grouped.value ? "" : e.area].filter(Boolean).join(" · ");

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
  if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey || e.isComposing || state.tab !== "layout" || ui.palette || question.value) return;
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
watch(() => [state.insertAt, state.insertKey], () => {
  if (state.insertAt < 0 && !state.insertKey) return;
  openSearch();
});
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
        <div v-if="full" class="lib-foot">{{ t(tileLimit < 48 ? "editor.library.full_update" : "editor.library.full", tileLimit) }}</div>
        <div v-else-if="memoryFull" class="lib-foot">{{ t("editor.memory.full_library") }}</div>
      </div>
    </div>
  </aside>
</template>
