<script setup lang="ts">
// One step of the screensaver in the drawer (app 0.4.83): whether it is used, and what it shows: its players in the
// order they are tried, or its camera. The order of the steps changes here too, a place earlier or later. The clock has
// an inspector of its own with its row of entities at the head (SaverClock.vue, app 0.4.89).
// Since app 0.4.89 also the photos (their folder, pace, order and fit) and a plugin's step of its own (its entity and
// options, and Remove); the music and the photos can show a plugin's face instead of the screen's own.
import { computed, watch } from "vue";
import { t } from "../i18n";
import { useSortableRows } from "../composables/useSortableRows";
import { text, type PluginTileOption } from "../model/plugins";
import { glyph } from "../model/topbar";
import type { PluginValue, SaverPhotos as Photos, SaverStep } from "../types";
import SaverPhotos from "./SaverPhotos.vue";
import PluginOptions from "./PluginOptions.vue";
import Segmented from "./Segmented.vue";
import Icon from "./ui/Icon.vue";
import InspectorHead from "./ui/InspectorHead.vue";
import PropRow from "./ui/PropRow.vue";
import Section from "./ui/Section.vue";
import SwitchRow from "./ui/SwitchRow.vue";
import UiChips from "./ui/UiChips.vue";
import UiPicker from "./ui/UiPicker.vue";
import UiSelect from "./ui/UiSelect.vue";
import { useEntitiesStore } from "../stores/entities";
import { usePluginsStore } from "../stores/plugins";
import { MAX_PLAYERS, PHOTO_EVERY, PHOTO_FITS, PHOTO_MOTIONS, PHOTO_ORDERS, isPluginKey, useScreensaverStore, type FaceStep } from "../stores/screensaver";
import { useInspectorStore } from "../stores/inspector";
import { useDocumentStore } from "../stores/document";

const doc = useDocumentStore();
const entities = useEntitiesStore();
const plugins = usePluginsStore();
const screensaver = useScreensaverStore();
const insp = useInspectorStore();

const props = defineProps<{ step: SaverStep }>();
const T = (name: string, values?: Record<string, unknown>) => t(`editor.screen_settings.screensaver.${name}`, values || {});
const place = computed(() => screensaver.stepPlace(props.step));
const crumbs = computed(() => [
  { text: T("title"), open: insp.closeInspector },
  ...(place.value.count > 1 ? [{ text: T("place", place.value) }] : []),
]);

// ---- The face of the music or the photos: the screen's own, or a plugin's.
const faceStep = computed<FaceStep | null>(() => (props.step === "media" || props.step === "photos" ? props.step : null));
const faceChoices = computed<[string, string][]>(() => {
  if (!faceStep.value) return [];
  const faces = screensaver.facesFor(faceStep.value).map((s) => [s.key, text(s.saver.name)] as [string, string]);
  const chosen = screensaver.faceOf(faceStep.value);
  // A face whose plugin left the screen stays named until another is chosen; the screen shows its own meanwhile.
  if (chosen && !faces.some(([key]) => key === chosen)) faces.push([chosen, screensaver.stepLabel(chosen)]);
  return faces.length ? [["", T("face_standard")], ...faces] : [];
});
const faceKey = computed(() => (faceStep.value ? screensaver.faceOf(faceStep.value) : ""));
const facePlugin = computed(() => (faceKey.value ? plugins.saverOf(faceKey.value) : undefined));

// ---- The photos: how long each stands, in what order, and how one fills the glass.
const everyChoices = computed<[number, string][]>(() => PHOTO_EVERY.map((seconds) => [seconds, T(`photos_every_${seconds}`)]));
const orderChoices = computed<[string, string][]>(() => PHOTO_ORDERS.map((order) => [order, T(`photos_order_${order}`)]));
const fitChoices = computed<[string, string][]>(() => PHOTO_FITS.map((fit) => [fit, T(`photos_fit_${fit}`)]));
const motionChoices = computed<[string, string][]>(() => PHOTO_MOTIONS.map((motion) => [motion, T(`photos_motion_${motion}`)]));

// ---- A plugin's step of its own: its entity and its options.
const pluginKey = computed(() => (isPluginKey(props.step) ? props.step : null));
const known = computed(() => (pluginKey.value ? plugins.saverOf(pluginKey.value) : undefined));
const here = computed(() => Boolean(pluginKey.value && screensaver.pluginHere(pluginKey.value)));
const stepEntity = computed(() => (pluginKey.value ? screensaver.pluginSetting(pluginKey.value).entity : ""));
const entityItems = computed(() => plugins.entitiesIn(known.value?.saver.domains || []).filter((e) => e.id !== stepEntity.value)
  .map((e) => ({ id: e.id, name: e.name, hint: screensaver.entityPlace(e.id) })));
