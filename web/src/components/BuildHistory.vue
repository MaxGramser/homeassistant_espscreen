<script setup lang="ts">
// A screen's last builds with how each ended, its log to download (kept on disk by the add-on, build_logs.py): at the
// foot of the screen's Plugins tab, so what happened to this screen is found where the screen is, not only under
// Firmware & USB. Folded away; a build that failed opens it.
import { computed, onMounted, watch } from "vue";
import { t } from "../i18n";
import type { Screen } from "../types";
import Icon from "./ui/Icon.vue";
import { buildLogHref, useBuildsStore } from "../stores/builds";

const builds = useBuildsStore();
const props = defineProps<{ screen: Screen }>();
const profile = computed(() => props.screen.update?.profile || null);
const mine = computed(() => (profile.value ? builds.keptLogs.filter((log) => log.file === profile.value).slice(0, 8) : []));
const endedIds = computed(() => builds.line.filter((b) => builds.lineEnded(b)).map((b) => b.id).join(","));
onMounted(() => void builds.loadKeptLogs());
watch(endedIds, () => void builds.loadKeptLogs());
const when = (at?: number) => (at ? new Date(at * 1000).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" }) : "");
const state = (s: string) => t(`editor.firmware.kept_state.${["success", "failed", "interrupted", "running"].includes(s) ? s : "other"}`);
const kind = (by?: string) => t(`editor.history.by.${["update", "plugins", "install", "icons"].includes(by || "") ? by : "other"}`);
</script>

<template>
  <details v-if="mine.length" class="sp-group sp-history" id="screen-build-history" :open="mine[0]?.state === 'failed' || mine[0]?.state === 'interrupted'">
    <summary><Icon name="chevron-right" />{{ t("editor.history.title", { n: mine.length }, mine.length) }}</summary>
    <ul class="kept-list">
      <li v-for="log in mine" :key="log.key" :class="log.state" :data-key="log.key">
        <span class="kept-words"><b>{{ kind(log.by) }}<template v-if="log.plugins?.length"> · {{ log.plugins.join(", ") }}</template></b><small>{{ when(log.started) }} · <span class="kept-state">{{ state(log.state) }}</span><template v-if="log.reason"> · {{ log.reason }}</template></small></span>
        <a class="btn quiet mini" :href="buildLogHref(log.key)" :download="`${log.key}.log`"><Icon name="tray-arrow-down" />{{ t("editor.firmware.kept_download") }}</a>
      </li>
    </ul>
  </details>
</template>
