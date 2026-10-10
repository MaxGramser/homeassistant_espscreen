// A list whose rows are dragged into another order (the screensaver's steps, a top bar's items) follows the pointer on the
// whole page while a row is held. A drawer that closes in the middle of it (another tile chosen, Escape) lets go of the
// page: no listener on the document and no hold that still starts a drag after it is gone.
import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ScreensaverCard from "../src/components/ScreensaverCard.vue";
import TopbarInspector from "../src/components/TopbarInspector.vue";
import { openBar, state } from "../src/store";
import type { Inventory } from "../src/types";
import { seedLayout } from "./page-fixtures";
import { liveListeners } from "./helpers/browser";

// The pointer and touch listeners on the document (jsdom adds some of its own the first time a selector runs).
const following = (live: () => string[]) => live().filter((name) => /^(pointer|touch)/.test(name));
const press = (target: Element, pointerType: string) => target.dispatchEvent(Object.assign(
  new Event("pointerdown", { bubbles: true, cancelable: true }), { pointerId: 1, pointerType, button: 0, clientX: 10, clientY: 10 }));

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
  state.inventory = { screens: [{ id: "living", name: "Living", virtual: true, shape: { width: 480, height: 480 }, screensaver: {
    show: true, media: "", more: [], camera: "", order: ["media", "camera", "clock"], off: [], weather: "auto", items: [], ready: true,
    pictures: true, standby: true } }], entities: [], builtin: [], header: { max_items: 6, builtin: [] } } as unknown as Inventory;
  state.selected = "living";
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
    seedLayout({ title: "Living", tiles: [], header: { items: [{ type: "clock" }, { type: "date" }] } } as any);
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
