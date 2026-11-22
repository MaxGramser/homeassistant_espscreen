<script setup lang="ts">
// Events (app 0.4.91): what Home Assistant shows on the screens, each one a part of this page with its own address
// (#/events/<kind>, ui.eventsKind): an alert (AlertsView) and a doorbell's ring (DoorbellView) that an automation fires,
// the alarm going off (AlarmView), which the screens follow themselves, and what rings when one screen calls another
// (CallsView). Another kind later is one more tab and part.
import { computed } from "vue";
import { t } from "../i18n";
import { glyph } from "../model/topbar";
import { useUiStore, type EventKind } from "../stores/ui";
import AlarmView from "./AlarmView.vue";
import AlertsView from "./AlertsView.vue";
import CallsView from "./CallsView.vue";
import DoorbellView from "./DoorbellView.vue";
import UiTabs from "./ui/UiTabs.vue";

const ui = useUiStore();
const tabs = computed(() => [
  { value: "alerts", label: t("editor.events.alerts"), glyph: glyph("F0594") },
  { value: "doorbell", label: t("editor.events.doorbell"), glyph: glyph("F12E6") },
  { value: "alarm", label: t("editor.events.alarm"), glyph: glyph("F0498") },
  { value: "calls", label: t("editor.events.calls"), glyph: glyph("F11AB") },
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
    <DoorbellView v-else-if="ui.eventsKind === 'doorbell'" />
    <AlarmView v-else-if="ui.eventsKind === 'alarm'" />
    <CallsView v-else />
  </div>
</template>

<style scoped>
.events { display: grid; gap: 14px; }
</style>
