// A screen's settings changed from the editor (stores/settings.ts): shown at once, sent after a short pause with what came
// in that pause, one screen at a time, taken back when the add-on refuses, taken over by Home Assistant's own values
// again once they match or four seconds passed, and sent on the way out when the page closes.
import { describe, expect, it } from "vitest";
import { i18n } from "../../src/i18n";
import { state } from "../../src/store";
import { SETTING_EDIT_MS, useSettingsStore } from "../../src/stores/settings";
import { useUiStore } from "../../src/stores/ui";
import type { Screen, SettingsView } from "../../src/types";
import { useFakeClock } from "../helpers/clock";
import { failure, fakeApi, type ApiRequest } from "../helpers/fake-api";
import { useScreenStore } from "../../src/stores/screen";
import { useInventoryStore } from "../../src/stores/inventory";

const view = (values: Record<string, any>): SettingsView => ({ owner: "screen", keys: Object.keys(values), values, unavailable: [] });
const screen = (id: string, values: Record<string, any>) => ({ id, name: id, online: true, layout: {}, settings: view(values) }) as unknown as Screen;
const VALUES = { brightness: 80, standby_brightness: 50, night_brightness: 20, dark_mode: false };

// The add-on takes every change and answers with the screen's settings as Home Assistant reports them a moment later:
// what it had, or (echo) with the changes in.
function addOn(echo = true) {
  return fakeApi({
    "PUT screens/:id/settings": (request: ApiRequest) => {
      const before = useInventoryStore().inventory.screens.find((s) => s.id === request.params.id)!.settings!.values;
      return view(echo ? { ...before, ...request.body.settings } : before);
    },
  });
}
function open(selected = "living") {
  useInventoryStore().inventory = { screens: [screen("living", VALUES), screen("kitchen", VALUES)], entities: [] } as any;
  useScreenStore().selected = selected;
}
const t = (key: string) => i18n.global.t(key);

