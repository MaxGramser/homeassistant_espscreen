<script setup lang="ts">
// A plugin's tile in the inspector (design, docs: the plugins proposal): its name, the options its manifest lists, drawn
// with the inspector's own rows (PluginOptions, which the screensaver's drawer shares), its background as any tile's
// (the layout keeps it for a plugin's tile, core.PLUGIN_TILE_OPTIONS), and the sizes it takes.
import { computed } from "vue";
import { t } from "../i18n";
import { healthText } from "../model/broken-tiles";
import { offeredEntities, pluginDefaults, text, type PluginTileOption } from "../model/plugins";
import { glyph } from "../model/topbar";
import type { PluginValue, Tile } from "../types";
import PluginOptions from "./PluginOptions.vue";
import Icon from "./ui/Icon.vue";
import InspectorHead from "./ui/InspectorHead.vue";
import NameField from "./inspector/NameField.vue";
import TitleButton from "./inspector/TitleButton.vue";
import PropRow from "./ui/PropRow.vue";
import Section from "./ui/Section.vue";
import UiSelect from "./ui/UiSelect.vue";
import { usePluginsStore } from "../stores/plugins";
import { removeTile, setTileOption } from "../editor/tiles";
import { useUiStore } from "../stores/ui";
import { useInspectorStore } from "../stores/inspector";
import { useBrokenStore } from "../stores/broken";
import { useInventoryStore } from "../stores/inventory";

const plugins = usePluginsStore();
const ui = useUiStore();
const insp = useInspectorStore();

const props = defineProps<{ tile: Tile }>();
const kind = computed(() => plugins.pluginTileOf(props.tile.entity)!);
const values = computed<Record<string, PluginValue>>(() => ({ ...pluginDefaults(kind.value.tile), ...(props.tile.options?.plugin || {}) }));
function set(option: PluginTileOption, value: PluginValue) {
  setTileOption(props.tile, "plugin", { ...(props.tile.options?.plugin || {}), [option.id]: value });
}
// A tile that belongs to an entity (its manifest's `domains`): the entities of those domains, only those with the
// attributes it needs when its manifest names them (`has_attributes`).
const entityChoices = computed(() => offeredEntities(plugins.entitiesIn(kind.value.tile.domains), kind.value.tile, props.tile.options?.plugin_entity)
  .map((e) => [e.id, e.name !== e.id ? `${e.name} (${e.id})` : e.id] as [string, string]));
const size = (value: string) => value.replace("x", "×");
// Its entity gone from Home Assistant, or away for a while (stores/broken.ts): said under the choice of another.
const broken = useBrokenStore();
const entityHealth = computed(() => props.tile.options?.plugin_entity ? broken.tileHealth(props.tile.options.plugin_entity) : null);
// Its background, chosen as on any tile (TileInspector): previewed under the pointer, kept on a click.
const inv = useInventoryStore();
const backgrounds = computed(() => Object.entries(inv.inventory.backgrounds || {}));
const backgroundName = computed(() => inv.inventory.backgrounds?.[props.tile.options?.background || "auto"]?.label || "");
function previewBackground(key: string | null) {
  if (key && props.tile.id && key !== (props.tile.options?.background || "auto")) insp.optionPreview = { tileId: props.tile.id, key: "background", value: key };
  else if (insp.optionPreview?.key === "background") insp.optionPreview = null;
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
        <template v-if="entityHealth" #note><small class="help warn" id="plugin-entity-broken">{{ healthText(entityHealth, ui.now) }}</small></template>
      </PropRow>
    </Section>
    <Section v-if="kind.tile.options?.length" :title="t('editor.plugin_tile.options')">
      <PluginOptions :plugin="kind.plugin" :options="kind.tile.options" :values="values" @change="set" />
    </Section>

    <Section :title="t('editor.tile.sections.style')" class="style-section">
      <PropRow :label="t('editor.tile.background.label')" icon="palette-outline" stack>
        <template #aside>{{ backgroundName }}</template>
        <div class="sw" @pointerleave="previewBackground(null)">
          <button v-for="[background, choice] in backgrounds" :key="background" type="button" :aria-label="t('editor.tile.background.aria', { name: choice.label })" :title="choice.label"
            :aria-pressed="(tile.options?.background || 'auto') === background ? 'true' : 'false'" @pointerenter="previewBackground(background)" @click="previewBackground(null); setTileOption(tile, 'background', background)">
            <i :class="choice.color ? '' : background === 'none' ? 'none' : 'auto'" :style="choice.color ? { background: choice.color } : undefined"></i>
          </button>
        </div>
      </PropRow>
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
