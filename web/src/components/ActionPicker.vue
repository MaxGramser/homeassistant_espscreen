<script setup lang="ts">
// Perform action (app 0.2.67): the actions Home Assistant offers for a tile's entity, under its own names,
// and one field per value Home Assistant asks for (its selector). An empty field is left out.
import { computed } from "vue";
import { t } from "../i18n";
import { beginFieldEdit, endFieldEdit, loadEntityActions, setTileAction, state, supports } from "../store";
import type { EntityAction, Tile } from "../types";
import Segmented from "./Segmented.vue";
import Icon from "./ui/Icon.vue";
import UiSelect from "./ui/UiSelect.vue";

const props = defineProps<{ tile: Tile }>();
const list = computed(() => state.entityActions[props.tile.entity]);
const chosen = computed(() => props.tile.options?.action);
const entry = computed(() => list.value?.find((a) => a.action === chosen.value?.action));
const open = computed(() => state.actionPickerOpen || !chosen.value);
const rows = computed(() => {
  const q = state.actionSearch.trim().toLocaleLowerCase();
  return (list.value || []).filter((a) => `${a.name} ${a.action} ${a.description}`.toLocaleLowerCase().includes(q));
});
if (list.value === undefined) loadEntityActions(props.tile.entity);

// Choosing an action stores Perform action with it (app 0.4.0): until then the tile keeps the tap choice it had, so a
// half-made choice never reaches the document (GitHub #47). The chosen action is the tile's own, from the document.
function pick(action: EntityAction) {
  const same = action.action === chosen.value?.action;
  if (setTileAction(props.tile, same && chosen.value ? chosen.value : { action: action.action }) || same) state.actionPickerOpen = false;
}
function setField(key: string, value: unknown) {
  const data: Record<string, unknown> = { ...(props.tile.options?.action?.data || {}) };
  if (value === undefined) delete data[key];
  else data[key] = value;
  setTileAction(props.tile, { action: chosen.value!.action, ...(Object.keys(data).length ? { data } : {}) }, `action:${props.tile.id}:${key}`);
}
const missing = computed(() => {
  if (!entry.value) return [];
  const data = props.tile.options?.action?.data || {};
  return entry.value.fields.filter((f) => f.required && data[f.key] === undefined).map((f) => f.name);
});
type Field = EntityAction["fields"][number];
const kindOf = (field: Field) => Object.keys(field.selector || {})[0] || "text";
const configOf = (field: Field) => (field.selector || {})[kindOf(field)] || {};
const exampleOf = (field: Field) => (field.example === undefined ? "" : typeof field.example === "string" ? field.example : JSON.stringify(field.example));
// A select's own options, or the values this entity has where Home Assistant asks for one of them (a source, an effect).
function choicesOf(field: Field): [string, string][] | null {
  const config = configOf(field), kind = kindOf(field);
  if (Array.isArray(field.options)) return field.options.map((o) => [o, o]);
  if (kind === "select" && Array.isArray(config.options) && !config.multiple)
    return config.options.map((o: any) => (o && typeof o === "object" ? [String(o.value), String(o.label ?? o.value)] : [String(o), String(o)]));
  return null;
}
const hex = (rgb: number[]) => "#" + rgb.map((c) => Math.max(0, Math.min(255, Number(c) || 0)).toString(16).padStart(2, "0")).join("");
const colorValue = (value: unknown) => (Array.isArray(value) && value.length === 3 ? hex(value as number[]) : "#ffffff");
const textValue = (value: unknown) => (value === undefined ? "" : typeof value === "string" ? value : JSON.stringify(value));
function onText(field: Field, raw: string) {
  const text = raw.trim();
  if (!text) return setField(field.key, undefined);
  if (kindOf(field) === "text") return setField(field.key, raw);
  try { setField(field.key, JSON.parse(text)); } catch { setField(field.key, raw); }
}
function onNumber(field: Field, raw: string) {
  setField(field.key, raw === "" || !Number.isFinite(Number(raw)) ? undefined : Number(raw));
}
const unitOf = (field: Field) => configOf(field).unit_of_measurement || (kindOf(field) === "color_temp" ? configOf(field).unit || "" : "");
</script>

