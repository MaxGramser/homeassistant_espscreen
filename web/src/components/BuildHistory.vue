<script setup lang="ts">
// A screen's last builds with how each ended, its log to download (kept on disk by the add-on, build_logs.py): at the
// foot of the screen's Plugins tab, so what happened to this screen is found where the screen is, not only under
// Firmware & USB. Folded away; a build that failed opens it.
import { computed, onMounted } from "vue";
import { t } from "../i18n";
import type { Screen } from "../types";
import Icon from "./ui/Icon.vue";
import KeptLogList from "./KeptLogList.vue";
import { useBuildsStore } from "../stores/builds";

const builds = useBuildsStore();
const props = defineProps<{ screen: Screen }>();
const profile = computed(() => props.screen.update?.profile || null);
const mine = computed(() => (profile.value ? builds.keptLogs.filter((log) => log.file === profile.value).slice(0, 8) : []));
onMounted(() => void builds.loadKeptLogs());   // the builds store follows them from then on
</script>

<template>
  <details v-if="mine.length" class="sp-group sp-history" id="screen-build-history" :open="mine[0]?.state === 'failed' || mine[0]?.state === 'interrupted'">
    <summary><Icon name="chevron-right" />{{ t("editor.history.title", { n: mine.length }, mine.length) }}</summary>
    <KeptLogList :logs="mine" label="kind" />
  </details>
</template>
