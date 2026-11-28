<script setup lang="ts">
// A section on the mockup (docs/PAGES.md "Sections"), drawn as the glass draws it (module_sections.h): the soft panel
// behind exactly its cells, its corner the card's plus the padding, and in its top the icon, the title and the summary,
// their capitals as far from the panel's top as from its side (in contrast: the page's opposite). The title row is
// what a section is taken by: a click opens its drawer, a click on its title names it there and then, a drag carries
// it whole, and the grips at its right and bottom edges make it wider, narrower, taller or lower.
import { useElementSize, useEventListener } from "@vueuse/core";
import { computed, nextTick, ref } from "vue";
import { vDrag } from "../drag";
import { t } from "../i18n";
import { useGesture } from "../composables/useGesture";
import { dotted, glyph, inkOf } from "../model/topbar";
import { resizeSection, showEdit, setSectionFields } from "../editor/sections";
import * as model from "../model/sections";
import type { SectionMetrics } from "../model/sections";
import theme from "virtual:esp-screens-theme";
import { useCanvasStore } from "../stores/canvas";
import { useDocumentStore } from "../stores/document";
import { useDragStore } from "../stores/drag";
import { useEntitiesStore } from "../stores/entities";
import { useInspectorStore } from "../stores/inspector";
import type { SectionBlock } from "../types";

const props = defineProps<{ block: SectionBlock; metrics: SectionMetrics; preview?: boolean; carried?: boolean }>();
const canvas = useCanvasStore();
const doc = useDocumentStore();
const insp = useInspectorStore();
const entities = useEntitiesStore();
const dragging = useDragStore();

const glass = computed(() => Number(canvas.deviceStyle["--glass"]) || 1);
const shape = computed(() => doc.screenShape as typeof doc.screenShape & import("../model/ui-scale").Shape);
const gap = computed(() => shape.value.spacing?.gap_y ?? shape.value.spacing?.gap ?? 12);
const radius = computed(() => (shape.value.spacing?.radius ?? 22) + gap.value);
const role = (name: string, dark = false) => `#${theme.roles[name][dark ? "dark" : "light"].toString(16).padStart(6, "0")}`;
// The panel covers exactly the section's cells (the block model); the header stands in its top, as high as the room
// the section's first row of tiles gives it (module_sections.h header).
const area = computed(() => ({ gridColumn: `${props.block.column + 1} / span ${props.block.columns}`, gridRow: `${props.block.row + 1} / span ${props.block.rows}` }));
// A section in contrast takes the page's opposite and its words that panel's ink (SECTION_CONTRAST, _INK).
// Its tiles following the contrast, the whole section is the other look: its own panel, ink and muted words there (the
// mockup is the light look, so the dark one's).
const follow = computed(() => Boolean(props.block.contrast && props.block.contrastTiles));
const ink = computed(() => (follow.value ? role("INK", true) : role(props.block.contrast ? "SECTION_CONTRAST_INK" : "INK")));
const muted = computed(() => (follow.value ? role("MUTED", true) : role(props.block.contrast ? "SECTION_CONTRAST_INK" : "MUTED")));
const panelStyle = computed(() => ({ ...area.value, borderRadius: `calc(var(--glass) * ${radius.value}px)`,
  background: follow.value ? role("SECTION", true) : role(props.block.contrast ? "SECTION_CONTRAST" : "SECTION") }));
const headStyle = computed(() => ({ ...area.value, height: `calc(var(--glass) * ${props.metrics.header - props.metrics.pad}px)` }));
const chosen = computed(() => insp.inspector?.kind === "section" && insp.inspector.id === props.block.id);

// ---- The header's words, in the glass's pixels times the mockup's zoom ----
const px = (n: number) => n * glass.value;
const fonts = computed(() => {
  const f = shape.value.fonts ?? {};
  return { title: `700 ${px(f.label ?? 18)}px "Bar Roboto"`, summary: `400 ${px(f.sublabel ?? 16)}px "Bar Roboto"`, icon: `${px(f.icon_mini ?? 26)}px "Tile Icons"` };
});
const cap = computed(() => inkOf("H", fonts.value.title));
// The capitals' top on the inset, so the title's baseline is that less their height (module_sections.h title_top).
const baseline = computed(() => px(props.metrics.inset) - cap.value.top);
const iconGlyph = computed(() => {
  const cp = props.block.icon ? entities.iconNamed(props.block.icon)?.cp : undefined;
  return cp ? glyph(cp) : "";
});
const iconInk = computed(() => (iconGlyph.value ? inkOf(iconGlyph.value, fonts.value.icon) : null));
const iconX = computed(() => px(props.metrics.inset) - (iconInk.value?.left ?? 0));
const iconY = computed(() => baseline.value + cap.value.top / 2 - ((iconInk.value?.top ?? 0) + (iconInk.value?.bottom ?? 0)) / 2);
const titleX = computed(() => px(props.metrics.inset) + (iconInk.value ? iconInk.value.right - iconInk.value.left + px(7 * (shape.value.dpi ?? 170) / 170) : 0));
const summaryText = computed(() => {
  const entity = props.block.summary;
  if (!entity) return "";
  const live = entities.liveOf(entity);
  if (!live) return "";
  // The state as the top bar words it (header_bar, the add-on's section_sums): its own word, else the state and its unit.
  const unit = live.a?.unit_of_measurement;
  return live.word || (unit ? `${live.state} ${unit}` : live.state);
});

