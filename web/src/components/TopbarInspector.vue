<script setup lang="ts">
import { editorLayout } from "../store";
const { pageCount } = editorLayout;

// The top bar: the name on the left; on the right up to six items: the time, an analog clock, the date, or an
// entity's state or last change. Edits belong to the selected page.
import { computed } from "vue";
import { useSortableRows } from "../composables/useSortableRows";
import { t } from "../i18n";
import { beginFieldEdit, endFieldEdit } from '../store';
import { entriesOf } from "../model/layout";
import { clockSample } from "../model/clock";
import { barLayout, BUILTIN_ICONS, glyph, itemKey, STATUS_CODES } from "../model/topbar";
import { barMetrics, openBar, openBarAdd, openPage, state, pageTitleShown } from "../store";
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
import { useUiStore } from "../stores/ui";
import { useRegionStore } from "../stores/region";
import { useEntitiesStore } from "../stores/entities";
import { useScreenStore } from "../stores/screen";
import { useTopbarStore } from "../stores/topbar";
import { useInventoryStore } from "../stores/inventory";

const ui = useUiStore();
const region = useRegionStore();
const entities = useEntitiesStore();
const scr = useScreenStore();
const topbar = useTopbarStore();
const inv = useInventoryStore();

const props = defineProps<{ index: number }>();
const items = computed(() => sort.live.value || topbar.topbarItems());
const item = computed<HeaderItem | undefined>(() => items.value[props.index]);
const lay = computed(() => {
  void ui.fontsVersion; void ui.now; void entities.topbarPreviews;
  return barLayout(items.value, barMetrics.value, pageTitleShown(page.value), topbar.topbarView);
});
const overflow = computed(() => lay.value.dropped);
const needed = computed(() => inv.inventory.header?.min_firmware || "0.2.32");
const supported = computed(() => scr.supportsVersion(needed.value));
const hint = computed(() => supported.value
  ? t(overflow.value.size ? "editor.topbar.hint.overflow" : "editor.topbar.hint.reorder")
  : t("editor.topbar.hint.needs_firmware", { version: needed.value }));
// Why an item is hidden on the mockup: an entity that is off, a Wi-Fi item while the signal is good, the link mark while
// everything is connected (the screen's own items, firmware 0.38.0).
const hiddenText = (it: HeaderItem) => t(it.type === "wifi" ? "editor.topbar.detail.hidden_signal" : it.type === "link" ? "editor.topbar.detail.hidden_link"
  : it.type === "battery" ? "editor.topbar.detail.hidden_battery" : "editor.topbar.detail.hidden");
const detail = (it: HeaderItem, i: number) => {
  const view = topbar.topbarView(it);
  return !view.shown ? hiddenText(it) : overflow.value.has(i) ? t("editor.topbar.detail.overflow") : view.analog ? t("editor.topbar.detail.dial") : view.text || topbar.topbarLabel(it);
};
const iconOf = (it: HeaderItem) => {
  const view = topbar.topbarView(it);
  if (STATUS_CODES[it.type]) return view.icon || STATUS_CODES[it.type];
  return view.analog || it.type !== "entity" ? entities.iconNamed(BUILTIN_ICONS[it.type])?.cp : view.icon;
};
// The screen's own items need firmware 0.38.0; an older screen leaves them out of its bar.
const statusNeeded = computed(() => inv.inventory.header?.status_min_firmware || "0.38.0");
const statusSupported = computed(() => scr.supportsVersion(statusNeeded.value));
// The battery item needs firmware 0.41.0 (docs/BATTERY.md); an older screen leaves it out of its bar.
const batteryNeeded = computed(() => inv.inventory.header?.battery_min_firmware || "0.41.0");
const batterySupported = computed(() => scr.supportsVersion(batteryNeeded.value));
const justAdded = (it: HeaderItem) => topbar.topbarAdded?.key === itemKey(it) && Date.now() - topbar.topbarAdded.time < 1200;
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
  topbar.setTopbarItems(list);
}
const liveNote = computed(() => {
  if (!item.value) return "";
  const view = topbar.topbarView(item.value);
  return !view.shown ? (item.value.type === "entity" ? t("editor.topbar.live.hidden") : hiddenText(item.value)) : overflow.value.has(props.index) ? t("editor.topbar.live.overflow") : t("editor.topbar.live.looks");
});
const samples = computed(() => {
  const clock = clockSample(ui.now, region.clock24, region.screenLanguage);
  return { clock: clock.time, analog: t("editor.topbar.analog_sample"), date: clock.date } as Record<string, string>;
});

// Pointer drag between the rows, mouse and touch (touch after a short hold, so the list still scrolls). The order
// updates while dragging, the mockup follows, and a finished drag is not a click (composables/useSortableRows.ts). The
// drawer that closes while an item is held (another tile chosen, Escape) lets go of the page, without a change.
const sort = useSortableRows<HeaderItem>({ rows: ".items .item[data-index]", items: () => topbar.topbarItems(), commit: (list) => topbar.setTopbarItems(list), skip: ".x",
  onMove: (from, to) => { if (props.index === from) openBar(to); } });
