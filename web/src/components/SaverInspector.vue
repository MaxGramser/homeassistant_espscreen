<script setup lang="ts">
// One step of the screensaver in the drawer (app 0.4.83): whether it is used, and what it shows: its players in the
// order they are tried, its camera, or the clock's temperature and the entities beside it. The order of the steps
// changes here too, a place earlier or later.
import { computed, watch } from "vue";
import { t } from "../i18n";
import { glyph } from "../model/topbar";
import { closeInspector, openSaverAdd, openSaverItem, stillSelected } from "../store";
import { useSortableRows } from "../composables/useSortableRows";
import type { SaverKind } from "../types";
import SaverGlass from "./SaverGlass.vue";
import Icon from "./ui/Icon.vue";
import InspectorHead from "./ui/InspectorHead.vue";
import Section from "./ui/Section.vue";
import SwitchRow from "./ui/SwitchRow.vue";
import UiMenu from "./ui/UiMenu.vue";
import UiMenuItem from "./ui/UiMenuItem.vue";
import UiSelect from "./ui/UiSelect.vue";
import { useEntitiesStore } from "../stores/entities";
import { useTopbarStore } from "../stores/topbar";
import { MAX_PLAYERS, SAVER_ICONS, SAVER_ITEMS_MAX, saverLabel, useScreensaverStore } from "../stores/screensaver";

const entities = useEntitiesStore();
const topbar = useTopbarStore();
const screensaver = useScreensaverStore();

const props = defineProps<{ step: SaverKind }>();
const T = (name: string, values?: Record<string, unknown>) => t(`editor.screen_settings.screensaver.${name}`, values || {});
const place = computed(() => screensaver.savedOrder.indexOf(props.step));
const crumbs = computed(() => [
  { text: T("title"), open: closeInspector },
  ...(screensaver.saver?.pictures ? [{ text: T("place", { n: place.value + 1, count: screensaver.savedOrder.length }) }] : []),
]);
const shown = computed(() => playerSort.live.value || screensaver.players);
const free = computed(() => screensaver.entitiesOf("media", screensaver.players));
const playerSort = useSortableRows<string>({ rows: "#saver-players > .item", items: () => screensaver.players, commit: screensaver.setPlayers, skip: "button", grip: ".grip",
  enabled: () => screensaver.saverReady && screensaver.players.length > 1 });
watch(() => screensaver.weatherSource, (id) => id && entities.loadLibraryStates([id], stillSelected()), { immediate: true });
</script>

<template>
  <InspectorHead :title="saverLabel(step)" :code="SAVER_ICONS[step]" :crumbs="crumbs" />
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
        <UiMenu v-if="screensaver.players.length < MAX_PLAYERS" align="start" width="260px">
          <template #trigger>
            <button type="button" class="ghost-btn" id="saver-add-player"><Icon name="plus" />{{ T("player_add") }}</button>
          </template>
          <UiMenuItem v-for="e in free" :key="e.id" :hint="e.area" @select="screensaver.addPlayer(e.id)">{{ e.name }}</UiMenuItem>
        </UiMenu>
        <small class="help">{{ T("players_hint") }}</small>
      </Section>
      <p class="hint saver-foot-hint">{{ T("keys_hint") }}</p>
    </template>

    <Section v-else-if="step === 'camera'" :title="saverLabel('camera')">
      <UiSelect id="saver-camera" :model-value="screensaver.saver.camera" :options="screensaver.cameraChoices" @update:model-value="(value: string) => screensaver.changeSaver({ camera: value })" />
      <small class="help">{{ T("camera_hint") }}</small>
    </Section>

    <template v-else>
      <Section :title="T('glass')">
        <SaverGlass :height="170" />
      </Section>
      <Section :title="T('temperature')">
        <UiSelect id="saver-weather" :model-value="screensaver.saver.weather ?? 'auto'" :options="screensaver.weatherChoices" @update:model-value="(value: string) => screensaver.changeSaver({ weather: value })" />
      </Section>
      <Section :title="T('beside')" :aside="`${screensaver.saverItems.length} / ${SAVER_ITEMS_MAX}`">
        <div v-if="screensaver.saverItems.length" id="screensaver-items" class="items" role="list" :aria-label="T('items_title')">
          <div v-for="(it, i) in screensaver.saverItems" :key="it.entity" class="item" role="listitem" tabindex="0" @click="openSaverItem(i)" @keydown.enter.prevent="openSaverItem(i)">
            <span class="av mdi">{{ topbar.topbarView(it).icon ? glyph(topbar.topbarView(it).icon!) : "" }}</span>
            <span class="tx"><b>{{ topbar.topbarLabel(it) }}</b><small>{{ it.content === "icon" ? T("item_icon") : topbar.topbarView(it).text }}</small></span>
            <button type="button" class="x" :aria-label="t('editor.topbar.remove_named', { name: topbar.topbarLabel(it) })" @click.stop="screensaver.removeSaverItem(i)"><Icon name="close" /></button>
          </div>
        </div>
        <button v-if="screensaver.saverItems.length < SAVER_ITEMS_MAX" type="button" class="ghost-btn" id="screensaver-add-item" @click="openSaverAdd"><Icon name="plus" />{{ T("items_add") }}</button>
        <small class="help">{{ T("items_hint") }}</small>
      </Section>
    </template>
  </div>
  <div class="dr-foot">
    <span class="spacer"></span>
    <div v-if="screensaver.saver?.pictures" class="tool-group" role="group">
      <button type="button" class="icon-btn" :disabled="place <= 0" :aria-label="T('earlier')" :title="T('earlier')" @click="screensaver.moveStep(step, -1)"><Icon name="arrow-up" /></button>
      <button type="button" class="icon-btn" :disabled="place >= screensaver.savedOrder.length - 1" :aria-label="T('later')" :title="T('later')" @click="screensaver.moveStep(step, 1)"><Icon name="arrow-down" /></button>
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
