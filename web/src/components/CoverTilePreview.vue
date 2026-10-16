<script setup lang="ts">
// A cover card's controls as the screen lays them out by its room (firmware 0.57.0, cover_tile.h, ported in
// model/cover-tile.ts): its sliders standing with open/stop/close under or beside them, the sliders alone, each group lying
// in a row, or one row and the key that swaps it to the slats. The slats stand at the angle the blind reports. Measured
// on the glass's own pixels, so the editor picks the tier the screen picks; where nothing fits the card shows what it
// shows without (the fallback slot). This preview never sends Home Assistant actions.
import { useElementSize } from '@vueuse/core';
import { computed, ref } from 'vue';
import { glyph } from '../model/topbar';
import { lineOf, tallKeys } from '../model/ui-scale';
import { controlKeys, coverTiltKeys, coverTiltKind, type ControlKey } from '../model/tall-controls';
import { coverLayout, empty, slats, Tier, type Group, type Rect } from '../model/cover-tile';
import { useRegionStore } from '../stores/region';
import { useInventoryStore } from "../stores/inventory";
import { useCanvasStore } from "../stores/canvas";
import { useDocumentStore } from "../stores/document";

const region = useRegionStore();
const inv = useInventoryStore();
const canvas = useCanvasStore();
const doc = useDocumentStore();
// `primary`: the chosen control beside the slats ('position', 'buttons' or ''); `tilt`: whether the slats were chosen.
// `standing`: false on a card one row high, which lays its controls only.
const props = withDefaults(defineProps<{ primary: string; entityState: string; attributes: Record<string, any>; tilt?: boolean; standing?: boolean }>(), { tilt: true, standing: true });
const root = ref<HTMLElement>();
const { width, height } = useElementSize(root);
// Mockup pixels per pixel of the glass.
const scale = computed(() => parseFloat(canvas.deviceStyle['--mockup-width']) / doc.screenShape.width);
const shape = computed(() => ({ ...doc.screenShape, look: canvas.isCompact ? 'compact' : 'standard' }) as { dpi?: number; look: string; width: number; fonts?: { sublabel?: number } });
const keys = computed(() => tallKeys(shape.value));
const tiltKind = computed(() => props.tilt ? coverTiltKind(props.entityState, props.attributes) : '');
const mainKeys = computed(() => props.primary === 'buttons' ? controlKeys('cover', 'buttons', props.entityState, props.attributes) : []);
const tiltKeys = computed(() => tiltKind.value === 'buttons' ? coverTiltKeys(props.attributes) : []);
const extraKeys = computed(() => props.primary === 'position' ? controlKeys('cover', 'buttons', props.entityState, props.attributes) : []);
const layout = computed(() => {
  const s = scale.value || 1, { touch, gap } = keys.value;
  const body: Rect = { x: 0, y: 0, w: Math.floor(width.value / s), h: Math.floor(height.value / s) };
  return coverLayout(body, touch, gap, lineOf(shape.value.fonts?.sublabel ?? 14), 2 * touch,
    props.primary === 'position', mainKeys.value.length, tiltKind.value === 'position', tiltKeys.value.length, extraKeys.value.length, props.standing);
});
// The row that shares its place with the slats shows the primary control in the mockup, as the screen does at first.
const shown = computed(() => [0, 1, 2].filter((i) => !empty(layout.value.groups[i].area) && !(layout.value.tier === Tier.SWAP && i === 1)));
const box = (r: Rect) => { const s = scale.value || 1; return { left: `${r.x * s}px`, top: `${r.y * s}px`, width: `${r.w * s}px`, height: `${r.h * s}px` }; };
const value = (i: number) => (i === 1 ? props.attributes.current_tilt_position : props.attributes.current_position) as number | undefined;
const keysOf = (i: number): ControlKey[] => (i === 0 ? mainKeys.value : i === 1 ? tiltKeys.value : extraKeys.value);
function keyBoxes(g: Group, count: number) {
  const { gap } = keys.value;
  const along = g.horizontal ? Math.trunc((g.control.w - (count - 1) * gap) / count) : g.control.w;
  const across = g.horizontal ? g.control.h : Math.trunc((g.control.h - (count - 1) * gap) / count);
  return Array.from({ length: count }, (_, n) => ({ x: g.control.x + (g.horizontal ? n * (along + gap) : 0), y: g.control.y + (g.horizontal ? 0 : n * (across + gap)), w: along, h: across }));
}
// The slats of a tilt slider in its own pixels (cover_tile::slats: 3 mm apart at least, a millimetre thick).
const mm = (n: number) => Math.floor(((shape.value.dpi || 170) * n + 12) / 25);
const slatsOf = (g: Group) => slats(g.control.w, g.control.h, Number(props.attributes.current_tilt_position ?? 50), mm(3), Math.max(3, mm(1) + 1));
const percent = (v: unknown) => typeof v === 'number' ? `${Math.round(v)}%` : '—';
const caption = (i: number, g: Group) => {
  const word = region.screenText(i === 1 ? 'screen.cover.tilt' : 'screen.cover.position');
  return g.slider && typeof value(i) === 'number' ? `${word} ${percent(value(i))}` : word;
};
const icon = (name: string) => glyph(inv.inventory.icons?.controls?.[name] || '');
</script>
<template>
  <span ref="root" class="cover-preview">
    <template v-if="layout.fits">
      <template v-for="i in shown" :key="i">
        <template v-if="layout.groups[i].slider">
          <span class="cover-slider" :class="{ tilt: i === 1, lying: layout.groups[i].lying }" :style="box(layout.groups[i].control)">
            <svg v-if="i === 1" class="slats" :viewBox="`0 0 ${layout.groups[i].control.w} ${layout.groups[i].control.h}`" preserveAspectRatio="none">
              <line v-for="(s, n) in slatsOf(layout.groups[i])" :key="n" :x1="s.x1" :y1="s.y1" :x2="s.x2" :y2="s.y2" :stroke-width="Math.max(3, mm(1) + 1)" />
            </svg>
            <span v-if="i === 0" class="fill" :style="layout.groups[i].lying ? { width: `${value(0) ?? 0}%` } : { height: `${100 - (value(0) ?? 100)}%` }"></span>
            <i class="handle" :style="i === 1 ? (layout.groups[i].lying ? { left: `${value(1) ?? 50}%` } : { bottom: `${value(1) ?? 50}%` })
              : (layout.groups[i].lying ? { left: `${value(0) ?? 0}%` } : { top: `${100 - (value(0) ?? 100)}%` })"></i>
          </span>
        </template>
        <template v-else>
          <span v-for="(k, n) in keysOf(i)" :key="n" class="cover-key mdi" :class="{ disabled: k.disabled }" :style="box(keyBoxes(layout.groups[i], keysOf(i).length)[n])">{{ icon(k.icon) }}</span>
        </template>
        <span v-if="i < 2 && !empty(layout.groups[i].caption)" class="cover-caption" :style="box(layout.groups[i].caption)">{{ caption(i, layout.groups[i]) }}</span>
      </template>
      <span v-if="!empty(layout.swap)" class="cover-key mdi" :style="box(layout.swap)">{{ icon('blinds-horizontal') }}</span>
    </template>
    <slot v-else name="fallback" />
  </span>
