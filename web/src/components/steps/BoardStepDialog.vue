<script setup lang="ts">
// A step of a screen's board in a window of its own (Reka UI's Dialog): the page of BoardStepView.vue, opened from the
// card above a screen and from the screen's menu. Later is kept by the add-on (the card then stays away); closing the
// window keeps nothing.
import { DialogClose, DialogContent, DialogOverlay, DialogPortal, DialogRoot, DialogTitle } from "reka-ui";
import { send } from "../../api";
import { t } from "../../i18n";
import { useInventoryStore } from "../../stores/inventory";
import { useUiStore } from "../../stores/ui";
import type { BoardStep, Screen } from "../../types";
import Icon from "../ui/Icon.vue";
import BoardStepView from "./BoardStepView.vue";

const props = defineProps<{ open: boolean; step: BoardStep | null; screen: Screen }>();
const emit = defineEmits<{ "update:open": [open: boolean] }>();
const inv = useInventoryStore(), ui = useUiStore();
async function later() {
  emit("update:open", false);
  if (!props.step || props.step.state !== "open") return;
  try {
    await send(`screens/${encodeURIComponent(props.screen.id)}/steps/${encodeURIComponent(props.step.id)}`, "POST", { answer: "later" });
    await inv.refresh(false);
  } catch (error) {
    ui.toast((error as Error).message);
  }
}
</script>

<template>
  <DialogRoot :open="open && !!step" @update:open="(value: boolean) => emit('update:open', value)">
    <DialogPortal>
      <DialogOverlay class="step-window-dim" />
      <DialogContent class="step-window ob" id="board-step-window" :aria-describedby="undefined" @interact-outside.prevent>
        <DialogTitle class="sr-only">{{ step ? t(`editor.steps.${step.id}.title`) : "" }}</DialogTitle>
        <DialogClose class="ob-close step-window-close" :aria-label="t('editor.common.close')"><Icon name="close" /></DialogClose>
        <BoardStepView v-if="step" :step="step" :screen="screen" :continue-label="t('editor.common.close')" @later="later" @next="emit('update:open', false)" />
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<style>
/* Above the page and the palette (70), below what opens from it (a toast 85, a confirm 90), as the wizard's window. */
.step-window-dim { position: fixed; inset: 0; z-index: 74; background: var(--dim); }
.step-window { position: fixed; z-index: 75; top: 50%; left: 50%; transform: translate(-50%, -50%); width: min(680px, calc(100vw - 32px)); max-height: calc(100vh - 48px);
  overflow-y: auto; box-sizing: border-box; padding: 36px 32px 0; border-radius: 22px; background: var(--surface); box-shadow: 0 24px 80px rgba(0, 0, 0, 0.28); flex: none; }
.step-window h1 { font-size: 28px; }
.step-window .ob-go { min-width: 240px; }
.step-window-close { position: absolute; top: 14px; right: 14px; }
</style>
