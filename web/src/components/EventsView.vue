<script setup lang="ts">
// Events (app 0.4.91): what Home Assistant shows on the screens, a page of parts like Settings (model/parts.ts,
// docs/PAGES.md "Pages of parts"). It opens on a list of its parts, each with one line of what is set now, and a part
// opens on its own address (#/events/<kind>, ui.eventsKind): an alert (AlertsView) and a doorbell's ring (DoorbellView)
// that an automation fires, the alarm going off (AlarmView), which the screens follow themselves, and what rings when one
// screen calls another (CallsView). Another kind later is one more row and part.
import { computed, onMounted } from "vue";
import { t } from "../i18n";
import type { PartRow } from "../model/parts";
import { PART_LOOK, type EventPart } from "../model/settings-parts";
import { useAlarmsStore } from "../stores/alarms";
import { useAutomationsStore } from "../stores/automations";
import { useSoundsStore } from "../stores/sounds";
import { useUiStore } from "../stores/ui";
import AlarmView from "./AlarmView.vue";
import AlertsView from "./AlertsView.vue";
import CallsView from "./CallsView.vue";
import DoorbellView from "./DoorbellView.vue";
import PartsPage from "./parts/PartsPage.vue";

const ui = useUiStore();
const sounds = useSoundsStore();

// What the list says of each part, from the stores every part reads too: the automations of Tessera in Home Assistant
// (stores/automations.ts), the alarm panels (stores/alarms.ts), the ring of a call (stores/sounds.ts). A change in a part
// shows here at once.
const automations = useAutomationsStore();
const alarms = useAlarmsStore();
onMounted(() => {
  void automations.refresh("alert", false);
  void automations.refresh("doorbell", false);
  void alarms.load().catch(() => undefined);
  void sounds.load().catch(() => undefined);
});
const automationsLine = (kind: "alert" | "doorbell") => {
  if (!automations.known[kind]) return "";
  const n = automations.listed[kind].length;
  return n ? t("editor.events.parts.automations", { n }, n) : t("editor.events.parts.no_automation");
};
const alarmLine = computed(() => {
  const n = alarms.view?.alarms.length;
  return n === undefined ? "" : n ? t("editor.events.parts.alarm_panels", { n }, n) : t("editor.events.parts.no_alarm");
});
const callLine = computed(() => {
  const ring = sounds.view?.kinds.call?.default;
  return ring ? t("editor.events.parts.rings_with", { sound: sounds.nameOf(ring) }) : "";
});

const rows = computed<PartRow<EventPart>[]>(() => [
  { id: "alerts", title: t("editor.events.alerts"), summary: automationsLine("alert") },
  { id: "doorbell", title: t("editor.events.doorbell"), summary: automationsLine("doorbell") },
  { id: "alarm", title: t("editor.events.alarm"), summary: alarmLine.value },
  { id: "calls", title: t("editor.events.calls"), summary: callLine.value },
].map((row) => ({ ...row, id: row.id as EventPart, ...PART_LOOK[row.id as EventPart] })));
</script>

<template>
  <PartsPage id="events-page" close-id="close-events" list-id="events-parts" row-prefix="events-part" :wide="Boolean(ui.eventsKind)"
    :eyebrow="t('editor.events.eyebrow')" :title="t('editor.nav.events')" :intro="t('editor.events.intro')" :close-label="t('editor.common.back')"
    :rows="rows" :open="ui.eventsKind" @open="ui.openEvents" @close="ui.go('')">
    <AlertsView v-if="ui.eventsKind === 'alerts'" />
    <DoorbellView v-else-if="ui.eventsKind === 'doorbell'" />
    <AlarmView v-else-if="ui.eventsKind === 'alarm'" />
    <CallsView v-else />
  </PartsPage>
</template>
