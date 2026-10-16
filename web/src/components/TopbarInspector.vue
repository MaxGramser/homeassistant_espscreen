<script setup lang="ts">

// The top bar of the selected page (app 0.4.89): the bar itself in small at the head (BarStrip), and under it only the
// part chosen in it: the title and Home button on the left, one item's settings, the things to add (the bar's +), an
// item's icons, or the copy onto other pages (the menu). The bar stays at the head whatever is under it and shows every
// choice on the item at once, so there is no list of items and no second head. On the right up to six items (more on a
// board that takes more): the time, an analog clock, the date, an entity's state or last change, the screen's own
// signal and battery, a plugin's item. Edits belong to the selected page.
import { computed, ref, watch } from "vue";
import { useSortableRows } from "../composables/useSortableRows";
import { t } from "../i18n";
import { entriesOf } from "../model/layout";
import { clockSample } from "../model/clock";
import { barLayout, glyph, itemKey } from "../model/topbar";
import type { HeaderItem } from "../types";
import BarStrip from "./BarStrip.vue";
import IconPicker from "./IconPicker.vue";
import IconChoices from "./IconChoices.vue";
import Segmented from "./Segmented.vue";
import TopbarAdd from "./TopbarAdd.vue";
import CopyPageBar from './CopyPageBar.vue';
import Icon from './ui/Icon.vue';
import InspectorHead from './ui/InspectorHead.vue';
import PropRow from './ui/PropRow.vue';
import UiMenu from './ui/UiMenu.vue';
import UiMenuItem from './ui/UiMenuItem.vue';
import PrecisionRow from './inspector/PrecisionRow.vue';
import { precisionOffered } from "../model/display-precision";
import { useUiStore } from "../stores/ui";
import { useRegionStore } from "../stores/region";
import { useEntitiesStore } from "../stores/entities";
import { useScreenStore } from "../stores/screen";
import { useTopbarStore } from "../stores/topbar";
import { useInventoryStore } from "../stores/inventory";
import { useCanvasStore } from "../stores/canvas";
import { pageTitleShown } from "../editor/pages";
import { useDocumentStore } from "../stores/document";
import { useInspectorStore } from "../stores/inspector";

const ui = useUiStore();
const region = useRegionStore();
const entities = useEntitiesStore();
const scr = useScreenStore();
const topbar = useTopbarStore();
const inv = useInventoryStore();
const canvas = useCanvasStore();
const doc = useDocumentStore();
const insp = useInspectorStore();
const { pageCount } = doc.editorLayout;

// `index` -1 is the left side; `adding` is the bar's + (the inspector's bar-add).
const props = defineProps<{ index: number; adding?: boolean }>();
const items = computed(() => sort.live.value || topbar.topbarItems());
const item = computed<HeaderItem | undefined>(() => (props.adding ? undefined : items.value[props.index]));
const lay = computed(() => {
  void ui.fontsVersion; void ui.now; void entities.topbarPreviews;
  return barLayout(items.value, canvas.barMetrics, pageTitleShown(page.value), topbar.topbarView);
});
const overflow = computed(() => lay.value.dropped);
const needed = computed(() => inv.inventory.header?.min_firmware || "0.2.32");
const supported = computed(() => scr.supportsVersion(needed.value));
// Why an item is hidden on the mockup: an entity that is off, a Wi-Fi item while the signal is good, the link mark while
// everything is connected (the screen's own items, firmware 0.38.0).
const hiddenText = (it: HeaderItem) => t(it.type === "wifi" ? "editor.topbar.detail.hidden_signal" : it.type === "link" ? "editor.topbar.detail.hidden_link"
  : it.type === "battery" ? "editor.topbar.detail.hidden_battery" : "editor.topbar.detail.hidden");
