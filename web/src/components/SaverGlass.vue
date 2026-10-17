<script setup lang="ts">
// The screensaver's clock in miniature, in the glass's own proportions: the time large in the middle, the date under it
// and the bottom line with the temperature and the entities, white on black as the screen draws it. A line wider than
// the glass loses its last entities until it fits, as on the screen, so the temperature always stays.
// A face of the module (Glass, Classic, Bauhaus) shows as that face instead (SaverFace.vue), and a plugin's face as its
// optional firmware screenshot, or its icon and example when no screenshot exists.
import { useResizeObserver } from "@vueuse/core";
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from "vue";
import { t } from "../i18n";
import { text } from "../model/plugins";
import { glyph } from "../model/topbar";
import { usePluginsStore } from "../stores/plugins";
import { useRegionStore } from "../stores/region";
import { useTopbarStore } from "../stores/topbar";
import { useScreensaverStore } from "../stores/screensaver";
import { useUiStore } from "../stores/ui";
import { useScreenStore } from "../stores/screen";
import SaverFace from "./SaverFace.vue";

const topbar = useTopbarStore();
const screensaver = useScreensaverStore();
const region = useRegionStore();
const ui = useUiStore();
const plugins = usePluginsStore();
const pluginFace = computed(() => (screensaver.clockPluginFace ? plugins.saverOf(screensaver.clockPluginFace) : undefined));
const pluginPreview = computed(() => {
  const known = pluginFace.value;
  return known?.plugin.image ? `${known.plugin.image}&saver=${encodeURIComponent(known.saver.id)}` : null;
});
const previewFailed = ref(false);
watch(pluginPreview, () => { previewFailed.value = false; });
const showPreview = computed(() => Boolean(pluginPreview.value && !previewFailed.value));
// Plugin code runs in an opaque-origin sandbox, with no same-origin access or network.
const screen = useScreenStore();
const frame = ref<HTMLIFrameElement | null>(null);
const interactiveReady = ref(false);
const interactiveUrl = computed(() => pluginPreview.value ? `${pluginPreview.value}&interactive=1` : null);
watch(interactiveUrl, () => { interactiveReady.value = false; });
function sendPreview() {
  if (!interactiveReady.value) return;
  frame.value?.contentWindow?.postMessage({ type: "tessera:preview", options: screensaver.pluginValues(screensaver.clockPluginFace),
    size: screensaver.glassSize, shape: screen.currentScreen?.shape, now: ui.now, language: region.screenLanguage }, "*");
}
function previewMessage(event: MessageEvent) {
  if (!frame.value?.contentWindow || event.source !== frame.value.contentWindow || event.data?.type !== "tessera:preview-ready") return;
  interactiveReady.value = true;
  sendPreview();
}
onMounted(() => window.addEventListener("message", previewMessage));
onBeforeUnmount(() => window.removeEventListener("message", previewMessage));
watch(() => [screensaver.pluginValues(screensaver.clockPluginFace), screensaver.glassSize, screen.currentScreen?.shape, ui.now, region.screenLanguage], sendPreview, { deep: true });
const at = computed(() => new Date(ui.now));
const say = (key: string) => t(key, {}, { locale: region.screenLanguage });
const words = computed(() => ({
  weekday: say(`screen.date.weekdays.${at.value.getDay()}`), short: say(`screen.date.weekdays_short.${at.value.getDay()}`),
  month: say(`screen.date.months.${at.value.getMonth()}`), day: at.value.getDate(),
}));

defineProps<{ height: number }>();
const line = ref<HTMLElement | null>(null);
const items = computed(() => screensaver.saverItems.map((it) => {
  const view = topbar.topbarView(it);
  return { key: it.entity, icon: view.icon && it.icon !== "none" ? glyph(view.icon) : "", text: it.content === "icon" ? "" : view.text };
}));
const temperature = computed(() => ((screensaver.saver?.weather ?? "auto") === "" ? null : screensaver.clockPreview.temperature));
const fit = ref(items.value.length);
async function measure() {
  fit.value = items.value.length;
  await nextTick();
  while (line.value && fit.value > 0 && line.value.scrollWidth > line.value.clientWidth + 1) {
    fit.value -= 1;
    await nextTick();
  }
}
watch([items, temperature], measure, { deep: true });
onMounted(measure);
useResizeObserver(line, () => measure());
</script>

