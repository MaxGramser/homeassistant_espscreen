<script setup lang="ts">
// ⌘K: one search for everything the editor has and a way to act on it (model/palette.ts), fed by the stores: the screens and
// what can be done to them, the editor's actions, every screen's settings, the tiles that show an entity on any screen,
// the entities to add to this page, and the plugins. Keyboard first: the arrows walk the rows from the field, Enter does
// what the row in focus says, Escape closes; what was chosen last comes first, kept in this browser. Updating every
// screen asks first.
import { computed, nextTick, ref, watch } from "vue";
import { t } from "../i18n";
import { useListNavigation } from "../composables/useListNavigation";
import { askConfirm } from "../composables/useConfirm";
import { usePreference } from "../composables/usePreference";
import { tileEntities } from "../model/broken-tiles";
import { paletteGroups, paletteItems, rememberChoice, type PaletteActions, type PaletteItem, type PaletteSetting, type PaletteTile } from "../model/palette";
import { text as pluginText } from "../model/plugins";
import { needsUpdate } from "../model/screen-status";
import { SETTING_GROUPS, settingLabel, type SettingRow } from "../model/settings";
import { glyph } from "../model/topbar";
import type { Screen } from "../types";
import { useUiStore } from "../stores/ui";
import { useEntitiesStore } from "../stores/entities";
import { useScreenStore } from "../stores/screen";
import { useSessionStore } from "../stores/session";
import { useInventoryStore } from "../stores/inventory";
import { useBuildsStore } from "../stores/builds";
import { usePluginsStore } from "../stores/plugins";
import { useSettingsStore } from "../stores/settings";
import { useRegionStore } from "../stores/region";
import { addTile } from "../editor/tiles";
import { showTile } from "../editor/tile-entity";
import { useDocumentStore } from "../stores/document";

const ui = useUiStore();
const entities = useEntitiesStore();
const scr = useScreenStore();
const session = useSessionStore();
const inv = useInventoryStore();
const builds = useBuildsStore();
const plugins = usePluginsStore();
const settings = useSettingsStore();
const region = useRegionStore();
const doc = useDocumentStore();

const query = ref("");
const input = ref<HTMLInputElement | null>(null);
const list = ref<HTMLElement | null>(null);
// What was chosen last, by the row's id, kept in this browser.
const recent = usePreference<string[]>("esp-screens.palette-recent", [], {
  serializer: { read: (raw) => { try { const ids = JSON.parse(raw); return Array.isArray(ids) ? ids.filter((id) => typeof id === "string") : []; } catch { return []; } },
    write: (ids) => JSON.stringify(ids) },
});

// A screen opened from here, then what to do on it once it is open (the person may keep the unsaved changes of another).
async function onScreen(screen: Screen, then: () => void) {
  if (scr.selected !== screen.id || !doc.document) await session.select(screen.id);
  if (scr.selected === screen.id) then();
}
// What a row does, by what it is.
const actions: PaletteActions = {
  openScreen: (screen) => session.select(screen.id),
  go: (route) => ui.go(route),
  showTab: (tab) => { ui.go(""); ui.tab = tab; },
  save: () => doc.save(),
  identify: (screen) => scr.identify(screen),
  exportLayout: () => doc.exportLayout(),
  addTile: (id) => addTile(id),
  update: (screen) => builds.startUpdate(screen),
  updateAll: async () => {
    const waiting = updatable.value.length;
    if (await askConfirm(t("editor.search.update_all_confirm", waiting), { confirm: t("editor.search.update_all_go") })) builds.runUpdateAll();
  },
  installSetAside: () => plugins.installTray(),
  showTile: (screen, tileId) => { void showTile(screen, tileId); },
  openSetting: (screen, key) => onScreen(screen, () => { ui.go(""); ui.tab = "settings"; settings.spotlight = key; }),
  openPlugin: (id) => { plugins.focus = id; ui.go("#plugins"); },
  addPlugin: (id) => {
    const screen = scr.currentScreen, plugin = plugins.index.find((p) => p.id === id);
    if (!screen || !plugin) return;
    plugins.setAside(screen, plugin);
    ui.go(""); ui.tab = "plugins"; plugins.focus = id;
  },
};

// ---- What the rows are made of ----
const open = computed(() => (scr.currentScreen && doc.layout ? scr.currentScreen : null));
// An update that can go now from here: the screen is there and the add-on knows how to reach it.
const updatable = computed(() => inv.inventory.screens.filter((screen) => !screen.virtual && screen.online && needsUpdate(screen)
  && screen.update?.profile && screen.update?.host && !builds.isBuilding(screen)));