// The title cut with LVGL's dots where it does not fit beside the summary (module_sections.h fit_title).
const head = ref<HTMLElement | null>(null);
const { width: headWidth } = useElementSize(head);
const titleShown = computed(() => {
  const summary = summaryText.value ? inkOf(summaryText.value, fonts.value.summary).advance + px(gap.value) : 0;
  const room = headWidth.value - titleX.value - px(props.metrics.inset) - summary;
  return headWidth.value ? dotted(props.block.title, fonts.value.title, Math.max(0, room)) : props.block.title;
});
// ---- A click on the title names it in place ----
const editing = ref(false);
const draft = ref("");
const field = ref<HTMLInputElement | null>(null);
async function rename(event: MouseEvent) {
  if (props.preview || dragging.active) return;
  event.stopPropagation();
  insp.openSection(props.block.id);
  draft.value = props.block.title;
  editing.value = true;
  await nextTick();
  field.value?.focus();
  field.value?.select();
}
function done(keep: boolean) {
  if (!editing.value) return;
  editing.value = false;
  const title = draft.value.trim();
  if (keep && title && title !== props.block.title) setSectionFields(props.block.id, { title });
}
function open(event: MouseEvent) {
  if (props.preview) return;
  event.stopPropagation();
  insp.openSection(props.block.id);
}

// ---- The grips: wider or narrower at the right edge, taller or lower at the bottom ----
type Axis = "columns" | "rows";
const following = useGesture();
const gesture = ref<{ axis: Axis; pointer: number; start: number; pitch: number; original: number; value: number; size: { columns: number; rows: number } } | null>(null);
function grip(event: PointerEvent, axis: Axis) {
  if (event.button !== 0 || gesture.value || props.preview) return;
  const panel = (event.currentTarget as HTMLElement).closest<HTMLElement>(".section-panel");
  const tiles = panel?.parentElement;
  if (!panel || !tiles) return;
  const rect = tiles.getBoundingClientRect(), style = getComputedStyle(tiles);
  const gapX = parseFloat(style.columnGap) || 0, cells = axis === "columns" ? doc.editorLayout.grid.columns : doc.editorLayout.grid.rows;
  const length = axis === "columns" ? rect.width : rect.height;
  gesture.value = { axis, pointer: event.pointerId, start: axis === "columns" ? event.clientX : event.clientY,
    pitch: (length + gapX) / cells, original: props.block[axis], value: props.block[axis], size: { columns: props.block.columns, rows: props.block.rows } };
  event.preventDefault();
  following.begin(() => {
    useEventListener(window, "pointermove", move);
    useEventListener(window, "pointerup", finish);
    useEventListener(window, "pointercancel", cancel);
    useEventListener(window, "keydown", (e: KeyboardEvent) => { if (e.key === "Escape") { e.preventDefault(); cancel(); } }, { capture: true });
  });
}
function wanted(event: PointerEvent) {
  const g = gesture.value!;
  return Math.max(1, Math.round(g.original + ((g.axis === "columns" ? event.clientX : event.clientY) - g.start) / g.pitch));
}
function edit(value: number) {
  const g = gesture.value, grid = doc.documentGrid;
  if (!g || !doc.layout || !grid) return null;
  return model.resizeSection(doc.layout, doc.screenGridOf(grid), props.block.id, g.axis === "columns" ? value : g.size.columns,
    g.axis === "rows" ? value : g.size.rows);
}
function move(event: PointerEvent) {
  const g = gesture.value;
  if (!g || event.pointerId !== g.pointer) return;
  event.preventDefault();
  const value = wanted(event);
  if (value === g.value) return;
  g.value = value;
  // The page shows the section at that size as it moves, its tiles laid out again where it gets too narrow for them.
  const next = edit(value);
  showEdit(next && !("refused" in next) ? next : null);
}
function cancel() {
  gesture.value = null;
  showEdit(null);
  following.end();
}
function finish(event: PointerEvent) {
  const g = gesture.value;
  if (!g || event.pointerId !== g.pointer) return;
  // The block as it was when the grip was taken: the props show the preview until the page is drawn again.
  const value = wanted(event), axis = g.axis, before = g.size;
  cancel();
  const swallow = (click: MouseEvent) => { click.stopPropagation(); click.preventDefault(); };
  window.addEventListener("click", swallow, { capture: true, once: true });
  setTimeout(() => window.removeEventListener("click", swallow, { capture: true }), 0);
  if (value !== before[axis]) resizeSection(props.block.id, axis === "columns" ? value : before.columns, axis === "rows" ? value : before.rows);
}
function keyboard(event: KeyboardEvent, axis: Axis) {
  const step = axis === "columns" ? ({ ArrowLeft: -1, ArrowRight: 1 } as Record<string, number>)[event.key]
    : ({ ArrowUp: -1, ArrowDown: 1 } as Record<string, number>)[event.key];
  if (!step) return;
  event.preventDefault();
  resizeSection(props.block.id, props.block.columns + (axis === "columns" ? step : 0), props.block.rows + (axis === "rows" ? step : 0));
}
</script>

