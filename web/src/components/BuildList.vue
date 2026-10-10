<script setup lang="ts">
// The builds on their way, each screen's ring, name and step, and the way to the log: what the head's ring opens
// (BuildIndicator). A row opens its screen.
import { t } from "../i18n";
import type { Screen } from "../types";
import Icon from "./ui/Icon.vue";
import ProgressRing from "./ui/ProgressRing.vue";
import { useBuildsStore } from "../stores/builds";
import { useSessionStore } from "../stores/session";
import { useUiStore } from "../stores/ui";

const builds = useBuildsStore();
const session = useSessionStore();
const ui = useUiStore();
const emit = defineEmits<{ done: [] }>();

// A screen waiting its turn is an empty ring; the one that runs says its step.
const percent = (screen: Screen) => builds.buildProgress(screen)?.percent ?? 0;
const step = (screen: Screen) => builds.buildProgress(screen)?.text ?? t("editor.build.waiting");
function choose(screen: Screen) {
  emit("done");
  session.select(screen.id);
}
function showLog() {
  emit("done");
  ui.go("#firmware");
}
</script>

<template>
  <h4>{{ t("editor.build.title") }}</h4>
  <button v-for="screen in builds.buildingScreens" :key="screen.id" type="button" class="builds-row" :data-screen="screen.id" @click="choose(screen)">
    <ProgressRing :percent="percent(screen)" :label="`${screen.name} · ${step(screen)}`" />
    <span class="builds-name"><strong>{{ screen.name }}</strong><small>{{ step(screen) }}</small></span>
    <small class="builds-percent">{{ builds.buildProgress(screen) ? `${percent(screen)} %` : "" }}</small>
  </button>
  <button type="button" class="builds-log" @click="showLog"><Icon name="code-braces" />{{ t("editor.build.show_log") }}</button>
</template>
