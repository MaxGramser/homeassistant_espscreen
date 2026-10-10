<script setup lang="ts">
// The bar at the top of a mockup page, drawn as the screen draws it: name left, items right.
import { computed } from "vue";
import { t } from "../i18n";
import { barLayout, dotted, inkOf, type BarMetrics, type BarPart } from "../model/topbar";
import { barMetrics, state, topbarView } from "../store";
import TesseraMark from "./TesseraMark.vue";
import { useUiStore } from "../stores/ui";
import { useEntitiesStore } from "../stores/entities";

const ui = useUiStore();
const entities = useEntitiesStore();

// `metrics`: another screen's bar, for that screen's home page on the overview (app 0.4.0).
const props = defineProps<{ items: any[]; nameText?: string; single?: boolean; home?: boolean; back?: boolean; metrics?: BarMetrics }>();

const lay = computed(() => {
  void ui.fontsVersion;
  void ui.now;
  void entities.topbarPreviews;
  return barLayout(props.items, props.metrics ?? barMetrics.value, props.nameText ?? '', topbarView,
                   Boolean(props.home) && !props.single, Boolean(props.back) && !props.single);
});
const m = computed(() => lay.value.metrics);
const height = computed(() => (props.single ? Math.round(m.value.text * 1.4) : m.value.top + Math.round(m.value.name * 0.45)));
const baseline = computed(() => (props.single ? Math.round(m.value.text * 1.05) : m.value.top));
const parts = computed<BarPart[]>(() => {
  if (!props.single) return lay.value.placed;
  const part = lay.value.parts[0];
  if (part) part.x = 0;
  return part ? [part] : [];
});
const viewBox = computed(() => (props.single
  ? `-2 0 ${Math.max(1, parts.value[0]?.width || 1) + 4} ${height.value}`
  : `0 0 ${m.value.width} ${height.value}`));
const capMiddle = computed(() => baseline.value + (lay.value.zero.top + lay.value.zero.bottom) / 2);
// The home key stands on the capitals' baseline of the name, not on the digits of the items: the screens place it
// that way. Back's chevron sits in the middle of the same slot.
const nameCap = computed(() => inkOf("H", lay.value.fonts.name));
const markY = computed(() => baseline.value + nameCap.value.bottom - lay.value.key!.size);
const backY = computed(() => baseline.value + nameCap.value.bottom - lay.value.key!.ink.bottom);
const backX = computed(() => (lay.value.key!.size - (lay.value.key!.ink.right - lay.value.key!.ink.left)) / 2 - lay.value.key!.ink.left);
const name = computed(() => dotted(lay.value.nameText, lay.value.fonts.name, Math.min(lay.value.natural, lay.value.nameRoom)));
const now = computed(() => new Date(ui.now));
function hands(d: number) {
  const n = now.value;
  return [[(n.getHours() % 12 + n.getMinutes() / 60) * 30, d * 0.24], [n.getMinutes() * 6, d * 0.34]].map(([angle, length]) => {
    const rad = (angle * Math.PI) / 180;
    return { x2: length * Math.sin(rad), y2: -length * Math.cos(rad) };
  });
}
const iconX = (p: BarPart) => p.x! - p.icon!.ink.left;
const textX = (p: BarPart) => (p.icon ? p.x! + (p.icon.ink.right - p.icon.ink.left) + lay.value.gaps.icon : p.x!) - p.text!.ink.left;
// `font` goes through CSSOM: the add-on's CSP blocks style attributes, and Vue sets styles through the CSSOM.
const singleWidth = computed(() => `${(Math.max(1, parts.value[0]?.width || 1) + 4) * (26 / m.value.icon)}px`);
defineExpose({ lay });
</script>

<template>
  <svg :viewBox="viewBox" role="img" :aria-label="single ? t('editor.topbar.live.looks') : t('editor.topbar.aria', { name: lay.nameText })" :style="single ? { width: singleWidth } : undefined">
    <TesseraMark v-if="lay.key?.mark" x="0" :y="markY" :width="lay.key.size" :height="lay.key.size" />
    <text v-else-if="lay.key" :x="backX" :y="backY" fill="#46525e" :style="{ font: lay.fonts.icon }">{{ lay.key.glyph }}</text>
    <text v-if="!single" :x="lay.homeShift" :y="m.top" fill="#1b1b1b" :style="{ font: lay.fonts.name }">{{ name }}</text>
    <g>
      <template v-for="p in parts" :key="p.index">
        <template v-if="p.dial">
          <circle :cx="p.x! + p.dial / 2" :cy="capMiddle" :r="p.dial / 2 - Math.max(1, Math.round(p.dial / 10)) / 2" fill="none" :stroke="p.view.color || '#46525e'" :stroke-width="Math.max(1, Math.round(p.dial / 10))" />
          <line v-for="(h, i) in hands(p.dial)" :key="i" :x1="p.x! + p.dial / 2" :y1="capMiddle" :x2="p.x! + p.dial / 2 + h.x2" :y2="capMiddle + h.y2" :stroke="p.view.color || '#46525e'" :stroke-width="Math.max(1, Math.round(p.dial * 0.075))" stroke-linecap="round" />
        </template>
        <template v-else>
          <text v-if="p.icon" :x="iconX(p)" :y="capMiddle - (p.icon.ink.top + p.icon.ink.bottom) / 2" :fill="p.view.color || '#46525e'" :style="{ font: lay.fonts.icon }">{{ p.icon.glyph }}</text>
          <text v-if="p.text" :x="textX(p)" :y="baseline" fill="#46525e" :style="{ font: lay.fonts.text }">{{ p.text.value }}</text>
        </template>
      </template>
    </g>
  </svg>
</template>
