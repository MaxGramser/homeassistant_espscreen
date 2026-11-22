<script setup lang="ts">
// A screen's Settings tab, in parts (docs/PAGES.md, "Settings"): it opens on a list of them, one row each with what is
// set now, and a part opens as a page of its own (`?settings=<part>` on the screen's address, model/settings-parts.ts).
// The rows are the screen's own settings (SettingRows), every change applied at once like on the screen; no Save needed.
import { computed } from "vue";
import { t } from "../i18n";
import FeedbackPanel from "./FeedbackPanel.vue";
import GridSettings from "./GridSettings.vue";
import ScreensaverCard from "./ScreensaverCard.vue";
import SettingRows from "./SettingRows.vue";
import SettingsHead from "./SettingsHead.vue";
import SettingsLink from "./SettingsLink.vue";
import Icon from "./ui/Icon.vue";
import PluginSettings from "./PluginSettings.vue";
import { text } from "../model/plugins";
import { glyph } from "../model/topbar";
import { SETTING_GROUPS, settingLabel, type SettingRow } from "../model/settings";
import { PART_LOOK, partCards, SCREEN_PART_ROWS, type ScreenSettingsPart } from "../model/settings-parts";
import type { IconName } from "../model/ui-icons";
import { useSettingsStore } from "../stores/settings";
import { usePluginsStore } from "../stores/plugins";
import { useScreenStore } from "../stores/screen";
import { useDocumentStore } from "../stores/document";
import { pageReachWarning } from "../editor/pages";
import { useUiStore } from "../stores/ui";
import { useScreenIconsStore } from "../stores/screenIcons";

const settings = useSettingsStore();
const plugins = usePluginsStore();
const scr = useScreenStore();
const doc = useDocumentStore();
const ui = useUiStore();
const screenIcons = useScreenIconsStore();

const view = computed(() => settings.settingsView());
const screen = computed(() => scr.currentScreen);
const real = computed(() => Boolean(screen.value && !screen.value.virtual));
// The settings the screen's board lists (boards.yaml `settings`, in its shape's catalog): its Extras card.
const boardExtras = computed(() => Boolean(screen.value?.shape?.catalog?.settings?.length));
// The plugins this screen runs that have settings: those are in each plugin's details on the Plugins tab (docs/PLUGINS.md).
const pluginsWithSettings = computed(() => {
  const s = screen.value;
  if (!s || s.virtual) return [];
  return [...plugins.index.filter((plugin) => plugins.installedOn(s, plugin.id)), ...plugins.testsOn(s)]
    .filter((plugin, i, all) => all.findIndex((other) => other.id === plugin.id) === i)
    .filter((plugin) => plugin.settings?.length || (plugin.inputs || []).length || (plugin.parts || []).length);
});
// A plugin's details on the screen's Plugins tab, opened from here, where its settings used to be.
function openPlugin(id: string) {
  plugins.focus = id;
  ui.tab = "plugins";
}
const values = computed(() => settings.settingValues());
const offline = computed(() => view.value?.owner === "screen" && !screen.value?.online);
// Page buttons and swiping off: the pages that only Go to page tiles could reach, and don't.
const reachWarning = computed(() => pageReachWarning());
const status = computed(() => offline.value
  ? t("editor.screen_settings.status.offline")
  : settings.settingPending
    ? t("editor.common.saving")
    : view.value?.owner === "screen"
      ? t("editor.screen_settings.status.screen")
      : t("editor.screen_settings.status.app"));
// Calibrate touch (app 0.2.117): the screen has to be there to show the crosses, whoever owns its settings.
const calibrateReady = computed(() => Boolean(screen.value?.online));
const startCalibration = () => screen.value && scr.calibrateTouch(screen.value);

// ---- The list of parts: each with its icon, its title and one line of what is set now ----
const ALL = SETTING_GROUPS.flatMap((group) => group.rows as readonly SettingRow[]);
const has = (key: string) => Boolean(view.value?.keys.includes(key));
const row = (key: string) => ALL.find((r) => r.key === key)!;
const on = (key: string) => has(key) && Boolean(values.value[key]);
const known = (key: string) => has(key) && values.value[key] !== null && values.value[key] !== undefined;
const valueText = (key: string) => settings.settingText(row(key), values.value);
// A part's blocks of rows, with only the rows this screen reports.
const blocks = (part: ScreenSettingsPart) => real.value && view.value
  ? (SCREEN_PART_ROWS[part] || []).filter((block) => block.keys.some(has)) : [];
const grid = computed(() => doc.documentGrid);
const gridShown = computed(() => Boolean(grid.value && (doc.gridWay || real.value)));

