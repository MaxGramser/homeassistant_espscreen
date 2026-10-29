<script setup lang="ts">
// The template tile (docs/TEXT_TILE.md): its template, written in a field that completes Home Assistant's entities,
// attributes and states (TemplateEditor.vue), keys for the tile's own markup, examples that work in any home, and the
// result as the screen gets it. That result comes from api/text/preview a moment after the typing stops: Home Assistant
// renders the template, and the add-on turns it into the rows it sends (text_tile.block), so what shows here is what the
// screen draws, bytes and all. Typing is one step of undo, as in the name field.
import { computed, defineAsyncComponent, onBeforeUnmount, ref, watch } from "vue";
import { send } from "../../api";
import { t } from "../../i18n";
import { setTileOption } from "../../editor/tiles";
import { useDocumentStore } from "../../stores/document";
import { useScreenStore } from "../../stores/screen";
import { TABLE } from "../../model/template-complete";
import { useInventoryStore } from "../../stores/inventory";
import type { Tile } from "../../types";
import Icon from "../ui/Icon.vue";
import Section from "../ui/Section.vue";
// CodeMirror comes with the first template tile opened, not with the editor.
const TemplateEditor = defineAsyncComponent(() => import("./TemplateEditor.vue"));

const props = defineProps<{ tile: Tile }>();
const doc = useDocumentStore();
const scr = useScreenStore();
const MANUAL = "https://github.com/MaxGramser/homeassistant_espscreen/blob/main/docs/TEXT_TILE.md#writing-a-template";
const editor = ref<{ insert(text: string): void } | null>(null);
const template = computed(() => (props.tile.options?.template as string | undefined) ?? "");
function write(text: string) { setTileOption(props.tile, "template", text.trim() ? text : undefined); }

// ---- The tile's own markup, one key each, and examples that read what every home has.
// Snippets: their fields are selected one after the other with Tab.
const MARKS: { key: string; text: string; label: string }[] = [
  { key: "heading", text: "# ${}", label: "#" }, { key: "bullet", text: "- ${}", label: "•" },
  { key: "table", text: TABLE, label: "▦" }, { key: "bold", text: "**${}**", label: "B" },
  { key: "good", text: ":good[${}]", label: "●" }, { key: "alert", text: ":alert[${}]", label: "●" }, { key: "accent", text: ":accent[${}]", label: "●" },
];
// The keys the field answers, shown as keys: the platform's own modifier.
const MOD = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent) ? "⌘" : "Ctrl";
const KEYS: { keys: string[]; word: string }[] = [
  { keys: ["Ctrl", "Space"], word: "complete" }, { keys: ["Tab"], word: "next" }, { keys: [MOD, "/"], word: "comment" },
];
const EXAMPLES: Record<string, string> = {
  lights: "# {{ t_lights }}\n{% set on = states.light | selectattr('state', 'eq', 'on') | list %}\n{% if on %}\n{% for light in on %}\n- {{ light.name }}\n{% endfor %}\n{% else %}\n:good[{{ t_none }}]\n{% endif %}",
  open: "{% set open = states.binary_sensor | selectattr('attributes.device_class', 'in', ['door', 'window', 'garage_door', 'opening']) | selectattr('state', 'eq', 'on') | list %}\n{% if open %}\n# {{ t_open }}\n{% for item in open %}\n- :alert[{{ item.name }}]\n{% endfor %}\n{% endif %}",
  weather: "{% set w = states.weather | first %}\n{% if w %}\n# {{ w.name }}\n| | |\n|---|---|\n| {{ t_now }} | **{{ state_attr(w.entity_id, 'temperature') }} {{ state_attr(w.entity_id, 'temperature_unit') }}** |\n| {{ t_humidity }} | {{ state_attr(w.entity_id, 'humidity') }} % |\n{% endif %}",
};
// The example's own words in the editor's language, written into it as text.
function example(key: string) {
  const words: Record<string, string> = {
    t_lights: t("editor.tile.text.examples.lights_heading"), t_none: t("editor.tile.text.examples.all_off"),
    t_open: t("editor.tile.text.examples.open_heading"), t_now: t("editor.tile.text.examples.now"), t_humidity: t("editor.tile.text.examples.humidity"),
  };
  write(EXAMPLES[key].replace(/\{\{ (t_\w+) \}\}/g, (_, word) => words[word]));
}

