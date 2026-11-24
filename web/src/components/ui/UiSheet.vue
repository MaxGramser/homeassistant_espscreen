<script setup lang="ts">
// A sheet from the bottom of a phone (Reka UI's Dialog, not modal): the look of the phone's other sheets (a grab, a
// rounded top, the safe area below), with the page above it still there to see and to touch. It rides on the on-screen
// keyboard: while one is up the sheet stands on it and takes the room above it (the visual viewport), so a field in it
// stays in sight. `low` lets it rest at a lower height, so more of the page shows; a tap on the grab gives it the other
// height, and another gives it back. A field in it is 16 px or more, so focusing it never zooms the page.
// It lies above the phone's dock (25) and its other sheets (41), below a picker or menu (.ui-popover, 80), a toast (85)
// and a confirm (90).
// Layoutbot's chat is its first user; the phone's other sheets, still built by hand, are its next (docs/LAYOUTBOT.md).
import { useEventListener } from "@vueuse/core";
import { DialogContent, DialogPortal, DialogRoot, DialogTitle } from "reka-ui";
import { computed, ref, watch } from "vue";
import { t } from "../../i18n";

const props = defineProps<{ open: boolean; title: string; low?: boolean }>();
const emit = defineEmits<{ "update:open": [open: boolean] }>();

// What the keyboard covers of the window's bottom, and the room left above it.
const covered = ref(0), room = ref(window.innerHeight);
function measure() {
  const view = window.visualViewport;
  room.value = view ? view.height : window.innerHeight;
  covered.value = view ? Math.max(0, Math.round(window.innerHeight - view.height - view.offsetTop)) : 0;
}
measure();
if (window.visualViewport) {
  useEventListener(window.visualViewport, "resize", measure);
  useEventListener(window.visualViewport, "scroll", measure);
}
useEventListener(window, "resize", measure);
const typing = computed(() => covered.value > 80);

// A tap on the grab gives it the other height; when the caller asks anew (`low` changes), the caller's height counts again.
const flipped = ref(false);
watch(() => props.low, () => { flipped.value = false; });
const resting = computed(() => props.low !== flipped.value && !typing.value);
const style = computed(() => ({
  bottom: `${covered.value}px`,
  maxHeight: `${Math.round(resting.value ? Math.min(room.value * 0.46, 420) : room.value - 12)}px`,
}));
</script>

<template>
  <DialogRoot :open="open" :modal="false" @update:open="(value: boolean) => emit('update:open', value)">
    <DialogPortal>
      <DialogContent class="phone-sheet ui-sheet" :class="{ typing, resting }" :style="style" :aria-describedby="undefined"
        @interact-outside.prevent @open-auto-focus.prevent>
        <button type="button" class="ui-sheet-grab" :aria-label="t(resting ? 'editor.common.expand' : 'editor.common.collapse')"
          :aria-expanded="!resting" @click="flipped = !flipped"><span class="sheet-grab"></span></button>
        <DialogTitle class="sr-only">{{ title }}</DialogTitle>
        <slot :resting="resting" :typing="typing" />
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<style scoped>
.ui-sheet { z-index: 62; padding-bottom: 0; transition: max-height .28s cubic-bezier(.2, .8, .2, 1); overflow: hidden; }
.ui-sheet:not(.typing) { padding-bottom: var(--safe-bottom); }
.ui-sheet.typing { border-radius: 18px 18px 0 0; transition: none; }
.ui-sheet-grab { display: block; width: 100%; height: 22px; padding: 0; border: 0; background: none; cursor: pointer; flex: none; }
.ui-sheet-grab .sheet-grab { margin: 8px auto 0; }
@media (prefers-reduced-motion: reduce) { .ui-sheet { transition: none; } }
</style>
