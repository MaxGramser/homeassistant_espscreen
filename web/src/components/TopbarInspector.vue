<script setup lang="ts">
import { editorLayout } from "../store";
const { pageCount } = editorLayout;

// The top bar: the name on the left; on the right up to six items: the time, an analog clock, the date, or an
// entity's state or last change. Edits belong to the selected page.
import { computed, ref } from "vue";
import { t } from "../i18n";
import { beginFieldEdit, endFieldEdit } from '../store';
import { entriesOf } from "../model/layout";
import { barLayout, BUILTIN_ICONS, clockText, dateText, glyph, itemKey, STATUS_CODES } from "../model/topbar";
import {
  automaticIcon, barMetrics, clock24, entityName, homeKeyShown, iconNamed, moveTopbarItem, openBar, openBarAdd, openPage,
  removeTopbarItem, screenLanguage, screenText, setTopbarItems, state, supports, topbarItems, topbarLabel, topbarMax, topbarView,
  pageTitleShown, pageReady,
} from "../store";
import type { HeaderItem } from "../types";
import IconPicker from "./IconPicker.vue";
import Segmented from "./Segmented.vue";
import TopbarSvg from "./TopbarSvg.vue";
import TesseraMark from "./TesseraMark.vue";
import CopyPageBar from './CopyPageBar.vue';
import Icon from './ui/Icon.vue';
import InspectorHead from './ui/InspectorHead.vue';
import Section from './ui/Section.vue';
import HelpTip from './HelpTip.vue';

const props = defineProps<{ index: number }>();
const draggedItems = ref<HeaderItem[] | null>(null);
const items = computed(() => draggedItems.value || topbarItems());
const item = computed<HeaderItem | undefined>(() => items.value[props.index]);
const lay = computed(() => {
  void state.fontsVersion; void state.now; void state.topbarPreviews;
  return barLayout(items.value, barMetrics.value, pageTitleShown(page.value), topbarView);
});
const overflow = computed(() => lay.value.dropped);
const needed = computed(() => state.inventory.header?.min_firmware || "0.2.32");
const supported = computed(() => { const [a, b, c] = needed.value.split(".").map(Number); return supports(a, b, c); });
const hint = computed(() => supported.value
  ? t(overflow.value.size ? "editor.topbar.hint.overflow" : "editor.topbar.hint.reorder")
  : t("editor.topbar.hint.needs_firmware", { version: needed.value }));
// Why an item is hidden on the mockup: an entity that is off, a Wi-Fi item while the signal is good, the link mark while
// everything is connected (the screen's own items, firmware 0.38.0).
const hiddenText = (it: HeaderItem) => t(it.type === "wifi" ? "editor.topbar.detail.hidden_signal" : it.type === "link" ? "editor.topbar.detail.hidden_link"
  : it.type === "battery" ? "editor.topbar.detail.hidden_battery" : "editor.topbar.detail.hidden");
const detail = (it: HeaderItem, i: number) => {
  const view = topbarView(it);
  return !view.shown ? hiddenText(it) : overflow.value.has(i) ? t("editor.topbar.detail.overflow") : view.analog ? t("editor.topbar.detail.dial") : view.text || topbarLabel(it);
};
const iconOf = (it: HeaderItem) => {
  const view = topbarView(it);
  if (STATUS_CODES[it.type]) return view.icon || STATUS_CODES[it.type];
  return view.analog || it.type !== "entity" ? iconNamed(BUILTIN_ICONS[it.type])?.cp : view.icon;
};
// The screen's own items need firmware 0.38.0; an older screen leaves them out of its bar.
const statusNeeded = computed(() => state.inventory.header?.status_min_firmware || "0.38.0");
const statusSupported = computed(() => { const [a, b, c] = statusNeeded.value.split(".").map(Number); return supports(a, b, c); });
// The battery item needs firmware 0.41.0 (docs/BATTERY.md); an older screen leaves it out of its bar.
const batteryNeeded = computed(() => state.inventory.header?.battery_min_firmware || "0.41.0");
const batterySupported = computed(() => { const [a, b, c] = batteryNeeded.value.split(".").map(Number); return supports(a, b, c); });
const justAdded = (it: HeaderItem) => state.topbarAdded?.key === itemKey(it) && Date.now() - state.topbarAdded.time < 1200;
// The page whose bar you clicked (app 0.2.105). Its left side, the title and the Home key, belongs to the page and is
// set in the page's own settings (app 0.3.19); this inspector is about what stands on the right.
const page = computed(() => state.barPage ?? 0);
const pages = computed(() => (state.layout ? pageCount(entriesOf(state.layout), state.layout.pages) : 1));
const pageId = computed(() => state.document?.pages[page.value]?.id);
const toPage = () => { if (pageId.value) openPage(pageId.value); };
const crumbs = computed(() => [
  { text: t("editor.page.label", { page: page.value + 1 }), open: pageId.value ? toPage : undefined },
  ...(item.value ? [{ text: t("editor.topbar.title"), open: () => openBar(-1) }] : []),
]);
function update(patch: Partial<HeaderItem>) {
  const list = [...items.value];
  list[props.index] = { ...list[props.index], ...patch };
  setTopbarItems(list);
}
const liveNote = computed(() => {
  if (!item.value) return "";
  const view = topbarView(item.value);
  return !view.shown ? (item.value.type === "entity" ? t("editor.topbar.live.hidden") : hiddenText(item.value)) : overflow.value.has(props.index) ? t("editor.topbar.live.overflow") : t("editor.topbar.live.looks");
});
const samples = computed(() => ({
  clock: clockText(clock24.value, new Date(state.now), screenLanguage.value),
  analog: t("editor.topbar.analog_sample"),
  date: dateText(new Date(state.now), screenLanguage.value),
} as Record<string, string>));

