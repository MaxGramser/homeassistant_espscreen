<script setup lang="ts">
// The editor's questions (composables/useConfirm.ts) in its own look, light and dark: the question in the words it always
// had, Cancel and OK, a field for a new name, a text selected to copy by hand. Cancel has the focus at first, as an alert
// should, so Enter alone never throws work away; a field has it where there is one, and Enter there is OK. Escape
// cancels, a click beside it does nothing, and the focus goes back where it was. On a phone it stands at the bottom,
// its keys the width of the thumb.
import { AlertDialogCancel, AlertDialogContent, AlertDialogOverlay, AlertDialogPortal, AlertDialogRoot, AlertDialogTitle } from "reka-ui";
import { computed, nextTick, ref, watch } from "vue";
import { answer, question } from "../composables/useConfirm";
import { t } from "../i18n";

const text = ref("");
const field = ref<HTMLInputElement | null>(null);
const typed = computed(() => question.value?.kind === "prompt" || question.value?.kind === "copy");
// A new question starts with its own text; a field takes the focus with all of it selected, after the dialog gave
// Cancel the focus.
watch(question, async (now) => {
  text.value = now && now.kind !== "confirm" ? now.value : "";
  if (!typed.value) return;
  await nextTick(); await nextTick();
  field.value?.focus();
  field.value?.select();
}, { immediate: true });
function ok() { answer(question.value?.kind === "prompt" ? text.value : true); }
function cancel() { answer(question.value?.kind === "prompt" ? null : false); }
</script>

<template>
  <AlertDialogRoot :open="Boolean(question)" @update:open="(open: boolean) => { if (!open) cancel(); }">
    <AlertDialogPortal>
      <AlertDialogOverlay class="confirm-dim" />
      <AlertDialogContent v-if="question" class="confirm" :aria-describedby="undefined" @keydown.enter="typed && ($event.preventDefault(), ok())">
        <AlertDialogTitle class="confirm-text">{{ question.message }}</AlertDialogTitle>
        <input v-if="typed" ref="field" v-model="text" class="confirm-field" type="text" spellcheck="false" autocomplete="off"
          :readonly="question.kind === 'copy'" :aria-label="question.message" />
        <div class="confirm-actions">
          <AlertDialogCancel v-if="question.kind !== 'copy'" class="btn quiet">{{ t("editor.common.cancel") }}</AlertDialogCancel>
          <button type="button" class="btn primary" @click="ok">{{ question.kind !== "copy" && question.confirm || t("editor.common.ok") }}</button>
        </div>
      </AlertDialogContent>
    </AlertDialogPortal>
  </AlertDialogRoot>
</template>

<style scoped>
.confirm-dim { position: fixed; inset: 0; z-index: 90; background: rgba(10, 12, 18, 0.32); animation: confirm-fade 0.14s ease-out; }
.confirm { position: fixed; z-index: 91; left: 50%; top: 50%; translate: -50% -50%; width: min(400px, calc(100vw - 32px)); padding: 20px;
  display: grid; gap: 16px; background: var(--surface); color: var(--ink); border: 1px solid var(--line); border-radius: 14px;
  box-shadow: var(--pop-shadow); animation: confirm-in 0.16s ease-out; }
.confirm:focus { outline: none; }
.confirm-text { margin: 0; font-size: 14px; font-weight: 500; line-height: 1.5; color: var(--ink); overflow-wrap: anywhere; }
.confirm-field { font-size: 13.5px; height: 34px; }
.confirm-field[readonly] { font-family: var(--mono); font-size: 12.5px; background: var(--surface-2); }
.confirm-actions { display: flex; justify-content: flex-end; gap: 8px; }
.confirm-actions .btn { min-width: 84px; padding: 8px 14px; font-size: 13px; }
@keyframes confirm-fade { from { opacity: 0; } }
@keyframes confirm-in { from { opacity: 0; scale: 0.97; } }
@media (max-width: 640px) {
  .confirm { top: auto; bottom: 12px; translate: -50% 0; width: calc(100vw - 24px); padding: 18px; }
  .confirm-actions .btn { flex: 1; min-height: 42px; }
}
@media (prefers-reduced-motion: reduce) { .confirm, .confirm-dim { animation: none; } }
</style>
