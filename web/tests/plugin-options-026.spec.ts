// Plugin API 0.26, the editor's side (docs/PLUGINS.md): an entity option that says which entities it is for offers
// those, with every entity of its domains one key away; a tile fills its entity options from one device, once; options
// stand under the manifest's headings; a number may stay empty and says what applies then; a tile keeps 24 options.
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import PluginOptions from "../src/components/PluginOptions.vue";
import PluginTileInspector from "../src/components/PluginTileInspector.vue";
import Section from "../src/components/ui/Section.vue";
import UiPicker from "../src/components/ui/UiPicker.vue";
import { pluginOptionsShape } from "../src/model/page-validation";
import { PLUGIN_OPTION_MAX, anySet, deviceFills, devicePick, entityFits, optionGroups, placeholderNumber, typedNumber, withOption,
  type EntityFacts, type Plugin, type PluginTileOption } from "../src/model/plugins";
import { useDocumentStore } from "../src/stores/document";
import { useInventoryStore } from "../src/stores/inventory";
import { usePluginsStore } from "../src/stores/plugins";
import { useScreenStore } from "../src/stores/screen";
import { useSessionStore } from "../src/stores/session";
import { screenFixture } from "./helpers/fixtures";

const co2: PluginTileOption = { id: "co2", kind: "entity", label: { en: "CO2" }, domains: ["sensor"], device_class: ["carbon_dioxide"] };
const pm25: PluginTileOption = { id: "pm25", kind: "entity", label: { en: "PM2.5" }, domains: ["sensor"], device_class: ["pm25"] };
const voc: PluginTileOption = { id: "voc", kind: "entity", label: { en: "VOC" }, domains: ["sensor"], matches: ["voc_index", "total_volatile_organic_component_index"] };
const standard: PluginTileOption = { id: "standard", kind: "choice", label: { en: "Standard" }, default: "who",
  choices: [{ value: "who", label: { en: "WHO" } }, { value: "eu", label: { en: "EU" } }] };
const limit: PluginTileOption = { id: "co2_limit", kind: "number", label: { en: "CO2 limit" }, min: 400, max: 5000, step: 50, unit: "ppm",
  optional: true, group: { en: "Limits" }, placeholder_from: { option: "standard", values: { who: 1000, eu: 800 } } };
const pmLimit: PluginTileOption = { id: "pm_limit", kind: "number", label: { en: "PM2.5 limit" }, min: 1, max: 500, optional: true, group: { en: "Limits" } };
const options = [co2, pm25, voc, standard, limit, pmLimit];
const plugin = { id: "air", name: { en: "Air" }, icon: "F0A66", tiles: [{ id: "room", name: { en: "Air quality" }, min: "1x1", max: "2x2", memory: 900, options, from_device: true }] } as unknown as Plugin;

// One AirGradient with a raw and a disabled double, a second device with two sensors, a third with one, and a sensor
// of YAML that belongs to no device.
const facts: EntityFacts = {
  "sensor.one_co2": { device: "d1", device_class: "carbon_dioxide" },
  "sensor.one_pm25": { device: "d1", device_class: "pm25" },
  "sensor.one_pm25_raw": { device: "d1", device_class: "pm25" },
  "sensor.one_pm": { device: "d1", device_class: "pm25", disabled: true },
  "sensor.one_air": { device: "d1", translation_key: "voc_index" },
  "sensor.two_co2": { device: "d2", device_class: "carbon_dioxide" },
  "sensor.two_voc_index": { device: "d2" },
  "sensor.three_co2": { device: "d3", device_class: "carbon_dioxide" },
  "sensor.yaml_co2": { device_class: "carbon_dioxide" },
};
const devices = { d1: "AirGradient ONE", d2: "Bedroom monitor", d3: "A lone sensor" };
const entities = [...Object.keys(facts).filter((id) => !facts[id].disabled), "sensor.hall_temperature", "light.hall"]
  .map((id) => ({ id, name: id.split(".")[1].replace(/_/g, " "), state: "1" }));

