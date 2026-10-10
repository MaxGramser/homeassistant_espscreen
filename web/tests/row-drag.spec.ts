// A list whose rows are dragged into another order (the screensaver's steps, a top bar's items) follows the pointer on the
// whole page while a row is held. A drawer that closes in the middle of it (another tile chosen, Escape) lets go of the
// page: no listener on the document and no hold that still starts a drag after it is gone.
import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ScreensaverCard from "../src/components/ScreensaverCard.vue";
import TopbarInspector from "../src/components/TopbarInspector.vue";
import { openBar, state } from "../src/store";
import type { Inventory } from "../src/types";
import { loadLayout } from "./helpers/fixtures";
import { liveListeners } from "./helpers/browser";
import { useScreenStore } from "../src/stores/screen";
import { useInventoryStore } from "../src/stores/inventory";
import { useDocumentStore } from "../src/stores/document";

let doc: ReturnType<typeof useDocumentStore>;
beforeEach(() => { doc = useDocumentStore(); });

// The pointer and touch listeners on the document (jsdom adds some of its own the first time a selector runs).
const following = (live: () => string[]) => live().filter((name) => /^(pointer|touch)/.test(name));
const press = (target: Element, pointerType: string) => target.dispatchEvent(Object.assign(
  new Event("pointerdown", { bubbles: true, cancelable: true }), { pointerId: 1, pointerType, button: 0, clientX: 10, clientY: 10 }));

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
  useInventoryStore().inventory = { screens: [{ id: "living", name: "Living", virtual: true, shape: { width: 480, height: 480 }, screensaver: {
    show: true, media: "", more: [], camera: "", order: ["media", "camera", "clock"], off: [], weather: "auto", items: [], ready: true,
    pictures: true, standby: true } }], entities: [], builtin: [], header: { max_items: 6, builtin: [] } } as unknown as Inventory;
  useScreenStore().selected = "living";
});

describe("a dragged list that closes while a row is held", () => {
  it.each(["touch", "mouse"])("the screensaver's steps let go of the page (%s)", async (pointer) => {
    const tracked = liveListeners(document), live = () => following(tracked);
    const card = mount(ScreensaverCard, { attachTo: document.body });
    press(card.find('.saver-row[data-kind="clock"]').element, pointer);
    expect(live()).toEqual(["pointercancel", "pointermove", "pointerup"]);
    card.unmount();
    expect(live()).toEqual([]);
    // The hold a finger starts would have begun the drag after the drawer was gone, and held the page's scrolling.
    await vi.advanceTimersByTimeAsync(1000);
    expect(live()).toEqual([]);
  });

  it.each(["touch", "mouse"])("a top bar's items let go of the page (%s)", async (pointer) => {
    loadLayout({ title: "Living", tiles: [], header: { items: [{ type: "clock" }, { type: "date" }] } } as any);
    openBar(0);
    const tracked = liveListeners(document), live = () => following(tracked);
    const drawer = mount(TopbarInspector, { props: { index: 0 }, attachTo: document.body });
    press(drawer.find(".items .item[data-index='1']").element, pointer);
    expect(live()).toEqual(["pointercancel", "pointermove", "pointerup"]);
    drawer.unmount();
    expect(live()).toEqual([]);
    await vi.advanceTimersByTimeAsync(1000);
    expect(live()).toEqual([]);
  });
});

describe("a top bar's items dragged into another order", () => {
  it("takes the place the pointer passed, keeps the drawer on the item, and is no click when let go", async () => {
    loadLayout({ title: "Living", tiles: [], header: { items: [{ type: "clock" }, { type: "date" }, { type: "analog" }] } } as any);
    openBar(0);
    const drawer = mount(TopbarInspector, { props: { index: 0 }, attachTo: document.body });
    drawer.findAll(".items .item[data-index]").forEach((row, i) => {
      row.element.getBoundingClientRect = () => ({ top: i * 40, height: 40, bottom: i * 40 + 40, left: 0, right: 200, width: 200 }) as DOMRect;
    });
    const at = (y: number, type: string) => Object.assign(new Event(type, { bubbles: true, cancelable: true }), { pointerId: 1, pointerType: "mouse", button: 0, clientX: 10, clientY: y });
    drawer.find(".items .item[data-index='0']").element.dispatchEvent(at(10, "pointerdown"));
    document.dispatchEvent(at(70, "pointermove"));
    expect(state.inspector).toEqual({ kind: "bar", index: 1 });
    document.dispatchEvent(at(70, "pointerup"));
    expect(doc.document!.pages[0].topbar.trailing.map((item) => item.type)).toEqual(["date", "clock", "analog"]);
    // The click the browser sends after the drag opens nothing.
    await drawer.find(".items .item[data-index='0']").trigger("click");
    expect(state.inspector).toEqual({ kind: "bar", index: 1 });
  });
});
