<script setup lang="ts">
// A screen's build, wherever the page shows one (the screen's Plugins tab, the Plugins page, the settings' Updates
// card): how far it is, or its turn while it waits, and its log, folded away until someone opens it. It reads the builds
// store: buildOf (the add-on's Manager.builds) and the build line (lineOf, the newest build of the screen's profile) for
// the lines. After a build that failed it stays, with that build's own log, until the next build of the screen starts.
import { computed, onMounted, ref, watch } from "vue";
import { useClock } from "../composables/useClock";
import { useStickToBottom } from "../composables/useStickToBottom";
import { t } from "../i18n";
import { waitingText } from "../model/screen-status";
import type { Screen } from "../types";
import BuildSteps from "./BuildSteps.vue";
import Icon from "./ui/Icon.vue";
import { useUiStore } from "../stores/ui";
import { buildLogHref, useBuildsStore } from "../stores/builds";

const ui = useUiStore();
const builds = useBuildsStore();

const props = defineProps<{ screen: Screen; name?: boolean }>();
const build = computed(() => builds.buildOf(props.screen));
const progress = computed(() => builds.buildProgress(props.screen));
// The newest build of this screen's profile in the line: the one on its way, or the last one that ended.
const last = computed(() => builds.lineOf(build.value?.file || props.screen.update?.profile));
const failed = computed(() => !build.value && (last.value?.state === "failed" || last.value?.state === "interrupted"));
// A build that went well stays a moment with its steps done, so whoever pressed the key sees that it did (docs/BUILDS.md).
const DONE_SHOWN_S = 600;
const now = useClock(30_000);
const done = computed(() => !build.value && last.value?.state === "success" && last.value.by !== "check"
  && Boolean(last.value.finished && now.value / 1000 - last.value.finished < DONE_SHOWN_S));
const lines = computed(() => builds.buildLogOf(last.value));
const open = ref(false);
const box = ref<HTMLElement | null>(null);
// The lines come with the firmware job: asked at once, then every few seconds while a build runs (the one poll of
// composables/useFirmwareJob.ts).
onMounted(() => { if (!last.value) builds.loadFirmwareJob(); });
watch(open, (now) => { if (now) builds.loadFirmwareJob(); });
// A build that ended keeps its own log in the add-on, asked once.
watch(() => (last.value && builds.lineEnded(last.value) ? last.value.id : null), (id) => { if (id !== null) void builds.loadBuildLog(id); }, { immediate: true });
// The log follows its last line while it is open, as the installer's does.
useStickToBottom(box, () => lines.value.length);
</script>

<template>
  <div v-if="progress || build || failed || done" class="build-log" :class="{ done, failed }" :data-screen="screen.id">
    <template v-if="progress">
      <div class="progress" role="progressbar" :aria-valuenow="progress.percent" aria-valuemin="0" aria-valuemax="100"><i :style="{ width: progress.percent + '%' }"></i></div>
      <div class="progress-text"><span>{{ name ? `${screen.name} · ` : "" }}{{ progress.percent }} %</span><span>{{ progress.text }}</span></div>
    </template>
    <p v-else-if="build" class="build-note"><span class="spin small" aria-hidden="true"></span>{{ name ? `${screen.name} · ` : "" }}{{ waitingText(build) }}</p>
    <p v-else-if="done" class="build-note done"><Icon name="check-circle" />{{ t(last?.verified ? "editor.build.done_confirmed" : "editor.build.done", { screen: screen.name }) }}</p>
    <p v-else class="build-note failed"><Icon name="alert-circle-outline" />{{ t("editor.build.failed", { screen: screen.name }) }}<a v-if="last?.log" class="btn quiet mini" :href="buildLogHref(last.log)" :download="`${last.log}.log`"><Icon name="tray-arrow-down" />{{ t("editor.plugins.download_log") }}</a></p>
    <BuildSteps :build="build || last" />
    <details v-if="lines.length" class="follow-log" :open="open" @toggle="open = ($event.target as HTMLDetailsElement).open">
      <summary><Icon name="code-braces" />{{ t(open ? "editor.installer.hide_log" : "editor.installer.show_log") }}<button v-if="open" type="button" class="btn quiet mini" @click.prevent="ui.copyText(lines.join('\n'), null, 'log')">{{ t("editor.common.copy") }}</button></summary>
      <pre ref="box" class="log">{{ lines.join("\n") }}</pre>
    </details>
  </div>
</template>