// The screen's own items need firmware 0.38.0; an older screen leaves them out of its bar.
const statusNeeded = computed(() => inv.inventory.header?.status_min_firmware || "0.38.0");
const statusSupported = computed(() => scr.supportsVersion(statusNeeded.value));
// The battery item needs firmware 0.41.0 (docs/BATTERY.md); an older screen leaves it out of its bar.
const batteryNeeded = computed(() => inv.inventory.header?.battery_min_firmware || "0.41.0");
const batterySupported = computed(() => scr.supportsVersion(batteryNeeded.value));
// The page whose bar you clicked (app 0.2.105). Its left side, the title and the Home key, belongs to the page and is
// set in the page's own settings (app 0.3.19); the left of the bar says what stands there and leads to them.
const page = computed(() => doc.barPage ?? 0);
const pages = computed(() => (doc.layout ? pageCount(entriesOf(doc.layout), doc.layout.pages) : 1));
const pageId = computed(() => doc.document?.pages[page.value]?.id);
const pageName = computed(() => t("editor.page.label", { page: page.value + 1 }));
const toPage = () => { if (pageId.value) insp.openPage(pageId.value); };
// Opened from the page's settings: the way back leads there, with the part of the page it left.
const back = computed(() => (insp.back?.kind === "page" ? { text: pageName.value, open: insp.goBack } : undefined));
const crumbs = computed(() => [{ text: pageName.value, open: pageId.value ? toPage : undefined }]);
// The copy onto other pages, chosen from the menu; another part chosen in the bar ends it.
const copying = ref(false);
watch(() => [props.index, props.adding], () => { copying.value = false; });
const canCopy = computed(() => Boolean(scr.pageReady && doc.document && pages.value > 1));
const selected = computed(() => (props.adding ? "add" : props.index >= 0 && item.value ? String(props.index) : "left"));
function choose(value: string) {
  copying.value = false;
  if (value === "add") { if (!props.adding) insp.openBarAdd(); }
  else insp.openBar(value === "left" ? -1 : Number(value));
}
function update(patch: Partial<HeaderItem>) {
  const list = [...items.value];
  list[props.index] = { ...list[props.index], ...patch };
  topbar.setTopbarItems(list);
}
// The line under the chosen part's name: where it stands, or why the screen doesn't show it right now.
const where = computed(() => {
  const it = item.value;
  if (!it) return "";
  if (!topbar.topbarView(it).shown) return hiddenText(it);
  if (overflow.value.has(props.index)) return t("editor.topbar.detail.overflow");
  return t("editor.topbar.strip.place", { place: props.index + 1, count: items.value.length });
});
const iconChoosing = computed(() => Boolean(insp.iconPickerOpen && item.value?.type === "entity" && !copying.value));
// A sensor's display precision: Home Assistant's own setting of the entity, which the bar writes its value with (not
// its icon alone, nor when it last changed).
const precisionShown = computed(() => item.value?.type === "entity" && (item.value.content || "state") === "state"
  && precisionOffered(item.value.entity || "", entities.liveOf(item.value.entity || "")));
const samples = computed(() => {
  const clock = clockSample(ui.now, region.clock24, region.screenLanguage);
  return { clock: clock.time, analog: t("editor.topbar.analog_sample"), date: clock.date } as Record<string, string>;
});
const itemGlyph = computed(() => (item.value ? topbar.topbarGlyph(item.value) : undefined));
const itemName = computed(() => (item.value ? (item.value.type === "entity" ? entities.entityName(item.value.entity!) : topbar.topbarLabel(item.value)) : ""));

// An item pressed in the bar and moved left or right takes the place it is over, mouse and touch (touch after a short
// hold); the inspector stays on it, and a finished drag is not a click (composables/useSortableRows.ts). Let go off the
// bar, it is taken off. The drawer that
// closes while an item is held (another tile chosen, Escape) lets go of the page, without a change.
const sort = useSortableRows<HeaderItem>({ rows: ".bar-strip .strip-item[data-index]", items: () => topbar.topbarItems(), commit: (list) => topbar.setTopbarItems(list),
  axis: "x", onMove: (from, to) => { if (props.index === from) insp.openBar(to); }, away: { from: "#topbar-chips", remove: (i) => topbar.removeTopbarItem(i) } });
const drag = sort.drag;
function move(step: number) { if (topbar.moveTopbarItem(props.index, props.index + step)) insp.openBar(props.index + step); }
</script>

