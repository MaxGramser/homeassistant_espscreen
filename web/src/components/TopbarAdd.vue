<script setup lang="ts">
// Adding to the top bar: the screen's own items, then an entity (EntityItemPicker).
import { computed } from "vue";
import { t } from "../i18n";
import { clockSample } from "../model/clock";
import { BUILTIN_ICONS, glyph, itemKey, STATUS_CODES } from "../model/topbar";
import { addTopbarItem, clock24, closeInspector, currentScreen, iconNamed, openBar, screenLanguage, state, topbarItems, topbarMax } from "../store";
import type { HeaderItem } from "../types";
import EntityItemPicker from "./EntityItemPicker.vue";
import { barItemsFor, pluginsEnabled } from "../plugin-state";
import InspectorHead from "./ui/InspectorHead.vue";
import { useUiStore } from "../stores/ui";

const ui = useUiStore();

const taken = computed(() => new Set(topbarItems().map(itemKey)));
const clock = computed(() => clockSample(ui.now, clock24.value, screenLanguage.value));
const samples = computed(() => ({
  clock: clock.value.time,
  analog: t("editor.topbar.analog_sample"),
  date: clock.value.date,
  wifi: t("editor.topbar.wifi_sample"),
  link: t("editor.topbar.link_sample"),
  battery: t("editor.topbar.battery_sample"),
} as Record<string, string>));
// What adding a built-in item puts in the bar: the Wi-Fi signal and the battery start as their icon alone, always shown.
const builtinItem = (type: string): HeaderItem => (type === "wifi" || type === "battery" ? { type, content: "icon", show: "always" } : { type });
// The battery only on a screen that has one (firmware 0.41.0): its hello said so, or its board has one.
// The items of the plugins this screen runs (docs/PLUGINS.md).
const fromPlugins = computed(() => (pluginsEnabled.value ? barItemsFor(currentScreen.value) : []));
const pluginItem = (item: string): HeaderItem => ({ type: "plugin", item });
const builtins = computed(() => (state.inventory.header?.builtin || []).filter((b) => b.type !== "battery" || currentScreen.value?.battery));
</script>

<template>
  <InspectorHead kind="bar" :title="t('editor.topbar.add.title')" icon="plus"
    :crumbs="[{ text: t('editor.topbar.title'), open: () => openBar(-1) }, { text: t('editor.topbar.add.slots', { used: topbarItems().length }, topbarMax()) }]" />
  <div class="dr-body">
    <div class="f">
      <span class="f-label">{{ t("editor.topbar.add.builtin") }}</span>
      <div class="options">
        <button v-for="b in builtins" :key="b.type" type="button" class="option" :disabled="taken.has(itemKey(builtinItem(b.type)))" @click="addTopbarItem(builtinItem(b.type))">
          <span class="mdi">{{ glyph(STATUS_CODES[b.type] || iconNamed(BUILTIN_ICONS[b.type])?.cp || "F0150") }}</span>
          <span class="tx"><strong>{{ b.label }}</strong><small>{{ taken.has(itemKey(builtinItem(b.type))) ? t("editor.topbar.add.added") : samples[b.type] }}</small></span>
        </button>
      </div>
    </div>
 <div v-if="fromPlugins.length" class="f">
      <span class="f-label">{{ t("editor.topbar.add.plugins") }}</span>
      <div class="options">
        <button v-for="p in fromPlugins" :key="p.item" type="button" class="option" :disabled="taken.has(itemKey(pluginItem(p.item)))" @click="addTopbarItem(pluginItem(p.item))">
          <span class="mdi">{{ glyph(p.icon) }}</span>
          <span class="tx"><strong>{{ p.label }}</strong><small>{{ taken.has(itemKey(pluginItem(p.item))) ? t("editor.topbar.add.added") : p.example || p.plugin }}</small></span>
        </button>
      </div>
    </div>
    <EntityItemPicker id="topbar-search" :taken="(item) => taken.has(itemKey(item))" @pick="addTopbarItem" />
  </div>
  <div class="dr-foot">
    <span class="spacer"></span>
    <button type="button" class="btn quiet" @click="closeInspector">{{ t("editor.common.cancel") }}</button>
  </div>
</template>