describe("which entities an option is for", () => {
  it("takes an entity by its device class, its translation key or the end of its id", () => {
    expect(entityFits(co2, "sensor.hall_air", { device_class: "carbon_dioxide" })).toBe(true);
    expect(entityFits(co2, "sensor.hall_co2", { device_class: "pm25" })).toBe(false);
    expect(entityFits(co2, "sensor.hall_co2")).toBe(false);
    expect(entityFits(voc, "sensor.hall_air", { translation_key: "voc_index" })).toBe(true);
    expect(entityFits(voc, "sensor.hall_voc_index")).toBe(true);
    expect(entityFits(voc, "sensor.hall_total_volatile_organic_component_index", { device_class: "aqi" })).toBe(true);
    expect(entityFits(voc, "sensor.hallvoc_index")).toBe(false);
    expect(entityFits(voc, "sensor.hall_voc_index_raw")).toBe(false);
  });

  it("never takes another domain, and takes every entity of its domains when it names no kind", () => {
    expect(entityFits(co2, "number.hall_co2", { device_class: "carbon_dioxide" })).toBe(false);
    const every: PluginTileOption = { id: "any", kind: "entity", label: { en: "Any" }, domains: ["sensor", "binary_sensor"] };
    expect(entityFits(every, "binary_sensor.door")).toBe(true);
    expect(entityFits(every, "light.door")).toBe(false);
  });
});

describe("a tile filled from a device", () => {
  it("picks, of two entities for one option, the one that is on, no diagnostic, no raw value, then the shortest", () => {
    expect(devicePick(["sensor.one_pm25_raw", "sensor.one_pm", "sensor.one_pm25"], facts)).toBe("sensor.one_pm25");
    // Disabled loses to everything, then a category, then raw, wherever "raw" stands as a word.
    const pick = (given: EntityFacts) => devicePick(Object.keys(given), given);
    expect(pick({ "sensor.a": { disabled: true }, "sensor.a_diagnostic_long_name": { category: "diagnostic" } })).toBe("sensor.a_diagnostic_long_name");
    expect(pick({ "sensor.a": { category: "diagnostic" }, "sensor.raw_a_long_name": {} })).toBe("sensor.raw_a_long_name");
    expect(pick({ "sensor.a_b": { translation_key: "raw_pm25" }, "sensor.a_b_long": { translation_key: "pm25" } })).toBe("sensor.a_b_long");
    expect(pick({ "sensor.strawberry_pm": {}, "sensor.strawberry_pm25": {} })).toBe("sensor.strawberry_pm");
    expect(pick({ "sensor.b": {}, "sensor.a": {} })).toBe("sensor.a");
    expect(devicePick([], facts)).toBeUndefined();
  });

  it("offers the devices with an entity for two or more options, the one with the most first", () => {
    const found = deviceFills(plugin.tiles![0], facts, devices);
    expect(found.map((device) => [device.name, Object.keys(device.fills).length])).toEqual([["AirGradient ONE", 3], ["Bedroom monitor", 2]]);
    expect(found[0].fills).toEqual({ co2: "sensor.one_co2", pm25: "sensor.one_pm25", voc: "sensor.one_air" });
    expect(found[1].fills).toEqual({ co2: "sensor.two_co2", voc: "sensor.two_voc_index" });
    // Two entities for the same option are one sensor of the tile, not two.
    expect(deviceFills(plugin.tiles![0], { "sensor.a_pm25": { device: "d", device_class: "pm25" }, "sensor.a_pm25_raw": { device: "d", device_class: "pm25" } }, {})).toEqual([]);
  });
});

