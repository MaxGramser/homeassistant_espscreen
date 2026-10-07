<script setup lang="ts">
// Adding an entity to the screensaver's clock (app 0.4.81): the top bar's own choice of entities (EntityItemPicker).
import { t } from "../i18n";
import { entityItem } from "../model/topbar";
import { addSaverItem, SAVER_ITEMS_MAX, saverItems } from "../store";
import type { HeaderItem } from "../types";
import { clockCrumb } from "../saver";
import EntityItemPicker from "./EntityItemPicker.vue";
import InspectorHead from "./ui/InspectorHead.vue";

// The clock shows an entity always, by its state or its icon; what else the top bar knows has no place there.
const plain = (item: HeaderItem): HeaderItem => ({ ...entityItem(item.entity!), content: item.content === "icon" ? "icon" : "state", icon: item.icon || "auto" });
const taken = (item: HeaderItem) => saverItems().some((other) => other.entity === item.entity);
</script>

<template>
  <InspectorHead kind="bar" :title="t('editor.screen_settings.screensaver.items_add_title')" icon="plus"
    :crumbs="[clockCrumb(), { text: t('editor.screen_settings.screensaver.items_slots', { used: saverItems().length, n: SAVER_ITEMS_MAX }) }]" />
  <div class="dr-body">
    <EntityItemPicker id="saver-search" :taken="taken" :accepts="(item) => item.type === 'entity'" @pick="(item) => addSaverItem(plain(item))" />
  </div>
  <div class="dr-foot">
    <span class="spacer"></span>
    <button type="button" class="btn quiet" @click="clockCrumb().open()">{{ t("editor.common.cancel") }}</button>
  </div>
</template>