// ---- The result as the screen gets it (api/text/preview).
type Run = [number, string];
type Row = [string, Run[] | Run[][]];
type Listeners = { entities: string[]; domains: string[]; all: boolean; time: boolean };
type Preview = { md: { v: number; r?: Row[]; e?: string }; bytes: number; budget: number; listeners?: Listeners | null };
const preview = ref<Preview | null>(null);
const failed = ref("");
let timer: ReturnType<typeof setTimeout> | undefined, asked = 0;
async function load() {
  const ask = ++asked;
  if (!template.value.trim()) { preview.value = null; failed.value = ""; return; }
  try {
    const answer = await send<Preview>("text/preview", "POST", { template: template.value, inbox: scr.currentScreen?.id });
    if (ask === asked) { preview.value = answer; failed.value = ""; }
  } catch (error) {
    if (ask === asked) { preview.value = null; failed.value = error instanceof Error ? error.message : String(error); }
  }
}
watch(() => [props.tile.id, template.value], (now, before) => {
  clearTimeout(timer);
  timer = setTimeout(load, before && now[0] === before[0] ? 400 : 0);
}, { immediate: true });
onBeforeUnmount(() => { clearTimeout(timer); asked++; });
const error = computed(() => preview.value?.md.e ?? null);
const rows = computed(() => preview.value?.md.r ?? []);
const empty = computed(() => preview.value !== null && !error.value && rows.value.length === 0);
const share = computed(() => (preview.value ? Math.min(100, Math.round((preview.value.bytes / preview.value.budget) * 100)) : 0));
const TONES = ["", "b", "good", "alert", "accent"];
// What makes Home Assistant render it again (its listeners), named as the editor names the entities.
const inv = useInventoryStore();
const listeners = computed(() => (error.value ? null : preview.value?.listeners ?? null));
const nameOf = (id: string) => inv.inventory.entities?.find((e) => e.id === id)?.name || id;
const columns = (row: Row) => (cells(row).length > 1 ? `minmax(0, 1.4fr) repeat(${cells(row).length - 1}, minmax(0, 1fr))` : "1fr");
const cells = (row: Row) => (row[0] === "t" || row[0] === "th" ? (row[1] as Run[][]) : [row[1] as Run[]]);
</script>

<template>
  <Section :title="t('editor.tile.text.title')">
    <p class="hint">{{ t("editor.tile.text.hint") }}
      <a :href="MANUAL" target="_blank" rel="noopener">{{ t("editor.tile.text.manual") }}</a></p>
    <TemplateEditor ref="editor" :model-value="template" :label="t('editor.tile.text.field')" :error="error"
      @update:model-value="write" @focus="doc.beginFieldEdit(`template:${tile.id}`)" @blur="doc.endFieldEdit()" />
    <div class="text-marks" role="toolbar" :aria-label="t('editor.tile.text.markup.label')">
      <button v-for="mark in MARKS" :key="mark.key" type="button" class="btn quiet mini" :class="`mark-${mark.key}`"
        :title="t(`editor.tile.text.markup.${mark.key}`)" :aria-label="t(`editor.tile.text.markup.${mark.key}`)"
        @click="editor?.insert(mark.text)">{{ mark.label }}</button>
      <span class="text-keys">
        <span v-for="key in KEYS" :key="key.word" class="text-key"><kbd v-for="k in key.keys" :key="k">{{ k === "Space" ? t("editor.tile.text.keys.space") : k }}</kbd>
          {{ t(`editor.tile.text.keys.${key.word}`) }}</span>
      </span>
    </div>
    <div v-if="!template.trim()" class="text-examples">
      <span>{{ t("editor.tile.text.examples.title") }}</span>
      <button v-for="key in Object.keys(EXAMPLES)" :key="key" type="button" class="btn quiet mini" @click="example(key)">
        {{ t(`editor.tile.text.examples.${key}`) }}</button>
    </div>
    <div v-if="template.trim()" class="text-result" aria-live="polite">
      <div class="text-result-head">
        <span>{{ t("editor.tile.text.result") }}</span>
        <span v-if="preview" class="text-bytes" :class="{ full: share >= 100 }">{{ t("editor.tile.text.bytes", { n: preview.bytes, of: preview.budget }) }}</span>
      </div>
      <p v-if="failed" class="help warn">{{ failed }}</p>
      <p v-else-if="error" class="text-error"><Icon name="alert-circle-outline" /> {{ error }}</p>
      <p v-else-if="empty" class="hint">{{ t("editor.tile.text.empty") }}</p>
      <div v-else-if="rows.length" class="text-rows">
        <div v-for="(row, i) in rows" :key="i" class="text-row" :class="`kind-${row[0]}`" :style="row[0] === 't' || row[0] === 'th' ? { gridTemplateColumns: columns(row) } : undefined">
          <span v-for="(cell, c) in cells(row)" :key="c" class="text-cell">
            <span v-for="(run, r) in cell" :key="r" :class="TONES[run[0]]">{{ run[1] }}</span>
          </span>
        </div>
      </div>
      <div v-if="preview" class="text-meter"><span :style="{ width: `${share}%` }" /></div>
      <div v-if="listeners" class="text-listens">
        <span class="text-listens-head">{{ t("editor.tile.text.listen.label") }}</span>
        <span v-for="id in listeners.entities.slice(0, 8)" :key="id" class="text-chip" :title="id">{{ nameOf(id) }}</span>
        <span v-if="listeners.entities.length > 8" class="text-chip more">+{{ listeners.entities.length - 8 }}</span>
        <span v-for="domain in listeners.domains" :key="domain" class="text-chip" :title="domain">{{ domain }}.*</span>
        <span v-if="listeners.time" class="text-chip time">{{ t("editor.tile.text.listen.time") }}</span>
        <span v-if="!listeners.entities.length && !listeners.domains.length && !listeners.time && !listeners.all" class="text-listens-none">{{ t("editor.tile.text.listen.none") }}</span>
        <p v-if="listeners.all" class="help warn">{{ t("editor.tile.text.listen.all") }}</p>
      </div>
    </div>
    <p class="hint quiet">{{ t("editor.tile.text.access") }}</p>
  </Section>
