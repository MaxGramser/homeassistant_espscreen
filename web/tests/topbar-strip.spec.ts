// The top bar's inspector with the bar itself at its head (app 0.4.89): the bar in small is the way through it, and
// under it stands only the part chosen there. The bar stays while an item's icons, the things to add or the copy take
// the place under it; a page that opened its bar is the way back, and Escape goes one step out at a time.
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TopbarInspector from "../src/components/TopbarInspector.vue";
import PageInspector from "../src/components/PageInspector.vue";
import type { Inventory } from "../src/types";
import { loadLayout } from "./helpers/fixtures";
import { useScreenStore } from "../src/stores/screen";
import { useInventoryStore } from "../src/stores/inventory";
import { useDocumentStore } from "../src/stores/document";
import { useInspectorStore } from "../src/stores/inspector";

let insp: ReturnType<typeof useInspectorStore>;
let doc: ReturnType<typeof useDocumentStore>;
beforeEach(() => {
  insp = useInspectorStore();
  doc = useDocumentStore();
  vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
  useInventoryStore().inventory = { screens: [{ id: "living", name: "Living", virtual: true, dock: true, shape: { width: 480, height: 480 } }],
    entities: [{ id: "sensor.out", name: "Outside", state: "12", area: "" }], builtin: [],
    icons: { groups: [{ label: "Weather", icons: [{ name: "thermometer", label: "Thermometer", cp: "F050F" }] }], weather: {}, sun: {}, defaults: {}, fallback: "F0335", builtin: {}, controls: {} },
    header: { max_items: 16, builtin: [{ type: "clock", label: "Clock" }, { type: "date", label: "Date" }],
      contents: [{ key: "state", label: "State" }, { key: "icon", label: "Icon" }], shows: [{ key: "always", label: "Always" }] } } as unknown as Inventory;
  useScreenStore().selected = "living";
  loadLayout({ title: "Living", pages: 2, tiles: [], header: { items: [{ type: "clock" }, { type: "entity", entity: "sensor.out" }] } } as any);
});
const drawer = () => {
  const kind = insp.inspector?.kind;
  return mount(TopbarInspector, { props: { index: insp.inspector?.kind === "bar" ? insp.inspector.index : -1, adding: kind === "bar-add" } });
};

describe("the top bar at the head of its inspector", () => {
  it("shows the left side, every item and a place to add, and only the chosen part under it", async () => {
    insp.openBar(-1, 0);
    let view = drawer();
    expect(view.findAll(".bar-strip .strip-item")).toHaveLength(2);
    expect(view.find(".strip-left").attributes("data-state")).toBe("active");
    expect(view.find(".bar-part .nav-row").exists()).toBe(true);
    // No list of items under the bar any more, and no second head.
    expect(view.find(".items").exists()).toBe(false);
    insp.openBar(1, 0);
    view = drawer();
    expect(view.find(".strip-item[data-index='1']").attributes("data-state")).toBe("active");
    expect(view.find(".bar-cap b").text()).toBe("Outside");
    expect(view.find(".bar-part .nav-row").exists()).toBe(false);
    expect(view.find(".dr-foot").exists()).toBe(true);
  });

  it("puts an item's icons in the place of its settings, with the bar still above, and Done or Escape ends it", async () => {
    insp.openBar(1, 0);
    const view = drawer();
    await view.find(".bar-part .choice-field").trigger("click");
    expect(insp.iconPickerOpen).toBe(true);
    expect(view.find(".bar-part > .picker").exists()).toBe(true);
    expect(view.find(".bar-part .seg").exists()).toBe(false);
    expect(view.find(".bar-strip").exists()).toBe(true);
    expect(view.find(".dr-foot").exists()).toBe(false);
    await view.find(".bar-part .icon-grid button").trigger("click");
        expect(doc.document!.pages[0].topbar.trailing[1].icon).toBe("thermometer");
    // The choice stays open to compare another; Escape closes it and keeps the inspector.
    expect(insp.iconPickerOpen).toBe(true);
    insp.escape();
    expect(insp.iconPickerOpen).toBe(false);
    expect(insp.inspector).toEqual({ kind: "bar", index: 1 });
  });

  it("adds under the bar, and Escape goes back to the bar instead of closing", async () => {
    insp.openBar(-1, 0);
    insp.openBarAdd();
    const view = drawer();
    expect(view.find(".strip-add").attributes("data-state")).toBe("active");
    expect(view.find(".bar-part .topbar-add").exists()).toBe(true);
    insp.escape();
    expect(insp.inspector).toEqual({ kind: "bar", index: -1 });
  });

  it("wraps many items onto lines under the title, with how many places are taken", () => {
    const items = Array.from({ length: 8 }, (_, i) => ({ type: "entity", entity: `sensor.s${i}` }));
    loadLayout({ title: "Living", tiles: [], header: { items } } as any);
    insp.openBar(-1, 0);
    const view = drawer();
    expect(view.find(".bar-strip").classes()).toContain("wrap");
    expect(view.find(".strip-count").text()).toBe("8 of 16 items");
  });
});

describe("the way back from a top bar to its page", () => {
  it("leads to the page that opened the bar, with the part of the page it left", async () => {
    const id = doc.document!.pages[1].id;
    insp.openPage(id);
    const page = mount(PageInspector, { props: { id } });
    await page.find("#page-part-dock").trigger("click");
    expect(insp.pagePart).toBe("dock");
    await page.find("#page-edit-topbar").trigger("click");
    expect(insp.inspector).toEqual({ kind: "bar", index: -1 });
    expect(doc.barPage).toBe(1);
    // Moving through the bar keeps the way back.
    insp.openBar(0);
    insp.openBarAdd();
    insp.openBar(-1);
    const view = drawer();
    expect(view.find("#inspector-back").text()).toContain("Page 2");
    expect(view.find(".dr-head .crumbs").exists()).toBe(false);
    await view.find("#inspector-back").trigger("click");
    expect(insp.inspector).toEqual({ kind: "page", id });
    expect(insp.pagePart).toBe("dock");
    // Escape goes the same way; a bar opened by itself has no way back and Escape closes it.
    insp.openBar(-1, 1);
    insp.escape();
    expect(insp.inspector).toEqual({ kind: "page", id });
    insp.closeInspector();
    insp.openBar(-1, 1);
    expect(insp.back).toBeNull();
    await nextTick();
    insp.escape();
    expect(insp.inspector).toBeNull();
  });
});