// The options of the plugin face or step that is open, and where a change goes.
const optionsKey = computed(() => pluginKey.value || faceKey.value);
const optionsOf = computed(() => (pluginKey.value ? known.value : facePlugin.value));
const setOption = (option: PluginTileOption, value: PluginValue) => optionsKey.value && screensaver.setPluginOption(optionsKey.value, option.id, value);
const shown = computed(() => playerSort.live.value || screensaver.players);
const free = computed(() => screensaver.entitiesOf("media", screensaver.players));
const freeItems = computed(() => free.value.map((e) => ({ id: e.id, name: e.name, hint: e.area })));
const playerSort = useSortableRows<string>({ rows: "#saver-players > .item", items: () => screensaver.players, commit: screensaver.setPlayers, skip: "button", grip: ".grip",
  enabled: () => screensaver.saverReady && screensaver.players.length > 1 });

// ---- Where each player counts (GitHub #182): the devices Home Assistant lists as its sources (Spotify Connect's), and
// those chosen before, also while they are offline. A player without sources has nothing to choose.
watch(() => (props.step === "media" ? screensaver.players : []), (ids) => ids.length && entities.loadLibraryStates(ids, doc.stillSelected()), { immediate: true });
function devicesOf(id: string) {
  const listed = entities.liveOf(id)?.a.source_list;
  const names = [...(Array.isArray(listed) ? listed.filter((name): name is string => typeof name === "string") : []), ...screensaver.playOnOf(id)];
  return [...new Set(names)].map((name) => ({ value: name, label: name }));
}
const withDevices = computed(() => screensaver.players.map((id) => ({ id, devices: devicesOf(id) })).filter((row) => row.devices.length));
</script>

