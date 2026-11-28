<script setup lang="ts">
// What several chosen tiles can be set to together (editor/shared-settings.ts): a row for each setting they all offer,
// under the headings of a tile's own inspector. A row shows the value they all have, or says that they differ; a pick
// is for every one of them, as one step of undo.
import { computed, ref } from "vue";
import { t } from "../../i18n";
import { setShared, sharedRows, type SharedRow } from "../../editor/shared-settings";
import { glyph } from "../../model/topbar";
import { useEntitiesStore } from "../../stores/entities";
import { useInventoryStore } from "../../stores/inventory";
import type { Tile } from "../../types";
import ChoiceField from "../ChoiceField.vue";
import IconChoices from "../IconChoices.vue";
import Icon from "../ui/Icon.vue";
import PropRow from "../ui/PropRow.vue";
import Section from "../ui/Section.vue";
import SwitchRow from "../ui/SwitchRow.vue";

const props = defineProps<{ tiles: Tile[] }>();
const entities = useEntitiesStore();
const inv = useInventoryStore();

const rows = computed(() => sharedRows(props.tiles));
const sections = computed(() => (["look", "controls", "style"] as const)
  .map((id) => ({ id, rows: rows.value.filter((row) => row.section === id) })).filter((section) => section.rows.length));
const mixed = computed(() => t("editor.selection.shared.mixed"));
const pick = (row: SharedRow, value: unknown) => setShared(props.tiles, row.key, value);
const color = (background: string | number) => inv.inventory.backgrounds?.[String(background)]?.color;

// The icon: automatic is each tile's own (Home Assistant's or its type's), so the first tile's stands for it.
const iconsOpen = ref(false);
const automatic = computed(() => entities.automaticIcon(props.tiles[0].entity));
const autoLabel = computed(() => t(inv.entityOf(props.tiles[0].entity)?.icon ? "editor.tile.icon.auto_ha" : "editor.tile.icon.auto_default"));
const iconGlyph = (row: SharedRow) => {
  if (row.value === null || row.value === "none") return "";
  const cp = entities.iconNamed(String(row.value))?.cp || automatic.value;
  return cp ? glyph(cp) : "";
};
const iconText = (row: SharedRow) => row.value === null ? mixed.value : row.value === "none" ? t("editor.icon.none") : entities.iconNamed(String(row.value))?.label || autoLabel.value;
</script>

<template>
  <template v-if="rows.length">
    <p class="help shared-hint" id="shared-hint">{{ t("editor.selection.shared.hint", { n: tiles.length }) }}</p>
    <Section v-for="section in sections" :key="section.id" :title="t(`editor.tile.sections.${section.id}`)" :class="`shared-${section.id}`">
      <template v-for="row in section.rows" :key="row.key">
        <SwitchRow v-if="row.kind === 'switch'" :data-shared="row.key" :label="row.label" :model-value="row.value === true" @update:model-value="(on: boolean) => pick(row, on)">
          <small v-if="row.value === null" class="shared-mixed">{{ mixed }}</small>
        </SwitchRow>
        <PropRow v-else-if="row.kind === 'background'" :data-shared="row.key" :label="row.label" :icon="row.icon" stack>
          <template #aside>{{ row.value === null ? mixed : row.text }}</template>
          <div class="sw">
            <button v-for="[background, label] in row.choices" :key="background" type="button" :aria-label="t('editor.tile.background.aria', { name: label })" :title="label"
              :aria-pressed="row.value === background ? 'true' : 'false'" @click="pick(row, background)">
              <i :class="color(background) ? '' : background === 'none' ? 'none' : 'auto'" :style="color(background) ? { background: color(background) } : undefined"></i>
            </button>
          </div>
        </PropRow>
        <PropRow v-else-if="row.kind === 'icon'" :data-shared="row.key" :label="row.label" :icon="row.icon">
          <button type="button" class="choice-field" :aria-expanded="iconsOpen ? 'true' : 'false'" :data-state="iconsOpen ? 'open' : 'closed'" @click="iconsOpen = !iconsOpen">
            <span class="choice-glyph mdi" aria-hidden="true">{{ iconGlyph(row) }}</span>
            <span class="choice-text">{{ iconText(row) }}</span>
            <Icon :name="iconsOpen ? 'chevron-up' : 'chevron-down'" />
          </button>
          <template v-if="iconsOpen" #note>
            <IconChoices :selected="String(row.value ?? '')" :automatic="automatic" :auto-label="autoLabel" @pick="(name: string) => pick(row, name)" />
          </template>
        </PropRow>
        <PropRow v-else :data-shared="row.key" :label="row.label" :icon="row.icon">
          <ChoiceField :choices="row.choices" :value="row.value ?? ''" :placeholder="row.value === null ? mixed : row.text" :aria-label="row.label" @pick="(value: unknown) => pick(row, value)" />
        </PropRow>
      </template>
    </Section>
  </template>
</template>

<style scoped>
.shared-hint { padding: 4px 16px 0; margin: 0; }
.shared-mixed { color: var(--muted); }
</style>
