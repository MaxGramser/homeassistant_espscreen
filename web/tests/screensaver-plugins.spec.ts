// The screensaver's photos and the screensavers of plugins (app 0.4.89, plugin API 0.14): the photos step only where the
// screen takes it, a plugin's own steps added, moved and taken off, the plugin faces of the clock, the music and the
// photos, a step's entity and options, the folder chosen by browsing, and the whole choice sent to the add-on.
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import ScreensaverCard from "../src/components/ScreensaverCard.vue";
import SaverClock from "../src/components/SaverClock.vue";
import SaverGlass from "../src/components/SaverGlass.vue";
import SaverInspector from "../src/components/SaverInspector.vue";
import { i18n } from "../src/i18n";
import type { Plugin } from "../src/model/plugins";
import { useInspectorStore } from "../src/stores/inspector";
import { useInventoryStore } from "../src/stores/inventory";
import { usePluginsStore } from "../src/stores/plugins";
import { useScreenStore } from "../src/stores/screen";
import { PLUGIN_STEPS_MAX, useScreensaverStore } from "../src/stores/screensaver";
import type { Screen, ScreensaverView } from "../src/types";
import { fakeApi } from "./helpers/fake-api";

const t = (key: string, named: Record<string, unknown> = {}) => i18n.global.t(key, named);
const T = (key: string, named: Record<string, unknown> = {}) => t(`editor.screen_settings.screensaver.${key}`, named);

describe("a plugin clock screenshot", () => {
  it("isolates an interactive preview and sends current options only to its own frame", async () => {
    const { saver, plugins } = open();
    plugins.index = [{ ...radar, image: "api/plugins/radar/image?v=one" }];
    saver.setFace("clock", "plugin:radar.big");
    const glass = mount(SaverGlass, { props: { height: 150 }, attachTo: document.body });
    await flushPromises();
    const frame = glass.find("iframe");
    expect(frame.attributes("sandbox")).toBe("allow-scripts");
    expect(frame.attributes("src")).toBe("api/plugins/radar/image?v=one&saver=big&interactive=1");
    const target = (frame.element as HTMLIFrameElement).contentWindow!;
    const post = vi.spyOn(target, "postMessage");
    window.dispatchEvent(new MessageEvent("message", { source: window, data: { type: "tessera:preview-ready" } }));
    expect(post).not.toHaveBeenCalled();
    window.dispatchEvent(new MessageEvent("message", { source: target, data: { type: "tessera:preview-ready" } }));
    expect(post).toHaveBeenLastCalledWith(expect.objectContaining({ type: "tessera:preview", options: { bold: false }, size: { width: 800, height: 480 } }), "*");
    saver.setPluginOption("plugin:radar.big", "bold", true);
    await flushPromises();
    expect(post).toHaveBeenLastCalledWith(expect.objectContaining({ options: { bold: true } }), "*");
    expect(glass.find("img").exists()).toBe(false);
    glass.unmount();
  });
  it("loads the declared face through the app and falls back when the image is missing", async () => {
    const { saver, plugins } = open();
    plugins.index = [{ ...radar, image: "api/plugins/radar/image?v=one" }];
    saver.setFace("clock", "plugin:radar.big");
    const glass = mount(SaverGlass, { props: { height: 150 } });
    await flushPromises();
    expect(glass.find("img").attributes("src")).toBe("api/plugins/radar/image?v=one&saver=big");
    expect(glass.find(".saver-glass-icon").exists()).toBe(false);
    await glass.find("img").trigger("error");
    expect(glass.find("img").exists()).toBe(false);
    expect(glass.find(".saver-glass-icon").exists()).toBe(true);
    plugins.index = [{ ...radar, image: "api/plugins/radar/image?v=two" }];
    await flushPromises();
    expect(glass.find("img").attributes("src")).toContain("v=two");
  });
});

// A plugin with a step of its own of an entity (a radar of a weather entity), one without, and a face of each core step.
const radar: Plugin = {
  id: "radar", name: { en: "Rain radar" }, summary: { en: "" }, icon: "F0597", maintainer: "", tessera: true, version: "1.0.0", repo: "", license: "MIT",
  boards: "any", requires: {}, flash_kb: 10, permissions: { home_assistant: [], network: [] }, readme: { en: "" }, languages: ["en"], attributes: [],
  savers: [
    { id: "map", name: { en: "Radar map" }, icon: "F0596", step: "own", domains: ["weather"],
      options: [{ id: "zoom", kind: "number", label: { en: "Zoom" }, default: 6, min: 1, max: 10 }], example: { en: "Rain over your home" } },
    { id: "sky", name: { en: "Sky" }, step: "own" },
    { id: "big", name: { en: "Big time" }, icon: "F0150", step: "clock", options: [{ id: "bold", kind: "toggle", label: { en: "Bold" }, default: false }] },
    { id: "vinyl", name: { en: "Vinyl" }, step: "media" },
    { id: "frame", name: { en: "Frame" }, step: "photos", example: { en: "A wooden frame" } },
  ],
};