<template>
  <!-- "Top bar" over the page's name: which bar this is. -->
  <InspectorHead kind="bar" :title="pageTitleShown(page) || pageName" icon="page-layout-header" :crumbs="crumbs" :back="back">
    <template #actions>
      <UiMenu width="240px">
        <template #trigger><button type="button" class="icon-btn" id="topbar-more" :aria-label="t('editor.screen_view.more')"><Icon name="dots-horizontal" /></button></template>
        <UiMenuItem v-if="canCopy" id="topbar-copy" icon="content-copy" @select="copying = true; insp.iconPickerOpen = false">{{ t("editor.topbar.strip.copy") }}</UiMenuItem>
        <UiMenuItem icon="view-column-outline" :disabled="!pageId" @select="toPage">{{ t("editor.topbar.strip.page_settings", { page: pageName }) }}</UiMenuItem>
      </UiMenu>
    </template>
  </InspectorHead>
  <div class="dr-body bar-body">
    <!-- The bar stays at the head while what is under it scrolls. -->
    <div class="bar-anchor">
      <div v-if="!scr.pageReady" class="notice warn"><Icon name="alert-circle-outline" /><span class="notice-text">{{ t('editor.pages.shared_bar') }}</span></div>
      <BarStrip id="topbar-chips" :items="items" :selected="copying ? '' : selected" :overflow="overflow" :title="pageTitleShown(page) || region.screenText('editor.mockup.home')"
        :home="topbar.homeKeyShown(page)" :full="items.length >= scr.topbarMax" :max="scr.topbarMax" :dragging="drag.active ? drag.index : -1" :leaving="drag.away"
        @select="choose" @press="(e, i) => sort.down(e, i)" @remove="topbar.removeTopbarItem" />
      <small v-if="overflow.size > 0 || !supported" id="topbar-hint" class="help warn">{{ supported ? t("editor.topbar.hint.overflow") : t("editor.topbar.hint.needs_firmware", { version: needed }) }}</small>
      <!-- What is chosen in the bar, named once. -->
      <div class="bar-cap" id="topbar-live">
        <span class="bar-cap-av">
          <Icon v-if="copying" name="content-copy" />
          <Icon v-else-if="adding" name="plus" />
          <span v-else-if="item && itemGlyph" class="mdi" aria-hidden="true">{{ glyph(itemGlyph) }}</span>
          <Icon v-else name="format-title" />
        </span>
        <span class="bar-cap-tx">
          <b>{{ copying ? t('editor.pages.copy_bar') : adding ? t('editor.topbar.add.title') : iconChoosing ? t('editor.icon.label') : item ? itemName : t('editor.topbar.strip.left_title') }}</b>
          <small :class="{ warn: item && overflow.has(index) }">{{ copying ? t('editor.topbar.strip.copy_hint') : adding ? t('editor.topbar.add.slots', { used: items.length }, scr.topbarMax)
            : iconChoosing ? itemName : item ? where : t('editor.topbar.strip.left_hint', { page: pageName }) }}</small>
        </span>
        <button v-if="iconChoosing || copying" type="button" class="btn quiet mini" id="topbar-done" @click="copying = false; insp.iconPickerOpen = false">{{ t('editor.common.done') }}</button>
      </div>
    </div>

    <div class="bar-part">
      <CopyPageBar v-if="copying && doc.document" :page-id="doc.document.pages[page].id" :foldable="false" />
      <TopbarAdd v-else-if="adding" />
      <!-- An item's icons in the place of its settings, the bar above showing each one picked. -->
      <IconChoices v-else-if="iconChoosing && item" :selected="item.icon || 'auto'" :automatic="entities.topbarPreviews[itemKey(item)]?.auto_icon || entities.automaticIcon(item.entity!)"
        :auto-label="t('editor.topbar.auto_icon')" :allow-none="item.content !== 'icon'" @pick="(n) => update({ icon: n })" />
      <template v-else-if="item">
        <template v-if="item.type === 'entity'">
          <PropRow :label="t('editor.topbar.content.label')" icon="eye-outline" :hint="t('editor.topbar.content.hint')" stack>
            <Segmented :choices="(inv.inventory.header?.contents || []).map((c) => [c.key, c.label] as [string, string])" :value="item.content" @pick="(v) => update(v === 'icon' && item!.icon === 'none' ? { content: v, icon: 'auto' } : { content: v })" />
          </PropRow>
          <!-- An item that shows its icon alone (GitHub #144) needs one, so it offers no "No icon". -->
          <IconPicker aside :selected="item.icon || 'auto'" :automatic="entities.topbarPreviews[itemKey(item)]?.auto_icon || entities.automaticIcon(item.entity!)" :auto-label="t('editor.topbar.auto_icon')" :allow-none="item.content !== 'icon'" @pick="(n) => update({ icon: n })" />
          <PropRow :label="t('editor.topbar.show.label')" icon="eye-outline" :hint="t('editor.topbar.show.hint')" stack>
            <Segmented :choices="(inv.inventory.header?.shows || []).map((s) => [s.key, s.label] as [string, string])" :value="item.show" @pick="(v) => update({ show: v })" />
          </PropRow>
          <PrecisionRow v-if="precisionShown" :entity="item.entity!" stack />
        </template>
        <!-- The screen's own Wi-Fi signal (firmware 0.38.0): what stands beside the bars, and when it shows. -->
        <template v-else-if="item.type === 'wifi'">
          <PropRow :label="t('editor.topbar.content.label')" icon="eye-outline" stack>
            <Segmented :choices="(inv.inventory.header?.wifi_contents || []).map((c) => [c.key, c.label] as [string, string])" :value="item.content || 'icon'" @pick="(v) => update({ content: v })" />
          </PropRow>
          <PropRow :label="t('editor.topbar.show.label')" icon="eye-outline" :hint="t('editor.topbar.wifi_show_hint')" stack>
            <Segmented :choices="(inv.inventory.header?.wifi_shows || []).map((s) => [s.key, s.label] as [string, string])" :value="item.show || 'always'" @pick="(v) => update({ show: v })" />
          </PropRow>
          <small class="help">{{ t("editor.topbar.wifi_hint") }}</small>
          <small v-if="!statusSupported" class="help warn">{{ t("editor.topbar.status_firmware", { version: statusNeeded }) }}</small>
        </template>
        <!-- The screen's own battery (firmware 0.41.0): the percentage beside Home Assistant's icon or not, and when it shows. -->
        <template v-else-if="item.type === 'battery'">
          <PropRow :label="t('editor.topbar.content.label')" icon="eye-outline" stack>
            <Segmented :choices="(inv.inventory.header?.battery_contents || []).map((c) => [c.key, c.label] as [string, string])" :value="item.content || 'icon'" @pick="(v) => update({ content: v })" />
          </PropRow>
          <PropRow :label="t('editor.topbar.show.label')" icon="eye-outline" :hint="t('editor.topbar.battery_show_hint')" stack>
            <Segmented :choices="(inv.inventory.header?.battery_shows || []).map((s) => [s.key, s.label] as [string, string])" :value="item.show || 'always'" @pick="(v) => update({ show: v })" />
          </PropRow>
          <small class="help">{{ t("editor.topbar.battery_hint") }}</small>
          <small v-if="!batterySupported" class="help warn">{{ t("editor.topbar.status_firmware", { version: batteryNeeded }) }}</small>
        </template>
        <template v-else-if="item.type === 'plugin'">
          <!-- Its icon and the words its plugin gives, or its icon alone (plugin API 0.8). -->
          <PropRow :label="t('editor.topbar.content.label')" icon="eye-outline" stack>
            <Segmented id="topbar-plugin-content" :choices="(inv.inventory.header?.plugin_contents || []).map((c) => [c.key, c.label] as [string, string])" :value="item.content || 'all'" @pick="(v) => update({ content: v })" />
          </PropRow>
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
      </template>
      <!-- The left side: the title and the Home button are the page's, set in its settings. -->
      <template v-else>
        <button type="button" class="nav-row" :disabled="!pageId" @click="toPage">
          <span class="tx"><b>{{ pageTitleShown(page) || region.screenText("editor.mockup.home") }}</b><small>{{ t('editor.topbar.left_hint') }}</small></span>
          <Icon name="chevron-right" class="nav-row-chevron" />
        </button>
        <small v-if="supported && !overflow.size" class="help">{{ t("editor.topbar.strip.hint") }}</small>
      </template>
    </div>
  </div>
  <div v-if="item && !iconChoosing && !copying" class="dr-foot">
    <button type="button" class="btn danger" @click="topbar.removeTopbarItem(index)"><Icon name="delete-outline" />{{ t("editor.common.remove") }}</button>
    <span class="spacer"></span>
    <div class="tool-group" role="group">
      <button type="button" class="icon-btn" :disabled="index === 0" :aria-label="t('editor.topbar.left_move')" :title="t('editor.topbar.left_move')" @click="move(-1)"><Icon name="chevron-left" /></button>
      <button type="button" class="icon-btn" :disabled="index >= items.length - 1" :aria-label="t('editor.topbar.right_move')" :title="t('editor.topbar.right_move')" @click="move(1)"><Icon name="chevron-right" /></button>
    </div>
  </div>
</template>