const displayLine = computed(() => [
  ...(grid.value ? [t("editor.screen_settings.parts.display.grid", { columns: grid.value.columns, rows: grid.value.rows })] : []),
  ...(known("brightness") ? [`${settingLabel(row("brightness"))} ${valueText("brightness")}`] : []),
  ...(on("dark_mode") ? [settingLabel(row("dark_mode"))] : []),
  ...(has("rotation") && Number(values.value.rotation) ? [valueText("rotation")] : []),
].join(" · "));
const standbyLine = computed(() => [
  // A value the screen has not reported (offline) says nothing, rather than "No standby".
  ...(known("standby_enabled") ? [on("standby_enabled")
    ? t("editor.screen_settings.parts.standby.after", { time: valueText("standby_seconds") })
    : t("editor.screen_settings.parts.standby.off")] : []),
  ...(on("night_enabled") ? [t("editor.screen_settings.parts.standby.night", { start: valueText("night_start"), end: valueText("night_end") })] : []),
].join(" · "));
const navigationLine = computed(() => [
  ...(on("auto_home") ? [t("editor.screen_settings.parts.navigation.home_after", { time: valueText("auto_home_seconds") })] : []),
  ...["swipe_pages", "page_buttons", "loop_pages", "home_button"].filter(on).map((key) => settingLabel(row(key))),
].join(" · "));
const boardLine = computed(() => [
  ...(boardExtras.value ? [t("editor.screen_settings.extras.title")] : []),
  ...(screenIcons.view ? [t("editor.screen_icons.card_title")] : []),
  ...(view.value?.calibrate ? [t("editor.screen_settings.actions.calibrate.button")] : []),
  ...(pluginsWithSettings.value.length ? [t("editor.screen_settings.plugins.title")] : []),
].join(" · "));
const feedback = computed(() => Boolean(screen.value?.feedback?.available));
const helpLine = computed(() => [
  ...(feedback.value ? [t("editor.screen_settings.parts.help.feedback")] : []),
  ...(real.value ? [t("editor.report.card_title")] : []),
].join(" · "));

type Part = { id: ScreenSettingsPart; icon: IconName; summary: string };
const parts = computed<Part[]>(() => [
  ...(gridShown.value || blocks("display").length ? [{ id: "display" as const, icon: "white-balance-sunny" as const, summary: displayLine.value }] : []),
  ...(blocks("standby").length ? [{ id: "standby" as const, icon: "weather-night" as const, summary: standbyLine.value }] : []),
  ...(blocks("navigation").length ? [{ id: "navigation" as const, icon: "gesture-swipe" as const, summary: navigationLine.value }] : []),
  ...(real.value && boardLine.value ? [{ id: "board" as const, icon: "chip" as const, summary: boardLine.value }] : []),
  ...(helpLine.value ? [{ id: "help" as const, icon: "lifebuoy" as const, summary: helpLine.value }] : []),
]);
const title = (part: ScreenSettingsPart) => t(`editor.screen_settings.parts.${part}.title`);
// The part the address names, while this screen has it.
const part = computed(() => parts.value.find((p) => p.id === ui.screenSettingsPart) || null);
// A block's own title, where the part shows more than that one block.
const titled = (p: ScreenSettingsPart) => p !== "navigation";
const flipDark = () => settings.setSetting("dark_mode", !values.value.dark_mode, 150);
</script>

