<script setup lang="ts">
// One step of the screensaver in the drawer (app 0.4.83): whether it is used, and what it shows: its players in the
// order they are tried, its camera, or the clock's temperature and the entities beside it. The order of the steps
// changes here too, a place earlier or later.
import { computed, watch } from "vue";
import { t } from "../i18n";
import { glyph } from "../model/topbar";
import { closeInspector, entityName, loadLibraryStates, openSaverAdd, openSaverItem, removeSaverItem, SAVER_ITEMS_MAX, saverItems, topbarLabel, topbarView } from "../store";
import {
  addPlayer, cameraChoices, changeSaver, entitiesOf, entityPlace, isOn, MAX_PLAYERS, moveStep, players, removePlayer, SAVER_ICONS, savedOrder, saver,
  saverLabel, saverReady, setPlayers, sorter, toggleStep, weatherChoices, weatherSource,
} from "../saver";
import type { SaverKind } from "../types";
import SaverGlass from "./SaverGlass.vue";
import Icon from "./ui/Icon.vue";
import InspectorHead from "./ui/InspectorHead.vue";
import Section from "./ui/Section.vue";
import SwitchRow from "./ui/SwitchRow.vue";
import UiMenu from "./ui/UiMenu.vue";
import UiMenuItem from "./ui/UiMenuItem.vue";
import UiSelect from "./ui/UiSelect.vue";

const props = defineProps<{ step: SaverKind }>();
const T = (name: string, values?: Record<string, unknown>) => t(`editor.screen_settings.screensaver.${name}`, values || {});
const place = computed(() => savedOrder.value.indexOf(props.step));
const crumbs = computed(() => [
  { text: T("title"), open: closeInspector },
  ...(saver.value?.pictures ? [{ text: T("place", { n: place.value + 1, count: savedOrder.value.length }) }] : []),
]);
const shown = computed(() => playerSort.live.value || players.value);
const free = computed(() => entitiesOf("media", players.value));
const playerSort = sorter<string>("#saver-players > .item", () => players.value, setPlayers, "button", () => saverReady.value && players.value.length > 1);
watch(weatherSource, (id) => id && loadLibraryStates([id]), { immediate: true });
</script>

<template>
  <InspectorHead :title="saverLabel(step)" :code="SAVER_ICONS[step]" :crumbs="crumbs" />
  <div v-if="saver" class="dr-body saver-drawer">
    <section class="insp-sec">
      <div class="insp-sec-body saver-use">
        <SwitchRow :label="T('on')" :model-value="isOn(step)" @update:model-value="(on: boolean) => toggleStep(step, on)" />
      </div>
    </section>

    <template v-if="step === 'media'">
      <Section :title="T('players_title')" :aside="`${players.length} / ${MAX_PLAYERS}`">
        <div v-if="shown.length" id="saver-players" class="items" role="list" :aria-label="T('players')">
          <div v-for="(id, row) in shown" :key="id" class="item saver-player" role="listitem" tabindex="0"
            :class="{ 'dragging-chip': playerSort.drag.value.active && playerSort.drag.value.index === row, single: shown.length < 2 }"
            @pointerdown="playerSort.down($event, row)" @keydown="playerSort.key($event, row)">
            <span class="saver-rank">{{ row + 1 }}</span>
            <span class="tx"><b>{{ entityName(id) }}</b><small v-if="entityPlace(id)">{{ entityPlace(id) }}</small></span>
            <Icon v-if="shown.length > 1" name="drag-vertical" class="grip" />
            <button type="button" class="x" :aria-label="T('remove_player', { name: entityName(id) })" @click="removePlayer(id)"><Icon name="close" /></button>
          </div>
        </div>
        <UiMenu v-if="players.length < MAX_PLAYERS" align="start" width="260px">
          <template #trigger>
            <button type="button" class="ghost-btn" id="saver-add-player"><Icon name="plus" />{{ T("player_add") }}</button>
          </template>
          <UiMenuItem v-for="e in free" :key="e.id" :hint="e.area" @select="addPlayer(e.id)">{{ e.name }}</UiMenuItem>
        </UiMenu>
        <small class="help">{{ T("players_hint") }}</small>
      </Section>
      <p class="hint saver-foot-hint">{{ T("keys_hint") }}</p>
    </template>

    <Section v-else-if="step === 'camera'" :title="saverLabel('camera')">
      <UiSelect id="saver-camera" :model-value="saver.camera" :options="cameraChoices" @update:model-value="(value: string) => changeSaver({ camera: value })" />
      <small class="help">{{ T("camera_hint") }}</small>
    </Section>

    <template v-else>
      <Section :title="T('glass')">
        <SaverGlass :height="170" />
      </Section>
      <Section :title="T('temperature')">
        <UiSelect id="saver-weather" :model-value="saver.weather ?? 'auto'" :options="weatherChoices" @update:model-value="(value: string) => changeSaver({ weather: value })" />
      </Section>
      <Section :title="T('beside')" :aside="`${saverItems().length} / ${SAVER_ITEMS_MAX}`">
        <div v-if="saverItems().length" id="screensaver-items" class="items" role="list" :aria-label="T('items_title')">
          <div v-for="(it, i) in saverItems()" :key="it.entity" class="item" role="listitem" tabindex="0" @click="openSaverItem(i)" @keydown.enter.prevent="openSaverItem(i)">
            <span class="av mdi">{{ topbarView(it).icon ? glyph(topbarView(it).icon!) : "" }}</span>
            <span class="tx"><b>{{ topbarLabel(it) }}</b><small>{{ it.content === "icon" ? T("item_icon") : topbarView(it).text }}</small></span>
            <button type="button" class="x" :aria-label="t('editor.topbar.remove_named', { name: topbarLabel(it) })" @click.stop="removeSaverItem(i)"><Icon name="close" /></button>
          </div>
        </div>
        <button v-if="saverItems().length < SAVER_ITEMS_MAX" type="button" class="ghost-btn" id="screensaver-add-item" @click="openSaverAdd"><Icon name="plus" />{{ T("items_add") }}</button>
        <small class="help">{{ T("items_hint") }}</small>
      </Section>
    </template>
  </div>
  <div class="dr-foot">
    <span class="spacer"></span>
    <div v-if="saver?.pictures" class="tool-group" role="group">
      <button type="button" class="icon-btn" :disabled="place <= 0" :aria-label="T('earlier')" :title="T('earlier')" @click="moveStep(step, -1)"><Icon name="arrow-up" /></button>
      <button type="button" class="icon-btn" :disabled="place >= savedOrder.length - 1" :aria-label="T('later')" :title="T('later')" @click="moveStep(step, 1)"><Icon name="arrow-down" /></button>
    </div>
  </div>
</template>

<style scoped>
.saver-use { padding-top: 12px; }
.saver-drawer .items { margin-bottom: 4px; }
.saver-player { cursor: grab; }
.saver-player.single { cursor: default; }
.saver-player .grip { color: var(--muted); opacity: 0.6; font-size: 16px; touch-action: none; }
.saver-rank { width: 18px; height: 18px; border-radius: 50%; background: var(--seg); color: var(--ink-2); font-size: 11px; font-weight: 600; display: grid; place-items: center; flex: none; }
.saver-foot-hint { margin: 4px 16px 0; }
</style>
