<script setup lang="ts">
// Build logs the add-on keeps on disk (build_logs.py, the builds store's keptLogs), as a list: when each build started,
// what it was, how it ended and why, and its log to download. Firmware & USB names each by its screen's file
// (`label: "file"`), a screen's own list by what the build was (`label: "kind"`).
import { t } from "../i18n";
import Icon from "./ui/Icon.vue";
import { buildLogHref, type KeptLog } from "../stores/builds";

defineProps<{ logs: KeptLog[]; label: "file" | "kind" }>();

const KNOWN_STATES = ["success", "failed", "interrupted", "running", "retry"];
const KNOWN_KINDS = ["update", "plugins", "install", "icons"];
const when = (at?: number) => (at ? new Date(at * 1000).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" }) : "");
const state = (s: string) => t(`editor.firmware.kept_state.${KNOWN_STATES.includes(s) ? s : "other"}`);
const kind = (by?: string) => t(`editor.history.by.${KNOWN_KINDS.includes(by || "") ? by : "other"}`);
</script>

<template>
  <ul class="kept-list">
    <li v-for="log in logs" :key="log.key" :class="log.state" :data-key="log.key">
      <span class="kept-words">
        <b v-if="label === 'file'">{{ log.file || log.key }}</b>
        <b v-else>{{ kind(log.by) }}<template v-if="log.plugins?.length"> · {{ log.plugins.join(", ") }}</template></b>
        <small>{{ when(log.started) }}<template v-if="label === 'file'"> · {{ kind(log.by) }}</template> · <span class="kept-state">{{ state(log.state) }}</span><template v-if="log.reason"> · {{ log.reason }}</template></small>
      </span>
      <a class="btn quiet mini" :href="buildLogHref(log.key)" :download="`${log.key}.log`"><Icon name="tray-arrow-down" />{{ t("editor.firmware.kept_download") }}</a>
    </li>
  </ul>
</template>
