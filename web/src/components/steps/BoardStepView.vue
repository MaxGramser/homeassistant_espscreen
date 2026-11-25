<script setup lang="ts">
// One step of a screen's board (docs/BOARD_STEPS.md), as a page: what it is and why, in the step's own words
// (editor.steps.<id>), and under it the part that does it, which is its kind's (kinds.ts). New screen shows it after the
// screen works (install/Progress.vue), and a window shows the same page from the card above a screen and from the
// screen's menu (BoardStepDialog.vue). It says `later` when someone puts the step off and `next` when they go on.
import "../../styles/new-screen.css";
import { computed, ref, watch } from "vue";
import { t } from "../../i18n";
import type { BoardStep, Screen } from "../../types";
import Icon from "../ui/Icon.vue";
import { KINDS, stepIcon } from "./kinds";

const props = defineProps<{ step: BoardStep; screen: Screen | null; continueLabel?: string }>();
const emit = defineEmits<{ later: []; next: [] }>();
// Done on this page: the kind said so, or the screen does (it found a chip someone wrote by hand meanwhile).
const finished = ref(false);
watch(() => props.step.id, () => { finished.value = false; });
const done = computed(() => finished.value || props.step.state === "done");
const kind = computed(() => KINDS[props.step.kind]);
const words = (key: string) => t(`editor.steps.${props.step.id}.${key}`);
const title = computed(() => words(done.value ? "done_title" : props.step.state === "update" ? "update_title" : "title"));
const lead = computed(() => words(done.value ? "done_lead" : props.step.state === "update" ? "update_lead" : "lead"));
</script>

<template>
  <section class="ob-step board-step" data-step="board-step" :data-id="step.id" :data-kind="step.kind" :class="{ done }">
    <span class="ob-badge" :class="{ good: done }" aria-hidden="true"><Icon :name="done ? 'check' : stepIcon(step.id)" /></span>
    <h1 id="board-step-title">{{ title }}</h1>
    <p class="ob-lead">{{ lead }}</p>
    <component :is="kind" v-if="kind && !(done && !finished)" :step="step" :screen="screen" @done="finished = true" />
    <p v-if="!done" class="ob-hint board-step-note">{{ words("note") }}</p>
    <footer class="ob-foot">
      <button v-if="done" type="button" class="ob-go" id="board-step-next" @click="emit('next')">{{ continueLabel || t("editor.installer.flow.continue") }}</button>
      <button v-else type="button" class="ob-quiet" id="board-step-later" @click="emit('later')">{{ t("editor.steps.later") }}</button>
    </footer>
  </section>
</template>

<style scoped>
.board-step { flex: 1 0 auto; }
.ob-badge.good { background: var(--good-soft); color: var(--good); }
.board-step-note { margin-top: 22px; }
</style>