<template>
  <InspectorHead :title="screensaver.stepLabel(step)" :code="screensaver.stepIcon(step)" :crumbs="crumbs" />
  <div v-if="screensaver.saver" class="dr-body saver-drawer">
    <section class="insp-sec">
      <div class="insp-sec-body saver-use">
        <SwitchRow :label="T('on')" :model-value="screensaver.isOn(step)" @update:model-value="(on: boolean) => screensaver.toggleStep(step, on)" />
      </div>
    </section>

    <template v-if="step === 'media'">
      <Section :title="T('players_title')" :aside="`${screensaver.players.length} / ${MAX_PLAYERS}`">
        <div v-if="shown.length" id="saver-players" class="items" role="list" :aria-label="T('players')">
          <div v-for="(id, row) in shown" :key="id" class="item saver-player" role="listitem" tabindex="0"
            :class="{ 'dragging-chip': playerSort.drag.value.active && playerSort.drag.value.index === row, single: shown.length < 2 }"
            @pointerdown="playerSort.down($event, row)" @keydown="playerSort.key($event, row)">
            <span class="saver-rank">{{ row + 1 }}</span>
            <span class="tx"><b>{{ entities.entityName(id) }}</b><small v-if="screensaver.entityPlace(id)">{{ screensaver.entityPlace(id) }}</small></span>
            <Icon v-if="shown.length > 1" name="drag-vertical" class="grip" />
            <button type="button" class="x" :aria-label="T('remove_player', { name: entities.entityName(id) })" @click="screensaver.removePlayer(id)"><Icon name="close" /></button>
          </div>
        </div>
        <UiPicker v-if="screensaver.players.length < MAX_PLAYERS" :items="freeItems" :placeholder="T('player_search')" :empty="T('player_none')" @pick="screensaver.addPlayer">
          <template #trigger>
            <button type="button" class="ghost-btn" id="saver-add-player"><Icon name="plus" />{{ T("player_add") }}</button>
          </template>
        </UiPicker>
        <small class="help">{{ T("players_hint") }}</small>
      </Section>
      <Section v-if="withDevices.length" :title="T('play_on_title')">
        <div v-for="row in withDevices" :key="row.id" class="saver-play-on">
          <b>{{ entities.entityName(row.id) }}</b>
          <UiChips :model-value="screensaver.playOnOf(row.id)" :chips="row.devices" :label="T('play_on_label', { name: entities.entityName(row.id) })"
            @update:model-value="(names: string[]) => screensaver.setPlayOn(row.id, names)" />
        </div>
        <small class="help">{{ T("play_on_hint") }}</small>
      </Section>
      <p class="hint saver-foot-hint">{{ T("keys_hint") }}</p>
    </template>

    <template v-else-if="step === 'photos'">
      <Section :title="T('photos_folder')">
        <SaverPhotos />
        <small class="help">{{ T("photos_hint") }}</small>
      </Section>
      <Section :title="T('photos_show')">
        <PropRow :label="T('photos_every')" icon="clock-outline" for="saver-photos-every">
          <UiSelect id="saver-photos-every" :model-value="screensaver.photos.every" :options="everyChoices" @update:model-value="(value: number) => screensaver.setPhotos({ every: value })" />
        </PropRow>
        <PropRow :label="T('photos_order')" icon="shuffle-variant" stack>
          <Segmented :choices="orderChoices" :value="screensaver.photos.order" @pick="(value: Photos['order']) => screensaver.setPhotos({ order: value })" />
        </PropRow>
        <PropRow :label="T('photos_fit')" icon="crop-landscape" stack>
          <Segmented :choices="fitChoices" :value="screensaver.photos.fit" @pick="(value: Photos['fit']) => screensaver.setPhotos({ fit: value })" />
        </PropRow>
        <small class="help">{{ T(`photos_fit_${screensaver.photos.fit}_hint`) }}</small>
        <PropRow :label="T('photos_motion')" icon="arrow-right" stack>
          <Segmented :choices="motionChoices" :value="screensaver.photos.motion || 'still'" @pick="(value: Photos['motion']) => screensaver.setPhotos({ motion: value })" />
        </PropRow>
        <small class="help">{{ T(`photos_motion_${screensaver.photos.motion || 'still'}_hint`) }}</small>
      </Section>
    </template>

    <template v-else-if="pluginKey">
      <p v-if="known" class="plugin-tile-from"><span class="mdi">{{ glyph("F0A66") }}</span>{{ t("editor.plugin_tile.from", { plugin: text(known.plugin.name) }) }}</p>
      <p v-if="!here" class="hint warn saver-foot-hint" id="saver-plugin-gone">{{ T("plugin_gone") }}</p>
      <p v-if="known?.saver.example" class="hint saver-foot-hint">{{ text(known.saver.example) }}</p>
      <Section v-if="known?.saver.domains?.length" :title="t('editor.plugin_tile.entity')">
        <div v-if="stepEntity" class="item saver-player single">
          <span class="tx"><b>{{ entities.entityName(stepEntity) }}</b><small v-if="screensaver.entityPlace(stepEntity)">{{ screensaver.entityPlace(stepEntity) }}</small></span>
          <button type="button" class="x" :aria-label="T('remove_player', { name: entities.entityName(stepEntity) })" @click="screensaver.setPluginEntity(pluginKey, '')"><Icon name="close" /></button>
        </div>
        <UiPicker :items="entityItems" :placeholder="T('plugin_entity_search')" :empty="T('plugin_entity_none')" @pick="(id: string) => pluginKey && screensaver.setPluginEntity(pluginKey, id)">
          <template #trigger>
            <button type="button" class="ghost-btn" id="saver-plugin-entity"><Icon name="plus" />{{ stepEntity ? T("plugin_entity_change") : T("plugin_entity_choose") }}</button>
          </template>
        </UiPicker>
      </Section>
    </template>

    <Section v-else :title="screensaver.stepLabel('camera')">
      <UiSelect id="saver-camera" :model-value="screensaver.saver.camera" :options="screensaver.cameraChoices" @update:model-value="(value: string) => screensaver.changeSaver({ camera: value })" />
      <small class="help">{{ T("camera_hint") }}</small>
    </Section>

    <!-- The face of the music or the photos, where a plugin this screen runs has one. -->
    <Section v-if="faceChoices.length" :title="T('face')">
      <UiSelect id="saver-step-face" :model-value="faceKey" :options="faceChoices" @update:model-value="(value: string) => faceStep && screensaver.setFace(faceStep, isPluginKey(value) ? value : '')" />
      <small v-if="facePlugin?.saver.example" class="help">{{ text(facePlugin.saver.example) }}</small>
    </Section>
    <!-- The options of the plugin's face or step that is open. -->
    <Section v-if="optionsKey && optionsOf?.saver.options?.length" :title="t('editor.plugin_tile.options')">
      <PluginOptions :plugin="optionsOf.plugin" :options="optionsOf.saver.options" :values="screensaver.pluginValues(optionsKey)" @change="setOption" />
    </Section>

  </div>
  <div class="dr-foot">
    <button v-if="pluginKey" type="button" class="btn danger" id="saver-plugin-remove" @click="screensaver.removePluginStep(pluginKey)"><Icon name="delete-outline" />{{ t("editor.common.remove") }}</button>
    <span class="spacer"></span>
    <div v-if="place.count > 1" class="tool-group" role="group">
      <button type="button" class="icon-btn" :disabled="place.n <= 1" :aria-label="T('earlier')" :title="T('earlier')" @click="screensaver.moveStep(step, -1)"><Icon name="arrow-up" /></button>
      <button type="button" class="icon-btn" :disabled="place.n >= place.count" :aria-label="T('later')" :title="T('later')" @click="screensaver.moveStep(step, 1)"><Icon name="arrow-down" /></button>
    </div>
  </div>
</template>

<style scoped>
.saver-use { padding-top: 12px; }
.saver-drawer .items { margin-bottom: 4px; }
.saver-player { cursor: grab; }
.saver-play-on { display: grid; gap: 6px; margin-bottom: 10px; }
.saver-player.single { cursor: default; }
.saver-player .grip { color: var(--muted); opacity: 0.6; font-size: 16px; touch-action: none; }
.saver-rank { width: 18px; height: 18px; border-radius: 50%; background: var(--seg); color: var(--ink-2); font-size: 11px; font-weight: 600; display: grid; place-items: center; flex: none; }
.saver-foot-hint { margin: 4px 16px 0; }
</style>