function open(patch: Partial<ScreensaverView> = {}, installed = true) {
  const screensaver: ScreensaverView = { show: true, media: "", camera: "", order: ["media", "photos", "camera", "clock"], off: [], weather: "", more: [], items: [],
    photos: { source: "", every: 60, order: "shuffle", fit: "auto" }, media_face: "", photos_face: "", plugins: {},
    ready: true, pictures: true, standby: true, photos_step: true, ...patch };
  useInventoryStore().inventory = { screens: [{ id: "hall", name: "Hall", online: true, layout: { title: "Hall", tiles: [] }, shape: { width: 800, height: 480 }, screensaver } as unknown as Screen],
    entities: [{ id: "weather.home", name: "Home", state: "", area: "Garden" }, { id: "weather.cabin", name: "Cabin", state: "", area: "" }, { id: "light.desk", name: "Desk", state: "", area: "" }],
    builtin: [], header: { max_items: 6, builtin: [] } } as any;
  useScreenStore().selected = "hall";
  const plugins = usePluginsStore();
  plugins.index = [radar];
  plugins.installed = installed ? { hall: [{ id: "radar", version: "1.0.0", source: "index", state: "active" }] } : {};
  useInspectorStore().inspector = null;
  const api = fakeApi({
    "PUT screens/:id/screensaver": ({ body }) => ({ screensaver: { ...body.screensaver } }),
    "GET screensaver/photos": ({ query }) => {
      const id = query.get("id") || "";
      if (!id) return { id: "", title: "Media", folders: [{ id: "media-source://media_source/local", title: "My media" }], photos: 0 };
      if (id === "media-source://media_source/local") return { id, title: "My media", folders: [{ id: `${id}/Holiday`, title: "Holiday 2026" }], photos: 0 };
      return { id, title: "Holiday 2026", folders: [], photos: 12 };
    },
  });
  return { saver: useScreensaverStore(), plugins, api, insp: useInspectorStore() };
}

describe("the photos step", () => {
  it("shows only where the board draws pictures and the firmware takes it, and keeps its place when hidden", () => {
    const { saver } = open();
    expect(saver.stepsShown(null)).toEqual(["media", "photos", "camera", "clock"]);
    useScreenStore().currentScreen!.screensaver!.photos_step = false;
    expect(saver.stepsShown(null)).toEqual(["media", "camera", "clock"]);
    // Moving the camera up past the music leaves the photos, which this screen does not show, where they were.
    saver.moveStep("camera", -1);
    expect(saver.savedOrder).toEqual(["camera", "photos", "media", "clock"]);
    expect(saver.stepPlace("media")).toEqual({ n: 2, count: 3 });
    useScreenStore().currentScreen!.screensaver!.pictures = false;
    expect(saver.stepsShown(null)).toEqual(["clock"]);
  });

  it("asks for a folder, then names it, and changes its pace, order and fit", async () => {
    const { saver } = open();
    expect(saver.summary("photos")).toEqual({ text: T("summary.photos_none"), missing: true });
    saver.setPhotos({ source: "media-source://media_source/local/Holiday" });
    // Named by its id at once, by Home Assistant's title once the add-on answers.
    expect(saver.summary("photos").text).toBe("Holiday");
    await flushPromises();
    expect(saver.summary("photos").text).toBe("Holiday 2026");
    saver.setPhotos({ every: 300, order: "in_order", fit: "whole", motion: "slow" });
    expect(saver.photos).toEqual({ source: "media-source://media_source/local/Holiday", every: 300, order: "in_order", fit: "whole", motion: "slow" });
  });

  it("is chosen by going down the media sources in its drawer", async () => {
    const { saver } = open();
    const wrapper = mount(SaverInspector, { props: { step: "photos" } });
    await flushPromises();
    const folders = () => wrapper.findAll(".saver-folders .item");
    expect(folders().map((row) => row.find(".tx").text())).toEqual(["My media"]);
    await folders()[0].trigger("click");
    await flushPromises();
    expect(wrapper.find("#saver-folder-choose").attributes("disabled")).toBeDefined();
    await folders()[0].trigger("click");
    await flushPromises();
    expect(wrapper.find(".saver-trail").text()).toContain("Holiday 2026");
    expect(wrapper.find("#saver-folder-count").text()).toBe("12 photos here");
    await wrapper.find("#saver-folder-choose").trigger("click");
    expect(saver.photos.source).toBe("media-source://media_source/local/Holiday");
    await flushPromises();
    expect(wrapper.find("#saver-folder").text()).toContain("Holiday 2026");
  });
});

