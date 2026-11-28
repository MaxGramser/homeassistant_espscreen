// The two settings pages in parts (docs/PAGES.md, "Settings"): each opens on a list of its parts with what is set now,
// a row opens its part at its own address, and the way back is the head of the part.
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import AppSettingsView from "../src/components/AppSettingsView.vue";
import SettingsTab from "../src/components/SettingsTab.vue";
import { screenPartOf, SCREEN_PART_ROWS, SCREEN_SETTINGS_PARTS } from "../src/model/settings-parts";
import { SETTING_GROUPS } from "../src/model/settings";
import { router } from "../src/router";
import type { Inventory } from "../src/types";
import { useInventoryStore } from "../src/stores/inventory";
import { useScreenStore } from "../src/stores/screen";
import { useSettingsStore } from "../src/stores/settings";
import { useUiStore } from "../src/stores/ui";

// One screen, Living room, open in the editor.
beforeEach(() => {
  useInventoryStore().inventory = {
    csrf: "t", connected: true, entities: [],
    screens: [{ id: "living", name: "Living room", online: true, firmware: "0.62.0", board: "guition", layout: { title: "Living room", tiles: [] } }],
  } as unknown as Inventory;
  useScreenStore().selected = "living";
});

describe("the app's Settings in parts", () => {
  beforeEach(async () => {
    await router.push("/settings");
    useInventoryStore().inventory.updates = { target: "0.62.0", pending: 0, auto: true };
  });

  it("opens on the list of parts, each with one line of what is set now", () => {
    const view = mount(AppSettingsView);
    const rows = view.findAll("#settings-parts .set-link");
    expect(rows.map((row) => row.find("b").text())).toEqual(["Updates", "Builds", "Home Assistant"]);
    expect(rows[0].find("small").text()).toBe("All screens have firmware 0.62.0. · Updated every night");
    expect(view.find("#updates").exists()).toBe(false);
  });

  it("opens a part at its own address, and goes back to the list from its head", async () => {
    const view = mount(AppSettingsView);
    await view.find("#settings-part-updates").trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.fullPath).toBe("/settings/updates");
    expect(useUiStore().settingsPart).toBe("updates");
    expect(view.find("h1").text()).toBe("Updates");
    expect(view.find("#updates").exists()).toBe(true);
    await view.find(".set-back").trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.fullPath).toBe("/settings");
    expect(view.find("#settings-parts").exists()).toBe(true);
  });

  it("names the screens waiting for an update on the row itself", () => {
    const [living] = useInventoryStore().inventory.screens;
    useInventoryStore().inventory.updates = { target: "0.62.0", pending: 1 };
    useInventoryStore().inventory.screens = [{ ...living, update: { available: true, target: "0.62.0" } }];
    expect(mount(AppSettingsView).find("#settings-parts .chip.update").text()).toBe("1 update");
  });

  it("shows the list for a part this app does not have", async () => {
    await router.push("/settings/language");
    delete useInventoryStore().inventory.language;
    expect(mount(AppSettingsView).find("#settings-parts").exists()).toBe(true);
  });
});

describe("a screen's Settings tab in parts", () => {
  const view = (extra: Record<string, unknown> = {}) => {
    Object.assign(useInventoryStore().inventory.screens[0], {
      settings: {
        owner: "screen", unavailable: [], rotations: [0, 180], switches: [],
        keys: ["brightness", "dark_mode", "standby_enabled", "standby_seconds", "auto_home", "auto_home_seconds", "swipe_pages"],
        values: { brightness: 70, dark_mode: false, standby_enabled: true, standby_seconds: 600, auto_home: true, auto_home_seconds: 60, swipe_pages: true },
        ...extra,
      },
    });
    return mount(SettingsTab);
  };
  beforeEach(async () => { await router.push("/screens/living"); });

  it("opens on the list of parts, each with one line of what is set now", () => {
    const tab = view();
    const rows = tab.findAll("#settings-groups .set-link");
    expect(rows.map((row) => row.find(".set-link-main").attributes("id"))).toEqual(
      ["settings-part-display", "settings-part-standby", "settings-part-navigation", "settings-part-help"]);
    const lines = Object.fromEntries(rows.map((row) => [row.find("b").text(), row.find("small").text()]));
    expect(lines.Display).toBe("Brightness 70%");
    expect(lines["Standby & night"]).toBe("Standby after 10 min");
    expect(lines.Navigation).toBe("Back to Home after 1 min · Swipe between pages");
  });

  it("switches dark mode from the list, without opening the part", async () => {
    const tab = view();
    await tab.find("#quick-dark-mode").trigger("click");
    expect(useSettingsStore().settingEdits.dark_mode.value).toBe(true);
    expect(router.currentRoute.value.query.settings).toBeUndefined();
  });

  it("opens a part in the screen's address, with only that part's rows", async () => {
    const tab = view();
    await tab.find("#settings-part-standby").trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.fullPath).toBe("/screens/living?settings=standby");
    expect(tab.findAll("[data-setting]").map((row) => row.attributes("data-setting"))).toEqual(["standby_enabled", "standby_seconds"]);
    await tab.find(".set-back").trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.query.settings).toBeUndefined();
  });
});

describe("the address of a part of the Settings tab", () => {
  it("stays when the screen it names opens (a link to the part, a reload), and goes with another screen", async () => {
    const ui = useUiStore();
    await router.push("/screens/living?settings=standby");
    ui.setMainView(() => ({ name: "screen", params: { id: "living" } }));
    await ui.go("");
    expect(router.currentRoute.value.fullPath).toBe("/screens/living?settings=standby");
    ui.setMainView(() => ({ name: "screen", params: { id: "kitchen" } }));
    await ui.go("");
    expect(router.currentRoute.value.fullPath).toBe("/screens/kitchen");
  });
});

describe("the parts of a screen's Settings tab", () => {
  it("show every setting the editor has, once", () => {
    const keys = SETTING_GROUPS.flatMap((group) => group.rows.map((row) => row.key));
    const shown = SCREEN_SETTINGS_PARTS.flatMap((part) => (SCREEN_PART_ROWS[part] || []).flatMap((block) => block.keys));
    expect([...shown].sort()).toEqual([...keys].sort());
  });
  it("say which part holds a setting, for ⌘K", () => {
    expect(screenPartOf("night_end")).toBe("standby");
    expect(screenPartOf("rotation")).toBe("display");
    expect(screenPartOf("loop_pages")).toBe("navigation");
    expect(screenPartOf("nothing")).toBeNull();
  });
});
