<script setup lang="ts">
// Choosing an entity item: Home Assistant's suggestions for this screen, then any entity the top bar can show. The top
// bar's add list and the screensaver clock's share it; `accepts` narrows the suggestions, `taken` marks what is in.
import { computed, ref } from "vue";
import { t } from "../i18n";
import { entityItem, glyph, itemKey } from "../model/topbar";
import { automaticIcon, state } from "../store";
import type { HeaderItem } from "../types";
import Icon from "./ui/Icon.vue";
import rules from "../model/page-rules.json";

const props = defineProps<{ id: string; taken: (item: HeaderItem) => boolean; accepts?: (item: HeaderItem) => boolean }>();
const emit = defineEmits<{ pick: [item: HeaderItem] }>();
const query = ref("");
const suggested = computed(() => (state.inventory.header?.suggestions?.[state.selected || ""] || []).filter((s) => !props.accepts || props.accepts(s.item)));
const matches = computed(() => {
  const q = query.value.trim().toLocaleLowerCase();
  // Only what the top bar can show (the add-on's header domains, app 0.4.1): a camera or an image is a tile, not a value.
  return state.inventory.entities.filter((e) => rules.headerDomains.includes(e.id.split(".")[0]) && `${e.name} ${e.id} ${e.area || ""} ${e.device || ""}`.toLocaleLowerCase().includes(q));
});
</script>

<template>
  <div v-if="suggested.length" class="f">
    <span class="f-label">{{ t("editor.topbar.add.suggestions") }}</span>
    <div class="options">
      <button v-for="s in suggested" :key="itemKey(s.item)" type="button" class="option" :disabled="taken(s.item)" @click="emit('pick', s.item)">
        <span class="mdi">{{ glyph(s.icon || automaticIcon(s.item.entity!)) }}</span>
        <span class="tx"><strong>{{ s.label }}</strong><small>{{ taken(s.item) ? t("editor.topbar.add.added") : [s.name, s.area].filter(Boolean).join(" · ") }}</small></span>
      </button>
    </div>
  </div>
  <div class="f">
    <label class="f-label" :for="id">{{ t("editor.topbar.add.entity") }}</label>
    <label class="search-field"><Icon name="magnify" /><input :id="id" v-model="query" type="search" :placeholder="t('editor.topbar.add.search')" :aria-label="t('editor.topbar.add.search_label')" /></label>
    <div class="options">
      <button v-for="e in matches.slice(0, 40)" :key="e.id" type="button" class="option" :disabled="taken(entityItem(e.id))" @click="emit('pick', entityItem(e.id))">
        <span class="mdi">{{ glyph(automaticIcon(e.id)) }}</span>
        <span class="tx"><strong>{{ e.name }}</strong><small>{{ [e.area, e.id].filter(Boolean).join(" · ") }}</small></span>
      </button>
      <p v-if="!matches.length" class="hint">{{ t("editor.topbar.add.none_found") }}</p>
      <p v-else-if="matches.length > 40" class="hint">{{ t("editor.common.results", matches.length) }}</p>
    </div>
  </div>
</template>
