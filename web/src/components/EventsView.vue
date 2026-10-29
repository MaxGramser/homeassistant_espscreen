<script setup lang="ts">
// Events (app 0.4.91): what an automation in Home Assistant can fire at the screens, each one a part of this page with
// its own address (#/events/<kind>, ui.eventsKind): an alert (AlertsView) and a doorbell's ring (DoorbellView). Another
// kind of event later is one more tab and one more part.
import { computed } from "vue";
import { t } from "../i18n";
import { glyph } from "../model/topbar";
import { useUiStore, type EventKind } from "../stores/ui";
import AlertsView from "./AlertsView.vue";
import DoorbellView from "./DoorbellView.vue";
import UiTabs from "./ui/UiTabs.vue";

const ui = useUiStore();
const tabs = computed(() => [
  { value: "alerts", label: t("editor.events.alerts"), glyph: glyph("F0594") },
  { value: "doorbell", label: t("editor.events.doorbell"), glyph: glyph("F12E6") },
]);
</script>

<template>
  <div class="panel wide events" id="events-page">
    <div class="panel-head">
      <div class="tx">
        <span class="eyebrow">{{ t("editor.events.eyebrow") }}</span>
        <h1>{{ t("editor.nav.events") }}</h1>
        <p>{{ t("editor.events.intro") }}</p>
      </div>
      <button type="button" class="btn quiet" id="close-events" @click="ui.go('')">{{ t("editor.common.back") }}</button>
    </div>
    <UiTabs id="events-tabs" :model-value="ui.eventsKind" :tabs="tabs" :label="t('editor.nav.events')"
      @update:model-value="(kind) => ui.openEvents(kind as EventKind)" />
    <AlertsView v-if="ui.eventsKind === 'alerts'" />
    <DoorbellView v-else />
  </div>
</template>

<style scoped>
.events { display: grid; gap: 14px; }
</style>