describe("a screen setting changed here", () => {
  it("shows at once and goes after its pause, with every change made in that pause in one request", async () => {
    const clock = useFakeClock();
    open();
    const api = addOn();
    const settings = useSettingsStore();
    settings.setSetting("dark_mode", true, 150);
    expect([settings.settingValues().dark_mode, settings.settingPending]).toEqual([true, true]);
    await clock.tick(100);
    settings.setSetting("brightness", 90, 600);
    await clock.tick(599);
    expect(api.count()).toBe(0);
    await clock.tick(1);
    expect(api.asked("PUT screens/:id/settings").map((r) => [r.params.id, r.body.settings, r.init.keepalive])).toEqual([["living", { dark_mode: true, brightness: 90 }, false]]);
    expect(settings.settingPending).toBe(false);
    // The answer is the screen's settings now, and a change that matches it is no longer kept apart.
    expect(useInventoryStore().inventory.screens[0].settings!.values).toMatchObject({ dark_mode: true, brightness: 90 });
    expect(settings.settingEdits).toEqual({});
  });

  it("pulls both dim levels down with a lower brightness, as the screen does, and only those above it", () => {
    useFakeClock();
    open();
    addOn();
    const settings = useSettingsStore();
    settings.setSetting("brightness", 30, 600);
    expect(Object.fromEntries(Object.entries(settings.settingEdits).map(([key, edit]) => [key, edit.value]))).toEqual({ brightness: 30, standby_brightness: 30 });
    expect(settings.settingValues()).toMatchObject({ brightness: 30, standby_brightness: 30, night_brightness: 20 });
  });

  it("sends one screen's changes at a time: another screen's change waits until the first are out, and says so", async () => {
    const clock = useFakeClock();
    open();
    const api = addOn();
    const settings = useSettingsStore();
    settings.setSetting("dark_mode", true, 600);
    // Another screen is shown before the pause is over (the switch itself sends what waits; here only the selection moves).
    useScreenStore().selected = "kitchen";
    settings.setSetting("brightness", 40, 600);
    expect(useUiStore().notice?.message).toBe(t("editor.screen_settings.other_screen_busy"));
    expect(settings.settingEdits.brightness).toBeUndefined();
    await clock.settle();
    expect(api.asked("PUT screens/:id/settings").map((r) => r.params.id)).toEqual(["living"]);
    // Once they are out, the kitchen's change goes to the kitchen.
    settings.setSetting("brightness", 40, 150);
    await clock.tick(150);
    expect(api.asked("PUT screens/:id/settings").map((r) => [r.params.id, r.body.settings])).toEqual([["living", { dark_mode: true }], ["kitchen", { brightness: 40 }]]);
  });

  it("waits for the request on its way: a change made meanwhile goes 150 ms after its answer", async () => {
    const clock = useFakeClock();
    open();
    const api = addOn();
    const held = api.defer("PUT screens/:id/settings");
    const settings = useSettingsStore();
    settings.setSetting("dark_mode", true, 150);
    await clock.tick(150);
    settings.setSetting("brightness", 70, 150);
    await clock.tick(1000);
    expect(api.count()).toBe(1);
    expect(settings.settingPending).toBe(true);
    held.resolve();
    await clock.settle();
    await clock.tick(149);
    expect(api.count()).toBe(1);
    await clock.tick(1);
    expect(api.asked().map((r) => r.body.settings)).toEqual([{ dark_mode: true }, { brightness: 70 }]);
    expect(settings.settingPending).toBe(false);
  });

  it("takes back what did not arrive, the dim levels a lower brightness pulled with it, and says why", async () => {
    const clock = useFakeClock();
    open();
    const api = addOn();
    api.on("PUT screens/:id/settings", failure(503, "Home Assistant did not answer in time"));
    const settings = useSettingsStore();
    settings.setSetting("dark_mode", true, 150);
    settings.setSetting("brightness", 30, 150);
    expect(settings.settingValues()).toMatchObject({ dark_mode: true, brightness: 30, standby_brightness: 30 });
    await clock.tick(150);
    expect(useUiStore().notice?.message).toBe("Home Assistant did not answer in time");
    expect(settings.settingEdits).toEqual({});
    expect(settings.settingValues()).toMatchObject(VALUES);
    expect(settings.settingPending).toBe(false);
  });

  it("wins over Home Assistant's old value for four seconds, then gives way to what the screen reports", async () => {
    const clock = useFakeClock();
    open();
    // The screen clamps the value: Home Assistant keeps reporting the old one.
    addOn(false);
    const settings = useSettingsStore();
    settings.setSetting("brightness", 100, 150);
    await clock.tick(150);
    expect(settings.settingValues().brightness).toBe(100);
    // A live update in between does not take it back early.
    await clock.tick(SETTING_EDIT_MS - 1000);
    settings.settleSettings();
    expect(settings.settingValues().brightness).toBe(100);
    // Four seconds after the change, the look the answer left behind gives the screen's own value back.
    await clock.tick(1100);
    expect(settings.settingEdits).toEqual({});
    expect(settings.settingValues().brightness).toBe(80);
  });

  it("goes out when the page closes, kept alive past it, while its start follows the page", async () => {
    useFakeClock();
    open();
    const api = addOn();
    const settings = useSettingsStore();
    const stop = settings.start();
    expect(settings.start()).toBe(stop);
    settings.setSetting("dark_mode", true, 600);
    window.dispatchEvent(new Event("pagehide"));
    expect(api.asked().map((r) => [r.body.settings, r.init.keepalive])).toEqual([[{ dark_mode: true }, true]]);
    stop();
    settings.setSetting("brightness", 60, 600);
    window.dispatchEvent(new Event("pagehide"));
    expect(api.count()).toBe(1);
  });

  it("sends what waits when another screen opens, and forgets everything of a screen that went", async () => {
    const clock = useFakeClock();
    open();
    const api = addOn();
    const settings = useSettingsStore();
    settings.setSetting("dark_mode", true, 600);
    settings.leaveScreen();
    expect(settings.settingEdits).toEqual({});
    await clock.settle();
    expect(api.asked().map((r) => [r.params.id, r.body.settings])).toEqual([["living", { dark_mode: true }]]);
    settings.setSetting("brightness", 60, 600);
    settings.forget();
    expect([settings.settingEdits, settings.settingPending]).toEqual([{}, false]);
    await clock.tick(1000);
    expect(api.count()).toBe(1);
  });
});
