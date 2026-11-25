<script setup lang="ts">
import { computedAsync, useElementSize } from '@vueuse/core';
import { computed, shallowRef, useTemplateRef } from 'vue';
import { t } from '../i18n';
import { cardGraph, GRAPH_FILL, type HistoryPreview } from '../model/history-preview';
import { useEntitiesStore } from '../stores/entities';
import { useUiStore } from '../stores/ui';

const ui = useUiStore();
const entities = useEntitiesStore();
const props = defineProps<{ entity: string; hours: number }>();
// The entity's history, asked again when the entity, the hours or the minute change; only the newest answer counts.
// While it is asked the card says so, as it did, instead of the graph of the last answer.
const loading = shallowRef(true);
const history = computedAsync<HistoryPreview | null>(async () => {
  const entity = props.entity, hours = props.hours;
  void Math.floor(ui.now / 60000);
  try { return await entities.loadHistory(entity, hours); }
  catch { return null; /* No recorder or unavailable history stays explicitly empty. */ }
}, null, { evaluating: loading });
// Drawn in the room the card gives it, in its own pixels, so the line keeps its width however the room is shaped.
const box = useTemplateRef<HTMLElement>('box');
const { width, height } = useElementSize(box);
const size = computed(() => ({ w: Math.max(2, Math.round(width.value) || 200), h: Math.max(2, Math.round(height.value) || 50) }));
const graph = computed(() => !loading.value && history.value ? cardGraph(history.value.values, size.value.w, size.value.h, 2) : null);
const caption = computed(() => history.value ? `${new Date(history.value.start * 1000).toLocaleString()} – ${new Date(history.value.end * 1000).toLocaleString()}` : '');
</script>
<template>
  <span ref="box" class="sensor-history">
    <svg v-if="graph" :viewBox="`0 0 ${size.w} ${size.h}`" role="img" :aria-label="t('editor.pages.history_label', { hours })">
      <title>{{ caption }}</title>
      <path class="area" :d="graph.area" :fill-opacity="GRAPH_FILL" />
      <path class="line" :d="graph.line" />
    </svg>
    <small v-else class="history-empty">{{ t(loading ? 'editor.pages.history_loading' : 'editor.pages.history_empty') }}</small>
  </span>
</template>
<style scoped>
.sensor-history { display: flex; align-items: center; min-width: 0; min-height: 20px; color: var(--tile-accent); }
svg { display: block; width: 100%; height: 100%; overflow: visible; }
.area { fill: currentColor; stroke: none; }
.line { stroke: currentColor; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; fill: none; }
.history-empty { font-size: 9px; color: #46525e; }
</style>
