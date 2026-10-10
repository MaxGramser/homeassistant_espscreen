<script setup lang="ts">
// The entity a tile shows, chosen again (editor/tile-entity.ts): at the top of the tile's inspector when Home Assistant no
// longer has it or has had no word from it for a while (stores/broken.ts), with why; and from the tile's menu for any
// tile of an entity. Entities of the same kind come first, the ones whose names share the most words with the old one
// first of all (model/broken-tiles.ts replacementCandidates). The arrows walk the list from the search field, Enter
// takes one.
import { computed, nextTick, ref, watch } from "vue";
import { t } from "../i18n";
import { healthText, replacementCandidates } from "../model/broken-tiles";
import { glyph } from "../model/topbar";
import type { Tile } from "../types";
import Icon from "./ui/Icon.vue";
import { useListNavigation } from "../composables/useListNavigation";
import { replaceTileEntity } from "../editor/tile-entity";
import { useBrokenStore } from "../stores/broken";
import { useEntitiesStore } from "../stores/entities";
import { useInspectorStore } from "../stores/inspector";
import { useInventoryStore } from "../stores/inventory";
import { useUiStore } from "../stores/ui";

const props = defineProps<{ tile: Tile }>();
const broken = useBrokenStore();
const entities = useEntitiesStore();
const insp = useInspectorStore();
const inv = useInventoryStore();
const ui = useUiStore();

const health = computed(() => broken.tileHealth(props.tile.entity));
const shown = computed(() => Boolean(health.value) || insp.entityPickerOpen);
const query = ref("");
const candidates = computed(() => replacementCandidates(props.tile.entity, inv.inventory.entities, query.value));
const field = ref<HTMLInputElement | null>(null);
const list = ref<HTMLElement | null>(null);
function pick(id: string) {
  if (replaceTileEntity(props.tile, id)) { insp.entityPickerOpen = false; query.value = ""; }
}
const { active, onKey } = useListNavigation(() => candidates.value.map((entity) => entity.id), {
  onPick: (id) => pick(id), resetOn: query,
  onMove: (index) => nextTick(() => list.value?.children[index]?.scrollIntoView?.({ block: "nearest" })),
});
// Asked for (the broken tiles' list, the tile's menu): the search field takes the keys at once.
watch(() => insp.entityPickerOpen, async (open) => { if (open) { await nextTick(); field.value?.focus(); } }, { immediate: true });
const title = computed(() => !health.value ? t("editor.broken.fix.choose")
  : health.value.kind === "missing" ? t("editor.broken.fix.missing") : healthText(health.value, ui.now));
const hint = computed(() => health.value ? t(`editor.broken.fix.${health.value.kind}_hint`) : "");
</script>

<template>
  <section v-if="shown" id="entity-fix" class="picker entity-fix" :class="{ broken: health }">
    <div class="fix-head">
      <Icon v-if="health" name="alert-circle-outline" class="fix-icon" />
      <div class="fix-words"><strong>{{ title }}</strong><small v-if="hint">{{ hint }}</small></div>
      <button v-if="!health" type="button" class="icon-btn fix-close" :aria-label="t('editor.common.close')" @click="insp.entityPickerOpen = false"><Icon name="close" /></button>
    </div>
    <label class="search-field">
      <Icon name="magnify" />
      <input id="entity-fix-search" ref="field" v-model="query" type="search" autocomplete="off" :placeholder="t('editor.broken.fix.search')"
        :aria-label="t('editor.broken.fix.search')" aria-controls="entity-fix-list" @keydown="onKey" @keydown.esc="insp.entityPickerOpen = false" />
    </label>
    <div id="entity-fix-list" ref="list" class="fix-list" role="listbox" :aria-label="t('editor.broken.fix.choose')">
      <button v-for="(entity, index) in candidates" :key="entity.id" type="button" role="option" class="fix-row" :class="{ active: index === active }"
        :aria-selected="index === active" :data-entity="entity.id" @mouseenter="active = index" @click="pick(entity.id)">
        <span class="mdi">{{ glyph(entities.automaticIcon(entity.id)) }}</span>
        <span class="tx"><strong>{{ entity.name }}</strong><small>{{ [entity.area, entity.id].filter(Boolean).join(" · ") }}</small></span>
      </button>
      <p v-if="!candidates.length" class="hint">{{ t("editor.topbar.add.none_found") }}</p>
    </div>
  </section>
</template>