<template>
  <div class="settings" id="general-settings" :class="{ offline }">
    <span v-if="real" class="status" id="settings-status" role="status">{{ status }}</span>

    <!-- The list of parts: a row each, with what is set now; a row opens its part. -->
    <div v-if="!part" class="set-column">
      <div id="settings-groups" class="set-cards">
        <div v-for="(card, i) in partCards(parts)" :key="i" class="set-list">
        <SettingsLink v-for="p in card" :key="p.id" :id="`settings-part-${p.id}`" :icon="p.icon" :tone="PART_LOOK[p.id].tone" :title="title(p.id)" :summary="p.summary" @open="ui.openScreenSettings(p.id)">
          <!-- The one thing people change most here needs no page: dark mode, on the row of the display. -->
          <button v-if="p.id === 'display' && has('dark_mode')" type="button" class="switch" role="switch" id="quick-dark-mode"
            :class="{ unknown: values.dark_mode === null || values.dark_mode === undefined }"
            :aria-checked="Boolean(values.dark_mode) ? 'true' : 'false'" :aria-label="settingLabel(row('dark_mode'))"
            :disabled="offline || view?.unavailable.includes('dark_mode')" @click="flipDark"></button>
        </SettingsLink>
        </div>
      </div>
    </div>

    <div v-else class="set-column" :class="{ dim: offline && part.id !== 'help' }">
      <SettingsHead :back="t('editor.screen_view.tabs.settings')" :title="title(part.id)" @back="ui.openScreenSettings(null)" />

      <template v-if="part.id === 'display'">
        <!-- The grid of the pages (GridSettings): a change of the draft, sent with the next save, so it is here also while
             the screen is offline, and the only card of a preview screen. -->
        <GridSettings />
        <section v-for="block in blocks('display')" :key="block.block" class="set-card">
          <h4>{{ t(`editor.screen_settings.blocks.${block.block}`) }}</h4>
          <SettingRows :keys="block.keys" />
        </section>
      </template>

      <template v-else-if="part.id === 'standby'">
        <template v-for="block in blocks('standby')" :key="block.block">
          <section class="set-card">
            <h4>{{ t(`editor.screen_settings.blocks.${block.block}`) }}</h4>
            <SettingRows :keys="block.keys" />
          </section>
          <!-- The screensaver (app 0.4.48) is what standby shows, so it stands right after the rows that turn standby on. -->
          <ScreensaverCard v-if="block.block === 'standby'" />
        </template>
      </template>

      <template v-else-if="part.id === 'navigation'">
        <section v-for="block in blocks('navigation')" :key="block.block" class="set-card">
          <h4 v-if="titled('navigation')">{{ t(`editor.screen_settings.blocks.${block.block}`) }}</h4>
          <SettingRows :keys="block.keys" />
          <p v-if="reachWarning" class="hint warn" id="settings-page-reach">{{ reachWarning }}</p>
        </section>
      </template>

      <template v-else-if="part.id === 'board'">
        <!-- The board's extras (docs/SETTINGS.md, "A board's own settings"): what only this board has, the same switches as
             on the screen's own settings page under Extras and in Home Assistant. -->
        <section v-if="boardExtras" class="set-card" id="settings-extras">
          <h4><span class="mdi">{{ glyph("F0493") }}</span>{{ t("editor.screen_settings.extras.title") }}</h4>
          <p class="hint">{{ t("editor.screen_settings.extras.note") }}</p>
          <PluginSettings extras />
        </section>
        <!-- The icons a screen takes on top of the fixed set (ScreenIconsPanel); a board with 4 MB of flash has no room for them. -->
        <section v-if="screenIcons.view && screen" class="set-card" id="settings-icons">
          <h4><span class="mdi">{{ glyph("F0832") }}</span>{{ t("editor.screen_icons.card_title") }}</h4>
          <template v-if="screenIcons.view.room">
            <p class="hint">{{ t("editor.screen_icons.card_hint", { room: screenIcons.view.room }) }}</p>
            <p v-if="screenIcons.view.chosen.length" class="hint">{{ t("editor.screen_icons.card_count", { n: screenIcons.view.chosen.length }) }}<template v-if="screenIcons.view.waiting.length"> · {{ t("editor.screen_icons.card_waiting", { n: screenIcons.view.waiting.length }) }}</template></p>
            <div class="s-action">
              <button type="button" class="btn quiet" id="setting-icons" @click="ui.openIcons(screen.id)">{{ t("editor.screen_icons.card_button") }}<Icon name="arrow-right" /></button>
            </div>
          </template>
          <p v-else class="hint">{{ t("editor.screen_icons.card_no_room") }}</p>
        </section>
        <!-- Calibrate touch: only a panel that needs it, so a capacitive one has no card here at all. -->
        <section v-if="view?.calibrate" class="set-card" id="settings-this-screen">
          <h4><span class="mdi">{{ glyph("F02FD") }}</span>{{ t("editor.screen_settings.groups.this_screen") }}</h4>
          <div class="s-action">
            <button type="button" class="btn quiet" id="setting-calibrate" :disabled="!calibrateReady" @click="startCalibration()">
              <span class="mdi">{{ glyph("F01A3") }}</span>{{ t("editor.screen_settings.actions.calibrate.button") }}
            </button>
          </div>
          <p class="hint">{{ t("editor.screen_settings.actions.calibrate.hint") }}</p>
        </section>
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
      </template>

      <template v-else-if="part.id === 'help' && screen">
        <!-- Does it work as you expect (app 0.3.10): also for a screen that is offline or never got its tiles. -->
        <FeedbackPanel v-if="feedback" :key="`settings-${screen.id}`" :screen="screen" mode="settings" />
        <!-- A screen that doesn't work right: the troubleshooting report (ReportPanel), also behind the screen's menu. -->
        <section v-if="real" class="set-card" id="settings-report">
          <h4><span class="mdi">{{ glyph("F02D7") }}</span>{{ t("editor.report.card_title") }}</h4>
          <p class="hint">{{ t("editor.report.card_hint") }}</p>
          <div class="s-action">
            <button type="button" class="btn quiet" id="setting-report" @click="ui.openReport(screen.id)">{{ t("editor.report.button") }}<Icon name="arrow-right" /></button>
          </div>
        </section>
      </template>
    </div>
  </div>
</template>

<style scoped>
/* An offline screen's rows wait for it; the grid is the draft's and is sent with the next save, so it stays as it is. */
.set-column.dim > :not(.grid-card):not(.set-head) { opacity: 0.6; }
</style>
