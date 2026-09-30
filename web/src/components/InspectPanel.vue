<script setup lang="ts">
// Read current data: what Home Assistant reports for the screen's tiles right now, and how each tile is set.
import { onMounted, ref, watch } from "vue";
import { getJson } from "../api";
import { t } from "../i18n";
import { controlsLabel, displayName, sizeName } from "../model/layout";
import { state, toast } from "../store";
import Icon from "./ui/Icon.vue";
import InspectorHead from "./ui/InspectorHead.vue";

// One tile (an entity may be on several, firmware 0.16.0+): its entity, its slot and, for a key, its place.
const props = defineProps<{ entity?: string; slot?: number; tileKey?: number }>();
const summary = ref<any[] | null>(null);
const raw = ref(t("editor.inspect.reading"));
const error = ref("");
async function load() {
  if (!state.selected) return;
  summary.value = null;
  error.value = "";
  raw.value = t("editor.inspect.fetching");
  try {
    const data = await getJson(`screens/${encodeURIComponent(state.selected)}/inspect`);
    const tiles = props.entity ? data.tiles.filter((t: any) => t.entity === props.entity &&
      (props.slot === undefined || t.slot === undefined || (t.slot === props.slot && (t.key ?? null) === (props.tileKey ?? null)))) : data.tiles;
    summary.value = tiles;
    raw.value = JSON.stringify(props.entity ? tiles[0] : data, null, 2);
  } catch (e: any) {
    error.value = e.message;
    raw.value = "";
    toast(e.message);
  }
}
const optionsText = (entity: string, own?: Record<string, any>) => {
  const options = own || state.layout?.tiles.find((t) => t.entity === entity)?.options || {};
  return t("editor.inspect.options", {
    slider: t(options.inline === "slider" ? "editor.inspect.yes" : "editor.inspect.no"),
    display: displayName(options.display || "standard"),
    size: sizeName(options.size as string),
    control: controlsLabel({ entity, name: "", slot: 0, options }, state.inventory),
    background: state.inventory.backgrounds?.[options.background || "auto"]?.label || t("editor.inspect.background_default"),
  });
};
onMounted(load);
watch(() => [props.entity, props.slot, props.tileKey], load);
</script>

<template>
  <InspectorHead :title="t('editor.inspect.title')" icon="database-search-outline" :crumbs="[{ text: entity || t('editor.inspect.subtitle'), mono: !!entity }]" />
  <div class="dr-body" id="inspector-section">
    <div id="inspection-summary">
      <p v-if="error" class="hint warn">{{ error }}</p>
      <p v-else-if="!summary" class="hint">{{ t("editor.inspect.fetching") }}</p>
      <article v-for="(tile, i) in summary || []" :key="i" class="inspection-tile">
        <strong>{{ tile.entity }}</strong>
        <span>{{ t("editor.inspect.status", { status: tile.word || tile.state }) }}</span>
        <small>{{ optionsText(tile.entity, tile.options) }}</small>
      </article>
    </div>
    <pre id="inspection">{{ raw }}</pre>
  </div>
  <div class="dr-foot">
    <button type="button" class="btn quiet" @click="load"><Icon name="refresh" />{{ t("editor.inspect.read_again") }}</button>
    <span class="spacer"></span>
  </div>
</template>
