<script setup lang="ts">
// The to-do card (docs/TODO.md) on the mockup: the list as the add-on sends it to the screen (api/todo/preview,
// todo_feed.card), laid out as module_todo.h lays it out at the screen's own sizes scaled to the glass. One cell shows
// the count, a wide cell the first items beside the name, and a card with room for the name and two rows the list: a
// round box per item, a due day where the name leaves room, a line for what does not fit, and what is done under what
// is open. The keys are drawn, not live: ticking and typing happen on the screen.
import { useElementSize } from "@vueuse/core";
import { computed, onBeforeUnmount, ref, watch } from "vue";
import theme from "virtual:esp-screens-theme";
import { send } from "../../api";
import { glyph } from "../../model/topbar";
import { touchMin, uiScale } from "../../model/ui-scale";
import { i18n, t } from "../../i18n";
import type { TileCardView } from "../../composables/useTileCard";
import { useDocumentStore } from "../../stores/document";

const props = defineProps<{ card: TileCardView }>();
const card = props.card;
const doc = useDocumentStore();

type Row = [number, number, string, number?];
type List = { v: number; w?: number; f?: number; n?: number; d?: number; i?: Row[] };
const list = ref<List | null>(null);
const key = computed(() => JSON.stringify([card.tile.entity, card.tile.options?.todo_order, card.tile.options?.todo_completed, card.tile.options?.todo_due,
  card.tile.options?.todo_add, card.current?.state]));
let asked = 0;
async function load() {
  const ask = ++asked;
  try {
    const answer = await send<{ todo: List }>("todo/preview", "POST", { tile: { entity: card.tile.entity, options: card.tile.options ?? {} } });
    if (ask === asked) list.value = answer.todo;
  } catch { if (ask === asked) list.value = null; }
}
watch(key, () => void load(), { immediate: true });
const again = setInterval(() => void load(), 60_000);
onBeforeUnmount(() => clearInterval(again));

const face = ref<HTMLElement | null>(null);
const size = useElementSize(face);
const hex = (n: number) => `#${n.toString(16).padStart(6, "0")}`;
const role = (name: string) => hex(theme.roles[name].light);

// The screen's sizes (module_todo.h), in editor pixels.
const m = computed(() => {
  const shape = doc.screenShape, { px } = uiScale(shape), glass = card.glassScale || 1;
  const fonts = ("fonts" in shape ? shape.fonts : undefined) ?? {};
  const label = fonts.label ?? 18, small = fonts.sublabel ?? 16, control = fonts.sublabel_big ?? 21, mini = fonts.icon_mini ?? 26;
  const dpi = shape.dpi || 170, mm = (n: number) => Math.floor((dpi * n + 12) / 25);
  const w = size.width.value / glass, h = size.height.value / glass;
  const big = w >= px(250), font = big ? control : small, touch = touchMin(shape);
  const rowh = Math.max(touch, Math.round(font * 1.172) + px(14)), head = Math.max(px(44), touch);
  const isList = h - head - px(6) >= 2 * rowh;
  const wide = !isList && w >= mm(52) && (h + px(16)) / 2 >= touch;
  const view = isList ? "list" : wide ? "wide" : "count";
  const rowsH = isList ? h - head - px(6) : 0, cap = Math.max(1, Math.floor(rowsH / rowh));
  return { glass, view, label, small, control, font, rowh, head, touch, cap, tick: Math.max(px(26), Math.round(mini * 1.0) + px(2)), gap: px(12),
    circle: px(44), add: w >= px(44) + touch + px(110), mini };
});
const g = (n: number) => `${(n * m.value.glass).toFixed(2)}px`;
const rows = computed(() => list.value?.i ?? []);
const open = computed(() => rows.value.filter((row) => !(row[1] & 1)));
const total = computed(() => list.value?.n ?? open.value.length);
const shown = computed(() => {
  if (m.value.view === "wide") return open.value.slice(0, 2);
  if (m.value.view !== "list") return [];
  const cap = m.value.cap, more = cap >= 4 && total.value > cap, keep = more ? cap - 1 : cap;
  const out = open.value.slice(0, keep);
  // What is done comes only into room that what is open leaves.
  if (total.value <= out.length) for (const row of rows.value) if (row[1] & 1 && out.length < keep) out.push(row);
  return out;
});
const rest = computed(() => (m.value.view === "list" && m.value.cap >= 4 ? Math.max(0, total.value - shown.value.filter((row) => !(row[1] & 1)).length) : 0));
const mayAdd = computed(() => Boolean((list.value?.f ?? 0) & 1) && m.value.add);
// A due day by its distance from today, as the screen words it (module_todo.cpp).
function day(days: number) {
  const locale = String(i18n.global.locale.value);
  if (days >= -1 && days <= 1) return new Intl.RelativeTimeFormat(locale, { numeric: "auto" }).format(days, "day").replace(/^./, (c) => c.toUpperCase());
  const date = new Date(Date.now() + days * 86_400_000);
  return days > 1 && days < 7 ? new Intl.DateTimeFormat(locale, { weekday: "long" }).format(date).replace(/^./, (c) => c.toUpperCase())
    : new Intl.DateTimeFormat(locale, { day: "numeric", month: "short" }).format(date);
}
const preview = computed(() => (m.value.view === "count" && size.width.value / m.value.glass >= 300 ? open.value.slice(0, 5).map((row) => row[2]).join(", ") : ""));
const more = computed(() => t("editor.mockup.todo_more", { x: rest.value }));
const blue = hex(theme.ha.BLUE), red = hex(theme.ha.RED);
</script>

