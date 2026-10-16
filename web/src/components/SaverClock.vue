<script setup lang="ts">
// The screensaver's clock (app 0.4.89): the clock's bottom row in small at the head (BarStrip, white on black as the
// glass draws it), and under it only the part chosen there: the clock itself (on or off, the glass, the temperature), one
// entity's look, its icons, or the entities to add (the row's +). It replaces the clock's own drawer, an entity's drawer
// with a second head, and Add as a drawer of its own whose Cancel left the clock: the row stays at the head whatever is
// under it and shows every choice on an entity at once. An entity is dragged left or right in the row and moved with left
// and right in the foot; Escape goes one step out (stores/inspector.ts escape).
import { computed, watch } from "vue";
import { t } from "../i18n";
import { useSortableRows } from "../composables/useSortableRows";
import { entityItem, glyph, itemKey } from "../model/topbar";
import type { HeaderItem } from "../types";
import BarStrip, { type StripFace } from "./BarStrip.vue";
import EntityItemPicker from "./EntityItemPicker.vue";
import IconChoices from "./IconChoices.vue";
import IconPicker from "./IconPicker.vue";
import SaverFace from "./SaverFace.vue";
import SaverGlass from "./SaverGlass.vue";
import { SAVER_FACES, twelveFits, type SaverFaceKind } from "../model/clock-faces";
import { useUiStore } from "../stores/ui";
import Segmented from "./Segmented.vue";
import Icon from "./ui/Icon.vue";
import InspectorHead from "./ui/InspectorHead.vue";
import PropRow from "./ui/PropRow.vue";
import SwitchRow from "./ui/SwitchRow.vue";
import UiSelect from "./ui/UiSelect.vue";
import { useEntitiesStore } from "../stores/entities";
import { useTopbarStore } from "../stores/topbar";
import { SAVER_ICONS, SAVER_ITEMS_MAX, saverLabel, useScreensaverStore } from "../stores/screensaver";
import { useDocumentStore } from "../stores/document";
import { useInspectorStore } from "../stores/inspector";

const entities = useEntitiesStore();
const topbar = useTopbarStore();
const screensaver = useScreensaverStore();
const doc = useDocumentStore();
const insp = useInspectorStore();

// `index` -1 is the clock itself; `adding` is the row's +.
const props = defineProps<{ index: number; adding?: boolean }>();
const T = (name: string, values?: Record<string, unknown>) => t(`editor.screen_settings.screensaver.${name}`, values || {});
const items = computed(() => sort.live.value || screensaver.saverItems);
const item = computed<HeaderItem | undefined>(() => (props.adding ? undefined : items.value[props.index]));
const selected = computed(() => (props.adding ? "add" : item.value ? String(props.index) : "left"));
function choose(value: string) {
  if (value === "add") { if (!props.adding) insp.openSaverAdd(); }
  else if (value === "left") insp.openSaverStep("clock");
  else insp.openSaverItem(Number(value));
}
// The temperature's entity, read for the glass and the row.
watch(() => screensaver.weatherSource, (id) => id && entities.loadLibraryStates([id], doc.stillSelected()), { immediate: true });
const temperature = computed(() => ((screensaver.saver?.weather ?? "auto") === "" ? null : screensaver.clockPreview.temperature));
const stripTitle = computed(() => [screensaver.clockPreview.time, temperature.value].filter(Boolean).join(" · "));
// An entity as the clock draws it: its icon unless it shows its text alone, its text unless it shows its icon alone,
// always (the screensaver has no rule for when an entity shows).
function face(it: HeaderItem): StripFace {
  const view = topbar.topbarView(it);
  return { glyph: view.icon && it.icon !== "none" ? glyph(view.icon) : "", text: it.content === "icon" ? "" : view.text || "", shown: true };
}
const itemName = computed(() => (item.value ? entities.entityName(item.value.entity!) : ""));
// Three looks of one entity: its text alone, its icon alone, or the icon and the text.
const look = computed(() => (!item.value ? "both" : item.value.content === "icon" ? "icon" : item.value.icon === "none" ? "text" : "both"));
const looks: [string, string][] = [["text", T("item_text")], ["icon", T("item_icon")], ["both", T("item_both")]];
const kept = computed(() => (item.value && item.value.icon && item.value.icon !== "none" ? item.value.icon : "auto"));
function pickLook(value: string) {
  if (value === "text") screensaver.updateSaverItem(props.index, { content: "state", icon: "none" });
  else screensaver.updateSaverItem(props.index, { content: value === "icon" ? "icon" : "state", icon: kept.value });
}
const automatic = computed(() => (item.value ? entities.topbarPreviews[itemKey(item.value)]?.auto_icon || entities.automaticIcon(item.value.entity!) : ""));
const iconChoosing = computed(() => Boolean(insp.iconPickerOpen && item.value && look.value !== "text"));

