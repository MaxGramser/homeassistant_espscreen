// A plugin tile's option of kind entity (plugin API 0.15): a searchable list of the entities of its domains, the
// editor's own and those the add-on lists for plugins, the chosen one by its name, and a key that takes it away again.
import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PluginOptions from "../src/components/PluginOptions.vue";
import UiPicker from "../src/components/ui/UiPicker.vue";
import { useInventoryStore } from "../src/stores/inventory";
import { usePluginsStore } from "../src/stores/plugins";
import type { Plugin, PluginTileOption } from "../src/model/plugins";

const grid: PluginTileOption = { id: "grid", kind: "entity", label: { en: "Grid" }, domains: ["sensor"], attributes: ["unit_of_measurement"] };
const plant: PluginTileOption = { id: "plant", kind: "entity", label: { en: "Plant" }, domains: ["plant"] };
const plugin = { id: "flow", name: { en: "Flow" }, tiles: [{ id: "flow", options: [grid, plant] }] } as unknown as Plugin;
const options = (values: Record<string, unknown> = {}) =>
  mount(PluginOptions, { attachTo: document.body, props: { plugin, options: [grid, plant], values: values as any } });

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
  useInventoryStore().inventory = { screens: [], entities: [
    { id: "sensor.grid_power", name: "Grid power", state: "120" }, { id: "light.kitchen", name: "Kitchen", state: "on" }] } as any;
  usePluginsStore().entities = [{ id: "plant.fern", name: "Fern" }];
});

describe("a plugin's entity option", () => {
  it("offers the entities of its own domains only, from the editor's list and the plugins' own", () => {
    const pickers = options().findAllComponents(UiPicker);
    expect(pickers.map((picker) => (picker.props("items") as readonly { id: string }[]).map((item) => item.id)))
      .toEqual([["sensor.grid_power"], ["plant.fern"]]);
  });

  it("keeps the entity picked, says it by its name, and takes it away again", async () => {
    const empty = options();
    empty.findAllComponents(UiPicker)[0].vm.$emit("pick", "sensor.grid_power");
    expect(empty.emitted("change")?.[0]).toEqual([grid, "sensor.grid_power"]);
    const chosen = options({ grid: "sensor.grid_power" });
    expect(chosen.text()).toContain("Grid power");
    await chosen.get(`[aria-label="Remove Grid power"]`).trigger("click");
    expect(chosen.emitted("change")?.[0]).toEqual([grid, ""]);
  });
});
