<script setup lang="ts">
// The template tile (docs/TEXT_TILE.md) on the mockup: the rows Home Assistant rendered, as the add-on sends them to
// the screen (api/text/preview, text_tile.block), laid out as module_text_card.h lays them out: headings in the bold
// label face and the rest in the face a calendar's lines take, at the screen's own font sizes and spacing scaled to
// the glass; bold in ink and the rest quiet, the tones in Home Assistant's green and red and the screen's blue;
// bullets with their dot; a table's value columns as wide as their widest cell and right-aligned, the first taking the
// rest, a line under each row. An empty result leaves the card bare, as on the screen; an error is its one red line.
import { useDebounceFn } from "@vueuse/core";
import { computed, onBeforeUnmount, ref, watch } from "vue";
import theme from "virtual:esp-screens-theme";
import { send } from "../../api";
import { uiScale } from "../../model/ui-scale";
import type { TileCardView } from "../../composables/useTileCard";
import { useDocumentStore } from "../../stores/document";
import { useScreenStore } from "../../stores/screen";

const props = defineProps<{ card: TileCardView }>();
const card = props.card;
const doc = useDocumentStore();
const scr = useScreenStore();

// One answer per template for every card that shows it, asked again after a minute.
const md = ref<Md | null>(null);
const template = computed(() => (card.tile.options?.template as string | undefined) ?? "");
const fetch = useDebounceFn(async () => {
  const text = template.value;
  if (!text.trim()) { md.value = { v: 1, r: [] }; return; }
  md.value = await previewOf(text, scr.currentScreen?.id);
}, 500);
watch(template, () => void fetch(), { immediate: true });
const again = setInterval(() => void fetch(), 60_000);
onBeforeUnmount(() => clearInterval(again));

const hex = (n: number) => `#${n.toString(16).padStart(6, "0")}`;
const role = (name: string) => hex(theme.roles[name].light);
const INKS = [role("MUTED"), role("INK"), hex(theme.ha.GREEN), hex(theme.ha.RED), role("ACCENT")];

// The screen's faces and steps (module_text_card.h title_face, meta_face, P), in editor pixels.
const metrics = computed(() => {
  const shape = doc.screenShape, { large, px } = uiScale(shape), glass = card.glassScale || 1;
  const fonts = ("fonts" in shape ? shape.fonts : undefined) ?? {};
  const label = fonts.label ?? (large ? 18 : 11), small = fonts.sublabel ?? (large ? 16 : 11), control = fonts.sublabel_big ?? (large ? 21 : 14);
  const P = (big: number, little: number) => px(large ? big : little) * glass;
  return {
    head: (large ? label : control) * glass, text: (large ? small : control) * glass,
    rowGap: P(4, 2), headGap: P(8, 4), indent: P(14, 9), dot: Math.max(3, px(large ? 5 : 3)) * glass, cellGap: P(10, 6),
  };
});
const rows = computed(() => md.value?.r ?? []);
const empty = computed(() => Boolean(md.value && !md.value.e && !rows.value.length));
const table = (row: Row) => row[0] === "t" || row[0] === "th";
const cells = (row: Row) => (table(row) ? (row[1] as Run[][]) : [row[1] as Run[]]);
// A run's ink: bold and the tones as the screen paints them; a plain run takes its row's own (a heading's and a cell's
// ink, a line's and a bullet's quiet one).
const ink = (tone: number, plain: string) => (tone === 0 ? plain : INKS[tone]);
const plainOf = (row: Row) => (row[0] === "h" || row[0] === "t" ? INKS[1] : INKS[0]);
// A table is the rows of one kind in a row: its columns are laid out together, as measure_table does.
const blocks = computed(() => {
  const out: { table: boolean; rows: Row[] }[] = [];
  for (const row of rows.value) {
    const last = out[out.length - 1];
    if (table(row) && last?.table) last.rows.push(row);
    else out.push({ table: table(row), rows: [row] });
  }
  return out;
});
const columns = (block: { rows: Row[] }) => {
  const n = Math.max(...block.rows.map((row) => cells(row).length));
  return n > 1 ? `minmax(0, 1fr) repeat(${n - 1}, max-content)` : "minmax(0, 1fr)";
};
const gapBefore = (i: number) => (i === 0 ? 0 : blocks.value[i].rows[0][0] === "h" ? metrics.value.headGap : metrics.value.rowGap);
</script>