// Adding: the top bar's own choice of entities. The clock shows an entity always, by its state or its icon; what else the
// top bar knows has no place there.
const plain = (it: HeaderItem): HeaderItem => ({ ...entityItem(it.entity!), content: it.content === "icon" ? "icon" : "state", icon: it.icon || "auto" });
const taken = (it: HeaderItem) => screensaver.saverItems.some((other) => other.entity === it.entity);

// ---- The clock's faces (module clock_faces): the face, its look, Glass's numerals and the seconds hand.
const ui = useUiStore();
const at = computed(() => new Date(ui.now));
const faceKind = computed(() => screensaver.face);
const analog = computed(() => faceKind.value !== "digital");
const faceChoices = computed(() => SAVER_FACES.map((kind) => ({ kind, label: T(`faces.${kind}`) })));
const looks2 = computed<[string, string][]>(() => [["dark", T("look_dark")], ["light", T("look_light")], ["auto", T("look_auto")]]);
// Twelve numerals bunch on long glass, so there only none and four.
const numeralChoices = computed<[number, string][]>(() => [[0, T("numerals_none")], [4, "4"],
  ...(twelveFits(screensaver.glassSize.width, screensaver.glassSize.height) ? [[12, "12"] as [number, string]] : [])]);
const numerals = computed(() => {
  const n = screensaver.saver?.numerals ?? 4;
  return n === 12 && !twelveFits(screensaver.glassSize.width, screensaver.glassSize.height) ? 4 : n;
});
const pickFace = (kind: SaverFaceKind) => screensaver.changeSaver({ face: kind });
// Glass and Bauhaus show the face alone; the temperature and the entities stand on Classic and the digital clock.
const withRow = computed(() => faceKind.value === "digital" || faceKind.value === "classic");

// The clock's place among the steps, as its own drawer had it.
const place = computed(() => screensaver.savedOrder.indexOf("clock"));
const crumbs = computed(() => [
  { text: T("title"), open: insp.closeInspector },
  ...(screensaver.saver?.pictures ? [{ text: T("place", { n: place.value + 1, count: screensaver.savedOrder.length }) }] : []),
]);

// An entity pressed in the row and moved left or right takes the place it is over (composables/useSortableRows.ts); let
// go off the row, it is taken off.
const sort = useSortableRows<HeaderItem>({ rows: ".bar-strip .strip-item[data-index]", items: () => screensaver.saverItems, commit: (list) => screensaver.setSaverItems(list),
  axis: "x", onMove: (from, to) => { if (props.index === from) insp.openSaverItem(to); }, away: { from: "#saver-strip", remove: (i) => screensaver.removeSaverItem(i) } });
const drag = sort.drag;
function move(step: number) { if (screensaver.moveSaverItem(props.index, props.index + step)) insp.openSaverItem(props.index + step); }
</script>

