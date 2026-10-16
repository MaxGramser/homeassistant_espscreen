<script setup lang="ts">
// The icon choice for tiles and top bar items: automatic, optionally none, or one from the set (IconChoices, under the
// field while it is open). A choice applies live; the open picker keeps its search and scroll position. With a `tile`,
// the icon the pointer rests on is drawn on that tile before it is picked (app 0.4.32).
import { computed } from "vue";
import { t } from "../i18n";
import { glyph } from "../model/topbar";
import Icon from "./ui/Icon.vue";
import PropRow from "./ui/PropRow.vue";
import IconChoices from "./IconChoices.vue";
import type { Tile } from "../types";
import { useEntitiesStore } from "../stores/entities";
import { useInspectorStore } from "../stores/inspector";

const entities = useEntitiesStore();
const insp = useInspectorStore();

// `aside`: the icons open in the place of the settings around it (the top bar's inspector, app 0.4.89), not under the field.
const props = defineProps<{ selected: string; automatic: string; autoLabel: string; allowNone?: boolean; note?: string; tile?: Tile; aside?: boolean }>();
const emit = defineEmits<{ (e: "pick", name: string): void }>();
const chosen = computed(() => entities.iconNamed(props.selected));
// No automatic icon (a page's own icon in the Dock, whose default is the page's picture) draws no glyph: an empty
// codepoint would throw and take the whole row with it.
const currentGlyph = computed(() => { const cp = props.selected === "none" ? "" : chosen.value?.cp || props.automatic; return cp ? glyph(cp) : ""; });
const currentText = computed(() => (props.selected === "none" ? t("editor.icon.none") : chosen.value?.label || props.autoLabel));
</script>

<template>
  <PropRow :label="t('editor.icon.label')" icon="tablet-dashboard">
    <button type="button" class="choice-field" :aria-expanded="insp.iconPickerOpen ? 'true' : 'false'" :data-state="insp.iconPickerOpen ? 'open' : 'closed'" @click="insp.iconPickerOpen = !insp.iconPickerOpen">
      <span class="choice-glyph mdi" aria-hidden="true">{{ currentGlyph }}</span>
      <span class="choice-text">{{ currentText }}</span>
      <Icon :name="aside ? 'chevron-right' : insp.iconPickerOpen ? 'chevron-up' : 'chevron-down'" />
    </button>
    <template v-if="(insp.iconPickerOpen && !aside) || note" #note>
      <IconChoices v-if="insp.iconPickerOpen && !aside" :selected="selected" :automatic="automatic" :auto-label="autoLabel" :allow-none="allowNone" :tile="tile" @pick="(name) => emit('pick', name)" />
      <small v-if="note" class="help">{{ note }}</small>
    </template>
  </PropRow>
</template>