</template>

<style scoped>
.text-marks, .text-examples { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-top: 8px; }
.text-marks .btn { min-width: 2em; font-family: var(--mono); }
.mark-bold { font-weight: 700; }
.mark-good { color: var(--good); }
.mark-alert { color: var(--danger); }
.mark-accent { color: var(--accent); }
.text-keys { display: flex; flex-wrap: wrap; gap: 4px 12px; color: var(--muted); font-size: 12px; margin-left: auto; }
.text-key { display: inline-flex; align-items: center; gap: 3px; white-space: nowrap; }
kbd { font: 600 11px/1 var(--mono); padding: 2px 5px; border: 1px solid var(--line-strong); border-bottom-width: 2px; border-radius: 4px; background: var(--surface); color: var(--ink-2); }
.text-listens { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; font-size: 12px; }
.text-listens-head { color: var(--muted); margin-right: 2px; }
.text-chip { padding: 1px 7px; border-radius: 99px; background: var(--accent-soft); color: var(--ink); white-space: nowrap; }
.text-chip.time, .text-chip.more { background: var(--surface); border: 1px solid var(--line); color: var(--muted); }
.text-listens-none { color: var(--muted); }
.text-listens .help { flex-basis: 100%; margin: 4px 0 0; }
.text-examples > span { color: var(--muted); font-size: 12px; }
.text-result { margin-top: 10px; border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px; display: grid; gap: 6px; background: var(--surface-2); }
.text-result-head { display: flex; justify-content: space-between; gap: 8px; font-size: 12px; color: var(--muted); }
.text-bytes { font-variant-numeric: tabular-nums; }
.text-bytes.full { color: var(--warn); }
.text-error { color: var(--danger); font-family: var(--mono); font-size: 12px; margin: 0; overflow-wrap: anywhere; }
.text-rows { display: grid; gap: 2px; font-size: 13px; color: var(--muted); min-width: 0; }
.text-row { overflow-wrap: anywhere; }
.kind-h { color: var(--ink); font-weight: 600; margin-top: 4px; }
.kind-h:first-child { margin-top: 0; }
.kind-li { padding-left: 1em; position: relative; }
.kind-li::before { content: "•"; position: absolute; left: 0.2em; color: var(--muted); }
.kind-t, .kind-th { display: grid; gap: 8px; border-bottom: 1px solid var(--line); color: var(--ink); font-variant-numeric: tabular-nums; }
.kind-th { color: var(--muted); }
.kind-t .text-cell:not(:first-child), .kind-th .text-cell:not(:first-child) { text-align: right; }
.b { color: var(--ink); font-weight: 600; }
.good { color: var(--good); }
.alert { color: var(--danger); }
.accent { color: var(--accent); }
.text-meter { height: 4px; border-radius: 2px; background: var(--line); overflow: hidden; }
.text-meter span { display: block; height: 100%; background: var(--good); }
.hint.quiet { font-size: 12px; margin-top: 8px; }
</style>