<template>
  <InspectorHead :title="saverLabel('clock')" :code="SAVER_ICONS.clock" :crumbs="crumbs" />
  <div v-if="screensaver.saver" class="dr-body bar-body">
    <!-- The clock's row stays at the head while what is under it scrolls. -->
    <div class="bar-anchor">
      <BarStrip id="saver-strip" saver :items="items" :selected="selected" :overflow="new Set()" :title="stripTitle" :home="false"
        :full="items.length >= SAVER_ITEMS_MAX" :max="SAVER_ITEMS_MAX" :dragging="drag.active ? drag.index : -1" :leaving="drag.away" :face="face"
        :label="T('items_title')" :left-title="T('clock_part')" :add-title="T('items_add')" add-id="screensaver-add-item"
        @select="choose" @press="(e, i) => sort.down(e, i)" @remove="screensaver.removeSaverItem" />
      <!-- What is chosen in the row, named once. -->
      <div class="bar-cap" id="saver-live">
        <span class="bar-cap-av">
          <Icon v-if="adding" name="plus" />
          <span v-else-if="item && face(item).glyph" class="mdi" aria-hidden="true">{{ face(item).glyph }}</span>
          <span v-else class="mdi" aria-hidden="true">{{ glyph(SAVER_ICONS.clock) }}</span>
        </span>
        <span class="bar-cap-tx">
          <b>{{ adding ? T('items_add_title') : iconChoosing ? t('editor.icon.label') : item ? itemName : saverLabel('clock') }}</b>
          <small>{{ adding ? T('items_slots', { used: items.length, n: SAVER_ITEMS_MAX }) : iconChoosing ? itemName
            : item ? t('editor.topbar.strip.place', { place: index + 1, count: items.length }) : T('clock_part') }}</small>
        </span>
        <button v-if="iconChoosing" type="button" class="btn quiet mini" id="saver-done" @click="insp.iconPickerOpen = false">{{ t('editor.common.done') }}</button>
      </div>
    </div>

    <div class="bar-part">
      <template v-if="adding">
        <EntityItemPicker id="saver-search" :taken="taken" :accepts="(it) => it.type === 'entity'" @pick="(it) => screensaver.addSaverItem(plain(it))" />
        <small class="help">{{ T("items_hint") }}</small>
      </template>
      <!-- An entity's icons in the place of its look, the row above showing each one picked. -->
      <IconChoices v-else-if="iconChoosing && item" :selected="item.icon || 'auto'" :automatic="automatic" :auto-label="t('editor.topbar.auto_icon')"
        @pick="(n) => screensaver.updateSaverItem(index, { icon: n })" />
      <template v-else-if="item">
        <PropRow :label="T('item_look')" icon="eye-outline" stack>
          <Segmented :choices="looks" :value="look" @pick="pickLook" />
        </PropRow>
        <IconPicker v-if="look !== 'text'" aside :selected="item.icon || 'auto'" :automatic="automatic" :auto-label="t('editor.topbar.auto_icon')" :allow-none="false"
          @pick="(n) => screensaver.updateSaverItem(index, { icon: n })" />
        <small class="help">{{ T("item_hint") }}</small>
      </template>
      <!-- The clock itself: whether it is used, how it looks on the glass, and the temperature beside its entities. -->
      <template v-else>
        <SwitchRow :label="T('on')" :model-value="screensaver.isOn('clock')" @update:model-value="(on: boolean) => screensaver.toggleStep('clock', on)" />
        <PropRow v-if="screensaver.facesHere" :label="T('face')" icon="clock-outline" stack>
          <div class="face-picks" id="saver-faces" role="radiogroup" :aria-label="T('face')">
            <button v-for="c in faceChoices" :key="c.kind" type="button" role="radio" class="face-pick" :data-face="c.kind"
              :aria-checked="faceKind === c.kind ? 'true' : 'false'" @click="pickFace(c.kind)">
              <span class="face-thumb" :style="{ aspectRatio: screensaver.glassRatio }">
                <span v-if="c.kind === 'digital'" class="face-digital">{{ screensaver.clockPreview.time }}</span>
                <SaverFace v-else :kind="c.kind" :dark="screensaver.faceDark" :numerals="numerals" :seconds="false"
                  :width="screensaver.glassSize.width" :height="screensaver.glassSize.height" :at="at" />
              </span>
              <span class="face-name">{{ c.label }}</span>
            </button>
          </div>
        </PropRow>
        <SaverGlass :height="150" />
        <template v-if="analog">
          <PropRow :label="T('look')" icon="theme-light-dark" stack>
            <Segmented :choices="looks2" :value="screensaver.saver.look ?? 'dark'" @pick="(v: 'dark' | 'light' | 'auto') => screensaver.changeSaver({ look: v })" />
          </PropRow>
          <PropRow v-if="faceKind === 'glass'" :label="T('numerals')" icon="format-list-bulleted" stack>
            <Segmented :choices="numeralChoices" :value="numerals" @pick="(v: number) => screensaver.changeSaver({ numerals: Number(v) })" />
          </PropRow>
          <SwitchRow :label="T('seconds')" :model-value="screensaver.saver.seconds ?? true" @update:model-value="(on: boolean) => screensaver.changeSaver({ seconds: on })" />
        </template>
        <PropRow v-if="withRow" :label="T('temperature')" stack>
          <UiSelect id="saver-weather" :model-value="screensaver.saver.weather ?? 'auto'" :options="screensaver.weatherChoices" @update:model-value="(value: string) => screensaver.changeSaver({ weather: value })" />
        </PropRow>
        <small class="help">{{ withRow ? T("row_hint") : T("face_alone_hint") }}</small>
        <small v-if="analog" class="help">{{ T("face_moves_hint") }}</small>
      </template>
    </div>
  </div>
  <div v-if="item && !iconChoosing" class="dr-foot">
    <button type="button" class="btn danger" @click="screensaver.removeSaverItem(index)"><Icon name="delete-outline" />{{ t("editor.common.remove") }}</button>
    <span class="spacer"></span>
    <div class="tool-group" role="group">
      <button type="button" class="icon-btn" :disabled="index === 0" :aria-label="t('editor.topbar.left_move')" :title="t('editor.topbar.left_move')" @click="move(-1)"><Icon name="chevron-left" /></button>
      <button type="button" class="icon-btn" :disabled="index >= items.length - 1" :aria-label="t('editor.topbar.right_move')" :title="t('editor.topbar.right_move')" @click="move(1)"><Icon name="chevron-right" /></button>
    </div>
  </div>
  <div v-else-if="!item && !adding && screensaver.saver?.pictures" class="dr-foot">
    <span class="spacer"></span>
    <div class="tool-group" role="group">
      <button type="button" class="icon-btn" :disabled="place <= 0" :aria-label="T('earlier')" :title="T('earlier')" @click="screensaver.moveStep('clock', -1)"><Icon name="arrow-up" /></button>
      <button type="button" class="icon-btn" :disabled="place >= screensaver.savedOrder.length - 1" :aria-label="T('later')" :title="T('later')" @click="screensaver.moveStep('clock', 1)"><Icon name="arrow-down" /></button>
    </div>
  </div>
</template>

<style scoped>
.face-picks { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.face-pick { display: grid; gap: 6px; justify-items: center; padding: 6px; border-radius: 10px; border: 1px solid var(--line); background: var(--surface);
  color: var(--ink-2); font: inherit; font-size: 12px; cursor: pointer; }
.face-pick[aria-checked="true"] { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); color: var(--ink); }
.face-pick:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.face-thumb { display: grid; place-items: center; width: 100%; max-height: 72px; border-radius: 4px; overflow: hidden; background: #000; }
.face-digital { color: #fff; font-size: 13px; font-weight: 300; font-variant-numeric: tabular-nums; }
.face-name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
</style>
