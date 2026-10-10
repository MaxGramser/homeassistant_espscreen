<script setup lang="ts">
// The live settings of a plugin this screen runs (docs/PLUGINS.md), in the plugin's details on the screen's Plugins tab:
// the ESPHome entities its manifest names, drawn with the rows of the screen's own settings and changed through Home
// Assistant at once. The same rows stand on the screen's own settings page under Plugins. A switch, a number, a choice
// (a dropdown from six options on), a text, and a button with the text sensor that says how it went (plugin API 0.6).
// With `extras` it draws the board's extras instead (docs/SETTINGS.md, "A board's own settings"), under Screen
// settings: the same rows, the entities the board lists in boards.yaml, for every screen with or without plugins.
import { onBeforeUnmount, ref, watch } from "vue";
import { getJson, send } from "../api";
import { editorNumber, t } from "../i18n";
import { text, type Texts } from "../model/plugins";
import { glyph } from "../model/topbar";
import { nodeOf, plugins, pluginsEnabled } from "../plugin-state";
import { currentScreen } from "../store";
import UiSelect from "./ui/UiSelect.vue";
import { useUiStore } from "../stores/ui";

const ui = useUiStore();

const props = defineProps<{ plugin?: string; extras?: boolean }>();
const route = (screenId: string) => `screens/${encodeURIComponent(screenId)}/${props.extras ? "extras" : "plugins/settings"}`;
type Row = { key: string; entity: string | null; kind: "switch" | "number" | "select" | "text" | "button" | null; label: Texts;
  hint?: Texts | null; available: boolean; value?: boolean | number | string | null; min?: number; max?: number; step?: number;
  unit?: string; options?: string[]; password?: boolean; status?: string | null };
type Group = { plugin: string; name: Texts; rows: Row[] };
const rows = ref<Row[]>([]);
async function load() {
  const screen = currentScreen.value;
  if (!screen || screen.virtual) { rows.value = []; return; }
  if (props.extras) {
    try { rows.value = await getJson<Row[]>(route(screen.id)); } catch { rows.value = []; }
    return;
  }
  if (!pluginsEnabled.value || !plugins.installed[nodeOf(screen)]?.length) { rows.value = []; return; }
  try {
    const groups = await getJson<Group[]>(route(screen.id));
    rows.value = groups.find((group) => group.plugin === props.plugin)?.rows || [];
  } catch { rows.value = []; }
}
watch(() => [currentScreen.value?.id, props.plugin, currentScreen.value && plugins.installed[nodeOf(currentScreen.value)]?.length], load, { immediate: true });
// A button's status changes on the screen after the press: read the rows again a few times while it runs.
let timers: number[] = [];
function follow() {
  timers.forEach(clearTimeout);
  timers = [1000, 2500, 5000, 9000, 15000].map((ms) => window.setTimeout(load, ms));
}
onBeforeUnmount(() => timers.forEach(clearTimeout));
async function set(row: Row, value: boolean | number | string) {
  const screen = currentScreen.value;
  if (!screen || !row.entity) return;
  if (row.kind !== "button") row.value = value;   // as the screen's own rows: the change shows at once, Home Assistant squares it
  try {
    await send(route(screen.id), "POST", { entity: row.entity, value });
    if (row.kind === "button") follow();
  } catch (error: any) { ui.toast(error.message); load(); }
}
function setText(row: Row, input: HTMLInputElement) {
  if (input.value === (row.value ?? "")) return;
  if (input.value.length < (row.min ?? 0)) { input.value = String(row.value ?? ""); ui.toast(t("editor.plugins.settings.too_short", { n: row.min ?? 0 })); return; }
  set(row, input.value);
}
const number = (value: unknown, unit = "") => `${editorNumber(Number(value))}${unit ? ` ${unit}` : ""}`;
function step(row: Row, direction: number) {
  const now = Number(row.value ?? row.min ?? 0), by = row.step || 1;
  const next = Math.min(row.max ?? Infinity, Math.max(row.min ?? -Infinity, now + direction * by));
  if (next !== now) set(row, next);
}
const choices = (row: Row) => (row.options || []).map((option) => [option, option] as [string, string]);
const rowClass = (row: Row) => `setting-${({ switch: "toggle", select: "choice", number: "number", text: "text", button: "action" } as Record<string, string>)[row.kind || ""] || "missing"}`;
</script>

<template>
  <div v-if="rows.length" class="plugin-settings" :data-plugin="plugin" :data-extras="extras ? '' : undefined">
    <div v-for="row in rows" :key="row.key" class="srow" :class="[rowClass(row), { inactive: !row.available }]" :data-setting="row.key"
      :title="row.available ? '' : t('editor.screen_settings.unavailable')">
      <span class="s-label">{{ text(row.label) }}<small v-if="row.hint" class="help">{{ text(row.hint) }}</small></span>
      <div class="s-control">
        <button v-if="row.kind === 'switch'" type="button" class="switch" role="switch" :aria-checked="row.value ? 'true' : 'false'" :disabled="!row.available"
          :aria-label="text(row.label)" @click="set(row, !row.value)"></button>
        <template v-else-if="row.kind === 'select'">
          <div v-if="(row.options || []).length <= 5" class="seg" role="group" :aria-label="text(row.label)">
            <button v-for="option in row.options" :key="option" type="button" :aria-pressed="row.value === option ? 'true' : 'false'" :disabled="!row.available" @click="set(row, option)">{{ option }}</button>
          </div>
          <UiSelect v-else :id="`plugin-setting-${row.key}`" :model-value="String(row.value ?? '')" :options="choices(row)" :disabled="!row.available"
            :placeholder="t('editor.plugin_tile.choose')" @update:model-value="(value: string) => set(row, value)" />
        </template>
        <div v-else-if="row.kind === 'number'" class="step">
          <button type="button" :aria-label="t('editor.screen_settings.lower', { name: text(row.label) })" :disabled="!row.available || Number(row.value) <= (row.min ?? -Infinity)" @click="step(row, -1)"><span class="mdi">{{ glyph("F0374") }}</span></button>
          <output>{{ row.value === null || row.value === undefined ? "–" : number(row.value, row.unit) }}</output>
          <button type="button" :aria-label="t('editor.screen_settings.higher', { name: text(row.label) })" :disabled="!row.available || Number(row.value) >= (row.max ?? Infinity)" @click="step(row, 1)"><span class="mdi">{{ glyph("F0415") }}</span></button>
        </div>
        <!-- A text is saved when it is left or with Enter, as the screen's own name field. -->
        <input v-else-if="row.kind === 'text'" :id="`plugin-setting-${row.key}`" class="s-text" :type="row.password ? 'password' : 'text'" autocomplete="off" spellcheck="false"
          :value="String(row.value ?? '')" :maxlength="row.max" :disabled="!row.available" :aria-label="text(row.label)"
          @change="setText(row, $event.target as HTMLInputElement)" @keydown.enter="($event.target as HTMLInputElement).blur()" />
        <template v-else-if="row.kind === 'button'">
          <span v-if="row.status" class="s-status" aria-live="polite">{{ row.status }}</span>
          <button type="button" class="btn quiet mini" :disabled="!row.available" @click="set(row, true)">{{ t("editor.plugins.settings.run") }}</button>
        </template>
        <small v-else class="help">{{ t("editor.plugins.settings_missing") }}</small>
      </div>
    </div>
  </div>
</template>
