<script setup lang="ts">
// The icon choice for tiles and top bar items: automatic, optionally none, or one from the set.
// A choice applies live; the open picker keeps its search and scroll position.
import { computed, ref } from "vue";
import { t } from "../i18n";
import { glyph } from "../model/topbar";
import { iconNamed, state } from "../store";
import Icon from "./ui/Icon.vue";

const props = defineProps<{ selected: string; automatic: string; autoLabel: string; allowNone?: boolean; note?: string }>();
const emit = defineEmits<{ (e: "pick", name: string): void }>();
const query = ref("");
const chosen = computed(() => iconNamed(props.selected));
const currentGlyph = computed(() => (props.selected === "none" ? "" : glyph(chosen.value?.cp || props.automatic)));
const currentText = computed(() => (props.selected === "none" ? t("editor.icon.none") : chosen.value?.label || props.autoLabel));
const groups = computed(() => {
  const q = query.value.trim().toLocaleLowerCase();
  return (state.inventory.icons?.groups || []).map((group) => ({
    label: group.label,
    icons: group.icons.filter((i) => !q || `${i.label} ${i.name.replaceAll("-", " ")} ${group.label}`.toLocaleLowerCase().includes(q)),
  })).filter((g) => g.icons.length);
});
</script>

<template>
  <div class="f">
    <span class="f-label">{{ t("editor.icon.label") }}</span>
    <button type="button" class="row" :aria-expanded="state.iconPickerOpen ? 'true' : 'false'" @click="state.iconPickerOpen = !state.iconPickerOpen">
      <span class="av mdi">{{ currentGlyph }}</span>
      <span class="tx"><b>{{ currentText }}</b></span>
      <Icon :name="state.iconPickerOpen ? 'chevron-up' : 'chevron-down'" class="row-chevron" />
    </button>
    <div v-if="state.iconPickerOpen" class="picker">
      <label class="search-field"><Icon name="magnify" /><input v-model="query" type="search" :placeholder="t('editor.icon.search')" :aria-label="t('editor.icon.search_label')" /></label>
      <button type="button" class="icon-choice icon-auto" :aria-pressed="selected === 'auto' ? 'true' : 'false'" :title="autoLabel" @click="emit('pick', 'auto')">
        <span class="mdi">{{ glyph(automatic) }}</span><span>{{ autoLabel }}</span>
      </button>
      <button v-if="allowNone" type="button" class="icon-choice icon-auto" :aria-pressed="selected === 'none' ? 'true' : 'false'" :title="t('editor.icon.none')" @click="emit('pick', 'none')">
        <span class="mdi"></span><span>{{ t("editor.icon.none_text_only") }}</span>
      </button>
      <div class="icon-list">
        <section v-for="group in groups" :key="group.label">
          <small>{{ group.label }}</small>
          <div class="icon-grid">
            <button v-for="icon in group.icons" :key="icon.name" type="button" class="icon-choice" :title="icon.label" :aria-label="t('editor.icon.aria', { name: icon.label })"
              :aria-pressed="selected === icon.name ? 'true' : 'false'" @click="emit('pick', icon.name)"><span class="mdi">{{ glyph(icon.cp) }}</span></button>
          </div>
        </section>
        <p v-if="!groups.length" class="hint">{{ t("editor.icon.none_found") }}</p>
      </div>
    </div>
    <small v-if="note" class="help">{{ note }}</small>
  </div>
</template>