// Pointer drag between the rows, mouse and touch (touch after a short hold, so the list still scrolls). The order
// updates while dragging, the mockup follows, and a finished drag is not a click.
const drag = ref({ index: -1, active: false, moved: false });
let start: { x: number; y: number } | null = null, timer = 0, pointerId: number | null = null, suppressUntil = 0;
function down(e: PointerEvent, i: number) {
  if (e.button !== 0 || (e.target as HTMLElement).closest(".x")) return;
  if (e.pointerType !== "touch") e.preventDefault();
  drag.value = { index: i, active: false, moved: false };
  start = { x: e.clientX, y: e.clientY };
  pointerId = e.pointerId;
  clearTimeout(timer);
  if (e.pointerType === "touch") timer = window.setTimeout(begin, 260);
  document.addEventListener("pointermove", move);
  document.addEventListener("pointerup", end);
  document.addEventListener("pointercancel", end);
}
function begin() {
  drag.value.active = true;
  document.addEventListener("touchmove", block, { passive: false });
}
function block(e: TouchEvent) { if (drag.value.active) e.preventDefault(); }
function move(e: PointerEvent) {
  if (e.pointerId !== pointerId || !start) return;
  if (!drag.value.active) {
    const distance = Math.hypot(e.clientX - start.x, e.clientY - start.y);
    if (e.pointerType === "touch") { if (distance > 10) { clearTimeout(timer); start = null; } return; }
    if (distance < 6) return;
    begin();
  }
  // The target is the row whose middle the pointer passed.
  const rows = [...document.querySelectorAll<HTMLElement>(".items .item[data-index]")];
  let target = drag.value.index;
  rows.forEach((row, i) => {
    const r = row.getBoundingClientRect();
    if (i < drag.value.index && e.clientY < r.top + r.height / 2) target = Math.min(target, i);
    if (i > drag.value.index && e.clientY > r.top + r.height / 2) target = Math.max(target, i);
  });
  if (target !== drag.value.index && state.layout) {
    const list = [...items.value];
    list.splice(target, 0, ...list.splice(drag.value.index, 1));
    draggedItems.value = list;
    const selectedMoved = props.index === drag.value.index;
    drag.value.index = target;
    drag.value.moved = true;
    if (selectedMoved) openBar(target);
  }
}
function end(e: PointerEvent) {
  if (e.pointerId !== pointerId) return;
  clearTimeout(timer);
  document.removeEventListener("pointermove", move);
  document.removeEventListener("pointerup", end);
  document.removeEventListener("pointercancel", end);
  document.removeEventListener("touchmove", block);
  if (drag.value.active) {
    suppressUntil = Date.now() + 400;
    if (drag.value.moved && e.type !== "pointercancel" && draggedItems.value) setTopbarItems(draggedItems.value);
  }
  draggedItems.value = null;
  drag.value = { index: -1, active: false, moved: false };
  start = null; pointerId = null;
}
function pick(i: number) {
  if (Date.now() < suppressUntil) return;
  openBar(i);
}
function onKey(e: KeyboardEvent, i: number) {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openBar(i); return; }
  const step = ({ ArrowUp: -1, ArrowDown: 1 } as Record<string, number>)[e.key];
  if (step && moveTopbarItem(i, i + step)) { if (props.index === i) openBar(i + step); e.preventDefault(); }
}
</script>