<template>
  <div v-if="screensaver.clockPluginFace" class="saver-glass plugin" :class="{ pictured: showPreview || interactiveReady }" aria-hidden="true" :style="{ aspectRatio: screensaver.glassRatio, height: `${height}px`, '--glass-h': `${height}px` }">
    <iframe v-if="interactiveUrl" ref="frame" class="saver-interactive" :class="{ ready: interactiveReady }" :src="interactiveUrl" sandbox="allow-scripts" tabindex="-1" title="" />
    <img v-if="showPreview && !interactiveReady" class="saver-glass-preview" :src="pluginPreview!" alt="" @error="previewFailed = true" />
    <template v-else-if="!interactiveReady">
      <span class="mdi saver-glass-icon">{{ glyph(pluginFace?.saver.icon || pluginFace?.plugin.icon || "F0A66") }}</span>
      <span class="saver-glass-date">{{ pluginFace ? text(pluginFace.saver.example || pluginFace.saver.name) : screensaver.stepLabel(screensaver.clockPluginFace) }}</span>
    </template>
  </div>
  <div v-else-if="screensaver.face !== 'digital'" class="saver-glass face" aria-hidden="true" :style="{ aspectRatio: screensaver.glassRatio, height: `${height}px`, '--glass-h': `${height}px` }">
    <SaverFace :kind="screensaver.face" :dark="screensaver.faceDark" :numerals="screensaver.saver?.numerals ?? 4" :seconds="screensaver.saver?.seconds ?? true"
      :width="screensaver.glassSize.width" :height="screensaver.glassSize.height" :at="at" v-bind="words" />
  </div>
  <div v-else class="saver-glass" aria-hidden="true" :style="{ aspectRatio: screensaver.glassRatio, height: `${height}px`, '--glass-h': `${height}px` }">
    <span class="saver-glass-time">{{ screensaver.clockPreview.time }}</span>
    <span class="saver-glass-date">{{ screensaver.clockPreview.date }}</span>
    <span ref="line" class="saver-glass-line">
      <span v-if="temperature">{{ temperature }}</span>
      <span v-for="it in items.slice(0, fit)" :key="it.key"><span v-if="it.icon" class="mdi">{{ it.icon }}</span>{{ it.text }}</span>
    </span>
  </div>
</template>

<style scoped>
.saver-interactive { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; visibility: hidden; pointer-events: none; }
.saver-interactive.ready { visibility: visible; }
.saver-glass.face { padding: 0; overflow: hidden; }
.saver-glass.plugin.pictured { padding: 0; overflow: hidden; }
.saver-glass-preview { display: block; width: 100%; height: 100%; object-fit: contain; }
.saver-glass { display: grid; justify-items: center; align-content: center; gap: 2px; width: auto; max-width: 100%; justify-self: center; position: relative;
  border-radius: calc(var(--glass-h) * 0.07); background: #000; color: #fff; padding: 0 10px; }
.saver-glass-time { font-size: calc(var(--glass-h) * 0.25); font-weight: 300; line-height: 1; letter-spacing: -0.01em; font-variant-numeric: tabular-nums; }
.saver-glass-icon { font-size: calc(var(--glass-h) * 0.22); opacity: 0.85; }
.saver-glass.plugin .saver-glass-date { text-align: center; padding: 0 8px; }
.saver-glass-date { font-size: max(10px, calc(var(--glass-h) * 0.07)); opacity: 0.8; }
.saver-glass-line { position: absolute; left: 8px; right: 8px; bottom: calc(var(--glass-h) * 0.06); display: flex; justify-content: safe center; gap: 4px;
  font-size: max(10px, calc(var(--glass-h) * 0.064)); opacity: 0.85; white-space: nowrap; overflow: hidden; }
.saver-glass-line > span + span::before { content: "·"; margin-right: 4px; opacity: 0.7; }
.saver-glass-line .mdi { margin-right: 3px; }
</style>
