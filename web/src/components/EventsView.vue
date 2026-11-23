<script setup lang="ts">
// Events (app 0.4.91): what Home Assistant shows on the screens, a page of parts like Settings (model/parts.ts,
// docs/PAGES.md "Pages of parts"). It opens on a list of its parts, each with one line of what is set now, and a part
// opens on its own address (#/events/<kind>, ui.eventsKind): an alert (AlertsView) and a doorbell's ring (DoorbellView)
// that an automation fires, the alarm going off (AlarmView), which the screens follow themselves, and what rings when one
// screen calls another (CallsView). Another kind later is one more row and part.
import { computed, onMounted, ref } from "vue";
import { getJson } from "../api";
import { t } from "../i18n";
import type { PartRow } from "../model/parts";
import { PART_LOOK, type EventPart } from "../model/settings-parts";
import type { IconName } from "../model/ui-icons";
import { useAutomations } from "../composables/useAutomations";
import { useSoundsStore } from "../stores/sounds";
import { useUiStore } from "../stores/ui";
import AlarmView from "./AlarmView.vue";
import AlertsView from "./AlertsView.vue";
import CallsView from "./CallsView.vue";
import DoorbellView from "./DoorbellView.vue";
import PartsPage from "./parts/PartsPage.vue";

const ui = useUiStore();
const sounds = useSoundsStore();

// What the list says of each part: the automations of Tessera in Home Assistant, the alarm panels, the ring of a call.
const alerts = useAutomations("alert");
const doorbells = useAutomations("doorbell");
const alarms = ref<number | null>(null);
const loaded = ref(false);
onMounted(async () => {
  await Promise.all([
    alerts.refresh(), doorbells.refresh(), sounds.load().catch(() => undefined),
    getJson<{ alarms: unknown[] }>("alarms").then((view) => { alarms.value = view.alarms?.length ?? 0; }).catch(() => { alarms.value = null; }),
  ]);
  loaded.value = true;
});
const automationsLine = (n: number) => (!loaded.value ? "" : n ? t("editor.events.parts.automations", { n }, n) : t("editor.events.parts.no_automation"));
const alarmLine = computed(() => (alarms.value === null ? "" : alarms.value ? t("editor.events.parts.alarm_panels", { n: alarms.value }, alarms.value) : t("editor.events.parts.no_alarm")));
const callLine = computed(() => {
  const ring = sounds.view?.kinds.call?.default;
  return ring ? t("editor.events.parts.rings_with", { sound: sounds.nameOf(ring) }) : "";
});

const ICONS: Record<EventPart, IconName> = { alerts: "bell-ring-outline", doorbell: "doorbell", alarm: "shield-home-outline", calls: "phone-ring-outline" };
const rows = computed<PartRow<EventPart>[]>(() => [
  { id: "alerts", title: t("editor.events.alerts"), summary: automationsLine(alerts.listed.value.length) },
  { id: "doorbell", title: t("editor.events.doorbell"), summary: automationsLine(doorbells.listed.value.length) },
  { id: "alarm", title: t("editor.events.alarm"), summary: alarmLine.value },
  { id: "calls", title: t("editor.events.calls"), summary: callLine.value },
].map((row) => ({ ...row, id: row.id as EventPart, icon: ICONS[row.id as EventPart], ...PART_LOOK[row.id as EventPart] })));
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
