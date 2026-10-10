<script setup lang="ts">
// One entity on the screensaver's clock (app 0.4.81): its name and what it shows, in the top bar's drawer. Text, icon or
// both; the screensaver draws it black and white, so there is no colour to choose.
import { computed } from "vue";
import { t } from "../i18n";
import { glyph, itemKey } from "../model/topbar";
import { openSaverItem } from "../store";
import IconPicker from "./IconPicker.vue";
import Segmented from "./Segmented.vue";
import Icon from "./ui/Icon.vue";
import InspectorHead from "./ui/InspectorHead.vue";
import Section from "./ui/Section.vue";
import { useEntitiesStore } from "../stores/entities";
import { useTopbarStore } from "../stores/topbar";
import { useScreensaverStore } from "../stores/screensaver";

const entities = useEntitiesStore();
const topbar = useTopbarStore();
const screensaver = useScreensaverStore();

const props = defineProps<{ index: number }>();
const items = computed(() => screensaver.saverItems);
const item = computed(() => items.value[props.index]);
const view = computed(() => (item.value ? topbar.topbarView(item.value) : null));
// Three looks of one item: its text alone, its icon alone, or the icon and the text.
const look = computed(() => (!item.value ? "both" : item.value.content === "icon" ? "icon" : item.value.icon === "none" ? "text" : "both"));
const choices: [string, string][] = [["text", t("editor.screen_settings.screensaver.item_text")], ["icon", t("editor.screen_settings.screensaver.item_icon")], ["both", t("editor.screen_settings.screensaver.item_both")]];
const kept = computed(() => (item.value && item.value.icon && item.value.icon !== "none" ? item.value.icon : "auto"));
function pick(value: string) {
  if (value === "text") screensaver.updateSaverItem(props.index, { content: "state", icon: "none" });
  else screensaver.updateSaverItem(props.index, { content: value === "icon" ? "icon" : "state", icon: kept.value });
}
const crumbs = computed(() => [screensaver.clockCrumb()]);
</script>

<template>
  <InspectorHead v-if="item" kind="bar" :title="entities.entityName(item.entity!)" :code="view?.icon || entities.automaticIcon(item.entity!)" :crumbs="crumbs" />
  <div v-if="item" class="dr-body">
    <Section :title="t('editor.screen_settings.screensaver.item_look')" icon="tune-variant">
      <div class="live saver-live" id="saver-item-live">
        <span class="mdi" v-if="view?.icon && look !== 'text'">{{ glyph(view.icon) }}</span>
        <span v-if="look !== 'icon'">{{ view?.text }}</span>
      </div>
      <Segmented :choices="choices" :value="look" @pick="pick" />
      <IconPicker v-if="look !== 'text'" :selected="item.icon || 'auto'" :automatic="entities.topbarPreviews[itemKey(item)]?.auto_icon || entities.automaticIcon(item.entity!)"
        :auto-label="t('editor.topbar.auto_icon')" :allow-none="false" @pick="(n) => screensaver.updateSaverItem(index, { icon: n })" />
      <small class="help">{{ t("editor.screen_settings.screensaver.item_hint") }}</small>
    </Section>
  </div>
  <div v-if="item" class="dr-foot">
    <button type="button" class="btn danger" @click="screensaver.removeSaverItem(index)"><Icon name="delete-outline" />{{ t("editor.common.remove") }}</button>
    <span class="spacer"></span>
    <div class="tool-group" role="group">
      <button type="button" class="icon-btn" :disabled="index === 0" :aria-label="t('editor.topbar.up')" :title="t('editor.topbar.up')" @click="screensaver.moveSaverItem(index, index - 1) && openSaverItem(index - 1)"><Icon name="arrow-up" /></button>
      <button type="button" class="icon-btn" :disabled="index >= items.length - 1" :aria-label="t('editor.topbar.down')" :title="t('editor.topbar.down')" @click="screensaver.moveSaverItem(index, index + 1) && openSaverItem(index + 1)"><Icon name="arrow-down" /></button>
    </div>
  </div>
</template>

<style scoped>
/* The glass in miniature: black, white, centred, as the screensaver draws it. */
.saver-live { display: flex; align-items: center; justify-content: center; gap: 8px; min-height: 44px; border-radius: 10px; background: #000; color: #fff; font-size: 18px; }
.saver-live .mdi { font-size: 22px; }
</style>
