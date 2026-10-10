<script setup lang="ts">
// Screen settings: the same groups and rows as the settings page on the screen itself. Every change applies at
// once, like on the screen; no Save needed.
import { computed } from "vue";
import { usePressRepeat } from "../composables/usePressRepeat";
import { t } from "../i18n";
import { glyph } from "../model/topbar";
import FeedbackPanel from "./FeedbackPanel.vue";
import ScreensaverCard from "./ScreensaverCard.vue";
import Icon from "./ui/Icon.vue";
import PluginSettings from "./PluginSettings.vue";
import { text } from "../model/plugins";
import { choiceText, SETTING_GROUPS, settingLabel, steppedSetting, type SettingRow } from "../model/settings";
import { pageReachWarning, state } from "../store";
import { useSettingsStore } from "../stores/settings";
import { usePluginsStore } from "../stores/plugins";
import { useScreenStore } from "../stores/screen";

const settings = useSettingsStore();
const plugins = usePluginsStore();
const scr = useScreenStore();

const view = computed(() => settings.settingsView());
// The plugins this screen runs that have settings: those are in each plugin's details on the Plugins tab (docs/PLUGINS.md).
// The settings the screen's board lists (boards.yaml `settings`, in its shape's catalog): its Extras card.
const boardExtras = computed(() => Boolean(scr.currentScreen?.shape?.catalog?.settings?.length));
const pluginsWithSettings = computed(() => {
  const screen = scr.currentScreen;
  if (!screen || screen.virtual) return [];
  return [...plugins.index.filter((plugin) => plugins.installedOn(screen, plugin.id)), ...plugins.testsOn(screen)]
    .filter((plugin, i, all) => all.findIndex((other) => other.id === plugin.id) === i)
    .filter((plugin) => plugin.settings?.length || (plugin.inputs || []).length || (plugin.parts || []).length);
});
// A plugin's details on the screen's Plugins tab, opened from here, where its settings used to be.
function openPlugin(id: string) {
  plugins.focus = id;
  state.tab = "plugins";
}
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
const groups = computed(() => SETTING_GROUPS.map((group) => ({ ...group, rows: (group.rows as readonly SettingRow[]).filter((row) => view.value?.keys.includes(row.key)) })).filter((g) => g.rows.length));
// What one tap on a switch writes: a plain switch flips true/false, a brightness drawn as a switch writes 0 or 100.
const flip = (row: SettingRow) => (asSwitch(row) ? (Number(values.value[row.key]) > 0 ? 0 : 100) : !values.value[row.key]);
// Page buttons and swiping off: the pages that only Go to page tiles could reach, and don't.
const reachWarning = computed(() => pageReachWarning());
const unavailable = (row: SettingRow) => offline.value || Boolean(view.value?.unavailable.includes(row.key));
const needs = (row: SettingRow) => (row.needs ? Boolean(values.value[row.needs]) : true);
const status = computed(() => offline.value
  ? t("editor.screen_settings.status.offline")
  : settings.settingPending
    ? t("editor.common.saving")
    : view.value?.owner === "screen"
      ? t("editor.screen_settings.status.screen")
      : t("editor.screen_settings.status.app"));
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
// Calibrate touch (app 0.2.117): the screen has to be there to show the crosses, whoever owns its settings.
const calibrateReady = computed(() => Boolean(scr.currentScreen?.online));
const startCalibration = () => scr.currentScreen && scr.calibrateTouch(scr.currentScreen);
</script>

<template>
  <div class="settings" id="general-settings" :class="{ offline }">
    <span class="status" id="settings-status" role="status">{{ status }}</span>
    <div v-if="view" class="set-grid" id="settings-groups">
      <template v-for="group in groups" :key="group.group">
      <section class="set-card">
        <h4><span class="mdi">{{ glyph(group.icon) }}</span>{{ t(`editor.screen_settings.groups.${group.group}`) }}</h4>
        <div v-for="row in group.rows" :key="row.key" class="srow" :class="[`setting-${isSwitch(row) ? 'toggle' : row.kind}`, { inactive: !needs(row) || unavailable(row) }]" :data-setting="row.key"
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
        <p v-if="reachWarning && group.rows.some((row) => row.key === 'page_buttons')" class="hint warn" id="settings-page-reach">{{ reachWarning }}</p>
      </section>
      <!-- The screensaver (app 0.4.48) goes with standby, so it stands right after the group that turns standby on. -->
      <ScreensaverCard v-if="group.group === 'brightness'" />
      </template>
      <!-- The board's extras (docs/SETTINGS.md, "A board's own settings"): what only this board has, the same switches as
           on the screen's own settings page under Extras and in Home Assistant. -->
      <section v-if="boardExtras" class="set-card" id="settings-extras">
        <h4><span class="mdi">{{ glyph("F0493") }}</span>{{ t("editor.screen_settings.extras.title") }}</h4>
        <p class="hint">{{ t("editor.screen_settings.extras.note") }}</p>
        <PluginSettings extras />
      </section>
      <!-- This screen: the group the screen's own page keeps its actions in. Only what this screen can do shows up,
           so a capacitive panel has no card here at all. -->
      <!-- The plugins' own settings (docs/PLUGINS.md) are in each plugin's details on the Plugins tab; this says where. -->
      <section v-if="pluginsWithSettings.length" class="set-card" id="settings-plugins">
        <h4><span class="mdi">{{ glyph("F0A66") }}</span>{{ t("editor.screen_settings.plugins.title") }}</h4>
        <p class="hint">{{ t("editor.screen_settings.plugins.note") }}</p>
        <div class="s-action plugin-links">
          <button v-for="plugin in pluginsWithSettings" :key="plugin.id" type="button" class="btn quiet" :data-plugin="plugin.id" @click="openPlugin(plugin.id)">
            {{ text(plugin.name) }}<Icon name="arrow-right" />
          </button>
        </div>
      </section>
      <section v-if="view.calibrate" class="set-card" id="settings-this-screen">
        <h4><span class="mdi">{{ glyph("F02FD") }}</span>{{ t("editor.screen_settings.groups.this_screen") }}</h4>
        <div class="s-action">
          <button type="button" class="btn quiet" id="setting-calibrate" :disabled="!calibrateReady" @click="startCalibration()">
            <span class="mdi">{{ glyph("F01A3") }}</span>{{ t("editor.screen_settings.actions.calibrate.button") }}
          </button>
        </div>
        <p class="hint">{{ t("editor.screen_settings.actions.calibrate.hint") }}</p>
      </section>
    </div>
    <!-- Does it work as you expect (app 0.3.10): always here, also for a screen that is offline or never got its tiles. -->
    <div v-if="scr.currentScreen?.feedback?.available" class="set-grid feedback-grid">
      <FeedbackPanel :key="`settings-${scr.currentScreen.id}`" :screen="scr.currentScreen" mode="settings" />
    </div>
  </div>
</template>

<style scoped>
.feedback-grid { margin-top: 14px; }
.offline .feedback-grid { opacity: 1; }
</style>
