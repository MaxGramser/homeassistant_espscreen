// The screensaver's card and drawer (app 0.4.83): the card lists the steps with one line each, a step opens in the
// drawer, and the choice of the screen changes as it did.
import { flushPromises, mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SaverInspector from "../src/components/SaverInspector.vue";
import ScreensaverCard from "../src/components/ScreensaverCard.vue";
import { currentScreen, openSaverStep, state } from "../src/store";
import { summary } from "../src/saver";
import type { Inventory, ScreensaverView } from "../src/types";

const saver = (patch: Partial<ScreensaverView> = {}): ScreensaverView => ({
  show: true, media: "media_player.tv", more: ["media_player.speaker"], camera: "", order: ["media", "camera", "clock"], off: ["camera"],
  weather: "auto", items: [], ready: true, pictures: true, standby: true, ...patch,
});

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
  state.inventory = {
    screens: [{ id: "living", name: "Living", virtual: true, shape: { width: 480, height: 480 }, screensaver: saver() }],
    entities: [
      { id: "media_player.tv", name: "Apple TV", area: "Living room" }, { id: "media_player.speaker", name: "Speaker", area: "Living room" },
      { id: "media_player.kitchen", name: "Kitchen", area: "Kitchen" }, { id: "camera.door", name: "Front door", area: "Outside" },
      { id: "weather.home", name: "Home" }, { id: "lock.front", name: "Front lock" },
    ],
    builtin: [], header: { max_items: 6, builtin: [] },
  } as unknown as Inventory;
  state.selected = "living";
  state.inspector = null;
  state.tab = "settings";
});

const rows = (wrapper: ReturnType<typeof mount>) => wrapper.findAll(".saver-row").map((row) => `${row.find("b").text()}: ${row.find("small").text()}`);

describe("the screensaver card", () => {
  it("lists the steps in their order, each with one line of what it shows", () => {
    const wrapper = mount(ScreensaverCard);
    expect(wrapper.findAll(".saver-row").map((row) => row.attributes("data-kind"))).toEqual(["media", "camera", "clock"]);
    expect(rows(wrapper)).toEqual(["Music playing: Apple TV, Speaker", "Camera: Off", "Clock: Outside temperature"]);
    // No field in the card: the choices live in the drawer, so nothing can push the rows past a narrow card.
    expect(wrapper.find(".ui-select").exists()).toBe(false);
  });

  it("says what a step still lacks, and names the clock's temperature and entities", () => {
    currentScreen.value!.screensaver = saver({ media: "", more: [], off: [], weather: "", items: [{ type: "entity", entity: "lock.front", content: "state", icon: "auto", show: "always" }] });
    expect(summary("media")).toEqual({ text: "No player yet", missing: true });
    expect(summary("camera")).toEqual({ text: "No camera yet", missing: true });
    expect(summary("clock").text).toBe("Time and date, Front lock");
  });

  it("opens a step in the drawer on a click, and its switch turns it off without opening it", async () => {
    const wrapper = mount(ScreensaverCard);
    await wrapper.find('.saver-row[data-kind="media"] [role="switch"]').trigger("click");
    await flushPromises();
    expect(currentScreen.value!.screensaver!.off).toEqual(["camera", "media"]);
    expect(state.inspector).toBeNull();
    await wrapper.find('.saver-row[data-kind="clock"]').trigger("click");
    expect(state.inspector).toEqual({ kind: "saver", step: "clock" });
    expect(wrapper.find('.saver-row[data-kind="clock"]').classes()).toContain("opened");
  });

  it("moves a focused row with the arrow keys", async () => {
    const wrapper = mount(ScreensaverCard, { attachTo: document.body });
    const clock = wrapper.find('.saver-row[data-kind="clock"]');
    await clock.trigger("keydown", { key: "ArrowUp" });
    expect(currentScreen.value!.screensaver!.order).toEqual(["media", "clock", "camera"]);
  });

  it("shows the clock alone on a screen without pictures", () => {
    currentScreen.value!.screensaver = saver({ pictures: false });
    const wrapper = mount(ScreensaverCard);
    expect(wrapper.findAll(".saver-row").map((row) => row.attributes("data-kind"))).toEqual(["clock"]);
  });
});

describe("a step in the drawer", () => {
  it("lists the players in the order they are tried, and takes one out", async () => {
    const wrapper = mount(SaverInspector, { props: { step: "media" } });
    expect(wrapper.findAll(".saver-player").map((row) => row.find(".tx b").text())).toEqual(["Apple TV", "Speaker"]);
    expect(wrapper.findAll(".saver-rank").map((rank) => rank.text())).toEqual(["1", "2"]);
    await wrapper.findAll(".saver-player")[0].find("button.x").trigger("click");
    expect(currentScreen.value!.screensaver).toMatchObject({ media: "media_player.speaker", more: [] });
  });

  it("turns its step off and moves it a place later", async () => {
    const wrapper = mount(SaverInspector, { props: { step: "media" } });
    expect(wrapper.text()).toContain("1 of 3");
    await wrapper.find('.switch-row [role="switch"]').trigger("click");
    await flushPromises();
    expect(currentScreen.value!.screensaver!.off).toContain("media");
    await wrapper.find('button[aria-label="Try later"]').trigger("click");
    expect(currentScreen.value!.screensaver!.order).toEqual(["camera", "media", "clock"]);
  });

  it("shows the clock in the glass's own shape, without a temperature when none is chosen", async () => {
    currentScreen.value!.screensaver = saver({ weather: "" });
    const wrapper = mount(SaverInspector, { props: { step: "clock" } });
    const glass = wrapper.find(".saver-glass");
    expect((glass.element as HTMLElement).style.aspectRatio).toBe("480 / 480");
    expect(glass.find(".saver-glass-time").text()).toMatch(/\d/);
    expect(glass.find(".saver-glass-line").text()).toBe("");
  });

  it("closes when the layout comes back", async () => {
    openSaverStep("clock");
    state.tab = "layout";
    await nextTick();
    expect(state.inspector).toBeNull();
  });
});
