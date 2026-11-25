<script setup lang="ts">
// The steps of one build in a row (model/build-steps.ts): waits its turn, builds, sends it to the screen, the screen
// confirms. The step it is at turns, a step that is done has its check, and the step a build stopped at says so.
import { computed } from "vue";
import { t } from "../i18n";
import { stepsOf } from "../model/build-steps";
import type { Build, LineBuild } from "../types";
import Icon from "./ui/Icon.vue";

const props = defineProps<{ build: (Build | LineBuild) & { verified?: boolean | null } | null }>();
const steps = computed(() => stepsOf(props.build));
// Where it builds: on the build server by its name, or here.
const where = computed(() => (props.build?.where === "server" && props.build.server ? t("editor.build.steps.on", { name: props.build.server }) : ""));
</script>

<template>
  <ol v-if="steps.length" class="build-steps" :aria-label="t('editor.build.steps.title')">
    <li v-for="step in steps" :key="step.key" :class="step.state" :data-step="step.key">
      <Icon v-if="step.state === 'done'" name="check" />
      <Icon v-else-if="step.state === 'failed'" name="alert-circle-outline" />
      <span v-else-if="step.state === 'now'" class="spin small" aria-hidden="true"></span>
      <Icon v-else-if="step.state === 'waits'" name="clock-outline" />
      <i v-else aria-hidden="true"></i>
      <span>{{ step.state === "waits" ? t("editor.build.steps.send_waits") : t(`editor.build.steps.${step.key}`) }}<small v-if="step.key === 'build' && where">{{ where }}</small></span>
    </li>
  </ol>
</template>
