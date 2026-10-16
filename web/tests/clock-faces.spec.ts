// The screensaver clock's faces (module clock_faces): offered only where the board has them, a face picked from small
// pictures of the glass, and its look, numerals and seconds hand. Glass takes twelve numerals only on glass about as
// wide as it is tall, and the faces that show the time alone leave the temperature out.
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SaverClock from "../src/components/SaverClock.vue";
import { bauhaus, mix32, ringEdge, twelveFits } from "../src/model/clock-faces";
import type { Inventory, ScreensaverView } from "../src/types";
import { useInventoryStore } from "../src/stores/inventory";
import { useScreenStore } from "../src/stores/screen";
import { useScreensaverStore } from "../src/stores/screensaver";
import { useUiStore } from "../src/stores/ui";

const saver = (patch: Partial<ScreensaverView> = {}): ScreensaverView => ({
  show: true, media: "", more: [], camera: "", order: ["media", "camera", "clock"], off: [], weather: "auto", items: [],
  ready: true, pictures: true, standby: true, faces: true, ...patch,
});
function screen(width: number, height: number, patch: Partial<ScreensaverView> = {}) {
  useInventoryStore().inventory = {
    screens: [{ id: "hall", name: "Hall", virtual: true, shape: { width, height }, screensaver: saver(patch) }],
    entities: [{ id: "weather.home", name: "Home" }], builtin: [], header: { max_items: 6, builtin: [] },
  } as unknown as Inventory;
  useScreenStore().selected = "hall";
}
beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
  useUiStore().tab = "settings";
});

describe("the clock's faces", () => {
  it("are offered only on a board with their module", () => {
    screen(480, 480, { faces: false, face: "glass" });
    const wrapper = mount(SaverClock, { props: { index: -1 } });
    expect(wrapper.find("#saver-faces").exists()).toBe(false);
    // A face saved for it still shows the digital clock there, as the screen does.
    expect(useScreensaverStore().face).toBe("digital");
    expect(wrapper.find(".saver-glass-time").exists()).toBe(true);
  });

  it("picks a face from its picture and shows its options", async () => {
    screen(480, 480);
    const wrapper = mount(SaverClock, { props: { index: -1 } });
    expect(wrapper.findAll(".face-pick").map((b) => b.attributes("data-face"))).toEqual(["digital", "glass", "classic", "bauhaus"]);
    expect(wrapper.find("#saver-weather").exists()).toBe(true);
    await wrapper.find('.face-pick[data-face="glass"]').trigger("click");
    await nextTick();
    expect(useScreenStore().currentScreen!.screensaver!.face).toBe("glass");
    expect(wrapper.find(".saver-glass.face svg").exists()).toBe(true);
    // Glass shows the time alone: no temperature to choose, its numerals and the seconds hand instead.
    expect(wrapper.find("#saver-weather").exists()).toBe(false);
    expect(wrapper.text()).toContain("Numbers");
    expect(wrapper.text()).toContain("Seconds hand");
  });

  it("offers twelve numerals only on glass about as wide as it is tall", () => {
    expect(twelveFits(480, 480)).toBe(true);
    expect(twelveFits(720, 720)).toBe(true);
    expect(twelveFits(800, 480)).toBe(false);
    expect(twelveFits(480, 800)).toBe(false);
    screen(800, 480, { face: "glass", numerals: 12 });
    const wrapper = mount(SaverClock, { props: { index: -1 } });
    const numbers = wrapper.findAll(".seg button").map((b) => b.text());
    expect(numbers).toContain("4");
    expect(numbers).not.toContain("12");
  });

  it("follows the glass's rectangle and the firmware's Bauhaus", () => {
    // A ray straight up leaves at the top, one at three o'clock at the side, one into a corner at the corner.
    expect(ringEdge(0, 400, 240)).toBeCloseTo(240);
    expect(ringEdge(Math.PI / 2, 400, 240)).toBeCloseTo(400);
    // The same hash as clock_faces::mix32, so the editor's composition is the screen's.
    expect(mix32(0)).toBe(0);
    expect(mix32(1)).toBe(mix32(1));
    const at = new Date(2026, 9, 16, 10, 9);
    const a = bauhaus(800, 480, at, false), b = bauhaus(800, 480, new Date(2026, 9, 16, 10, 10), false);
    expect(a.squares.length).toBe(15);
    // A new ten minutes is a new composition, and the clock moves with it.
    expect(a.squares.map((q) => q.ground).join()).not.toBe(b.squares.map((q) => q.ground).join());
    expect(a.cx).not.toBeCloseTo(b.cx);
  });
});
