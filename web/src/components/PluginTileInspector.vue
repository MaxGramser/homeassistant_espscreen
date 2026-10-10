<script setup lang="ts">
// A plugin's tile in the inspector (design, docs: the plugins proposal): its name, the options its manifest lists, drawn
// with the inspector's own rows, and the sizes it takes. A choice can come from one of the plugin's fetches (the lines of
// a stop): the add-on asks the plugin's service with the tile's other options and hands back only the choices.
import { computed } from "vue";
import { editorNumber, t } from "../i18n";
import { offeredEntities, pluginDefaults, text, type PluginTileOption } from "../model/plugins";
import { glyph } from "../model/topbar";
import type { Tile } from "../types";
import Icon from "./ui/Icon.vue";
import InspectorHead from "./ui/InspectorHead.vue";
import NameField from "./inspector/NameField.vue";
import TitleButton from "./inspector/TitleButton.vue";
import PropRow from "./ui/PropRow.vue";
import Section from "./ui/Section.vue";
import SwitchRow from "./ui/SwitchRow.vue";
import UiSelect from "./ui/UiSelect.vue";
import { usePluginsStore } from "../stores/plugins";
import { removeTile, setTileOption } from "../editor/tiles";
import { useUiStore } from "../stores/ui";
import { useInspectorStore } from "../stores/inspector";

const plugins = usePluginsStore();
const ui = useUiStore();
const insp = useInspectorStore();

const props = defineProps<{ tile: Tile }>();
const kind = computed(() => plugins.pluginTileOf(props.tile.entity)!);
const values = computed(() => ({ ...pluginDefaults(kind.value.tile), ...(props.tile.options?.plugin || {}) }));
function set(option: PluginTileOption, value: string | number | boolean) {
  setTileOption(props.tile, "plugin", { ...(props.tile.options?.plugin || {}), [option.id]: value });
}
// A tile that belongs to an entity (its manifest's `domains`): the entities of those domains, only those with the
// attributes it needs when its manifest names them (`has_attributes`).
const entityChoices = computed(() => offeredEntities(plugins.entitiesIn(kind.value.tile.domains), kind.value.tile, props.tile.options?.plugin_entity)
  .map((e) => [e.id, e.name !== e.id ? `${e.name} (${e.id})` : e.id] as [string, string]));
const choices = (option: PluginTileOption) => plugins.choicesFor(kind.value.plugin, option, values.value).map((choice) => [choice.value, text(choice.label)] as [string, string]);
const fromFetch = (option: PluginTileOption) => Boolean(option.options_from);
const size = (value: string) => value.replace("x", "×");
const number = (value: number) => editorNumber(value);
function step(option: PluginTileOption, by: number) {
  const now = Number(values.value[option.id] ?? option.min ?? 0);
  set(option, Math.min(option.max ?? Infinity, Math.max(option.min ?? -Infinity, now + by * (option.step ?? 1))));
}
// The plugin's details, in the screen's Plugins tab: the README says what the options mean.
function openPlugin() { insp.closeInspector(); ui.tab = "plugins"; }
</script>

<template>
  <InspectorHead :title="tile.name || text(kind.tile.name)" :code="kind.tile.icon || kind.plugin.icon" :tone="{ color: 'var(--accent)', background: 'var(--accent-soft)' }"
    :crumbs="[{ text: text(kind.plugin.name) }, { text: tile.entity, mono: true }]" kind="tile">
    <template #title><TitleButton :text="tile.name || text(kind.tile.name)" @rename="insp.renameTile(tile)" /></template>
  </InspectorHead>
  <div class="dr-body" id="plugin-tile-inspector">
    <NameField :tile="tile" :fallback="text(kind.tile.name)" />
    <p class="plugin-tile-from"><span class="mdi">{{ glyph("F0A66") }}</span>{{ t("editor.plugin_tile.from", { plugin: text(kind.plugin.name) }) }}
      <button type="button" class="btn link mini" @click="openPlugin">{{ t("editor.plugin_tile.details") }}</button></p>

    <Section v-if="kind.tile.domains?.length" :title="t('editor.plugin_tile.entity')">
      <PropRow :label="t('editor.plugin_tile.entity')" icon="link-variant" for="plugin-entity">
        <UiSelect id="plugin-entity" :model-value="tile.options?.plugin_entity || ''" :options="entityChoices"
          :placeholder="t('editor.plugin_tile.choose')" @update:model-value="(value: string) => setTileOption(tile, 'plugin_entity', value)" />
      </PropRow>
    </Section>
    <Section v-if="kind.tile.options?.length" :title="t('editor.plugin_tile.options')">
      <template v-for="option in kind.tile.options" :key="option.id">
        <SwitchRow v-if="option.kind === 'toggle'" :label="text(option.label)" :description="option.hint ? text(option.hint) : undefined"
          :model-value="Boolean(values[option.id])" @update:model-value="(on: boolean) => set(option, on)" />
        <PropRow v-else :label="text(option.label)" icon="tune-variant" :hint="option.hint ? text(option.hint) : undefined" :for="`plugin-option-${option.id}`">
          <UiSelect v-if="option.kind === 'choice'" :id="`plugin-option-${option.id}`" :model-value="String(values[option.id] ?? '')"
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
    </Section>

    <Section :title="t('editor.plugin_tile.on_screen')">
      <p class="hint">{{ t("editor.plugin_tile.sizes", { min: size(kind.tile.min), max: size(kind.tile.max) }) }}</p>
      <p class="hint">{{ t(kind.tile.preview ? "editor.plugin_tile.live" : "editor.plugin_tile.placeholder") }}</p>
    </Section>
  </div>
  <div class="dr-foot">
    <button type="button" class="btn danger-soft" @click="removeTile(tile)"><Icon name="delete-outline" />{{ t("editor.common.remove") }}</button>
  </div>
</template>
