<script setup lang="ts">
// Where an installation from this browser stands (New screen and Firmware & USB): the step, the bar while it writes,
// and when something went wrong, what to do about it. The steps are those of ESPHome's own browser install.
import { computed } from "vue";
import { t } from "../i18n";
import type { FlashState } from "../flasher/session";

const props = defineProps<{ state: FlashState }>();
const line = computed(() => {
  const s = props.state;
  if (s.phase === "failed") return t(`editor.webflash.errors.${s.problem || "failed"}`, { error: s.detail, ...s.params });
  if (s.phase === "writing") return t("editor.webflash.phase.writing", { percent: s.percent });
  if (s.phase === "waiting") return t("editor.webflash.phase.waiting", { chip: s.chip });
  return s.phase === "idle" ? "" : t(`editor.webflash.phase.${s.phase}`);
});
// An empty port list and a picker closed without a port look the same to the page: ESPHome's checklist for both.
const hints = computed(() => props.state.phase === "failed" && props.state.problem === "no_port"
  ? ["computer", "power", "cable", "driver"].map((key) => t(`editor.webflash.hints.${key}`)) : []);
</script>

<template>
  <div v-if="state.phase !== 'idle'" class="webflash" :class="{ bad: state.phase === 'failed' }" id="webflash" role="status">
    <p id="webflash-line">{{ line }}</p>
    <div v-if="state.phase === 'writing'" class="progress" id="webflash-progress"><i :style="{ width: `${state.percent}%` }"></i></div>
    <small v-if="state.phase === 'writing' || state.phase === 'erasing'">{{ t("editor.webflash.keep_open") }}</small>
    <ul v-if="hints.length" id="webflash-hints">
      <li v-for="hint in hints" :key="hint">{{ hint }}</li>
    </ul>
  </div>
</template>

<style scoped>
.webflash { display: grid; gap: 6px; padding: 10px 12px; border-radius: 8px; background: var(--surface-2); }
.webflash p { margin: 0; }
.webflash.bad p { color: var(--danger); }
.webflash ul { margin: 0; padding-left: 18px; }
</style>
