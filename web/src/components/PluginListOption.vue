<script setup lang="ts">
// An option of a plugin tile that keeps several values, or one found by searching (plugin API 0.12): the values as a
// list of rows in the order the person put them (dragged into another, taken off with ×), and a way to add one: the
// choices in a picker (the plugin's own, from its fetch, or found by what is typed), or a text typed in. A choice keeps
// each pick with the words the person saw, so a list found by searching still reads right when that search is gone.
import { computed, onBeforeUnmount, ref } from "vue";
import { t } from "../i18n";
import { useSortableRows } from "../composables/useSortableRows";
import { keepsPicks, listValue, optionsFit, picksOf, text, type Plugin, type PluginTileOption } from "../model/plugins";
import type { PluginPick, PluginValue } from "../types";
import { usePluginsStore } from "../stores/plugins";
import Icon from "./ui/Icon.vue";
import UiPicker from "./ui/UiPicker.vue";

const props = defineProps<{ plugin: Plugin; option: PluginTileOption; values: Record<string, PluginValue> }>();
const emit = defineEmits<{ change: [value: PluginValue] }>();
const plugins = usePluginsStore();
const T = (name: string, values?: Record<string, unknown>) => t(`editor.plugin_tile.${name}`, values || {});

const many = computed(() => Boolean(props.option.multiple));
const value = computed(() => props.values[props.option.id]);
// A list's values, or the one pick of a single choice found by searching.
const picks = computed<PluginPick[]>(() => (many.value ? picksOf(value.value)
  : typeof value.value === "object" && value.value && !Array.isArray(value.value) ? picksOf([value.value]) : []));
// The words a row shows: a choice of the plugin's own list in the editor's language, else the words kept with it.
function words(pick: PluginPick) {
  const own = props.option.choices?.find((choice) => choice.value === pick.value);
  return own ? text(own.label) : pick.label || pick.value;
}

// ---- Adding ----
const room = computed(() => !many.value || picks.value.length < (props.option.multiple || 0));
const query = ref("");
const typed = ref("");
let wait: ReturnType<typeof setTimeout> | undefined;
// What the person types reaches the plugin's search a moment after the last key, so a word is one question.
function search(text: string) {
  clearTimeout(wait);
  wait = setTimeout(() => { typed.value = text; }, 300);
}
onBeforeUnmount(() => clearTimeout(wait));
const offered = computed(() => {
  const taken = new Set(picks.value.map((pick) => pick.value));
  return plugins.choicesFor(props.plugin, props.option, props.values, typed.value)
    .filter((choice) => !taken.has(choice.value)).map((choice) => ({ id: choice.value, name: text(choice.label) }));
});
const busy = computed(() => Boolean(props.option.search && [...typed.value.trim()].length >= 2 &&
  plugins.choicesPending(props.plugin, props.option, props.values, typed.value)));
const empty = computed(() => (props.option.search && [...typed.value.trim()].length < 2 ? T("search_more") : T("none_found")));
// The tile's options go to the screen with its data in one message: what would not fit there is not taken.
const full = ref(false);
function keep(next: PluginPick[]) {
  const kept: PluginValue = many.value ? listValue(props.option, next) : next[0] ? { ...next[0] } : "";
  full.value = !optionsFit({ ...props.values, [props.option.id]: kept });
  if (!full.value) emit("change", kept);
}
function add(id: string) {
  const name = offered.value.find((item) => item.id === id)?.name || id;
  keep(many.value ? [...picks.value, { value: id, label: name }] : [{ value: id, label: name }]);
}
function addText() {
  const word = query.value.trim();
  if (!word || [...word].length > 64 || picks.value.some((pick) => pick.value === word)) return;
  keep([...picks.value, { value: word, label: word }]);
  if (!full.value) query.value = "";
}
function remove(row: number) {
  full.value = false;
  keep(picks.value.filter((_, i) => i !== row));
}

// ---- Order ----
const listId = computed(() => `plugin-list-${props.option.id}`);
const sort = useSortableRows<PluginPick>({ rows: `#plugin-list-${props.option.id} > .item`, items: () => picks.value, commit: keep,
  skip: "button", grip: ".grip", enabled: () => many.value && picks.value.length > 1 });
const shown = computed(() => sort.live.value || picks.value);
const fromList = computed(() => props.option.kind === "choice");
</script>

<template>
  <div class="plugin-list" :class="{ single: !many }">
    <div v-if="shown.length" :id="listId" class="items" role="list" :aria-label="text(option.label)">
      <div v-for="(pick, row) in shown" :key="pick.value" class="item plugin-list-item" role="listitem" tabindex="0"
        :class="{ 'dragging-chip': sort.drag.value.active && sort.drag.value.index === row, single: shown.length < 2 }"
        @pointerdown="sort.down($event, row)" @keydown="sort.key($event, row)">
        <span class="tx"><b>{{ words(pick) }}</b></span>
        <Icon v-if="shown.length > 1" name="drag-vertical" class="grip" />
        <button type="button" class="x" :aria-label="T('remove', { name: words(pick) })" @click="remove(row)"><Icon name="close" /></button>
      </div>
    </div>
    <template v-if="room">
      <UiPicker v-if="fromList" :id="`plugin-option-${option.id}`" :items="offered" :remote="option.search" :busy="busy"
        :placeholder="T(option.search ? 'search' : 'find')" :empty="empty" @search="search" @pick="add">
        <template #trigger>
          <button type="button" class="ghost-btn plugin-list-add"><Icon :name="many ? 'plus' : 'magnify'" />{{ T(many ? "add" : (picks.length ? "change" : "choose")) }}</button>
        </template>
      </UiPicker>
      <form v-else class="plugin-list-type" @submit.prevent="addText">
        <input :id="`plugin-option-${option.id}`" v-model="query" type="text" maxlength="64" autocomplete="off" :placeholder="T('type')" />
        <button type="submit" class="btn quiet mini" :disabled="!query.trim()" :aria-label="T('add')"><Icon name="plus" /></button>
      </form>
    </template>
    <small v-if="full" class="help warn">{{ T("full") }}</small>
  </div>
</template>

<style scoped>
.plugin-list { display: grid; gap: 6px; }
.plugin-list-item { cursor: grab; }
.plugin-list-item.single { cursor: default; }
.plugin-list-item .grip { color: var(--muted); opacity: 0.6; font-size: 16px; touch-action: none; }
.plugin-list-type { display: flex; gap: 6px; align-items: center; }
.plugin-list-type input { flex: 1; min-width: 0; }
</style>
