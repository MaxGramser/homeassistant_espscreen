<script setup lang="ts">
import { useEventListener } from '@vueuse/core';
import { computed, ref, watch } from 'vue';
import { useGesture } from '../composables/useGesture';
import { t } from '../i18n';
import { dimensions, sizeOf, type Size } from '../model/layout';
import type { Tile } from '../types';
import { useScreenStore } from "../stores/screen";
import { resizeChoices, resizeTile } from "../editor/tiles";
import { useDocumentStore } from "../stores/document";

const scr = useScreenStore();
const doc = useDocumentStore();
const { grid } = doc.editorLayout;

const props = defineProps<{ tile: Tile }>();
type Axis = 'columns' | 'rows';
const axes: Axis[] = ['columns', 'rows'];
const following = useGesture();
const available = computed(() => axes.filter(axis => resizeChoices(props.tile, axis).some(size => size !== sizeOf(props.tile))));
const gesture = ref<{ axis: Axis; pointer: number; start: number; pitch: number; gap: number;
  left: number; top: number; width: number; height: number; original: number; size: Size; choices: Size[] }>();
const outline = computed(() => {
  const g = gesture.value;
  if (!g) return {};
  const length = dimensions(g.size, grid)[g.axis] * g.pitch - g.gap;
  return { left: `${g.left}px`, top: `${g.top}px`, width: `${g.axis === 'columns' ? length : g.width}px`,
    height: `${g.axis === 'rows' ? length : g.height}px` };
});
function start(event: PointerEvent, axis: Axis) {
  if (event.button !== 0 || gesture.value) return;
  const element = (event.currentTarget as HTMLElement).closest<HTMLElement>('.tile');
  if (!element?.parentElement) return;
  const choices = resizeChoices(props.tile, axis);
  if (choices.length < 2) return;
  const rect = element.getBoundingClientRect(), shape = dimensions(sizeOf(props.tile), grid);
  // Bounding rectangles include the advanced map's zoom. CSS gaps do not.
  const scale = element.offsetWidth ? rect.width / element.offsetWidth : 1;
  const gap = (parseFloat(getComputedStyle(element.parentElement)[axis === 'columns' ? 'columnGap' : 'rowGap']) || 0) * scale;
  gesture.value = { axis, pointer: event.pointerId, start: axis === 'columns' ? event.clientX : event.clientY,
    pitch: ((axis === 'columns' ? rect.width : rect.height) + gap) / shape[axis], gap,
    left: rect.left, top: rect.top, width: rect.width, height: rect.height,
    original: shape[axis], size: sizeOf(props.tile), choices };
  event.preventDefault();
  // The pointer is followed on the whole window while the edge is held; Escape or a scroll lets go of it.
  following.begin(() => {
    useEventListener(window, 'pointermove', move);
    useEventListener(window, 'pointerup', finish);
    useEventListener(window, 'pointercancel', cancel);
    useEventListener(window, 'keydown', escape, { capture: true });
    useEventListener(window, 'scroll', cancel, { capture: true });
  });
}
function move(event: PointerEvent) {
  const g = gesture.value;
  if (!g || event.pointerId !== g.pointer) return;
  event.preventDefault();
  const wanted = g.original + ((g.axis === 'columns' ? event.clientX : event.clientY) - g.start) / g.pitch;
  g.size = g.choices.reduce((best, size) => Math.abs(dimensions(size, grid)[g.axis] - wanted) < Math.abs(dimensions(best, grid)[g.axis] - wanted) ? size : best, sizeOf(props.tile));
}
function cancel() {
  gesture.value = undefined;
  following.end();
}
function finish(event: PointerEvent) {
  const g = gesture.value;
  if (!g || event.pointerId !== g.pointer) return;
  move(event);
  const { size, axis } = g;
  cancel();
  resizeTile(props.tile, size, axis);
}
function escape(event: KeyboardEvent) {
  if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); cancel(); }
}
function keyboard(event: KeyboardEvent, axis: Axis) {
  const direction = axis === 'columns' ? ({ ArrowLeft: -1, ArrowRight: 1 } as Record<string, number>)[event.key]
    : ({ ArrowUp: -1, ArrowDown: 1 } as Record<string, number>)[event.key];
  if (!direction) return;
  event.preventDefault();
  const choices = resizeChoices(props.tile, axis).sort((a, b) => dimensions(a, grid)[axis] - dimensions(b, grid)[axis]);
  const target = choices[choices.indexOf(sizeOf(props.tile)) + direction];
  if (target) resizeTile(props.tile, target, axis);
}
watch(() => scr.selected, cancel);
</script>