describe("a plugin's own steps", () => {
  it("are offered from the plugins this screen runs, put before the clock, and moved like the screen's own", () => {
    const { saver, insp } = open();
    expect(saver.addableSteps.map((s) => s.key)).toEqual(["plugin:radar.map", "plugin:radar.sky"]);
    saver.addPluginStep("plugin:radar.map");
    expect(saver.savedOrder).toEqual(["media", "photos", "camera", "plugin:radar.map", "clock"]);
    expect(insp.inspector).toEqual({ kind: "saver", step: "plugin:radar.map" });
    expect([saver.stepLabel("plugin:radar.map"), saver.stepIcon("plugin:radar.map")]).toEqual(["Radar map", "F0596"]);
    expect(saver.addableSteps.map((s) => s.key)).toEqual(["plugin:radar.sky"]);
    saver.moveStep("plugin:radar.map", -1);
    expect(saver.savedOrder).toEqual(["media", "photos", "plugin:radar.map", "camera", "clock"]);
    saver.toggleStep("plugin:radar.map");
    expect(saver.saver?.off).toEqual(["plugin:radar.map"]);
  });

  it("keep at most four, and leave the order, the steps turned off and their options when removed", () => {
    const { saver, insp } = open({ order: ["media", "photos", "camera", "plugin:radar.a", "plugin:radar.b", "plugin:radar.c", "clock"] });
    saver.addPluginStep("plugin:radar.map");
    expect(saver.pluginSteps).toHaveLength(PLUGIN_STEPS_MAX);
    expect(saver.canAddStep).toBe(false);
    saver.addPluginStep("plugin:radar.sky");
    expect(saver.savedOrder).not.toContain("plugin:radar.sky");
    saver.toggleStep("plugin:radar.map", false);
    saver.setPluginOption("plugin:radar.map", "zoom", 8);
    expect(saver.saver?.plugins).toEqual({ "plugin:radar.map": { options: { zoom: 8 }, entity: "" } });
    insp.openSaverStep("plugin:radar.map");
    saver.removePluginStep("plugin:radar.map");
    expect([saver.savedOrder.includes("plugin:radar.map"), saver.saver?.off, saver.saver?.plugins]).toEqual([false, [], {}]);
    expect(insp.inspector).toBeNull();
  });

  it("ask for their entity, then name it, and say when their plugin left the screen", () => {
    const { saver } = open({ order: ["media", "photos", "camera", "plugin:radar.map", "plugin:radar.sky", "clock"] });
    expect(saver.summary("plugin:radar.map")).toEqual({ text: T("summary.plugin_entity"), missing: true });
    expect(saver.summary("plugin:radar.sky")).toEqual({ text: "Rain radar" });
    saver.setPluginEntity("plugin:radar.map", "weather.home");
    expect(saver.summary("plugin:radar.map")).toEqual({ text: "Home" });
    expect(saver.pluginValues("plugin:radar.map")).toEqual({ zoom: 6 });
    usePluginsStore().installed = {};
    expect(saver.summary("plugin:radar.map")).toEqual({ text: T("summary.plugin_gone"), missing: true });
  });

  it("show in the card with Add from plugins, and in their drawer with their entity, options and Remove", async () => {
    const { saver } = open({ order: ["media", "photos", "camera", "plugin:radar.map", "clock"] });
    const card = mount(ScreensaverCard);
    expect(card.findAll(".saver-row").map((row) => row.attributes("data-kind"))).toEqual(["media", "photos", "camera", "plugin:radar.map", "clock"]);
    expect(card.find('.saver-row[data-kind="plugin:radar.map"] b').text()).toBe("Radar map");
    expect(card.find("#saver-add-step").text()).toContain(T("plugin_add"));
    const drawer = mount(SaverInspector, { props: { step: "plugin:radar.map" } });
    expect(drawer.find("#saver-plugin-entity").exists()).toBe(true);
    expect(drawer.text()).toContain("Zoom");
    expect(drawer.text()).toContain("4 of 5");
    await drawer.find("#saver-plugin-remove").trigger("click");
    expect(saver.savedOrder).toEqual(["media", "photos", "camera", "clock"]);
  });
});