const drag = sort.drag;
function pick(e: MouseEvent, i: number) {
  if (sort.click(e)) return;
  openBar(i);
}
function onKey(e: KeyboardEvent, i: number) {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openBar(i); return; }
  const step = ({ ArrowUp: -1, ArrowDown: 1 } as Record<string, number>)[e.key];
  if (step && topbar.moveTopbarItem(i, i + step)) { if (props.index === i) openBar(i + step); e.preventDefault(); }
}
</script>

<template>
  <InspectorHead kind="bar" :title="item ? (item.type === 'entity' ? entities.entityName(item.entity!) : topbar.topbarLabel(item)) : t('editor.topbar.title')"
    :code="item ? iconOf(item) || 'F0150' : undefined" :icon="item ? undefined : 'page-layout-header'" :crumbs="crumbs" />
  <div class="dr-body">
    <div v-if="!scr.pageReady" class="notice warn"><Icon name="alert-circle-outline" /><span class="notice-text">{{ t('editor.pages.shared_bar') }}</span></div>

    <Section :title="t('editor.topbar.left')" icon="format-title">
      <button type="button" class="nav-row" :disabled="!pageId" @click="toPage">
        <TesseraMark v-if="topbar.homeKeyShown(page)" class="nav-row-lead" />
        <span class="tx"><b>{{ pageTitleShown(page) || region.screenText("editor.mockup.home") }}</b><small>{{ t('editor.topbar.left_hint') }}</small></span>
        <Icon name="chevron-right" class="nav-row-chevron" />
      </button>
    </Section>

    <Section :title="t('editor.topbar.right')" icon="format-list-bulleted" :aside="`${items.length} / ${scr.topbarMax}`" :hint="overflow.size > 0 || !supported ? undefined : hint">
      <div class="items" id="topbar-chips" role="list" :aria-label="t('editor.topbar.right')">
        <div v-for="(it, i) in items" :key="itemKey(it) + i" class="item" role="listitem" tabindex="0" :data-index="i"
          :class="{ selected: i === index, 'is-hidden': !topbar.topbarView(it).shown, 'is-overflow': overflow.has(i), 'just-added': justAdded(it), 'dragging-chip': drag.active && drag.index === i }"
          :aria-label="t('editor.topbar.item_label', { name: topbar.topbarLabel(it), slot: i + 1 })"
          @pointerdown="sort.down($event, i)" @click="pick($event, i)" @keydown="onKey($event, i)">
          <Icon name="drag-vertical" class="grip" />
          <span class="av mdi" :style="topbar.topbarView(it).color ? { color: topbar.topbarView(it).color! } : undefined">{{ iconOf(it) ? glyph(iconOf(it)!) : "" }}</span>
          <span class="tx"><b>{{ topbar.topbarLabel(it) }}</b><small>{{ detail(it, i) }}</small></span>
          <button type="button" class="x" :aria-label="t('editor.topbar.remove_named', { name: topbar.topbarLabel(it) })" @click.stop="topbar.removeTopbarItem(i)"><Icon name="close" /></button>
        </div>
        <button type="button" class="ghost-btn" id="topbar-add" :disabled="items.length >= scr.topbarMax" :title="items.length >= scr.topbarMax ? t('editor.topbar.max', scr.topbarMax) : t('editor.topbar.add_title')" @click="openBarAdd"><Icon name="plus" />{{ t("editor.topbar.add_button") }}</button>
      </div>
      <small v-if="overflow.size > 0 || !supported" id="topbar-hint" class="help warn">{{ hint }}</small>
    </Section>

    <Section v-if="item" :title="topbar.topbarLabel(item)" icon="tune-variant">
      <div class="live" id="topbar-live">
        <small>{{ liveNote }}</small>
        <TopbarSvg :items="[item]" single />
      </div>
      <template v-if="item.type === 'entity'">
        <div class="f">
          <span class="f-label">{{ t("editor.topbar.content.label") }}<HelpTip :text="t('editor.topbar.content.hint')" /></span>
          <Segmented :choices="(inv.inventory.header?.contents || []).map((c) => [c.key, c.label] as [string, string])" :value="item.content" @pick="(v) => update(v === 'icon' && item!.icon === 'none' ? { content: v, icon: 'auto' } : { content: v })" />
        </div>
        <!-- An item that shows its icon alone (GitHub #144) needs one, so it offers no "No icon". -->
        <IconPicker :selected="item.icon || 'auto'" :automatic="entities.topbarPreviews[itemKey(item)]?.auto_icon || entities.automaticIcon(item.entity!)" :auto-label="t('editor.topbar.auto_icon')" :allow-none="item.content !== 'icon'" @pick="(n) => update({ icon: n })" />
        <div class="f">
          <span class="f-label">{{ t("editor.topbar.show.label") }}<HelpTip :text="t('editor.topbar.show.hint')" /></span>
          <Segmented :choices="(inv.inventory.header?.shows || []).map((s) => [s.key, s.label] as [string, string])" :value="item.show" @pick="(v) => update({ show: v })" />
        </div>
      </template>
      <!-- The screen's own Wi-Fi signal (firmware 0.38.0): what stands beside the bars, and when it shows. -->
      <template v-else-if="item.type === 'wifi'">
        <div class="f">
          <span class="f-label">{{ t("editor.topbar.content.label") }}</span>
          <Segmented :choices="(inv.inventory.header?.wifi_contents || []).map((c) => [c.key, c.label] as [string, string])" :value="item.content || 'icon'" @pick="(v) => update({ content: v })" />
        </div>
        <div class="f">
          <span class="f-label">{{ t("editor.topbar.show.label") }}<HelpTip :text="t('editor.topbar.wifi_show_hint')" /></span>
          <Segmented :choices="(inv.inventory.header?.wifi_shows || []).map((s) => [s.key, s.label] as [string, string])" :value="item.show || 'always'" @pick="(v) => update({ show: v })" />
        </div>
        <small class="help">{{ t("editor.topbar.wifi_hint") }}</small>
        <small v-if="!statusSupported" class="help warn">{{ t("editor.topbar.status_firmware", { version: statusNeeded }) }}</small>
      </template>
      <!-- The screen's own battery (firmware 0.41.0): the percentage beside Home Assistant's icon or not, and when it shows. -->
      <template v-else-if="item.type === 'battery'">
        <div class="f">
          <span class="f-label">{{ t("editor.topbar.content.label") }}</span>
          <Segmented :choices="(inv.inventory.header?.battery_contents || []).map((c) => [c.key, c.label] as [string, string])" :value="item.content || 'icon'" @pick="(v) => update({ content: v })" />
        </div>
        <div class="f">
          <span class="f-label">{{ t("editor.topbar.show.label") }}<HelpTip :text="t('editor.topbar.battery_show_hint')" /></span>
          <Segmented :choices="(inv.inventory.header?.battery_shows || []).map((s) => [s.key, s.label] as [string, string])" :value="item.show || 'always'" @pick="(v) => update({ show: v })" />
        </div>
        <small class="help">{{ t("editor.topbar.battery_hint") }}</small>
        <small v-if="!batterySupported" class="help warn">{{ t("editor.topbar.status_firmware", { version: batteryNeeded }) }}</small>
      </template>
      <template v-else-if="item.type === 'plugin'">
        <!-- Its icon and the words its plugin gives, or its icon alone (plugin API 0.8). -->
        <div class="f">
          <span class="f-label">{{ t("editor.topbar.content.label") }}</span>
          <Segmented id="topbar-plugin-content" :choices="(inv.inventory.header?.plugin_contents || []).map((c) => [c.key, c.label] as [string, string])" :value="item.content || 'all'" @pick="(v) => update({ content: v })" />
        </div>
        <p class="help" id="topbar-plugin">{{ t("editor.topbar.plugin_item") }}</p>
      </template>
      <template v-else-if="item.type === 'link'">
        <small class="help">{{ t("editor.topbar.link_hint") }}</small>
        <small v-if="!statusSupported" class="help warn">{{ t("editor.topbar.status_firmware", { version: statusNeeded }) }}</small>
      </template>
      <!-- The clock's format is one choice for every screen, under Settings → Language & region (app 0.2.90). -->
      <i18n-t v-else-if="item.type !== 'date'" :keypath="region.clock24 ? 'editor.topbar.clock_24' : 'editor.topbar.clock_12'" tag="small" id="topbar-clock" class="help" scope="global">
        <template #settings><a href="#settings">{{ t("editor.topbar.clock_settings") }}</a></template>
      </i18n-t>
      <small v-else class="help">{{ t("editor.topbar.date_hint", { date: samples.date }) }}</small>
    </Section>

    <CopyPageBar v-if="scr.pageReady && state.document && pages > 1" :page-id="state.document.pages[page].id" />
  </div>
  <div v-if="item" class="dr-foot">
    <button type="button" class="btn danger" @click="topbar.removeTopbarItem(index)"><Icon name="delete-outline" />{{ t("editor.common.remove") }}</button>
    <span class="spacer"></span>
    <div class="tool-group" role="group">
      <button type="button" class="icon-btn" :disabled="index === 0" :aria-label="t('editor.topbar.up')" :title="t('editor.topbar.up')" @click="topbar.moveTopbarItem(index, index - 1) && openBar(index - 1)"><Icon name="arrow-up" /></button>
      <button type="button" class="icon-btn" :disabled="index >= items.length - 1" :aria-label="t('editor.topbar.down')" :title="t('editor.topbar.down')" @click="topbar.moveTopbarItem(index, index + 1) && openBar(index + 1)"><Icon name="arrow-down" /></button>
    </div>
  </div>
</template>
