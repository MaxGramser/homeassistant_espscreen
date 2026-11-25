<script setup lang="ts">
// A step of this screen's board that is not done (docs/BOARD_STEPS.md): the card above the screen that offers it, in
// the step's own words. Set it up asks the screen's page to open the step in its window (ScreenView.vue); Not now is
// kept by the add-on, and the card stays away, while the step waits in the screen's menu. A newer one of something that is done (`update`) is offered the same
// way. One step at a time, and never on top of the board's own card, the stars card or a build.
import { computed } from "vue";
import { send } from "../api";
import { useBusy } from "../composables/useBusy";
import { t } from "../i18n";
import { stepsToDo } from "../model/board-steps";
import { useBuildsStore } from "../stores/builds";
import { useInventoryStore } from "../stores/inventory";
import { useUiStore } from "../stores/ui";
import type { Screen } from "../types";
import Icon from "./ui/Icon.vue";
import { KINDS, stepIcon } from "./steps/kinds";

const props = defineProps<{ screen: Screen }>();
const emit = defineEmits<{ open: [step: string] }>();
const builds = useBuildsStore(), inv = useInventoryStore(), ui = useUiStore();
const { busy, runOnce } = useBusy();
const step = computed(() => stepsToDo(props.screen).find((one) => KINDS[one.kind]) || null);
const visible = computed(() => Boolean(step.value) && props.screen.online && !props.screen.feedback?.ask && !props.screen.plugin_ask
  && !props.screen.plugin_suggest && !builds.updating.includes(props.screen.id));
function setUp() { if (step.value) emit("open", step.value.id); }
async function notNow() {
  const now = step.value;
  if (!now) return;
  await runOnce(async () => {
    await send(`screens/${encodeURIComponent(props.screen.id)}/steps/${encodeURIComponent(now.id)}`, "POST", { answer: "later" });
    await inv.refresh(false);
    ui.toast(t("editor.steps.kept", { screen: props.screen.name }));
  }).catch((error: any) => ui.toast(error.message));
}
</script>

<template>
  <section v-if="visible && step" class="step-card" id="board-step-card" :data-step="step.id" aria-labelledby="board-step-card-title">
    <span class="step-card-badge" aria-hidden="true"><Icon :name="stepIcon(step.id)" /></span>
    <div class="step-card-body">
      <h2 id="board-step-card-title" class="step-card-title">{{ t(`editor.steps.${step.id}.${step.state === "update" ? "update_title" : "title"}`) }}</h2>
      <p class="step-card-lead">{{ t(`editor.steps.${step.id}.${step.state === "update" ? "update_lead" : "lead"}`) }}</p>
      <div class="step-card-actions">
        <button type="button" class="btn primary" id="board-step-set-up" @click="setUp">{{ t(step.state === "update" ? "editor.steps.update" : "editor.steps.set_up") }}</button>
        <button v-if="step.state === 'open'" type="button" class="btn quiet" id="board-step-not-now" :disabled="busy" @click="notNow">{{ t("editor.steps.not_now") }}</button>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* The same box as the card that suggests a plugin (PluginSuggestCard.vue). */
.step-card { position: relative; flex: none; display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 14px; align-items: start; margin: 14px 18px 0; padding: 14px 16px;
  border: 1px solid var(--line); border-radius: 12px; background: var(--surface); }
.step-card-badge { width: 40px; height: 40px; border-radius: 11px; display: grid; place-items: center; background: var(--accent-soft); color: var(--accent); font-size: 22px; }
.step-card-body { display: grid; gap: 8px; min-width: 0; justify-items: start; }
.step-card-title { margin: 0; font-size: 14px; font-weight: 600; line-height: 1.35; text-wrap: balance; }
.step-card-lead { margin: 0; font-size: 12.5px; color: var(--ink-2); line-height: 1.4; max-width: 620px; }
.step-card-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 2px; }
@media (max-width: 640px) { .step-card { margin: 10px 16px 0; } }
</style>
