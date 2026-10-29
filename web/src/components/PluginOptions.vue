<script setup lang="ts">
// The options of a plugin's tile or screensaver (docs/PLUGINS.md), drawn with the inspector's own rows: a toggle, a
// choice, a number with its steps, a text, or a list of values (PluginListOption). A choice can come from one of the
// plugin's fetches (the lines of a stop): the add-on asks the plugin's service with the other options and hands back only
// the choices. The tile's inspector and the screensaver's drawer share it, so an option behaves the same in both.
import { editorNumber, t } from "../i18n";
import { picksOf, text, type Plugin, type PluginTileOption } from "../model/plugins";
import type { PluginValue } from "../types";
import PluginListOption from "./PluginListOption.vue";
import Icon from "./ui/Icon.vue";
import PropRow from "./ui/PropRow.vue";
import SwitchRow from "./ui/SwitchRow.vue";
import UiSelect from "./ui/UiSelect.vue";
import UiPicker from "./ui/UiPicker.vue";
import { usePluginsStore } from "../stores/plugins";

const plugins = usePluginsStore();
const props = defineProps<{ plugin: Plugin; options: PluginTileOption[]; values: Record<string, PluginValue> }>();
const emit = defineEmits<{ change: [option: PluginTileOption, value: PluginValue] }>();
const set = (option: PluginTileOption, value: PluginValue) => emit("change", option, value);

const choices = (option: PluginTileOption) => plugins.choicesFor(props.plugin, option, props.values).map((choice) => [choice.value, text(choice.label)] as [string, string]);
const fromFetch = (option: PluginTileOption) => Boolean(option.options_from);
const isList = (option: PluginTileOption) => Boolean(option.multiple || (option.kind === "choice" && option.search));
const count = (option: PluginTileOption) => t("editor.plugin_tile.count", { n: picksOf(props.values[option.id]).length, max: option.multiple });
const number = (value: number) => editorNumber(value);
const entityItems = (option: PluginTileOption) => plugins.entitiesIn(option.domains || []);
const entityName = (option: PluginTileOption) => {
  const id = String(props.values[option.id] ?? "");
  return entityItems(option).find((item) => item.id === id)?.name || id || t("editor.plugin_tile.choose");
};
function step(option: PluginTileOption, by: number) {
  const now = Number(props.values[option.id] ?? option.min ?? 0);
  set(option, Math.min(option.max ?? Infinity, Math.max(option.min ?? -Infinity, now + by * (option.step ?? 1))));
}
</script>

<template>
  <template v-for="option in options" :key="option.id">
    <SwitchRow v-if="option.kind === 'toggle'" :label="text(option.label)" :description="option.hint ? text(option.hint) : undefined"
      :model-value="Boolean(values[option.id])" @update:model-value="(on: boolean) => set(option, on)" />
    <PropRow v-else-if="isList(option)" :label="text(option.label)" icon="format-list-bulleted" :hint="option.hint ? text(option.hint) : undefined" stack>
      <template v-if="option.multiple" #aside>{{ count(option) }}</template>
      <PluginListOption :plugin="plugin" :option="option" :values="values" @change="(value: PluginValue) => set(option, value)" />
    </PropRow>
    <PropRow v-else :label="text(option.label)" :icon="option.kind === 'entity' ? 'link-variant' : 'tune-variant'"
      :hint="option.hint ? text(option.hint) : undefined" :for="`plugin-option-${option.id}`" :stack="option.kind === 'entity'">
      <UiPicker v-if="option.kind === 'entity'" :id="`plugin-option-${option.id}`" :items="entityItems(option)"
        :placeholder="t('editor.plugin_tile.search')" :empty="t('editor.plugin_tile.none_found')" @pick="(value: string) => set(option, value)">
        <template #trigger>
          <button type="button" class="ghost-btn"><Icon name="magnify" />{{ entityName(option) }}</button>
        </template>
      </UiPicker>
      <button v-if="option.kind === 'entity' && values[option.id]" type="button" class="btn quiet mini"
        :aria-label="t('editor.plugin_tile.remove', { name: entityName(option) })" @click="set(option, '')"><Icon name="close" /></button>
      <UiSelect v-else-if="option.kind === 'choice'" :id="`plugin-option-${option.id}`" :model-value="String(values[option.id] ?? '')"
        :options="choices(option)" :placeholder="t('editor.plugin_tile.choose')" @update:model-value="(value: string) => set(option, value)" />
      <span v-else-if="option.kind === 'number'" class="plugin-stepper">
        <button type="button" class="btn quiet mini" :aria-label="t('editor.plugin_tile.less')" @click="step(option, -1)"><Icon name="minus" /></button>
        <b>{{ number(Number(values[option.id] ?? option.min ?? 0)) }}{{ option.unit ? ` ${option.unit}` : "" }}</b>
        <button type="button" class="btn quiet mini" :aria-label="t('editor.plugin_tile.more')" @click="step(option, 1)"><Icon name="plus" /></button>
      </span>
      <input v-else :id="`plugin-option-${option.id}`" type="text" :value="String(values[option.id] ?? '')" autocomplete="off"
        @change="set(option, ($event.target as HTMLInputElement).value)" />
      <template v-if="fromFetch(option)" #note><small class="help">{{ t("editor.plugin_tile.from_fetch") }}</small></template>
    </PropRow>
  </template>
</template>