describe("options under a heading, and a number that may stay empty", () => {
  it("lays the options without a heading out first, then each group in the manifest's order", () => {
    const laid = optionGroups(options);
    expect(laid.plain.map((option) => option.id)).toEqual(["co2", "pm25", "voc", "standard"]);
    expect(laid.groups.map((group) => [group.title.en, group.options.map((option) => option.id)])).toEqual([["Limits", ["co2_limit", "pm_limit"]]]);
    expect(optionGroups(undefined)).toEqual({ plain: [], groups: [] });
  });

  it("opens a group only when a person gave one of its options a value", () => {
    expect(anySet([limit, pmLimit], {})).toBe(false);
    expect(anySet([limit, pmLimit], { co2: "sensor.one_co2" })).toBe(false);
    expect(anySet([limit, pmLimit], { pm_limit: 25 })).toBe(true);
    expect(anySet([standard], { standard: "who" })).toBe(false);
    expect(anySet([standard], { standard: "eu" })).toBe(true);
    expect(anySet([co2], { co2: "" })).toBe(false);
  });

  it("says what applies while the number is empty, by the choice as it is now", () => {
    expect(placeholderNumber(limit, { standard: "who" })).toBe(1000);
    expect(placeholderNumber(limit, { standard: "eu" })).toBe(800);
    expect(placeholderNumber(limit, {})).toBeUndefined();
    expect(placeholderNumber(limit, { standard: "toString" })).toBeUndefined();
    expect(placeholderNumber(pmLimit, { standard: "who" })).toBeUndefined();
  });

  it("keeps what is typed within the option's min, max and steps, and an empty field as nothing", () => {
    expect(typedNumber(limit, "930")).toBe(950);
    expect(typedNumber(limit, " 12 ")).toBe(400);
    expect(typedNumber(limit, "99999")).toBe(5000);
    expect(typedNumber({ ...pmLimit, step: 0.5 }, "2,3")).toBe(2.5);
    for (const empty of ["", "  ", "abc"]) expect(typedNumber(limit, empty)).toBeUndefined();
    expect(withOption({ co2: "sensor.a", co2_limit: 900 }, "co2_limit", undefined)).toEqual({ co2: "sensor.a" });
    expect(withOption(undefined, "co2_limit", 900)).toEqual({ co2_limit: 900 });
  });

  it("keeps 24 options of a tile within the same bytes, and refuses a 25th", () => {
    const many = (n: number, value: unknown = "sensor.hall_carbon_dioxide") => Object.fromEntries(Array.from({ length: n }, (_, i) => [`o${i}`, value]));
    expect(PLUGIN_OPTION_MAX).toBe(24);
    expect(pluginOptionsShape(many(24))).toBe(true);
    expect(pluginOptionsShape(many(25, 1))).toBe(false);
    expect(pluginOptionsShape(many(24, "x".repeat(64)))).toBe(false);
  });
});

describe("the inspector's rows", () => {
  const rows = (values: Record<string, unknown> = {}, shown = options) =>
    mount(PluginOptions, { attachTo: document.body, props: { plugin, options: shown, values: { standard: "who", ...values } as any } });
  const ids = (picker: { props(name: string): unknown }) => (picker.props("items") as readonly { id: string }[]).map((item) => item.id);

  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
    useInventoryStore().inventory = { screens: [], entities } as any;
    usePluginsStore().entityFacts = facts;
    usePluginsStore().devices = devices;
  });

  it("offers the entities the option is for, the chosen one always, and all of its domains once asked", async () => {
    const shown = rows({ co2: "sensor.hall_temperature" });
    const [first, , third] = shown.findAllComponents(UiPicker);
    expect(ids(first)).toEqual(["sensor.one_co2", "sensor.two_co2", "sensor.three_co2", "sensor.yaml_co2", "sensor.hall_temperature"]);
    expect(ids(third)).toEqual(["sensor.one_air", "sensor.two_voc_index"]);
    expect(shown.text()).toContain("hall temperature");
    // The key under the list: every entity of the domains, and back.
    await first.find("button").trigger("click");
    await nextTick();
    const all = document.querySelector<HTMLButtonElement>('[data-all="plugin-option-co2"]')!;
    expect(all.textContent).toContain("Show all entities");
    all.click();
    await nextTick();
    expect(ids(first)).toHaveLength(entities.length - 1);
    expect(ids(third)).toEqual(["sensor.one_air", "sensor.two_voc_index"]);
    expect(all.textContent).toContain("Show only what fits");
    all.click();
    await nextTick();
    expect(ids(first)).toHaveLength(5);
  });

  it("has no such key for an option that takes every entity of its domains", async () => {
    const any: PluginTileOption = { id: "any", kind: "entity", label: { en: "Any" }, domains: ["sensor"] };
    const shown = rows({}, [any]);
    expect(ids(shown.findComponent(UiPicker))).toHaveLength(entities.length - 1);
    await shown.findComponent(UiPicker).find("button").trigger("click");
    await nextTick();
    expect(document.querySelector("[data-all]")).toBeNull();
  });

  it("shows an empty number as what applies, takes a typed one, and takes it off again", async () => {
    const empty = rows();
    const field = empty.get<HTMLInputElement>("#plugin-option-co2_limit");
    expect(field.element.value).toBe("");
    expect(field.element.placeholder).toBe("1,000 ppm");
    expect(empty.get<HTMLInputElement>("#plugin-option-pm_limit").element.placeholder).toBe("Not set");
    expect(rows({ standard: "eu" }).get<HTMLInputElement>("#plugin-option-co2_limit").element.placeholder).toBe("800 ppm");
    await field.setValue("930");
    expect(empty.emitted("change")?.[0]).toEqual([limit, 950]);
    expect(field.element.value).toBe("950");
    const filled = rows({ co2_limit: 950 });
    const kept = filled.get<HTMLInputElement>("#plugin-option-co2_limit");
    expect(kept.element.value).toBe("950");
    expect(filled.text()).toContain("ppm");
    await kept.setValue("");
    expect(filled.emitted("change")?.[0]).toEqual([limit, undefined]);
  });
});

