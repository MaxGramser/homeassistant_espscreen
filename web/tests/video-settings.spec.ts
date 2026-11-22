// Settings, Video in Home Assistant (AppSettingsView, screen_video.py): Install writes the tessera_video integration only
// when pressed, Restart Home Assistant shows while Home Assistant has not loaded what was written, and it restarts
// nothing without the person's yes. The routes themselves are tests/test_screen_video.py's Endpoint.
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import AppSettingsView from "../src/components/AppSettingsView.vue";
import { useInventoryStore } from "../src/stores/inventory";
import type { Inventory, VideoIntegration } from "../src/types";
import { answerDialogs } from "./helpers/dialogs";
import { fakeApi } from "./helpers/fake-api";
import { router } from "../src/router";

const PATH = "/homeassistant/custom_components/tessera_video";
function video(extra: Partial<VideoIntegration> = {}): VideoIntegration {
  return { path: PATH, installed: false, current: false, version: "1.0.0", loaded: null, screens: [], entries: 0, ...extra };
}
beforeEach(async () => {
  // Video is in the Home Assistant part of Settings (#/settings/home-assistant).
  await router.push("/settings/home-assistant");
  useInventoryStore().inventory = {
    csrf: "t", screens: [], entities: [], updates: { target: "0.4.97", pending: 0 }, editor_features: { plugins: true }, video: video(),
  } as unknown as Inventory;
});

describe("Video in Home Assistant", () => {
  it("installs on Install, then offers the restart that loads it", async () => {
    const api = fakeApi({ "POST video": video({ installed: true, current: true, restart: true }) });
    const view = mount(AppSettingsView);
    expect(view.find("#video-install").text()).toBe("Install in Home Assistant");
    expect(view.find("#video-restart").exists()).toBe(false);
    expect(api.count()).toBe(0);
    await view.find("#video-install").trigger("click");
    await flushPromises();
    expect(api.count("POST video")).toBe(1);
    expect(view.find("#video-status").text()).toBe("Installed · restart Home Assistant to load it");
    expect(view.find("#video-restart").exists()).toBe(true);
  });

  it("restarts Home Assistant only after the person's yes", async () => {
    useInventoryStore().inventory.video = video({ installed: true, current: true });
    const api = fakeApi({ "POST video/restart": { restarting: true } });
    const view = mount(AppSettingsView);
    let yes = false;
    const asked = answerDialogs(() => yes);
    await view.find("#video-restart").trigger("click");
    await flushPromises();
    expect(asked).toEqual([{
      kind: "confirm", confirm: "Restart Home Assistant",
      message: "Restart Home Assistant now? It is away for a minute or two, and so are its dashboards and automations.",
    }]);
    expect(api.count("POST video/restart")).toBe(0);
    yes = true;
    await view.find("#video-restart").trigger("click");
    await flushPromises();
    expect(api.count("POST video/restart")).toBe(1);
  });

  it("says it runs once Home Assistant loaded this version, with no restart left to offer", () => {
    useInventoryStore().inventory.video = video({ installed: true, current: true, loaded: "1.0.0", screens: ["Tablet"] });
    const view = mount(AppSettingsView);
    expect(view.find("#video-restart").exists()).toBe(false);
    expect(view.find("#video-status").text()).toBe("● Running in Home Assistant");
    expect(view.find("#video-screens").text()).toBe("Screens with video: Tablet");
  });
});
