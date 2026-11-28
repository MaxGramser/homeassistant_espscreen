// The inspector's width (app dev): dragged by its left edge as the sidebar is by its right one, kept per browser as the
// sidebar's width is (stores/sidebar.ts). A template tile's code field and its completion read better in a wider one.
import { defineStore } from "pinia";
import { ref } from "vue";
import { usePreference } from "../composables/usePreference";

export const DRAWER_MIN = 340, DRAWER_MAX = 720, DRAWER_DEFAULT = 380;
export const clampDrawer = (px: number) => Math.round(Math.min(DRAWER_MAX, Math.max(DRAWER_MIN, px)));

export const useDrawerStore = defineStore("drawer", () => {
  const width = usePreference("esp-screens.drawer-width", DRAWER_DEFAULT, { serializer: { read: (raw) => clampDrawer(Number(raw) || DRAWER_DEFAULT), write: String } });
  // While its edge is held: the inspector follows the pointer without its glide.
  const resizing = ref(false);
  function drag(px: number) { width.value = clampDrawer(px); }
  function reset() { width.value = DRAWER_DEFAULT; }
  return { width, resizing, drag, reset };
});