describe("the tile's inspector", () => {
  let doc: ReturnType<typeof useDocumentStore>;
  const tile = () => doc.layout!.tiles[0];
  const inspector = () => mount(PluginTileInspector, { attachTo: document.body, props: { tile: tile() } });
  // The route of the chosen screen settles before the page is taken down (the router scrolls a new view to the top).
  afterEach(() => flushPromises());

  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ states: {}, previews: [], capabilities: {}, items: [] }))));
    doc = useDocumentStore();
    useScreenStore().selected = null;
    useInventoryStore().inventory = { screens: [screenFixture({ id: "test", name: "Test", firmware: "0.61.0", online: true,
      layout: { title: "Home", tiles: [{ entity: "light.test", name: "Test", slot: 0 }] } })], entities, editor_features: { plugins: true } } as any;
    useSessionStore().select("test");
    const plugins = usePluginsStore();
    plugins.index = [plugin];
    plugins.entityFacts = facts;
    plugins.devices = devices;
    doc.document!.pages[0].tiles[0].content = { kind: "plugin", plugin: "air", tile: "room", options: { voc: "sensor.yaml_voc_index", pm25: "sensor.hall_pm" } } as never;
  });

  it("offers the devices by name and how many of the tile's sensors each has, and fills the options once", async () => {
    expect(tile().entity).toBe("plugin:air.room");
    const shown = inspector();
    const picker = shown.findAllComponents(UiPicker)[0];
    expect(picker.props("items")).toEqual([{ id: "d1", name: "AirGradient ONE", hint: "3 sensors" }, { id: "d2", name: "Bedroom monitor", hint: "2 sensors" }]);
    expect(shown.get("#plugin-fill-device-open").text()).toContain("Fill from a device");
    // The second device has no PM2.5: that option stays as it was.
    picker.vm.$emit("pick", "d2");
    await nextTick();
    expect(tile().options?.plugin).toEqual({ voc: "sensor.two_voc_index", pm25: "sensor.hall_pm", co2: "sensor.two_co2" });
    // Nothing of the device is kept, and each sensor can still be changed.
    expect(JSON.stringify(tile().options)).not.toContain("d2");
  });

  it("keeps a group folded until one of its options has a value, and an empty number as no key", async () => {
    const shown = inspector();
    const group = () => shown.findAllComponents(Section).find((section) => section.props("title") === "Limits")!;
    expect(group().props("foldable")).toBe(true);
    expect(group().find(".insp-sec-body").exists()).toBe(false);
    // The options without a heading stand above it, open; an empty entity option is its picker alone, no text field.
    expect(shown.find("#plugin-option-standard").exists()).toBe(true);
    expect(shown.findAll(".insp-sec-body input[type=text]")).toHaveLength(0);
    await group().get("button").trigger("click");
    await group().get<HTMLInputElement>("#plugin-option-pm_limit").setValue("25");
    await nextTick();
    expect(tile().options?.plugin).toEqual({ voc: "sensor.yaml_voc_index", pm25: "sensor.hall_pm", pm_limit: 25 });
    const again = inspector();
    const open = again.findAllComponents(Section).find((section) => section.props("title") === "Limits")!;
    expect(open.find(".insp-sec-body").exists()).toBe(true);
    await open.get<HTMLInputElement>("#plugin-option-pm_limit").setValue("");
    await nextTick();
    expect(tile().options?.plugin).toEqual({ voc: "sensor.yaml_voc_index", pm25: "sensor.hall_pm" });
  });

  it("shows no device picker for a tile whose manifest does not ask for one", () => {
    usePluginsStore().index = [{ ...plugin, tiles: [{ ...plugin.tiles![0], from_device: false }] }];
    expect(inspector().find("#plugin-fill-device-open").exists()).toBe(false);
  });
});
