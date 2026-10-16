<script lang="ts">
import { ref } from "vue";
// Whether the press under way is a finger's or a pen's: one listener on the window for every menu, so the thing's own
// press (a drag, a tab) stays its own.
const finger = ref(false);
let following = false;
function follow() {
  if (following || typeof window === "undefined") return;
  following = true;
  window.addEventListener("pointerdown", (e) => { finger.value = e.pointerType !== "mouse"; }, { capture: true, passive: true });
}
</script>

<script setup lang="ts">
// The menu on the right mouse button (Reka UI): the thing it belongs to is the slot, the items are UiMenuItem,
// UiMenuLabel, UiMenuSeparator and UiMenuSub in the `menu` slot. The editor's rule (docs/PAGES.md, "Menus"): it is the
// same menu as the thing's ··· and comes from the same component, so the two never differ. It is the mouse's alone: a
// finger held on a tile or a bar item drags it, and the ··· stays the way to the menu on a touch screen. Reka's own
// hold to open and the menu a long press sends both wait for a mouse.
import { ContextMenuContent, ContextMenuPortal, ContextMenuRoot, ContextMenuTrigger } from "reka-ui";
defineProps<{ width?: string; disabled?: boolean }>();
const open = defineModel<boolean>("open", { default: false });
follow();
// A closed menu gives the focus back to its thing once it has faded. A menu opened on something else meanwhile has the
// focus by then, and taking it closed that menu at once: it keeps it.
function closeFocus(e: Event) { if (document.activeElement?.closest("[role='menu']")) e.preventDefault(); }
</script>

<template>
  <ContextMenuRoot v-model:open="open" :modal="false">
    <ContextMenuTrigger as-child :disabled="disabled || finger"><slot /></ContextMenuTrigger>
    <ContextMenuPortal>
      <ContextMenuContent class="ui-popover ui-menu" :style="width ? { minWidth: width } : undefined" :collision-padding="8" @close-auto-focus="closeFocus">
        <slot name="menu" />
      </ContextMenuContent>
    </ContextMenuPortal>
  </ContextMenuRoot>
</template>