</template>
<style scoped>
.cover-preview { flex: 1; min-height: 0; min-width: 0; align-self: stretch; position: relative; font-size: 10px; display: block; }
.cover-slider, .cover-key, .cover-caption { position: absolute; }
.cover-slider { border-radius: 12px; background: var(--tile-circle); overflow: hidden; }
.cover-slider.lying { border-radius: 9px; }
.cover-slider .fill { position: absolute; left: 0; top: 0; right: 0; background: var(--tile-accent); }
.cover-slider.lying .fill { bottom: 0; right: auto; }
.cover-slider .handle { position: absolute; left: 30%; width: 40%; height: 3px; border-radius: 3px; background: white; transform: translateY(-7px); }
.cover-slider.lying .handle { left: auto; top: 25%; width: 3px; height: 50%; transform: translateX(-7px); }
.cover-slider.tilt .handle { left: 20%; width: 60%; height: 5px; background: var(--tile-accent); transform: translateY(50%); }
.cover-slider.tilt.lying .handle { left: auto; top: 20%; width: 5px; height: 60%; transform: translateX(-50%); }
.slats { position: absolute; inset: 0; width: 100%; height: 100%; }
.slats line { stroke: var(--tile-accent); stroke-opacity: .32; stroke-linecap: round; }
.cover-key { border-radius: 999px; display: grid; place-items: center; font-size: 1.6em; background: var(--tile-circle); color: var(--tile-accent); }
.cover-key.disabled { opacity: .35; }
.cover-caption { line-height: 1.3; text-align: center; text-overflow: ellipsis; white-space: nowrap; overflow: hidden; color: var(--muted); }
</style>
