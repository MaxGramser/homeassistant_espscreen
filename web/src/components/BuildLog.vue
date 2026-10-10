<script setup lang="ts">
// A screen's build, wherever the page shows one (the screen's Plugins tab, the Plugins page, the settings' Updates
// card): how far it is, and its log, folded away until someone opens it. It reads the builds store (buildOf, the
// add-on's Manager.builds) and the add-on's firmware job for the lines. After a build that failed it stays, with the
// last lines of that build, until the next one starts.
import { computed, onMounted, ref, watch } from "vue";
import { useStickToBottom } from "../composables/useStickToBottom";
import { t } from "../i18n";
import type { Screen } from "../types";
import Icon from "./ui/Icon.vue";
import { useUiStore } from "../stores/ui";
import { useBuildsStore } from "../stores/builds";

const ui = useUiStore();
const builds = useBuildsStore();

const props = defineProps<{ screen: Screen; name?: boolean }>();
const build = computed(() => builds.buildOf(props.screen));
const progress = computed(() => builds.buildProgress(props.screen));
// The add-on's firmware job when it is this screen's: the one that runs, or the last one.
const job = computed(() => {
  const current = builds.firmwareJob;
  const file = build.value?.file || props.screen.update?.profile;
  return current?.job && file && current.job.file === file ? current : null;
});
const failed = computed(() => !build.value && job.value?.job?.state === "failed");
const lines = computed(() => job.value?.logs || []);
const open = ref(false);
const box = ref<HTMLElement | null>(null);
// The lines come with the firmware job: asked at once, then every few seconds while a build runs (the one poll of
// composables/useFirmwareJob.ts).
onMounted(() => { if (!job.value) builds.loadFirmwareJob(); });
watch(open, (now) => { if (now) builds.loadFirmwareJob(); });
// The log follows its last line while it is open, as the installer's does.
useStickToBottom(box, () => lines.value.length);
</script>

<template>
  <div v-if="progress || build || failed" class="build-log" :data-screen="screen.id">
    <template v-if="progress">
      <div class="progress" role="progressbar" :aria-valuenow="progress.percent" aria-valuemin="0" aria-valuemax="100"><i :style="{ width: progress.percent + '%' }"></i></div>
      <div class="progress-text"><span>{{ name ? `${screen.name} · ` : "" }}{{ progress.percent }} %</span><span>{{ progress.text }}</span></div>
    </template>
    <p v-else-if="build" class="build-note"><span class="spin small" aria-hidden="true"></span>{{ name ? `${screen.name} · ` : "" }}{{ t("editor.sidebar.update.queued") }}</p>
    <p v-else class="build-note failed"><Icon name="alert-circle-outline" />{{ t("editor.build.failed", { screen: screen.name }) }}</p>
    <details v-if="lines.length" class="follow-log" :open="open" @toggle="open = ($event.target as HTMLDetailsElement).open">
      <summary><Icon name="code-braces" />{{ t(open ? "editor.installer.hide_log" : "editor.installer.show_log") }}<button v-if="open" type="button" class="btn quiet mini" @click.prevent="ui.copyText(lines.join('\n'), null, 'log')">{{ t("editor.common.copy") }}</button></summary>
      <pre ref="box" class="log">{{ lines.join("\n") }}</pre>
    </details>
  </div>
</template>
