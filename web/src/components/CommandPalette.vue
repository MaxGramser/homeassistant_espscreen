<script setup lang="ts">
// ⌘K: screens, entities for the open screen, and the editor's actions, from one search field.
import { computed, nextTick, ref, watch } from "vue";
import { t } from "../i18n";
import { domainInfo } from "../model/layout";
import { glyph } from "../model/topbar";
import { addTile, automaticIcon, canAlert, currentScreen, exportLayout, go, identify, repeatable, save, select, state, tileLimit } from "../store";

type Item = { group: string; label: string; detail?: string; icon?: string; glyphText?: string; key?: string; run: () => void };
const query = ref("");
const active = ref(0);
const input = ref<HTMLInputElement | null>(null);
const items = computed<Item[]>(() => {
  const q = query.value.trim().toLocaleLowerCase();
  const list: Item[] = [];
  const screens = t("editor.palette.groups.screens"), actionsGroup = t("editor.palette.groups.actions");
  for (const screen of state.inventory.screens)
    list.push({ group: screens, label: screen.name, detail: `${screen.online ? t("editor.common.online") : t("editor.common.offline")} · ${screen.firmware || t("editor.common.unknown")}`, glyphText: "▦", run: () => select(screen.id) });
  const screen = currentScreen.value;
  const actions: Item[] = [
    { group: actionsGroup, label: t("editor.nav.new_screen"), detail: t("editor.nav.new_screen_detail"), glyphText: "+", run: () => go("#new-screen") },
    { group: actionsGroup, label: t("editor.nav.firmware"), icon: "F0241", run: () => go("#firmware") },
    { group: actionsGroup, label: t("editor.nav.alerts"), detail: t("editor.palette.alerts_detail"), icon: "F0594", run: () => go("#alerts") },
    { group: actionsGroup, label: t("editor.nav.settings"), detail: t("editor.palette.settings_detail"), icon: "F0493", run: () => go("#settings") },
  ];
  if (screen && state.layout) {
    actions.unshift(
      { group: actionsGroup, label: t("editor.common.save_send"), detail: state.dirty ? t("editor.common.unsaved") : t("editor.palette.nothing_to_save"), key: "⌘S", run: () => save() },
      { group: actionsGroup, label: t("editor.screen_view.tabs.layout"), detail: screen.name, run: () => { go(""); state.tab = "layout"; } },
      { group: actionsGroup, label: t("editor.screen_view.tabs.settings"), detail: screen.name, run: () => { go(""); state.tab = "settings"; } },
      { group: actionsGroup, label: t("editor.palette.identify"), detail: canAlert(screen) ? t("editor.palette.identify_detail") : t("editor.palette.identify_needs"), run: () => { if (canAlert(screen)) identify(screen); } },
      { group: actionsGroup, label: t("editor.palette.export"), detail: t("editor.palette.export_detail"), run: exportLayout },
    );
  }
  list.push(...actions);
  if (screen && state.layout && q) {
    const chosen = new Set(state.layout.tiles.map((t) => t.entity));
    const full = state.layout.tiles.length >= tileLimit.value;
    for (const e of state.inventory.entities) {
      // One on the screen comes again when the firmware takes an entity on several tiles (0.16.0+).
      if (e.tile === false || (chosen.has(e.id) && !repeatable(e.id))) continue;
      if (!`${e.name} ${e.id} ${e.area || ""} ${e.device || ""}`.toLocaleLowerCase().includes(q)) continue;
      list.push({ group: t("editor.palette.groups.add"), label: e.name, detail: [domainInfo(e.id)[0], e.area].filter(Boolean).join(" · "), icon: state.inventory.icons ? automaticIcon(e.id) : undefined,
        run: () => { if (!full) addTile(e.id); } });
      if (list.length > 60) break;
    }
  }
  return q ? list.filter((i) => `${i.label} ${i.detail || ""}`.toLocaleLowerCase().includes(q)) : list;
});
const grouped = computed(() => {
  const out: { group: string; items: { item: Item; index: number }[] }[] = [];
  items.value.forEach((item, index) => {
    const g = out.find((o) => o.group === item.group) || (out.push({ group: item.group, items: [] }), out[out.length - 1]);
    g.items.push({ item, index });
  });
  return out;
});
function close() { state.palette = false; }
function run(item: Item) { close(); item.run(); }
function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") { e.preventDefault(); close(); }
  else if (e.key === "ArrowDown") { e.preventDefault(); active.value = Math.min(items.value.length - 1, active.value + 1); }
  else if (e.key === "ArrowUp") { e.preventDefault(); active.value = Math.max(0, active.value - 1); }
  else if (e.key === "Enter") { e.preventDefault(); const item = items.value[active.value]; if (item) run(item); }
}
watch(query, () => (active.value = 0));
watch(() => state.palette, async (open) => { if (open) { query.value = ""; active.value = 0; await nextTick(); input.value?.focus(); } });
</script>

<template>
  <div v-if="state.palette" class="palette-backdrop" @click="close">
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
