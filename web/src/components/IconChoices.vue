<script setup lang="ts">
// The icons to choose from: a search, automatic, optionally none, and the set by group. A choice applies at once and the
// list stays, with its search and scroll position. With a `tile`, the icon the pointer rests on is drawn on that tile
// before it is picked (app 0.4.32). IconPicker shows it under its field; the top bar's inspector in place of an item's
// settings, under the bar that shows the choice (app 0.4.89).
import { computed, ref } from "vue";
import { t } from "../i18n";
import { glyph } from "../model/topbar";
import { iconGroupsMatching } from "../model/search";
import Icon from "./ui/Icon.vue";
import type { Tile } from "../types";
import { useInventoryStore } from "../stores/inventory";
import { useInspectorStore } from "../stores/inspector";

const inv = useInventoryStore();
const insp = useInspectorStore();

const props = defineProps<{ selected: string; automatic: string; autoLabel: string; allowNone?: boolean; tile?: Tile }>();
const emit = defineEmits<{ (e: "pick", name: string): void }>();
const query = ref("");
function show(name: string | null) {
  if (!props.tile?.id) return;
  if (name && name !== props.selected) insp.optionPreview = { tileId: props.tile.id, key: "icon", value: name };
  else if (insp.optionPreview?.key === "icon") insp.optionPreview = null;
}
function pick(name: string) { show(null); emit("pick", name); }
const groups = computed(() => iconGroupsMatching(inv.inventory.icons?.groups || [], query.value));
</script>

<template>
  <div class="picker" @pointerleave="show(null)">
    <label class="search-field"><Icon name="magnify" /><input v-model="query" type="search" :placeholder="t('editor.icon.search')" :aria-label="t('editor.icon.search_label')" /></label>
    <button type="button" class="icon-choice icon-auto" :aria-pressed="selected === 'auto' ? 'true' : 'false'" :title="autoLabel" @pointerenter="show('auto')" @click="pick('auto')">
      <span class="mdi">{{ automatic ? glyph(automatic) : "" }}</span><span>{{ autoLabel }}</span>
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
</template>
