// The sidebar's width and whether it is folded to its icons (app 0.4.85): dragged by its edge, folded with its button.
// Kept per browser, as the library's state is: a convenience of this computer, not a setting of the screens.
import { reactive } from "vue";
import { flagSerializer, renewable, usePreference } from "./composables/usePreference";
import { onReset } from "./resets";

export const SIDE_MIN = 200, SIDE_MAX = 420, SIDE_DEFAULT = 248;
// The icons alone: the board icon, the dot beside it and the room around them.
export const SIDE_FOLDED = 60;
// Dragged narrower than this, the sidebar folds to its icons; out of its icons past it, it opens again.
const FOLD_AT = 140;

export const clampWidth = (px: number) => Math.round(Math.min(SIDE_MAX, Math.max(SIDE_MIN, px)));

// The width and the fold as this browser keeps them (composables/usePreference.ts), each written as it changes.
const preferences = renewable(() => ({
  width: usePreference("esp-screens.sidebar-width", SIDE_DEFAULT, { serializer: { read: (raw) => clampWidth(Number(raw) || SIDE_DEFAULT), write: String } }),
  folded: usePreference("esp-screens.sidebar-folded", false, { serializer: flagSerializer }),
}));
export const sidebar = reactive({ ...preferences(), resizing: false });
onReset(() => Object.assign(sidebar, preferences(), { resizing: false }));

export const sideWidth = () => (sidebar.folded ? SIDE_FOLDED : sidebar.width);
export function toggleSidebar() { sidebar.folded = !sidebar.folded; }
/** The edge dragged to `px` from the window's left: a width between the bounds, or folded below FOLD_AT. */
export function dragSidebar(px: number) {
  if (px < FOLD_AT) { sidebar.folded = true; return; }
  sidebar.folded = false;
  sidebar.width = clampWidth(px);
}
export function resetSidebar() { sidebar.folded = false; sidebar.width = SIDE_DEFAULT; }