<template>
  <div class="section-panel" :class="{ chosen, carried, preview }" :style="panelStyle" :data-section-id="block.id" @click="open">
    <template v-if="!preview">
      <button v-for="axis in (['columns', 'rows'] as const)" :key="axis" type="button" class="resize-handle section-grip" :class="axis"
        :aria-label="t(`editor.sections.resize_${axis}`)" :title="t(`editor.sections.resize_${axis}`)"
        @pointerdown.stop="grip($event, axis)" @click.stop @keydown.stop="keyboard($event, axis)">
        <span aria-hidden="true"><svg viewBox="0 -64 512 512" focusable="false"><path d="M64 128V171H107V128ZM64 213V256H107V213ZM149 128V171H192V128ZM149 213V256H192V213ZM235 128V171H277V128ZM235 213V256H277V213ZM320 128V171H363V128ZM320 213V256H363V213ZM405 128V171H448V128ZM405 213V256H448V213Z" /></svg></span>
      </button>
    </template>
  </div>
  <div ref="head" class="section-head" :class="{ chosen, preview }" :style="headStyle" :data-section-id="block.id"
    v-drag="preview ? null : { kind: 'section', id: block.id }" :title="preview ? undefined : t('editor.sections.head_title')"
    role="button" :tabindex="preview ? undefined : 0" :aria-label="t('editor.sections.aria', { title: block.title })"
    @click="open" @keydown.enter.prevent="insp.openSection(block.id)">
    <svg class="section-words" aria-hidden="true">
      <text v-if="iconGlyph" :x="iconX" :y="iconY" :fill="ink" :style="{ font: fonts.icon }">{{ iconGlyph }}</text>
      <text v-if="!editing" class="section-title" :x="titleX" :y="baseline" :fill="ink" :style="{ font: fonts.title }">{{ titleShown }}</text>
      <text v-if="summaryText" x="100%" :dx="-px(metrics.inset)" :y="baseline" text-anchor="end" :fill="muted" :style="{ font: fonts.summary }">{{ summaryText }}</text>
    </svg>
    <button v-if="!preview && !editing" type="button" class="section-title-hit" :style="{ left: `${titleX}px`, top: `${baseline + cap.top - px(2)}px`, height: `${-cap.top + px(6)}px`, font: fonts.title }"
      :aria-label="t('editor.sections.rename')" @click="rename">{{ titleShown }}</button>
    <input v-if="editing" ref="field" v-model="draft" class="section-title-field" maxlength="48" :aria-label="t('editor.sections.title')"
      :style="{ left: `${titleX - 3}px`, top: `${baseline + cap.top - px(4)}px`, font: fonts.title }"
      @pointerdown.stop @click.stop @keydown.enter.prevent="done(true)" @keydown.esc.prevent.stop="done(false)" @blur="done(true)" />
  </div>
</template>

<style>
/* A section's panel stands behind the page's cards and empty cells, which come after it. */
.tiles > .cell { position: relative; }
.section-panel { position: relative; min-width: 0; min-height: 0; z-index: 0; cursor: default; transition: box-shadow .12s ease; }
.section-panel.chosen { box-shadow: 0 0 0 2px var(--accent); }
.section-panel.carried { opacity: .55; }
/* The grips take the pointer even before they show, so a press on a section's edge always takes them. */
.section-grip { pointer-events: auto; transition: opacity .12s ease; }
.section-panel:not(.preview):hover > .section-grip, .section-panel.chosen > .section-grip, .section-grip:focus-visible, .section-grip:hover { opacity: 1; }
.section-grip.columns { right: 0; top: 50%; width: 24px; height: 40px; transform: translate(50%, -50%); cursor: ew-resize; }
.section-grip.rows { bottom: 0; left: 50%; width: 40px; height: 24px; transform: translate(-50%, 50%); cursor: ns-resize; }
.section-head { position: relative; align-self: start; min-width: 0; min-height: 0; z-index: 1; cursor: grab; touch-action: none; user-select: none; }
.section-head.preview { cursor: default; }
.section-head:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; border-radius: 8px; }
.section-words { position: absolute; inset: 0; width: 100%; height: 100%; overflow: hidden; pointer-events: none; }
.section-title-hit { position: absolute; padding: 0; border: 0; background: transparent; color: transparent; white-space: nowrap; cursor: text; max-width: calc(100% - 40px); overflow: hidden; }
.section-title-hit:hover { background: rgb(0 0 0 / .05); border-radius: 4px; }
.section-title-field { position: absolute; width: min(70%, 18em); padding: 1px 3px; border: 1px solid var(--accent); border-radius: 4px; background: #fff; color: #1b1b1b; outline: none; box-shadow: 0 0 0 3px rgb(0 0 0 / .06); }
</style>