<template>
  <div class="f">
    <span class="f-label">{{ t("editor.action.label") }}</span>
    <small v-if="list === undefined">{{ t("editor.action.asking") }}</small>
    <small v-else-if="list === null" class="warn">{{ t("editor.action.not_answering") }}</small>
    <template v-else>
      <button type="button" class="row" :aria-expanded="open ? 'true' : 'false'" @click="state.actionPickerOpen = !open">
        <span class="tx">
          <b>{{ entry ? entry.name : chosen ? chosen.action : t("editor.action.choose") }}</b>
          <small v-if="chosen" class="mono">{{ chosen.action }}</small>
        </span>
        <Icon :name="open ? 'chevron-up' : 'chevron-down'" class="row-chevron" />
      </button>
      <div v-if="open" class="picker">
        <label class="search-field"><Icon name="magnify" /><input v-model="state.actionSearch" type="search" :placeholder="t('editor.action.search')" :aria-label="t('editor.action.search_label')" /></label>
        <div class="action-list">
          <button v-for="action in rows" :key="action.action" type="button" class="action-choice" :aria-pressed="action.action === chosen?.action ? 'true' : 'false'" @click="pick(action)">
            <strong>{{ action.name }}</strong>
            <small>{{ action.description ? `${action.action} · ${action.description}` : action.action }}</small>
          </button>
          <p v-if="!rows.length" class="hint">{{ t("editor.action.none_found") }}</p>
        </div>
      </div>
      <small v-if="chosen && !entry" class="warn">{{ t("editor.action.gone") }}</small>
      <template v-if="entry && !open">
        <div v-for="field in entry.fields" :key="field.key" class="f">
          <span class="f-label">{{ field.required ? field.name : t("editor.action.optional", { name: field.name }) }}</span>
          <Segmented v-if="kindOf(field) === 'boolean'" :choices="[['', t('editor.action.not_set')], ['true', t('editor.action.on')], ['false', t('editor.action.off')]]" :value="chosen?.data?.[field.key] === undefined ? '' : String(chosen?.data?.[field.key])"
            @pick="(v) => setField(field.key, v === '' ? undefined : v === 'true')" />
          <Segmented v-else-if="choicesOf(field) && choicesOf(field)!.length <= 4" :choices="[['', t('editor.action.not_set')], ...choicesOf(field)!]" :value="chosen?.data?.[field.key] === undefined ? '' : String(chosen?.data?.[field.key])"
            @pick="(v) => setField(field.key, v === '' ? undefined : v)" />
          <UiSelect v-else-if="choicesOf(field)" :aria-label="field.name" :model-value="String(chosen?.data?.[field.key] ?? '')"
            :options="[['', t('editor.action.not_set')], ...choicesOf(field)!] as [string, string][]" @update:model-value="(value) => setField(field.key, value === '' ? undefined : value)" />
          <div v-else-if="kindOf(field) === 'color_rgb'" class="action-number">
            <input type="color" :aria-label="field.name" @focus="beginFieldEdit(`action:${tile.id}:${field.key}`)" @blur="endFieldEdit()" :value="colorValue(chosen?.data?.[field.key])" @input="setField(field.key, [1, 3, 5].map((i) => parseInt(($event.target as HTMLInputElement).value.slice(i, i + 2), 16)))" />
            <button type="button" class="btn quiet mini" @click="setField(field.key, undefined)">{{ t("editor.action.not_set") }}</button>
          </div>
          <div v-else-if="kindOf(field) === 'number' || kindOf(field) === 'color_temp'" class="action-number">
            <input type="number" :aria-label="field.name" @focus="beginFieldEdit(`action:${tile.id}:${field.key}`)" @blur="endFieldEdit()" :min="configOf(field).min" :max="configOf(field).max" :step="configOf(field).step === 'any' ? 'any' : configOf(field).step"
              :value="chosen?.data?.[field.key] ?? ''" :placeholder="exampleOf(field)" @input="onNumber(field, ($event.target as HTMLInputElement).value)" />
            <span v-if="unitOf(field)">{{ unitOf(field) }}</span>
          </div>
          <input v-else type="text" :aria-label="field.name" @focus="beginFieldEdit(`action:${tile.id}:${field.key}`)" @blur="endFieldEdit()" :value="textValue(chosen?.data?.[field.key])" :placeholder="exampleOf(field)" @input="onText(field, ($event.target as HTMLInputElement).value)" />
          <small v-if="field.description" class="help">{{ field.description }}</small>
        </div>
        <small v-if="missing.length" class="warn">{{ t("editor.action.needs", { fields: missing.join(", ") }) }}</small>
      </template>
      <small v-if="!supports(0, 2, 58)">{{ t("editor.action.needs_firmware") }}</small>
    </template>
  </div>
</template>
