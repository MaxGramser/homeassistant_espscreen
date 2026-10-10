// The sidebar's width and whether it is folded to its icons (app 0.4.85): dragged by its edge, folded with its button.
// Kept per browser, as the library's state is: a convenience of this computer, not a setting of the screens.
import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { flagSerializer, usePreference } from "../composables/usePreference";

export const SIDE_MIN = 200, SIDE_MAX = 420, SIDE_DEFAULT = 248;
// The icons alone: the board icon, the dot beside it and the room around them.
export const SIDE_FOLDED = 60;
// Dragged narrower than this, the sidebar folds to its icons; out of its icons past it, it opens again.
const FOLD_AT = 140;

export const clampWidth = (px: number) => Math.round(Math.min(SIDE_MAX, Math.max(SIDE_MIN, px)));

export const useSidebarStore = defineStore("sidebar", () => {
  // The width and the fold as this browser keeps them (composables/usePreference.ts), each written as it changes.
  const width = usePreference("esp-screens.sidebar-width", SIDE_DEFAULT, { serializer: { read: (raw) => clampWidth(Number(raw) || SIDE_DEFAULT), write: String } });
  const folded = usePreference("esp-screens.sidebar-folded", false, { serializer: flagSerializer });
  // While its edge is held: the page lays nothing out again meanwhile.
  const resizing = ref(false);

  /** The width it takes on the page: its icons alone when folded. */
  const shownWidth = computed(() => (folded.value ? SIDE_FOLDED : width.value));
  function toggle() { folded.value = !folded.value; }
  /** The edge dragged to `px` from the window's left: a width between the bounds, or folded below FOLD_AT. */
  function drag(px: number) {
    if (px < FOLD_AT) { folded.value = true; return; }
    folded.value = false;
    width.value = clampWidth(px);
  }
  function reset() { folded.value = false; width.value = SIDE_DEFAULT; }

  return { width, folded, resizing, shownWidth, toggle, drag, reset };
});
