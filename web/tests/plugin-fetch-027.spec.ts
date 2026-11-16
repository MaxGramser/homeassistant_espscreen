// Plugin API 0.27, the editor's side (docs/PLUGINS.md): a plugin whose fetch reads an attribute of an entity a person
// chooses says so under "What it may do", one line per host, and an entity option may start with an entity chosen
// (`default: zone.home`), which the inspector shows as the choice until the person takes it off.
import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PluginDetail from "../src/components/PluginDetail.vue";
import PluginOptions from "../src/components/PluginOptions.vue";
import { pluginDefaults, sendsLines, testPlugin, type Plugin, type PluginTileOption } from "../src/model/plugins";
import { useInventoryStore } from "../src/stores/inventory";

const place: PluginTileOption = { id: "place", kind: "entity", label: { en: "Place", nl: "Plek" }, domains: ["zone", "person"],
  attributes: ["latitude", "longitude"], default: "zone.home" };
const sends: Plugin["sends"] = [
  { host: "api.example.org", options: [{ option: "place", label: { en: "Place" }, attributes: ["latitude", "longitude"] }] },
  { host: "tiles.example.org", options: [
    { option: "place", label: { en: "Place" }, attributes: ["state"] },
    { option: "sensor", label: { en: "Sensor" }, attributes: ["next_rising", "unit_of_measurement", "state"] }] },
];
const plugin: Plugin = {
  ...testPlugin({ id: "weather", version: "1.0.0", source: "index" } as any), tessera: true,
  permissions: { home_assistant: [], network: ["api.example.org", "tiles.example.org"] }, sends,
  tiles: [{ id: "now", name: { en: "Weather" }, min: "1x1", max: "2x2", memory: 600, options: [place] }],
} as Plugin;

describe("what a plugin's fetches send of Home Assistant", () => {
  it("says it per host, with the option's label and the attributes in words", () => {
    expect(sendsLines(plugin)).toEqual([
      { host: "api.example.org", what: "Sends to api.example.org: latitude and longitude of the entity you choose for Place" },
      { host: "tiles.example.org", what: "Sends to tiles.example.org: state of the entity you choose for Place and next rising, "
        + "unit of measurement and state of the entity you choose for Sensor" },
    ]);
    expect(sendsLines({ sends: [] })).toEqual([]);
    expect(sendsLines({})).toEqual([]);
  });

  it("stands under What it may do, after the hosts it connects to", () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
    const detail = mount(PluginDetail, { props: { plugin } });
    const lines = detail.findAll(".plugin-sends b").map((line) => line.text());
    expect(lines).toEqual(sendsLines(plugin).map((line) => line.what));
    expect(detail.text()).toContain("Connects to api.example.org, tiles.example.org");
    expect(mount(PluginDetail, { props: { plugin: { ...plugin, sends: undefined } } }).findAll(".plugin-sends")).toHaveLength(0);
  });
});

describe("an entity option that starts with an entity", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
    useInventoryStore().inventory = { screens: [], entities: [{ id: "zone.home", name: "Home", state: "1" },
      { id: "person.someone", name: "Someone", state: "home" }] } as any;
  });
  const rows = (kept: Record<string, unknown>) => mount(PluginOptions, { attachTo: document.body,
    props: { plugin, options: [place], values: { ...pluginDefaults({ options: [place] }), ...kept } as any } });

  it("shows the default as the choice, and what the person chose over it", () => {
    expect(pluginDefaults({ options: [place] })).toEqual({ place: "zone.home" });
    const shown = rows({});
    expect(shown.text()).toContain("Home");
    expect(shown.find(".plugin-entity-clear").exists()).toBe(true);
    expect(rows({ place: "person.someone" }).text()).toContain("Someone");
  });

  it("is taken off with the key beside it, and then stays off", async () => {
    const shown = rows({});
    await shown.find(".plugin-entity-clear").trigger("click");
    expect(shown.emitted("change")?.[0]?.[1]).toBe("");
    const off = rows({ place: "" });
    expect(off.find(".plugin-entity-clear").exists()).toBe(false);
    expect(off.text()).toContain("Choose");
  });
});