describe("plugin faces", () => {
  it("are offered per step, from the plugins this screen runs", () => {
    const { saver } = open();
    expect(saver.facesFor("clock").map((s) => s.key)).toEqual(["plugin:radar.big"]);
    expect(saver.facesFor("media").map((s) => s.key)).toEqual(["plugin:radar.vinyl"]);
    expect(saver.facesFor("photos").map((s) => s.key)).toEqual(["plugin:radar.frame"]);
    usePluginsStore().installed = {};
    expect(saver.facesFor("clock")).toEqual([]);
  });

  it("take the place of the screen's own face, keep their options, and go back to it", () => {
    const { saver } = open({ faces: true, face: "glass", media: "media_player.tv" });
    saver.setFace("clock", "plugin:radar.big");
    expect([saver.saver?.face, saver.clockPluginFace, saver.face]).toEqual(["plugin:radar.big", "plugin:radar.big", "digital"]);
    expect(saver.summary("clock").text).toBe(`Big time, ${T("summary.time_date")}`);
    saver.setPluginOption("plugin:radar.big", "bold", true);
    expect(saver.pluginValues("plugin:radar.big")).toEqual({ bold: true });
    saver.setFace("media", "plugin:radar.vinyl");
    saver.setFace("photos", "plugin:radar.frame");
    expect([saver.faceOf("media"), saver.faceOf("photos")]).toEqual(["plugin:radar.vinyl", "plugin:radar.frame"]);
    expect(saver.summary("media").text.startsWith("Vinyl, ")).toBe(true);
    saver.setFace("clock", "");
    expect([saver.saver?.face, saver.clockPluginFace]).toEqual(["digital", ""]);
    saver.setFace("media", "");
    expect(saver.saver?.media_face).toBe("");
  });

  it("stand beside the clock's own faces in its drawer, and as a choice of the music's face", async () => {
    const { saver } = open({ faces: true });
    const clock = mount(SaverClock, { props: { index: -1 } });
    expect(clock.findAll(".face-pick").map((pick) => pick.attributes("data-face"))).toEqual(["digital", "glass", "classic", "bauhaus", "plugin:radar.big"]);
    await clock.find('.face-pick[data-face="plugin:radar.big"]').trigger("click");
    expect(saver.saver?.face).toBe("plugin:radar.big");
    expect(clock.find('.face-pick[data-face="plugin:radar.big"]').attributes("aria-checked")).toBe("true");
    expect(clock.text()).toContain("Bold");
    // On a board without the module's faces the digital clock and the plugin's face.
    useScreenStore().currentScreen!.screensaver!.faces = false;
    await flushPromises();
    expect(clock.findAll(".face-pick").map((pick) => pick.attributes("data-face"))).toEqual(["digital", "plugin:radar.big"]);
    const music = mount(SaverInspector, { props: { step: "media" } });
    expect(music.find("#saver-step-face").exists()).toBe(true);
  });
});

describe("the choice sent to the add-on", () => {
  it("carries the photos, the faces of the steps and the plugins' settings", () => {
    const { saver, api } = open();
    saver.setPhotos({ source: "media-source://media_source/local/Holiday", every: 900 });
    saver.setFace("media", "plugin:radar.vinyl");
    saver.addPluginStep("plugin:radar.map");
    saver.setPluginEntity("plugin:radar.map", "weather.cabin");
    const sent = api.asked("PUT screens/:id/screensaver").at(-1)!.body.screensaver;
    expect(sent).toMatchObject({
      order: ["media", "photos", "camera", "plugin:radar.map", "clock"],
      photos: { source: "media-source://media_source/local/Holiday", every: 900, order: "shuffle", fit: "auto" },
      media_face: "plugin:radar.vinyl", photos_face: "",
      plugins: { "plugin:radar.map": { options: {}, entity: "weather.cabin" } },
    });
    expect(Object.keys(sent)).not.toContain("photos_step");
  });

  it("sends the photos' defaults for a screen listed with only the photos' flag", () => {
    const { saver, api } = open({ photos: true as never, photos_step: undefined });
    expect(saver.photosHere).toBe(true);
    saver.toggleStep("camera");
    expect(api.asked("PUT screens/:id/screensaver").at(-1)!.body.screensaver.photos).toEqual({ source: "", every: 60, order: "shuffle", fit: "auto" });
  });
});
