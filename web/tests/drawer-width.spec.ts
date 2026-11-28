// The inspector's width (stores/drawer.ts): dragged between its bounds, kept per browser, back to its width on reset.
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import { clampDrawer, DRAWER_DEFAULT, DRAWER_MAX, DRAWER_MIN, useDrawerStore } from "../src/stores/drawer";

describe("the inspector's width", () => {
  beforeEach(() => { localStorage.clear(); setActivePinia(createPinia()); });
  it("stays between its bounds", () => {
    expect(clampDrawer(10)).toBe(DRAWER_MIN);
    expect(clampDrawer(5000)).toBe(DRAWER_MAX);
    expect(clampDrawer(500.4)).toBe(500);
  });
  it("is dragged, kept and reset", () => {
    const drawer = useDrawerStore();
    expect(drawer.width).toBe(DRAWER_DEFAULT);
    drawer.drag(560);
    expect(drawer.width).toBe(560);
    setActivePinia(createPinia());
    expect(useDrawerStore().width).toBe(560);
    useDrawerStore().reset();
    expect(useDrawerStore().width).toBe(DRAWER_DEFAULT);
  });
});
