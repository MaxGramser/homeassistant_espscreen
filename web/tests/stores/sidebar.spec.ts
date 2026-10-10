// The sidebar's width and fold (app 0.4.85): bounded, folded when dragged past the narrowest, kept per browser.
import { describe, expect, it } from "vitest";
import { nextTick } from "vue";
import { SIDE_DEFAULT, SIDE_FOLDED, SIDE_MAX, SIDE_MIN, useSidebarStore } from "../../src/stores/sidebar";
import { freshPinia } from "../helpers/pinia";

describe("the sidebar's edge", () => {
  it("keeps its width within bounds, folds past the narrowest and opens again when dragged out", async () => {
    const sidebar = useSidebarStore();
    sidebar.drag(1000);
    expect(sidebar.shownWidth).toBe(SIDE_MAX);
    sidebar.drag(150);
    expect([sidebar.folded, sidebar.shownWidth]).toEqual([false, SIDE_MIN]);
    sidebar.drag(90);
    expect([sidebar.folded, sidebar.shownWidth]).toEqual([true, SIDE_FOLDED]);
    sidebar.drag(300);
    expect([sidebar.folded, sidebar.shownWidth]).toEqual([false, 300]);
    await nextTick();
    expect(localStorage.getItem("esp-screens.sidebar-width")).toBe("300");
  });
  it("folds and unfolds with its button, keeping the width it had", async () => {
    const sidebar = useSidebarStore();
    sidebar.drag(320);
    sidebar.toggle();
    expect(sidebar.shownWidth).toBe(SIDE_FOLDED);
    await nextTick();
    expect(localStorage.getItem("esp-screens.sidebar-folded")).toBe("1");
    sidebar.toggle();
    expect(sidebar.shownWidth).toBe(320);
    sidebar.reset();
    expect([sidebar.folded, sidebar.shownWidth]).toEqual([false, SIDE_DEFAULT]);
  });
  it("starts with what this browser kept, a width out of bounds brought back within them", () => {
    localStorage.setItem("esp-screens.sidebar-width", "9999");
    localStorage.setItem("esp-screens.sidebar-folded", "1");
    freshPinia();
    const sidebar = useSidebarStore();
    expect([sidebar.width, sidebar.folded, sidebar.shownWidth]).toEqual([SIDE_MAX, true, SIDE_FOLDED]);
    localStorage.setItem("esp-screens.sidebar-folded", "0");
    freshPinia();
    expect(useSidebarStore().shownWidth).toBe(SIDE_MAX);
  });
});