// The tiles that show an entity: the open screen as its draft has it, the others as they were saved.
const tiles = computed<PaletteTile[]>(() => inv.inventory.screens.flatMap((screen) => {
  const layout = screen.id === scr.selected && doc.document ? doc.document : screen.page_document?.format === "pages-v2" ? screen.page_document.layout : null;
  return layout ? tileEntities(layout).map((tile) => ({ screen, ...tile })) : [];
}));
// Every screen's settings as its settings page lists them, each with its value in words.
const settingRows = computed<PaletteSetting[]>(() => inv.inventory.screens.flatMap((screen) => {
  const view = screen.settings;
  if (screen.virtual || !view) return [];
  return SETTING_GROUPS.flatMap((group) => (group.rows as readonly SettingRow[]).filter((row) => view.keys.includes(row.key)).map((row) => {
    const value = view.values[row.key];
    const words = row.kind === "toggle" ? (value === true ? t("editor.search.on") : value === false ? t("editor.search.off") : "")
      : row.kind === "choice" ? (value === undefined || value === null ? "" : `${value}°`) : settings.settingText(row, view.values);
    return { screen, key: row.key, label: settingLabel(row), group: t(`editor.screen_settings.groups.${group.group}`), value: words === "—" ? "" : words };
  }));
}));
const pluginRows = computed(() => !plugins.pluginsEnabled ? [] : plugins.index.map((plugin) => ({
  id: plugin.id, name: pluginText(plugin.name), summary: pluginText(plugin.summary), icon: plugin.icon,
  addable: Boolean(open.value && !open.value.virtual && !plugins.installedOn(open.value, plugin.id) && !plugins.isSetAside(open.value, plugin.id)
    && plugins.fits(plugin, open.value).ok),
})));
const items = computed(() => {
  void region.clock24;
  const screen = open.value;
  return paletteItems({ query: query.value, screens: inv.inventory.screens, open: screen, dirty: doc.dirty, alerts: Boolean(screen && scr.canAlert(screen)),
    entities: inv.inventory.entities, placed: new Set(doc.layout?.tiles.map((tile) => tile.entity) || []), repeatable: scr.repeatable,
    full: (doc.layout?.tiles.length || 0) >= doc.tileLimit, icon: inv.inventory.icons ? entities.automaticIcon : undefined,
    recent: recent.value, canIdentify: (each) => each.online && scr.canAlert(each), updateTo: (each) => updatable.value.includes(each) ? each.update?.target || "" : null,
    updatesWaiting: updatable.value.length, setAside: plugins.tray.items.length, tiles: tiles.value, entityName: entities.entityName,
    settings: settingRows.value, plugins: pluginRows.value }, actions);
});
const grouped = computed(() => paletteGroups(items.value));

function close() { ui.palette = false; }
function run(item: PaletteItem) {
  recent.value = rememberChoice(recent.value, item.id);
  close();
  item.run();
}
// The arrows walk the results and stop at the ends, Enter runs the one in focus, a new search starts at the first.
const { active, onKey: walk } = useListNavigation(items, { onPick: run, resetOn: query,
  onMove: (index) => nextTick(() => document.getElementById(`palette-item-${index}`)?.scrollIntoView?.({ block: "nearest" })) });
function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") { e.preventDefault(); close(); }
  else walk(e);
}
watch(() => ui.palette, async (shown) => {
  if (!shown) return;
  query.value = ""; active.value = 0;
  if (plugins.pluginsEnabled) plugins.loadPlugins();
  await nextTick();
  input.value?.focus();
}, { immediate: true });
</script>

<template>
  <div v-if="ui.palette" class="palette-backdrop" @click="close">
    <div class="palette" role="dialog" aria-modal="true" :aria-label="t('editor.sidebar.search')" @click.stop @keydown="onKey">
      <input ref="input" v-model="query" id="palette-input" :placeholder="t('editor.palette.placeholder')" :aria-label="t('editor.sidebar.search')" autocomplete="off"
        role="combobox" aria-expanded="true" aria-controls="palette-list" aria-autocomplete="list" :aria-activedescendant="items.length ? `palette-item-${active}` : undefined" />
      <div ref="list" id="palette-list" class="palette-list" role="listbox" :aria-label="t('editor.sidebar.search')">
        <div v-for="g in grouped" :key="g.group" role="group" :aria-label="g.group">
          <div class="palette-group" aria-hidden="true">{{ g.group }}</div>
          <button v-for="{ item, index } in g.items" :id="`palette-item-${index}`" :key="item.id" type="button" role="option" class="palette-item"
            :class="{ active: index === active }" :aria-selected="index === active" :data-id="item.id" tabindex="-1" @mousemove="active = index" @click="run(item)">
            <span v-if="item.icon" class="mdi">{{ glyph(item.icon) }}</span>
            <span v-else class="glyph">{{ item.glyphText || "›" }}</span>
            <span class="tx"><span>{{ item.label }}</span><small v-if="item.detail">{{ item.detail }}</small></span>
            <kbd v-if="item.key" class="hint-key">{{ item.key }}</kbd>
            <span v-else-if="item.hint && index === active" class="palette-hint" aria-hidden="true">{{ item.hint }} <kbd>↵</kbd></span>
          </button>
        </div>
        <p v-if="!items.length" class="palette-empty">{{ t("editor.palette.empty") }}</p>
      </div>
      <div class="palette-foot" aria-hidden="true">
        <span><kbd>↑</kbd><kbd>↓</kbd>{{ t("editor.search.keys.move") }}</span>
        <span><kbd>↵</kbd>{{ t("editor.search.keys.choose") }}</span>
        <span><kbd>esc</kbd>{{ t("editor.search.keys.close") }}</span>
      </div>
    </div>
  </div>
</template>
