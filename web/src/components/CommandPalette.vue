<script setup lang="ts">
// ⌘K: screens, entities for the open screen, and the editor's actions, from one search field (model/palette.ts).
import { computed, nextTick, ref, watch } from "vue";
import { t } from "../i18n";
import { useListNavigation } from "../composables/useListNavigation";
import { paletteGroups, paletteItems, type PaletteActions, type PaletteItem } from "../model/palette";
import { glyph } from "../model/topbar";
import { useUiStore } from "../stores/ui";
import { useEntitiesStore } from "../stores/entities";
import { useScreenStore } from "../stores/screen";
import { useSessionStore } from "../stores/session";
import { useInventoryStore } from "../stores/inventory";
import { addTile } from "../editor/tiles";
import { useDocumentStore } from "../stores/document";

const ui = useUiStore();
const entities = useEntitiesStore();
const scr = useScreenStore();
const session = useSessionStore();
const inv = useInventoryStore();
const doc = useDocumentStore();

const query = ref("");
const input = ref<HTMLInputElement | null>(null);
// What a row does, by what it is.
const actions: PaletteActions = {
  openScreen: (screen) => session.select(screen.id),
  go: (route) => ui.go(route),
  showTab: (tab) => { ui.go(""); ui.tab = tab; },
  save: () => doc.save(),
  identify: (screen) => scr.identify(screen),
  exportLayout: () => doc.exportLayout(),
  addTile: (id) => addTile(id),
};
const items = computed(() => {
  const screen = scr.currentScreen && doc.layout ? scr.currentScreen : null;
  return paletteItems({ query: query.value, screens: inv.inventory.screens, open: screen, dirty: doc.dirty, alerts: Boolean(screen && scr.canAlert(screen)),
    entities: inv.inventory.entities, placed: new Set(doc.layout?.tiles.map((tile) => tile.entity) || []), repeatable: scr.repeatable,
    full: (doc.layout?.tiles.length || 0) >= doc.tileLimit, icon: inv.inventory.icons ? entities.automaticIcon : undefined }, actions);
});
const grouped = computed(() => paletteGroups(items.value));
function close() { ui.palette = false; }
function run(item: PaletteItem) { close(); item.run(); }
// The arrows walk the results and stop at the ends, Enter runs the one in focus, a new search starts at the first.
const { active, onKey: walk } = useListNavigation(items, { onPick: run, resetOn: query });
function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") { e.preventDefault(); close(); }
  else walk(e);
}
watch(() => ui.palette, async (open) => { if (open) { query.value = ""; active.value = 0; await nextTick(); input.value?.focus(); } });
</script>

<template>
  <div v-if="ui.palette" class="palette-backdrop" @click="close">
    <div class="palette" role="dialog" :aria-label="t('editor.sidebar.search')" @click.stop @keydown="onKey">
      <input ref="input" v-model="query" id="palette-input" :placeholder="t('editor.palette.placeholder')" :aria-label="t('editor.sidebar.search')" autocomplete="off" />
      <div class="palette-list">
        <template v-for="g in grouped" :key="g.group">
          <div class="palette-group">{{ g.group }}</div>
          <button v-for="{ item, index } in g.items" :key="index" type="button" class="palette-item" :class="{ active: index === active }" @mouseenter="active = index" @click="run(item)">
            <span v-if="item.icon" class="mdi">{{ glyph(item.icon) }}</span>
            <span v-else class="glyph">{{ item.glyphText || "›" }}</span>
            <span class="tx"><span>{{ item.label }}</span><small v-if="item.detail">{{ item.detail }}</small></span>
            <kbd v-if="item.key" class="hint-key">{{ item.key }}</kbd>
          </button>
        </template>
        <p v-if="!items.length" class="palette-empty">{{ t("editor.palette.empty") }}</p>
      </div>
    </div>
  </div>
</template>
