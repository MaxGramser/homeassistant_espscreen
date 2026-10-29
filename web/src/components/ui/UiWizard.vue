<script setup lang="ts">
// A wizard in a window of its own (Reka UI's Dialog with its Stepper): one step at a time, each with its title, a line of
// help and its own part (the slot named after the step), Back and Next below, and the steps above as numbered dots (the
// current one with its name) to see where you are and go back to one already done. The page that opens it keeps what is
// chosen; `ready` says whether Next may go on. It lies above the page and the palette (70) and below what opens from it:
// a picker or menu (.ui-popover, 80), a toast (85) and a confirm (90).
import { computed } from "vue";
import { DialogClose, DialogContent, DialogDescription, DialogOverlay, DialogPortal, DialogRoot, DialogTitle,
  StepperIndicator, StepperItem, StepperRoot, StepperSeparator, StepperTitle, StepperTrigger } from "reka-ui";
import { t } from "../../i18n";
import Icon from "./Icon.vue";

export type WizardStep = { id: string; title: string; help: string };
const props = defineProps<{ open: boolean; title: string; steps: WizardStep[]; step: number; ready?: boolean; next?: string; hideNext?: boolean }>();
const emit = defineEmits<{ "update:open": [open: boolean]; "update:step": [step: number] }>();
const current = computed(() => props.steps[props.step - 1]);
const last = computed(() => props.step >= props.steps.length);
const go = (step: number) => emit("update:step", Math.max(1, Math.min(props.steps.length, step)));
</script>

<template>
  <DialogRoot :open="open" @update:open="(value: boolean) => emit('update:open', value)">
    <DialogPortal>
      <DialogOverlay class="wizard-dim" />
      <DialogContent class="wizard" @interact-outside.prevent>
        <header class="wizard-head">
          <DialogTitle class="wizard-title">{{ title }}</DialogTitle>
          <DialogClose class="wizard-close" :aria-label="t('editor.common.close')"><Icon name="close" /></DialogClose>
        </header>
        <StepperRoot class="wizard-steps" :model-value="step" linear @update:model-value="(value) => value !== undefined && go(Number(value))">
          <StepperItem v-for="(item, index) in steps" :key="item.id" class="wizard-step" :step="index + 1" :completed="index + 1 < step">
            <StepperTrigger class="wizard-step-trigger" :disabled="index + 1 > step">
              <StepperIndicator class="wizard-dot">{{ index + 1 }}</StepperIndicator>
              <StepperTitle class="wizard-step-title">{{ item.title }}</StepperTitle>
            </StepperTrigger>
            <StepperSeparator v-if="index < steps.length - 1" class="wizard-line" />
          </StepperItem>
        </StepperRoot>
        <section v-if="current" class="wizard-body" :data-step="current.id">
          <h3>{{ current.title }}</h3>
          <DialogDescription class="wizard-help">{{ current.help }}</DialogDescription>
          <slot :name="current.id" />
        </section>
        <footer class="wizard-foot">
          <button v-if="step > 1" type="button" class="btn quiet" data-wizard="back" @click="go(step - 1)">{{ t("editor.events.wizard.back") }}</button>
          <span class="wizard-spacer" />
          <slot name="footer" :last="last" />
          <button v-if="!last && !hideNext" type="button" class="btn primary" data-wizard="next" :disabled="ready === false" @click="go(step + 1)">{{ next || t("editor.events.wizard.next") }}</button>
        </footer>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<style scoped>
.wizard-dim { position: fixed; inset: 0; z-index: 74; background: rgba(10, 12, 18, 0.36); animation: wizard-fade 0.14s ease-out; }
.wizard { position: fixed; z-index: 75; left: 50%; top: 50%; translate: -50% -50%; width: min(680px, calc(100vw - 32px)); height: min(640px, calc(100vh - 48px));
  display: grid; grid-template-rows: auto auto 1fr auto; background: var(--surface); color: var(--ink); border: 1px solid var(--line); border-radius: 16px;
  box-shadow: var(--pop-shadow); animation: wizard-in 0.16s ease-out; overflow: hidden; }
.wizard:focus { outline: none; }
.wizard-head { display: flex; align-items: center; gap: 12px; padding: 18px 20px 4px; }
.wizard-title { margin: 0; font-size: 16px; font-weight: 600; flex: 1; }
.wizard-close { display: grid; place-items: center; width: 32px; height: 32px; border-radius: 50%; border: 0; background: transparent; color: var(--muted); cursor: pointer; font-size: 18px; }
.wizard-close:hover { background: var(--surface-2); }
.wizard-steps { display: flex; align-items: center; gap: 4px; padding: 10px 20px 14px; overflow-x: auto; }
.wizard-step { display: flex; align-items: center; gap: 4px; flex: 1; min-width: 0; }
.wizard-step:last-child { flex: none; }
.wizard-step-trigger { display: flex; align-items: center; gap: 6px; border: 0; background: none; padding: 0; color: var(--muted); font: inherit; cursor: pointer; min-width: 0; }
.wizard-step-trigger:disabled { cursor: default; }
.wizard-dot { display: grid; place-items: center; width: 22px; height: 22px; border-radius: 50%; flex: none; font-size: 11.5px; font-weight: 600;
  background: var(--surface-2); color: var(--muted); }
.wizard-step[data-state="active"] .wizard-dot { background: var(--accent); color: var(--accent-ink); }
.wizard-step[data-state="completed"] .wizard-dot { background: var(--accent-soft); color: var(--accent); }
.wizard-step-title { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); font-size: 12.5px; white-space: nowrap; }
.wizard-step[data-state="active"] { flex: 2 0 auto; }
.wizard-step[data-state="active"] .wizard-step-trigger { flex: none; }
.wizard-step[data-state="active"] .wizard-step-title { position: static; width: auto; height: auto; overflow: visible; clip-path: none; color: var(--ink); font-weight: 600; }
.wizard-line { flex: 1; height: 1px; min-width: 8px; background: var(--line); }
.wizard-body { min-height: 0; padding: 8px 20px 20px; overflow-y: auto; display: grid; gap: 12px; align-content: start; }
.wizard-body h3 { margin: 10px 0 0; font-size: 18px; font-weight: 600; }
.wizard-help { margin: 0; color: var(--muted); font-size: 13.5px; line-height: 1.55; }
.wizard-foot { display: flex; align-items: center; gap: 8px; padding: 14px 20px 18px; }
.wizard-foot .btn { min-width: 96px; }
.wizard-spacer { flex: 1; }
@keyframes wizard-fade { from { opacity: 0; } }
@keyframes wizard-in { from { opacity: 0; scale: 0.97; } }
@media (max-width: 640px) {
  .wizard { top: auto; bottom: 0; translate: -50% 0; width: 100vw; height: 92vh; border-radius: 16px 16px 0 0; }
}
@media (prefers-reduced-motion: reduce) { .wizard, .wizard-dim { animation: none; } }
</style>
