<script setup lang="ts">
import { computedAsync } from '@vueuse/core';
import { computed, shallowRef } from 'vue';
import { t } from '../i18n';
import { historyGeometry, loadHistory, type HistoryPreview } from '../model/history-preview';
import { state } from '../store';
const props = defineProps<{ entity: string; hours: number }>();
// The entity's history, asked again when the entity, the hours or the minute change; only the newest answer counts.
// While it is asked the card says so, as it did, instead of the graph of the last answer.
const loading = shallowRef(true);
const history = computedAsync<HistoryPreview | null>(async () => {
  const entity = props.entity, hours = props.hours;
  void Math.floor(state.now / 60000);
  try { return await loadHistory(entity, hours); }
  catch { return null; /* No recorder or unavailable history stays explicitly empty. */ }
}, null, { evaluating: loading });
const geometry = computed(() => !loading.value && history.value ? historyGeometry(history.value) : null);
const caption = computed(() => history.value ? `${new Date(history.value.start * 1000).toLocaleString()} – ${new Date(history.value.end * 1000).toLocaleString()}` : '');
</script>
<template>
  <svg v-if="geometry" class="sensor-history" viewBox="0 0 200 50" role="img" :aria-label="t('editor.pages.history_label', { hours })">
    <title>{{ caption }}</title>
    <path v-for="(path, index) in geometry.paths" :key="index" :d="path" />
    <circle v-for="(point, index) in geometry.points" :key="`point-${index}`" :cx="point.x" :cy="point.y" r="1.8" />
  </svg>
  <small v-else class="history-empty">{{ t(loading ? 'editor.pages.history_loading' : 'editor.pages.history_empty') }}</small>
</template>
<style scoped>
.sensor-history { width: 100%; min-height: 20px; max-height: 65px; color: var(--tile-accent); }
path { stroke: currentColor; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; fill: none; }
circle { fill: currentColor; }
.history-empty { font-size: 9px; color: #46525e; }
</style>