<template>
  <div ref="face" class="todo-face" :class="m.view" :style="{ '--muted': role('MUTED'), '--subtle': role('SUBTLE'), '--track': role('TRACK'), '--ink': role('INK'), '--blue': blue, '--red': red }">
    <template v-if="m.view === 'list'">
      <div class="td-head" :style="{ height: g(m.head) }">
        <span class="ic mdi td-circle" :style="{ width: g(m.circle), height: g(m.circle), fontSize: g(m.mini) }">{{ glyph(card.icon) }}</span>
        <span class="td-names">
          <span class="td-name" :style="{ fontSize: g(m.label) }">{{ card.texts.name }}</span>
          <span class="td-count" :style="{ fontSize: g(m.small) }">{{ card.texts.line }}</span>
        </span>
        <span v-if="mayAdd" class="td-add mdi" :style="{ width: g(m.touch), height: g(m.touch), fontSize: g(m.mini) }">{{ glyph("F0415") }}</span>
      </div>
      <div class="td-rows" :style="{ marginTop: g(6) }">
        <div v-for="row in shown" :key="row[0]" class="td-row" :class="{ done: row[1] & 1, late: row[1] & 2 }" :style="{ height: g(m.rowh), fontSize: g(m.font) }">
          <span class="td-tick mdi" :style="{ width: g(m.tick), height: g(m.tick), fontSize: g(m.mini), marginRight: g(m.gap) }">{{ row[1] & 1 ? glyph("F012C") : "" }}</span>
          <span class="td-text">{{ row[2] }}</span>
          <span v-if="row[3] !== undefined && !(row[1] & 1)" class="td-due" :style="{ fontSize: g(m.small) }">{{ day(row[3]) }}</span>
        </div>
        <div v-if="rest" class="td-more" :style="{ height: g(m.rowh), fontSize: g(m.small), paddingLeft: g(m.tick + m.gap) }">{{ more }}</div>
      </div>
    </template>
    <template v-else>
      <span class="head td-plain">
        <span class="ic mdi">{{ glyph(card.icon) }}</span>
        <span class="tx"><span class="nm">{{ card.texts.name }}</span><span class="st">{{ card.texts.line }}<template v-if="preview"> · {{ preview }}</template></span></span>
      </span>
      <div v-if="m.view === 'wide' && shown.length" class="td-side">
        <div v-for="row in shown" :key="row[0]" class="td-row" :class="{ late: row[1] & 2 }" :style="{ fontSize: g(m.small) }">
          <span class="td-tick" :style="{ width: g(m.tick), height: g(m.tick), marginRight: g(m.gap) }"></span>
          <span class="td-text">{{ row[2] }}</span>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.todo-face { position: relative; flex: 1 1 auto; align-self: stretch; min-width: 0; min-height: 0; width: 100%; overflow: hidden; text-align: left; display: flex; flex-direction: column; }
.todo-face.wide, .todo-face.count { flex-direction: row; align-items: center; }
.td-plain { flex: 0 1 auto; min-width: 0; }
.todo-face.wide .td-plain { flex: 0 0 46%; }
.td-side { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; justify-content: space-around; align-self: stretch; }
.td-head { display: flex; align-items: center; gap: 0.6em; flex: 0 0 auto; }
.td-circle { flex: 0 0 auto; }
.td-names { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; line-height: 1.17; }
.td-name { font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--ink); }
.td-count { color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.td-add { flex: 0 0 auto; border-radius: 50%; background: var(--track); color: var(--ink); display: grid; place-items: center; }
.td-rows { flex: 1 1 auto; min-height: 0; overflow: hidden; }
.td-row { display: flex; align-items: center; min-width: 0; color: var(--ink); }
.td-tick { flex: 0 0 auto; box-sizing: border-box; border-radius: 50%; border: 2px solid var(--subtle); display: grid; place-items: center; color: #fff; }
.td-row.late .td-tick { border-color: var(--red); }
.td-row.done .td-tick { border-color: var(--blue); background: var(--blue); }
.td-row.done .td-text { color: var(--subtle); text-decoration: line-through; }
.td-text { flex: 1 1 auto; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.td-due { flex: 0 0 auto; margin-left: 0.8em; color: var(--muted); }
.td-row.late .td-due { color: var(--red); }
.td-more { display: flex; align-items: center; color: var(--muted); }
</style>