<template>
  <button v-for="axis in available" :key="axis" type="button" class="resize-handle" :class="axis"
    :aria-label="t(`editor.tile.resize.${axis}`)" :title="t(`editor.tile.resize.${axis}`)"
    @pointerdown.stop="start($event, axis)" @click.stop @keydown.stop="keyboard($event, axis)">
    <span aria-hidden="true">
      <!-- MDI drag-horizontal from the bundled font, centred on its ink bounds.
           SVG avoids the font baseline shifting the dots inside the grip. -->
      <svg viewBox="0 -64 512 512" focusable="false">
        <path d="M64 128V171H107V128ZM64 213V256H107V213ZM149 128V171H192V128ZM149 213V256H192V213ZM235 128V171H277V128ZM235 213V256H277V213ZM320 128V171H363V128ZM320 213V256H363V213ZM405 128V171H448V128ZM405 213V256H448V213Z" />
      </svg>
    </span>
  </button>
  <Teleport to="body">
    <div v-if="gesture" class="tile-resize-preview" :style="outline" aria-hidden="true">
      <span>{{ dimensions(gesture.size, grid).columns }} × {{ dimensions(gesture.size, grid).rows }}</span>
    </div>
  </Teleport>
</template>

<style>
.resize-handle { position: absolute; z-index: 3; display: grid; place-items: center; padding: 0; border: 0; background: transparent; opacity: 0; pointer-events: none; touch-action: none; }
.tile:has(> .resize-handle) { overflow: visible; }
.tile:has(> .resize-handle):is(:hover, :focus-within) { z-index: 4; }
/* Absolute offsets start inside the 1px border. Centre the grip on its stroke. */
.resize-handle.columns { right: -.5px; top: 50%; width: 24px; height: 40px; transform: translate(50%, -50%); cursor: ew-resize; }
.resize-handle.rows { bottom: -.5px; left: 50%; width: 40px; height: 24px; transform: translate(-50%, 50%); cursor: ns-resize; }
.resize-handle span { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); display: grid; place-items: center; width: 12px; height: 30px; border: 1px solid var(--line); border-radius: 8px; background: var(--surface); color: var(--muted); box-shadow: 0 1px 3px rgb(0 0 0 / .12); font-size: 14px; }
.resize-handle.rows span { width: 30px; height: 12px; }
.resize-handle svg { position: absolute; top: 50%; left: 50%; width: 18px; height: 18px; fill: currentColor; transform: translate(-50%, -50%); }
.resize-handle.columns svg { transform: translate(-50%, -50%) rotate(90deg); }
.tile:hover .resize-handle, .tile:focus-within .resize-handle, .resize-handle:focus-visible { opacity: 1; pointer-events: auto; }
.resize-handle:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.tile-resize-preview { position: fixed; z-index: 10000; box-sizing: border-box; pointer-events: none; border: 2px solid var(--accent); border-radius: 12px; background: var(--accent-soft); opacity: .85; }
.tile-resize-preview > span { position: absolute; right: 6px; bottom: 6px; padding: 3px 6px; border-radius: 5px; background: var(--surface); color: var(--ink); font-size: 12px; }
@media (hover: none) { .tile.chosen .resize-handle { opacity: 1; pointer-events: auto; } }
</style>
