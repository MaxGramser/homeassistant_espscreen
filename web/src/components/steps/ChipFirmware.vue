<script setup lang="ts">
// A board step of the kind chip_firmware (docs/BOARD_STEPS.md): Tessera's firmware onto a board's second chip, from
// this page. What happens when is composables/useChipFirmware.ts; this is what a person sees of it: one key that
// starts it, a second that asks for the chip's drive, a line that says what happens meanwhile, and when it is on, a key
// that lets the chip play its own sound. Where the browser has no USB port or no folder access the same file goes on by
// hand, in three steps.
import { computed, watch } from "vue";
import { useChipFirmware } from "../../composables/useChipFirmware";
import { knownChipPort, tryChip } from "../../flasher/chip";
import { t } from "../../i18n";
import { useUiStore } from "../../stores/ui";
import type { ChipFirmwareStep, Screen } from "../../types";
import Icon from "../ui/Icon.vue";

const props = defineProps<{ step: ChipFirmwareStep; screen: Screen | null }>();
const emit = defineEmits<{ done: [] }>();
const ui = useUiStore();
const chip = useChipFirmware(() => props.step, () => props.screen);
const state = chip.state;
const words = (key: string, more: Record<string, unknown> = {}) =>
  t(`editor.steps.kinds.chip_firmware.${key}`, { drive: props.step.drive, version: props.step.version, name: props.step.download, ...more });
watch(() => state.phase, (phase) => { if (phase === "done") emit("done"); });
const now = computed(() => (state.phase === "wait" && state.onChip ? words("phase.wait_chip", { version: state.onChip }) : words(`phase.${state.phase}`)));
async function play() {
  try {
    const port = await knownChipPort(props.step);
    if (port) await tryChip(port);
  } catch (error) {
    ui.toast((error as Error).message);
  }
}
</script>

<template>
  <div class="chip-step" :data-phase="state.phase" :data-support="chip.support">
    <!-- On: what is on it, and its own sound to hear. -->
    <template v-if="state.phase === 'done'">
      <p class="chip-now good" id="step-done"><Icon name="check-circle" />{{ words("done") }}</p>
      <button v-if="chip.support === 'ok'" type="button" class="ob-quiet chip-try" id="step-try" @click="play"><Icon name="play" />{{ words("try") }}</button>
    </template>

    <!-- By hand, where this browser cannot reach the chip. -->
    <template v-else-if="chip.support !== 'ok'">
      <p class="ob-note" id="step-by-hand"><Icon name="information-outline" />{{ words(`hand.${chip.support}`) }}</p>
      <ol class="ob-howto" id="step-hand-steps">
        <li><span><a class="chip-file" id="step-download" :href="step.file" :download="step.download"><Icon name="tray-arrow-down" />{{ words("hand.download") }}</a></span></li>
        <li><span>{{ t(`editor.steps.${step.id}.button`) }}</span></li>
        <li><span>{{ words("hand.drag") }}</span></li>
      </ol>
      <p v-if="state.phase === 'wait'" class="chip-now" role="status"><span class="spin small"></span>{{ now }}</p>
      <p v-else-if="state.phase === 'failed'" class="ob-note warn" role="status"><Icon name="alert-circle-outline" />{{ words("errors.silent") }}</p>
      <button v-if="state.phase !== 'wait'" type="button" class="ob-go" id="step-did" @click="chip.wait">{{ words("hand.did") }}</button>
    </template>

    <template v-else>
      <p v-if="state.phase === 'failed' && state.problem" class="ob-note warn" id="step-problem" role="status"><Icon name="alert-circle-outline" />{{ words(`errors.${state.problem}`) }}</p>
      <p v-else-if="chip.busy.value || state.phase === 'drive'" class="chip-now" id="step-now" role="status">
        <span v-if="chip.busy.value" class="spin small"></span>{{ now }}
      </p>
      <p v-if="state.wrongDrive" class="ob-note warn" id="step-wrong-drive" role="status"><Icon name="alert-circle-outline" />{{ words("wrong_drive") }}</p>

      <button v-if="state.phase === 'idle'" type="button" class="ob-go" id="step-go" @click="chip.start">{{ words("go") }}</button>
      <button v-else-if="state.phase === 'drive'" type="button" class="ob-go" id="step-drive" @click="chip.chooseDrive">{{ words("choose_drive") }}</button>
      <template v-else-if="state.phase === 'failed'">
        <button type="button" class="ob-go" id="step-again" @click="chip.start">{{ words("again") }}</button>
        <button v-if="state.problem === 'no_port' || state.problem === 'port'" type="button" class="ob-quiet" id="step-drive-there" @click="chip.driveIsThere">{{ words("drive_there") }}</button>
      </template>
      <p v-if="state.phase === 'idle'" class="ob-hint">{{ words("cable") }}</p>
    </template>
  </div>
</template>

<style scoped>
.chip-step { width: 100%; display: flex; flex-direction: column; align-items: center; gap: 14px; margin-top: 32px; }
.chip-now { display: inline-flex; align-items: center; gap: 10px; margin: 0; max-width: 560px; font-size: 16px; line-height: 1.45; color: var(--ink-2); text-align: left; }
.chip-now.good { color: var(--ink); font-weight: 500; }
.chip-now.good .ui-icon { font-size: 22px; color: var(--good); }
.chip-try { display: inline-flex; align-items: center; gap: 6px; color: var(--accent); }
.chip-file { display: inline-flex; align-items: center; gap: 6px; color: var(--accent); font-weight: 500; text-decoration: none; }
.chip-file:hover { text-decoration: underline; }
.chip-step .ob-note { margin-top: 0; text-align: left; }
.chip-step .ob-hint { margin-top: 0; }
</style>