<script lang="ts">
type Run = [number, string];
type Row = [string, Run[] | Run[][]];
type Md = { v: number; r?: Row[]; e?: string };
// The answers, shared by every card of the page: a template asked once while its answer is fresh.
const answers = new Map<string, { at: number; md: Promise<Md> }>();
async function previewOf(template: string, inbox?: string): Promise<Md> {
  const key = `${inbox ?? ""}\n${template}`, known = answers.get(key);
  if (known && Date.now() - known.at < 30_000) return known.md;
  const md = send<{ md: Md }>("text/preview", "POST", { template, inbox }).then((a) => a.md).catch(() => ({ v: 1, r: [] }));
  answers.set(key, { at: Date.now(), md });
  if (answers.size > 40) answers.delete(answers.keys().next().value!);
  return md;
}
</script>

<template>
  <div class="text-face" :class="{ empty }" :style="{ '--head': `${metrics.head}px`, '--text': `${metrics.text}px`, '--indent': `${metrics.indent}px`,
    '--dot': `${metrics.dot}px`, '--cell-gap': `${metrics.cellGap}px`, '--muted': INKS[0], '--rule': INKS[0] }">
    <p v-if="md?.e" class="tf-line tf-error" :style="{ color: INKS[3] }">{{ md.e }}</p>
    <template v-else>
      <div v-for="(block, b) in blocks" :key="b" :style="{ marginTop: `${gapBefore(b)}px` }">
        <div v-if="block.table" class="tf-table" :style="{ gridTemplateColumns: columns(block) }">
          <template v-for="(row, r) in block.rows" :key="r">
            <span v-for="(cell, c) in cells(row)" :key="c" class="tf-cell" :class="{ value: c > 0 }">
              <span v-for="(run, k) in cell" :key="k" :style="{ color: row[0] === 'th' ? INKS[0] : ink(run[0], INKS[1]) }">{{ run[1] }}</span>
            </span>
          </template>
        </div>
        <p v-for="(row, r) in block.table ? [] : block.rows" v-else :key="r" class="tf-line" :class="row[0] === 'h' ? 'tf-head' : row[0] === 'li' ? 'tf-bullet' : ''">
          <span v-for="(run, k) in cells(row)[0]" :key="k" :style="{ color: ink(run[0], plainOf(row)) }">{{ run[1] }}</span>
        </p>
      </div>
    </template>
  </div>
</template>

<style scoped>
.text-face { position: relative; flex: 1 1 auto; align-self: stretch; min-width: 0; min-height: 0; width: 100%; overflow: hidden; text-align: left; }
.tf-line { margin: 0; font-size: var(--text); line-height: 1.17; font-weight: 400; overflow-wrap: anywhere; }
.tf-head { font-size: var(--head); font-weight: 700; }
.tf-bullet { position: relative; padding-left: var(--indent); }
.tf-bullet::before { content: ""; position: absolute; left: calc(var(--indent) * 0.2); top: calc(var(--text) * 0.585 - var(--dot) / 2); width: var(--dot); height: var(--dot); border-radius: 50%; background: var(--muted); }
.tf-table { display: grid; column-gap: var(--cell-gap); font-size: var(--text); line-height: 1.17; font-variant-numeric: tabular-nums; }
.tf-cell { min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding-bottom: calc(var(--text) * 0.3);
  border-bottom: 1px solid color-mix(in srgb, var(--rule) 35%, transparent); margin-bottom: calc(var(--text) * 0.15); }
.tf-cell.value { text-align: right; }
.tf-error { font-size: var(--text); }
</style>
