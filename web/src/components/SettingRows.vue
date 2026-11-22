<script setup lang="ts">
// The rows of the screen's own settings (model/settings.ts SETTING_GROUPS) that one part of the Settings tab shows, by
// key: a switch, a choice or -/+ steps, each change applied at once like on the screen; no Save needed. The rows this
// screen does not report are left out.
import { computed, nextTick, ref, watch } from "vue";
import { usePressRepeat } from "../composables/usePressRepeat";
import { t } from "../i18n";
import { glyph } from "../model/topbar";
import { choiceText, SETTING_GROUPS, settingLabel, steppedSetting, type SettingRow } from "../model/settings";
import { useSettingsStore } from "../stores/settings";
import { useScreenStore } from "../stores/screen";

const props = defineProps<{ keys: readonly string[] }>();
const settings = useSettingsStore();
const scr = useScreenStore();

const view = computed(() => settings.settingsView());
const ALL = SETTING_GROUPS.flatMap((group) => group.rows as readonly SettingRow[]);
const rows = computed(() => props.keys.map((key) => ALL.find((row) => row.key === key)).filter((row): row is SettingRow => Boolean(row && view.value?.keys.includes(row.key))));
// The choices of a row: the rotation offers the angles this screen's glass allows (the manager says which, app
// 0.2.94); an add-on from before said nothing, and then the four of the Guition stand.
const optionsOf = (row: SettingRow) => (row.key === "rotation" && view.value?.rotations?.length ? view.value.rotations : row.options!);
const values = computed(() => settings.settingValues());
const offline = computed(() => view.value?.owner === "screen" && !scr.currentScreen?.online);
// A screen whose backlight is lit or dark has no percentage for standby and night: the manager names those keys
// and they are drawn as the switch the screen draws (app 0.2.105). The row stays the number it is - one number
// underneath either way, 0 or 100 - only its control changes.
const asSwitch = (row: SettingRow) => Boolean(view.value?.switches?.includes(row.key));
const isSwitch = (row: SettingRow) => row.kind === "toggle" || asSwitch(row);
// What one tap on a switch writes: a plain switch flips true/false, a brightness drawn as a switch writes 0 or 100.
const flip = (row: SettingRow) => (asSwitch(row) ? (Number(values.value[row.key]) > 0 ? 0 : 100) : !values.value[row.key]);
const unavailable = (row: SettingRow) => offline.value || Boolean(view.value?.unavailable.includes(row.key));
const needs = (row: SettingRow) => (row.needs ? Boolean(values.value[row.needs]) : true);
const stepDisabled = (row: SettingRow, direction: number) => {
  const value = values.value[row.key];
  if (unavailable(row) || !needs(row) || value === null || value === undefined) return true;
  return row.kind !== "moment" && steppedSetting(row, value, direction, false, values.value) === value;
};
// A key held down steps again and again, faster after five steps, like the -/+ keys on the screen.
const hold = usePressRepeat({ delay: 450, interval: 180 });
function step(row: SettingRow, direction: number, held: boolean) {
  const v = settings.settingValues();
  const next = steppedSetting(row, v[row.key], direction, held, v);
  if (next !== v[row.key]) settings.setSetting(row.key, next, 600);
}
const down = (e: PointerEvent, row: SettingRow, direction: number) => hold.down(e, (repeats) => step(row, direction, repeats > 5));
const up = () => hold.up();
function click(e: MouseEvent, row: SettingRow, direction: number) {
  if (!hold.click(e)) step(row, direction, false);
}
// A setting ⌘K found: its part opens (SettingsTab), and here its row comes into sight, takes the focus on its control
// and is marked for a moment.
const marked = ref<string | null>(null);
let unmark = 0;
watch(() => settings.spotlight, async (key) => {
  if (!key || !rows.value.some((row) => row.key === key)) return;
  settings.spotlight = null;
  await nextTick();
  const row = document.querySelector<HTMLElement>(`[data-setting="${key}"]`);
  if (!row) return;
  row.scrollIntoView?.({ block: "center", behavior: matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  row.querySelector<HTMLElement>(`#setting-${key}, button:not(:disabled)`)?.focus({ preventScroll: true });
  marked.value = key;
  clearTimeout(unmark);
  unmark = window.setTimeout(() => { marked.value = null; }, 1600);
}, { immediate: true });
defineExpose({ rows });
</script>

<template>
  <div v-for="row in rows" :key="row.key" class="srow" :class="[`setting-${isSwitch(row) ? 'toggle' : row.kind}`, { inactive: !needs(row) || unavailable(row), spotlit: marked === row.key }]" :data-setting="row.key"
    :title="unavailable(row) && !offline ? t('editor.screen_settings.unavailable') : ''"
    @click="isSwitch(row) && ($event.target as HTMLElement).closest('.srow') === $event.currentTarget && !($event.target as HTMLElement).closest('button') && !unavailable(row) && settings.setSetting(row.key, flip(row), 150)">
    <span class="s-label" :id="`setting-label-${row.key}`">{{ settingLabel(row) }}</span>
    <div class="s-control">
      <button v-if="isSwitch(row)" type="button" class="switch" :class="{ unknown: values[row.key] === null || values[row.key] === undefined }" role="switch"
        :id="`setting-${row.key}`" :aria-checked="Boolean(values[row.key]) ? 'true' : 'false'" :aria-labelledby="`setting-label-${row.key}`"
        :disabled="unavailable(row)" @click.stop="settings.setSetting(row.key, flip(row), 150)"></button>
      <div v-else-if="row.kind === 'choice'" class="seg" role="group" :aria-labelledby="`setting-label-${row.key}`">
        <button v-for="value in optionsOf(row)" :key="String(value)" type="button" :aria-pressed="values[row.key] === value ? 'true' : 'false'" :disabled="unavailable(row)" @click="settings.setSetting(row.key, value, 150)">{{ choiceText(row, value) }}</button>
      </div>
      <div v-else class="step">
        <button type="button" :aria-label="t('editor.screen_settings.lower', { name: settingLabel(row) })" :disabled="stepDisabled(row, -1)" @pointerdown="down($event, row, -1)" @pointerup="up" @pointercancel="up" @pointerleave="up" @click="click($event, row, -1)"><span class="mdi">{{ glyph("F0374") }}</span></button>
        <output :id="`setting-${row.key}`" :aria-labelledby="`setting-label-${row.key}`">{{ settings.settingText(row, values) }}</output>
        <button type="button" :aria-label="t('editor.screen_settings.higher', { name: settingLabel(row) })" :disabled="stepDisabled(row, 1)" @pointerdown="down($event, row, 1)" @pointerup="up" @pointercancel="up" @pointerleave="up" @click="click($event, row, 1)"><span class="mdi">{{ glyph("F0415") }}</span></button>
      </div>
    </div>
  </div>
</template>
