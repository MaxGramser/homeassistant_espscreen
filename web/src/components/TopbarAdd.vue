<script setup lang="ts">
// Adding to the top bar: the screen's own items, Home Assistant's suggestions, or any entity.
import { computed, ref } from "vue";
import { t } from "../i18n";
import { BUILTIN_ICONS, clockText, dateText, glyph, itemKey } from "../model/topbar";
import { addTopbarItem, automaticIcon, clock24, closeInspector, iconNamed, openBar, screenLanguage, state, topbarItems, topbarMax } from "../store";
import type { HeaderItem } from "../types";
import Icon from "./ui/Icon.vue";
import InspectorHead from "./ui/InspectorHead.vue";

const query = ref("");
const taken = computed(() => new Set(topbarItems().map(itemKey)));
const samples = computed(() => ({
  clock: clockText(clock24.value, new Date(state.now), screenLanguage.value),
  analog: t("editor.topbar.analog_sample"),
  date: dateText(new Date(state.now), screenLanguage.value),
} as Record<string, string>));
const suggested = computed(() => state.inventory.header?.suggestions?.[state.selected || ""] || []);
const matches = computed(() => {
  const q = query.value.trim().toLocaleLowerCase();
  return state.inventory.entities.filter((e) => `${e.name} ${e.id} ${e.area || ""} ${e.device || ""}`.toLocaleLowerCase().includes(q));
});
const entityItem = (id: string): HeaderItem => ({ type: "entity", entity: id, content: "state", icon: "auto", show: "always" });
</script>

<template>
  <InspectorHead :title="t('editor.topbar.add.title')" icon="plus"
    :crumbs="[{ text: t('editor.topbar.title'), open: () => openBar(-1) }, { text: t('editor.topbar.add.slots', { used: topbarItems().length }, topbarMax()) }]" />
  <div class="dr-body">
    <div class="f">
      <span class="f-label">{{ t("editor.topbar.add.builtin") }}</span>
      <div class="options">
        <button v-for="b in state.inventory.header?.builtin || []" :key="b.type" type="button" class="option" :disabled="taken.has(itemKey({ type: b.type }))" @click="addTopbarItem({ type: b.type })">
          <span class="mdi">{{ glyph(iconNamed(BUILTIN_ICONS[b.type])?.cp || "F0150") }}</span>
          <span class="tx"><strong>{{ b.label }}</strong><small>{{ taken.has(itemKey({ type: b.type })) ? t("editor.topbar.add.added") : samples[b.type] }}</small></span>
        </button>
      </div>
    </div>
    <div v-if="suggested.length" class="f">
      <span class="f-label">{{ t("editor.topbar.add.suggestions") }}</span>
      <div class="options">
        <button v-for="s in suggested" :key="itemKey(s.item)" type="button" class="option" :disabled="taken.has(itemKey(s.item))" @click="addTopbarItem(s.item)">
          <span class="mdi">{{ glyph(s.icon || automaticIcon(s.item.entity!)) }}</span>
          <span class="tx"><strong>{{ s.label }}</strong><small>{{ taken.has(itemKey(s.item)) ? t("editor.topbar.add.added") : [s.name, s.area].filter(Boolean).join(" · ") }}</small></span>
        </button>
      </div>
    </div>
    <div class="f">
      <label class="f-label" for="topbar-search">{{ t("editor.topbar.add.entity") }}</label>
      <label class="search-field"><Icon name="magnify" /><input id="topbar-search" v-model="query" type="search" :placeholder="t('editor.topbar.add.search')" :aria-label="t('editor.topbar.add.search_label')" /></label>
      <div class="options">
        <button v-for="e in matches.slice(0, 40)" :key="e.id" type="button" class="option" :disabled="taken.has(itemKey(entityItem(e.id)))" @click="addTopbarItem(entityItem(e.id))">
          <span class="mdi">{{ glyph(automaticIcon(e.id)) }}</span>
          <span class="tx"><strong>{{ e.name }}</strong><small>{{ [e.area, e.id].filter(Boolean).join(" · ") }}</small></span>
        </button>
        <p v-if="!matches.length" class="hint">{{ t("editor.topbar.add.none_found") }}</p>
        <p v-else-if="matches.length > 40" class="hint">{{ t("editor.common.results", matches.length) }}</p>
      </div>
    </div>
  </div>
  <div class="dr-foot">
    <span class="spacer"></span>
    <button type="button" class="btn quiet" @click="closeInspector">{{ t("editor.common.cancel") }}</button>
  </div>
</template>