<template>
  <InspectorHead kind="bar" :title="item ? (item.type === 'entity' ? entityName(item.entity!) : topbarLabel(item)) : t('editor.topbar.title')"
    :code="item ? iconOf(item) || 'F0150' : undefined" :icon="item ? undefined : 'page-layout-header'" :crumbs="crumbs" />
  <div class="dr-body">
    <div v-if="!pageReady" class="notice warn"><Icon name="alert-circle-outline" /><span class="notice-text">{{ t('editor.pages.shared_bar') }}</span></div>

    <Section :title="t('editor.topbar.left')" icon="format-title">
      <button type="button" class="nav-row" :disabled="!pageId" @click="toPage">
        <TesseraMark v-if="homeKeyShown(page)" class="nav-row-lead" />
        <span class="tx"><b>{{ pageTitleShown(page) || screenText("editor.mockup.home") }}</b><small>{{ t('editor.topbar.left_hint') }}</small></span>
        <Icon name="chevron-right" class="nav-row-chevron" />
      </button>
    </Section>

    <Section :title="t('editor.topbar.right')" icon="format-list-bulleted" :aside="`${items.length} / ${topbarMax()}`" :hint="overflow.size > 0 || !supported ? undefined : hint">
      <div class="items" id="topbar-chips" role="list" :aria-label="t('editor.topbar.right')">
        <div v-for="(it, i) in items" :key="itemKey(it) + i" class="item" role="listitem" tabindex="0" :data-index="i"
          :class="{ selected: i === index, 'is-hidden': !topbarView(it).shown, 'is-overflow': overflow.has(i), 'just-added': justAdded(it), 'dragging-chip': drag.active && drag.index === i }"
          :aria-label="t('editor.topbar.item_label', { name: topbarLabel(it), slot: i + 1 })"
          @pointerdown="down($event, i)" @click="pick(i)" @keydown="onKey($event, i)">
          <Icon name="drag-vertical" class="grip" />
          <span class="av mdi" :style="topbarView(it).color ? { color: topbarView(it).color! } : undefined">{{ iconOf(it) ? glyph(iconOf(it)!) : "" }}</span>
          <span class="tx"><b>{{ topbarLabel(it) }}</b><small>{{ detail(it, i) }}</small></span>
          <button type="button" class="x" :aria-label="t('editor.topbar.remove_named', { name: topbarLabel(it) })" @click.stop="removeTopbarItem(i)"><Icon name="close" /></button>
        </div>
        <button type="button" class="ghost-btn" id="topbar-add" :disabled="items.length >= topbarMax()" :title="items.length >= topbarMax() ? t('editor.topbar.max', topbarMax()) : t('editor.topbar.add_title')" @click="openBarAdd"><Icon name="plus" />{{ t("editor.topbar.add_button") }}</button>
      </div>
      <small v-if="overflow.size > 0 || !supported" id="topbar-hint" class="help warn">{{ hint }}</small>
    </Section>

    <Section v-if="item" :title="topbarLabel(item)" icon="tune-variant">
      <div class="live" id="topbar-live">
        <small>{{ liveNote }}</small>
        <TopbarSvg :items="[item]" single />
      </div>
      <template v-if="item.type === 'entity'">
        <div class="f">
          <span class="f-label">{{ t("editor.topbar.content.label") }}<HelpTip :text="t('editor.topbar.content.hint')" /></span>
          <Segmented :choices="(state.inventory.header?.contents || []).map((c) => [c.key, c.label] as [string, string])" :value="item.content" @pick="(v) => update(v === 'icon' && item!.icon === 'none' ? { content: v, icon: 'auto' } : { content: v })" />
        </div>
        <!-- An item that shows its icon alone (GitHub #144) needs one, so it offers no "No icon". -->
        <IconPicker :selected="item.icon || 'auto'" :automatic="state.topbarPreviews[itemKey(item)]?.auto_icon || automaticIcon(item.entity!)" :auto-label="t('editor.topbar.auto_icon')" :allow-none="item.content !== 'icon'" @pick="(n) => update({ icon: n })" />
        <div class="f">
          <span class="f-label">{{ t("editor.topbar.show.label") }}<HelpTip :text="t('editor.topbar.show.hint')" /></span>
          <Segmented :choices="(state.inventory.header?.shows || []).map((s) => [s.key, s.label] as [string, string])" :value="item.show" @pick="(v) => update({ show: v })" />
        </div>
      </template>
      <!-- The screen's own Wi-Fi signal (firmware 0.38.0): what stands beside the bars, and when it shows. -->
      <template v-else-if="item.type === 'wifi'">
        <div class="f">
          <span class="f-label">{{ t("editor.topbar.content.label") }}</span>
          <Segmented :choices="(state.inventory.header?.wifi_contents || []).map((c) => [c.key, c.label] as [string, string])" :value="item.content || 'icon'" @pick="(v) => update({ content: v })" />
        </div>
        <div class="f">
          <span class="f-label">{{ t("editor.topbar.show.label") }}<HelpTip :text="t('editor.topbar.wifi_show_hint')" /></span>
          <Segmented :choices="(state.inventory.header?.wifi_shows || []).map((s) => [s.key, s.label] as [string, string])" :value="item.show || 'always'" @pick="(v) => update({ show: v })" />
        </div>
        <small class="help">{{ t("editor.topbar.wifi_hint") }}</small>
        <small v-if="!statusSupported" class="help warn">{{ t("editor.topbar.status_firmware", { version: statusNeeded }) }}</small>
      </template>
      <!-- The screen's own battery (firmware 0.41.0): the percentage beside Home Assistant's icon or not, and when it shows. -->
      <template v-else-if="item.type === 'battery'">
        <div class="f">
          <span class="f-label">{{ t("editor.topbar.content.label") }}</span>
          <Segmented :choices="(state.inventory.header?.battery_contents || []).map((c) => [c.key, c.label] as [string, string])" :value="item.content || 'icon'" @pick="(v) => update({ content: v })" />
        </div>
        <div class="f">
          <span class="f-label">{{ t("editor.topbar.show.label") }}<HelpTip :text="t('editor.topbar.battery_show_hint')" /></span>
          <Segmented :choices="(state.inventory.header?.battery_shows || []).map((s) => [s.key, s.label] as [string, string])" :value="item.show || 'always'" @pick="(v) => update({ show: v })" />
        </div>
        <small class="help">{{ t("editor.topbar.battery_hint") }}</small>
        <small v-if="!batterySupported" class="help warn">{{ t("editor.topbar.status_firmware", { version: batteryNeeded }) }}</small>
      </template>
      <template v-else-if="item.type === 'link'">
        <small class="help">{{ t("editor.topbar.link_hint") }}</small>
        <small v-if="!statusSupported" class="help warn">{{ t("editor.topbar.status_firmware", { version: statusNeeded }) }}</small>
      </template>
      <!-- The clock's format is one choice for every screen, under Settings → Language & region (app 0.2.90). -->
      <i18n-t v-else-if="item.type !== 'date'" :keypath="clock24 ? 'editor.topbar.clock_24' : 'editor.topbar.clock_12'" tag="small" id="topbar-clock" class="help" scope="global">
        <template #settings><a href="#settings">{{ t("editor.topbar.clock_settings") }}</a></template>
      </i18n-t>
      <small v-else class="help">{{ t("editor.topbar.date_hint", { date: samples.date }) }}</small>
    </Section>

    <CopyPageBar v-if="pageReady && state.document && pages > 1" :page-id="state.document.pages[page].id" />
  </div>
  <div v-if="item" class="dr-foot">
    <button type="button" class="btn danger" @click="removeTopbarItem(index)"><Icon name="delete-outline" />{{ t("editor.common.remove") }}</button>
    <span class="spacer"></span>
    <div class="tool-group" role="group">
      <button type="button" class="icon-btn" :disabled="index === 0" :aria-label="t('editor.topbar.up')" :title="t('editor.topbar.up')" @click="moveTopbarItem(index, index - 1) && openBar(index - 1)"><Icon name="arrow-up" /></button>
      <button type="button" class="icon-btn" :disabled="index >= items.length - 1" :aria-label="t('editor.topbar.down')" :title="t('editor.topbar.down')" @click="moveTopbarItem(index, index + 1) && openBar(index + 1)"><Icon name="arrow-down" /></button>
    </div>
  </div>
</template>
