<script setup lang="ts">
// A plugin's tile in the inspector (design, docs: the plugins proposal): its name, the options its manifest lists, drawn
// with the inspector's own rows (PluginOptions, which the screensaver's drawer shares), and the sizes it takes.
// Plugin API 0.26: options under a heading of the manifest (`group`) stand in a section of their own after the others,
// folded until one of them has a value; and a tile whose manifest says `from_device` has one picker above its options
// that fills its entity options from a Home Assistant device, once: each can still be changed after.
import { computed } from "vue";
import { t } from "../i18n";
import { healthText } from "../model/broken-tiles";
import { anySet, deviceFills, offeredEntities, optionGroups, optionsFit, pluginDefaults, text, withOption, type PluginTileOption } from "../model/plugins";
import { glyph } from "../model/topbar";
import type { PluginValue, Tile } from "../types";
import PluginOptions from "./PluginOptions.vue";
import Icon from "./ui/Icon.vue";
import InspectorHead from "./ui/InspectorHead.vue";
import NameField from "./inspector/NameField.vue";
import TitleButton from "./inspector/TitleButton.vue";
import PropRow from "./ui/PropRow.vue";
import Section from "./ui/Section.vue";
import UiPicker from "./ui/UiPicker.vue";
import UiSelect from "./ui/UiSelect.vue";
import { usePluginsStore } from "../stores/plugins";
import { removeTile, setTileOption, tileSizeChoices } from "../editor/tiles";
import SwitchRow from "./ui/SwitchRow.vue";
import { useUiStore } from "../stores/ui";
import { useInspectorStore } from "../stores/inspector";
import { useBrokenStore } from "../stores/broken";

const plugins = usePluginsStore();
const ui = useUiStore();
const insp = useInspectorStore();

const props = defineProps<{ tile: Tile }>();
const kind = computed(() => plugins.pluginTileOf(props.tile.entity)!);
const values = computed<Record<string, PluginValue>>(() => ({ ...pluginDefaults(kind.value.tile), ...(props.tile.options?.plugin || {}) }));
// `undefined` takes the option off the tile: a number that may stay empty is kept as no key at all.
function set(option: PluginTileOption, value: PluginValue | undefined) {
  setTileOption(props.tile, "plugin", withOption(props.tile.options?.plugin, option.id, value));
}
// The options without a heading, then each group of the manifest; a group opens by itself when one of its has a value.
const laidOut = computed(() => optionGroups(kind.value.tile.options));
const groupOpen = (options: PluginTileOption[]) => anySet(options, props.tile.options?.plugin);
// The devices that have an entity for two or more of the tile's entity options, the one with the most first, each
// saying how many of them it has; choosing one sets those options and leaves the others as they are.
const fills = computed(() => (kind.value.tile.from_device ? deviceFills(kind.value.tile, plugins.entityFacts, plugins.devices) : []));
const deviceItems = computed(() => fills.value.map((device) => {
  const n = Object.keys(device.fills).length;
  return { id: device.id, name: device.name, hint: t("editor.plugin_tile.fill_device_count", { n }, n) };
}));
function fillFrom(id: string) {
  const device = fills.value.find((item) => item.id === id);
  if (!device) return;
  const next = { ...(props.tile.options?.plugin || {}), ...device.fills };
  if (!optionsFit({ ...values.value, ...device.fills })) { ui.toast(t("editor.plugin_tile.full")); return; }
  setTileOption(props.tile, "plugin", next);
}
// A tile that belongs to an entity (its manifest's `domains`): the entities of those domains, only those with the
// attributes it needs when its manifest names them (`has_attributes`).
const entityChoices = computed(() => offeredEntities(plugins.entitiesIn(kind.value.tile.domains), kind.value.tile, props.tile.options?.plugin_entity)
  .map((e) => [e.id, e.name !== e.id ? `${e.name} (${e.id})` : e.id] as [string, string]));
const size = (value: string) => value.replace("x", "×");
// What the manifest says of its sizes (plugin API 0.25: the whole page, or only that).
const sizesHint = computed(() => {
  const { min, max, full } = kind.value.tile;
  if (!min || !max) return t("editor.plugin_tile.sizes_only_page");
  return t(full ? "editor.plugin_tile.sizes_or_page" : "editor.plugin_tile.sizes", { min: size(min), max: size(max) });
});
// The edges go one direction at a time, and a tile of at most 2 x 2 has no way to the whole page along them.
const sizes = computed(() => tileSizeChoices(props.tile));
const isPage = computed(() => props.tile.options?.size === "full");
const setPage = (on: boolean) => setTileOption(props.tile, "size", on ? "full" : sizes.value.find((choice) => choice !== "full"));
// Its entity gone from Home Assistant, or away for a while (stores/broken.ts): said under the choice of another.
const broken = useBrokenStore();
const entityHealth = computed(() => props.tile.options?.plugin_entity ? broken.tileHealth(props.tile.options.plugin_entity) : null);
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
        <template v-if="entityHealth" #note><small class="help warn" id="plugin-entity-broken">{{ healthText(entityHealth, ui.now) }}</small></template>
      </PropRow>
    </Section>
    <Section v-if="laidOut.plain.length || kind.tile.from_device" :title="t('editor.plugin_tile.options')">
      <UiPicker v-if="kind.tile.from_device" id="plugin-fill-device" :items="deviceItems" :placeholder="t('editor.plugin_tile.search')"
        :empty="t('editor.plugin_tile.fill_device_none')" width="320px" @pick="fillFrom">
        <template #trigger>
          <button type="button" class="ghost-btn" id="plugin-fill-device-open" :title="t('editor.plugin_tile.fill_device_hint')"><Icon name="magnify" />{{ t("editor.plugin_tile.fill_device") }}</button>
        </template>
      </UiPicker>
      <PluginOptions :plugin="kind.plugin" :options="laidOut.plain" :values="values" @change="set" />
    </Section>
    <Section v-for="group in laidOut.groups" :key="`${tile.id || tile.slot}-${group.key}`" :title="text(group.title)" foldable :open="groupOpen(group.options)">
      <PluginOptions :plugin="kind.plugin" :options="group.options" :values="values" @change="set" />
    </Section>

    <Section :title="t('editor.plugin_tile.on_screen')">
      <SwitchRow v-if="sizes.includes('full') && sizes.length > 1" :label="t('editor.plugin_tile.whole_page')"
        :model-value="isPage" @update:model-value="setPage" />
      <p class="hint">{{ sizesHint }}</p>
      <p class="hint">{{ t(kind.tile.preview ? "editor.plugin_tile.live" : "editor.plugin_tile.placeholder") }}</p>
    </Section>
  </div>
  <div class="dr-foot">
    <button type="button" class="btn danger-soft" @click="removeTile(tile)"><Icon name="delete-outline" />{{ t("editor.common.remove") }}</button>
  </div>
</template>
