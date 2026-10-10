<script setup lang="ts">
// The icon choice for tiles and top bar items: automatic, optionally none, or one from the set.
// A choice applies live; the open picker keeps its search and scroll position. With a `tile`, the icon the pointer
// rests on is drawn on that tile before it is picked (app 0.4.32).
import { computed, ref } from "vue";
import { t } from "../i18n";
import { glyph } from "../model/topbar";
import { matchesQuery } from "../model/search";
import { iconNamed, state } from "../store";
import Icon from "./ui/Icon.vue";
import PropRow from "./ui/PropRow.vue";
import type { Tile } from "../types";

const props = defineProps<{ selected: string; automatic: string; autoLabel: string; allowNone?: boolean; note?: string; tile?: Tile }>();
const emit = defineEmits<{ (e: "pick", name: string): void }>();
const query = ref("");
const chosen = computed(() => iconNamed(props.selected));
const currentGlyph = computed(() => (props.selected === "none" ? "" : glyph(chosen.value?.cp || props.automatic)));
const currentText = computed(() => (props.selected === "none" ? t("editor.icon.none") : chosen.value?.label || props.autoLabel));
function show(name: string | null) {
  if (!props.tile?.id) return;
  if (name && name !== props.selected) state.optionPreview = { tileId: props.tile.id, key: "icon", value: name };
  else if (state.optionPreview?.key === "icon") state.optionPreview = null;
}
function pick(name: string) { show(null); emit("pick", name); }
const groups = computed(() => {
  return (state.inventory.icons?.groups || []).map((group) => ({
    label: group.label,
    icons: group.icons.filter((i) => matchesQuery(query.value, i.label, i.name.replaceAll("-", " "), group.label)),
  })).filter((g) => g.icons.length);
});
</script>

<template>
  <PropRow :label="t('editor.icon.label')" icon="tablet-dashboard">
    <button type="button" class="choice-field" :aria-expanded="state.iconPickerOpen ? 'true' : 'false'" :data-state="state.iconPickerOpen ? 'open' : 'closed'" @click="state.iconPickerOpen = !state.iconPickerOpen">
      <span class="choice-glyph mdi" aria-hidden="true">{{ currentGlyph }}</span>
      <span class="choice-text">{{ currentText }}</span>
      <Icon :name="state.iconPickerOpen ? 'chevron-up' : 'chevron-down'" />
    </button>
    <template v-if="state.iconPickerOpen || note" #note>
      <div v-if="state.iconPickerOpen" class="picker" @pointerleave="show(null)">
        <label class="search-field"><Icon name="magnify" /><input v-model="query" type="search" :placeholder="t('editor.icon.search')" :aria-label="t('editor.icon.search_label')" /></label>
        <button type="button" class="icon-choice icon-auto" :aria-pressed="selected === 'auto' ? 'true' : 'false'" :title="autoLabel" @pointerenter="show('auto')" @click="pick('auto')">
          <span class="mdi">{{ glyph(automatic) }}</span><span>{{ autoLabel }}</span>
        </button>
        <button v-if="allowNone" type="button" class="icon-choice icon-auto" :aria-pressed="selected === 'none' ? 'true' : 'false'" :title="t('editor.icon.none')" @pointerenter="show('none')" @click="pick('none')">
          <span class="mdi"></span><span>{{ t("editor.icon.none_text_only") }}</span>
        </button>
        <div class="icon-list">
          <section v-for="group in groups" :key="group.label">
            <small>{{ group.label }}</small>
            <div class="icon-grid">
              <button v-for="icon in group.icons" :key="icon.name" type="button" class="icon-choice" :title="icon.label" :aria-label="t('editor.icon.aria', { name: icon.label })"
                :aria-pressed="selected === icon.name ? 'true' : 'false'" @pointerenter="show(icon.name)" @click="pick(icon.name)"><span class="mdi">{{ glyph(icon.cp) }}</span></button>
            </div>
          </section>
          <p v-if="!groups.length" class="hint">{{ t("editor.icon.none_found") }}</p>
        </div>
      </div>
      <small v-if="note" class="help">{{ note }}</small>
    </template>
  </PropRow>
</template>
