// ⌘K that can do everything (CommandPalette.vue over model/palette.ts): a screen's setting opened there and marked, a tile
// on another screen shown in the inspector, every screen updated after the question, the keys and the hints, and what
// was chosen last kept in this browser.
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CommandPalette from "../src/components/CommandPalette.vue";
import SettingsTab from "../src/components/SettingsTab.vue";
import { t } from "../src/i18n";
import { useDocumentStore } from "../src/stores/document";
import { useInspectorStore } from "../src/stores/inspector";
import { useInventoryStore } from "../src/stores/inventory";
import { useScreenStore } from "../src/stores/screen";
import { useSettingsStore } from "../src/stores/settings";
import { useUiStore } from "../src/stores/ui";
import type { Screen } from "../src/types";
import { answerDialogs } from "./helpers/dialogs";
import { fakeApi } from "./helpers/fake-api";
import { screenFixture } from "./helpers/fixtures";

const screen = (id: string, name: string, more: Partial<Screen> = {}) => screenFixture({ id, name, online: true, firmware: "0.53.0",
  layout: { title: name, tiles: [{ entity: "light.a", name: "Reading", slot: 0 }] }, ...more } as unknown as Screen);
beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
  useInventoryStore().inventory = { connected: true, entities: [{ id: "light.a", name: "Lamp A" }, { id: "light.b", name: "Lamp B" }], screens: [
    screen("living", "Living room", { settings: { owner: "screen", keys: ["brightness", "dark_mode"], values: { brightness: 80, dark_mode: true }, unavailable: [] } }),
    screen("kitchen", "Kitchen", { update: { available: true, target: "0.54.0", profile: "kitchen.yaml", host: "10.0.0.3" },
      settings: { owner: "screen", keys: ["brightness"], values: { brightness: 40 }, unavailable: [] } }),
  ] } as any;
});
const opened = async () => {
  useUiStore().palette = true;
  const palette = mount(CommandPalette, { attachTo: document.body });
  await flushPromises();
  return palette;
};
const type = async (palette: Awaited<ReturnType<typeof opened>>, text: string) => { await palette.find("#palette-input").setValue(text); await flushPromises(); };
const ids = (palette: Awaited<ReturnType<typeof opened>>) => palette.findAll(".palette-item").map((row) => row.attributes("data-id"));

describe("⌘K can do everything", () => {
  it("takes the keys: the field has the focus, the arrows walk, the row in focus says what Enter does, Escape closes", async () => {
    const palette = await opened();
    expect(document.activeElement?.id).toBe("palette-input");
    expect(palette.find("#palette-input").attributes("aria-activedescendant")).toBe("palette-item-0");
    expect(palette.find("#palette-item-0 .palette-hint").text()).toContain(t("editor.search.hint.open"));
    await palette.find("#palette-input").trigger("keydown", { key: "ArrowDown" });
    expect(palette.find("#palette-item-1").attributes("aria-selected")).toBe("true");
    expect(palette.find("#palette-item-0 .palette-hint").exists()).toBe(false);
    await palette.find(".palette").trigger("keydown", { key: "Escape" });
    expect(useUiStore().palette).toBe(false);
    palette.unmount();
  });

  it("opens a screen's setting on its screen, marked a moment, and keeps it as chosen last", async () => {
    const palette = await opened();
    await type(palette, "kitchen bright");
    expect(ids(palette)).toEqual(["setting:kitchen:brightness"]);
    expect(palette.find(".palette-item small").text()).toBe("Kitchen · 40%");
    await palette.find("#palette-input").trigger("keydown", { key: "Enter" });
    await flushPromises();
    expect([useScreenStore().selected, useUiStore().tab]).toEqual(["kitchen", "settings"]);
    const page = mount(SettingsTab, { attachTo: document.body });
    await flushPromises();
    expect(page.find('[data-setting="brightness"]').classes()).toContain("spotlit");
    expect(useSettingsStore().spotlight).toBeNull();
    expect(JSON.parse(localStorage.getItem("esp-screens.palette-recent")!)).toEqual(["setting:kitchen:brightness"]);
    // Next time, it comes first.
    useUiStore().palette = false; await flushPromises();
    useUiStore().palette = true; await flushPromises();
    expect(palette.find(".palette-group").text()).toBe(t("editor.search.groups.recent"));
    expect(ids(palette)[0]).toBe("setting:kitchen:brightness");
    page.unmount(); palette.unmount();
  });

  it("shows a tile of any screen in the inspector", async () => {
    const palette = await opened();
    await type(palette, "reading");
    expect(ids(palette).filter((id) => id!.startsWith("tile:"))).toHaveLength(2);
    await palette.find('[data-id^="tile:kitchen:"]').trigger("click");
    await flushPromises();
    expect(useScreenStore().selected).toBe("kitchen");
    expect([useInspectorStore().inspector?.kind, useDocumentStore().currentTile?.name]).toEqual(["tile", "Reading"]);
    palette.unmount();
  });

  it("updates every screen only after asking, and a screen by its name at once", async () => {
    const api = fakeApi({ "POST updates/run": {}, "POST screens/:id/update": {}, "GET inventory": { screens: [], entities: [] } });
    const asked = answerDialogs(false);
    const palette = await opened();
    await type(palette, "update");
    expect(ids(palette).slice(0, 2)).toEqual(["action:update-all", "update:kitchen"]);
    await palette.find('[data-id="action:update-all"]').trigger("click");
    await flushPromises();
    expect(asked.map((q) => [q.message, (q as any).confirm])).toEqual([[t("editor.search.update_all_confirm", 1), t("editor.search.update_all_go")]]);
    expect(api.count("POST updates/run")).toBe(0);
    useUiStore().palette = true; await flushPromises();
    await type(palette, "update kitchen");
    await palette.find('[data-id="update:kitchen"]').trigger("click");
    await flushPromises();
    expect(api.count("POST screens/:id/update")).toBe(1);
    palette.unmount();
  });
});
