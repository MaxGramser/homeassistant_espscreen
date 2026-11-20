<script setup lang="ts">
// The options of a plugin's tile or screensaver (docs/PLUGINS.md), drawn with the inspector's own rows: a toggle, a
// choice, a number with its steps, a text, or a list of values (PluginListOption). A choice can come from one of the
// plugin's fetches (the lines of a stop): the add-on asks the plugin's service with the other options and hands back only
// the choices. The tile's inspector and the screensaver's drawer share it, so an option behaves the same in both.
// Plugin API 0.26: an entity option that says which entities it is for offers those, with a key under the list for every
// entity of its domains; a number that may stay empty is a field, which says what applies while it is empty.
import { reactive } from "vue";
import { editorNumber, t } from "../i18n";
import { entityFits, hasFilter, picksOf, placeholderNumber, text, typedNumber, type Plugin, type PluginTileOption } from "../model/plugins";
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
// `undefined` takes the option off the tile: a number that may stay empty, left empty.
const emit = defineEmits<{ change: [option: PluginTileOption, value: PluginValue | undefined] }>();
const set = (option: PluginTileOption, value: PluginValue | undefined) => emit("change", option, value);

const choices = (option: PluginTileOption) => plugins.choicesFor(props.plugin, option, props.values).map((choice) => [choice.value, text(choice.label)] as [string, string]);
const fromFetch = (option: PluginTileOption) => Boolean(option.options_from);
const isList = (option: PluginTileOption) => Boolean(option.multiple || (option.kind === "choice" && option.search));
const count = (option: PluginTileOption) => t("editor.plugin_tile.count", { n: picksOf(props.values[option.id]).length, max: option.multiple });
const number = (value: number) => editorNumber(value);
// The entities an option offers: those it is for (and always the one it has), or every entity of its domains once the
// person asked for them under the list. An option that names no kind of entity offers them all.
const everything = reactive<Record<string, boolean>>({});
const entitiesOf = (option: PluginTileOption) => plugins.entitiesIn(option.domains || []);
const entityItems = (option: PluginTileOption) => {
  const all = entitiesOf(option);
  if (!hasFilter(option) || everything[option.id]) return all;
  const chosen = String(props.values[option.id] ?? "");
  return all.filter((item) => item.id === chosen || entityFits(option, item.id, plugins.entityFacts[item.id]));
};
const entityName = (option: PluginTileOption) => {
  const id = String(props.values[option.id] ?? "");
  return entitiesOf(option).find((item) => item.id === id)?.name || id || t("editor.plugin_tile.choose");
};
// A number that may stay empty: what its field shows while it is (the number that applies, with the unit), and what a
// person typed, kept within the option's min, max and steps, or taken off the tile when the field is empty.
const withUnit = (option: PluginTileOption, value: number) => `${number(value)}${option.unit ? ` ${option.unit}` : ""}`;
const emptyText = (option: PluginTileOption) => {
  const applies = placeholderNumber(option, props.values);
  return applies === undefined ? t("editor.plugin_tile.not_set") : withUnit(option, applies);
};
const filled = (option: PluginTileOption) => typeof props.values[option.id] === "number";
function typed(option: PluginTileOption, event: Event) {
  const field = event.target as HTMLInputElement;
  const value = typedNumber(option, field.value);
  field.value = value === undefined ? "" : String(value);
  if (value !== (filled(option) ? props.values[option.id] : undefined)) set(option, value);
}
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
      <template v-if="option.kind === 'entity'">
      <UiPicker :id="`plugin-option-${option.id}`" :items="entityItems(option)"
        :placeholder="t('editor.plugin_tile.search')" :empty="t('editor.plugin_tile.none_found')" @pick="(value: string) => set(option, value)">
        <template #trigger>
          <button type="button" class="ghost-btn"><Icon name="magnify" />{{ entityName(option) }}</button>
        </template>
        <template v-if="hasFilter(option)" #foot>
          <button type="button" class="btn mini" :data-all="`plugin-option-${option.id}`" :aria-pressed="everything[option.id] ? 'true' : 'false'"
            @click="everything[option.id] = !everything[option.id]"><Icon :name="everything[option.id] ? 'filter-variant' : 'format-list-bulleted'" />{{
              t(everything[option.id] ? "editor.plugin_tile.show_fitting" : "editor.plugin_tile.show_all") }}</button>
        </template>
      </UiPicker>
      <button v-if="values[option.id]" type="button" class="btn quiet mini plugin-entity-clear"
        :aria-label="t('editor.plugin_tile.remove', { name: entityName(option) })" @click="set(option, '')"><Icon name="close" /></button>
      </template>
      <UiSelect v-else-if="option.kind === 'choice'" :id="`plugin-option-${option.id}`" :model-value="String(values[option.id] ?? '')"
        :options="choices(option)" :placeholder="t('editor.plugin_tile.choose')" @update:model-value="(value: string) => set(option, value)" />
      <span v-else-if="option.kind === 'number' && option.optional" class="plugin-number">
        <input :id="`plugin-option-${option.id}`" type="text" inputmode="decimal" autocomplete="off" :placeholder="emptyText(option)"
          :value="filled(option) ? String(values[option.id]) : ''" @change="typed(option, $event)" />
        <span v-if="option.unit && filled(option)" class="plugin-number-unit">{{ option.unit }}</span>
      </span>
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
