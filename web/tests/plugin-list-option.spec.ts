// A plugin tile's option that keeps several values, or one found by searching (plugin API 0.12): what it keeps, what
// it asks the add-on, and what it refuses so the screen's message keeps its 4 KB.
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import PluginListOption from "../src/components/PluginListOption.vue";
import UiPicker from "../src/components/ui/UiPicker.vue";
import { useInventoryStore } from "../src/stores/inventory";
import { keepsPicks, listValue, optionsFit, picksOf, PLUGIN_OPTIONS_BYTES, type Plugin, type PluginTileOption } from "../src/model/plugins";
import { pluginOptionsShape } from "../src/model/page-validation";


const artists: PluginTileOption = { id: "artists", kind: "choice", label: { en: "Artists" }, multiple: 3, options_from: "artist_search", search: true };
const kinds: PluginTileOption = { id: "kinds", kind: "choice", label: { en: "Kinds" }, multiple: 2,
  choices: [{ value: "album", label: { en: "Albums" } }, { value: "single", label: { en: "Singles" } }] };
const tags: PluginTileOption = { id: "tags", kind: "text", label: { en: "Tags" }, multiple: 4 };
const plugin = { id: "music", name: { en: "New music" }, tiles: [{ id: "releases", options: [artists, kinds, tags] }] } as unknown as Plugin;
const list = (option: PluginTileOption, values: Record<string, unknown> = {}) =>
  mount(PluginListOption, { attachTo: document.body, props: { plugin, option, values: values as any } });

// What the editor asked the add-on: [path, method, body].
let asked: [string, string, unknown][] = [];
beforeEach(() => {
  asked = [];
  useInventoryStore().inventory = { screens: [], entities: [] } as any;
  vi.stubGlobal("fetch", vi.fn((path: string, init: RequestInit) => {
    asked.push([path, String(init.method), init.body ? JSON.parse(String(init.body)) : undefined]);
    return Promise.resolve(new Response(JSON.stringify({ choices: [{ value: "9635624", label: "Billie Eilish" }] }), { status: 200 }));
  }));
});

describe("a plugin's list option", () => {
  it("keeps picks for a choice and texts for a text, in the order given", () => {
    expect(keepsPicks(artists) && keepsPicks(kinds) && !keepsPicks(tags)).toBe(true);
    expect(keepsPicks({ ...artists, multiple: undefined })).toBe(true);   // one found by searching is a pick too
    expect(picksOf([{ value: "1", label: "One" }, "two"])).toEqual([{ value: "1", label: "One" }, { value: "two", label: "two" }]);
    expect(listValue(tags, [{ value: "a", label: "a" }])).toEqual(["a"]);
    expect(listValue(kinds, [{ value: "album", label: "Albums" }])).toEqual([{ value: "album", label: "Albums" }]);
  });

  it("has the shape the add-on keeps, within the bytes the screen takes", () => {
    expect(pluginOptionsShape({ artists: [{ value: "1", label: "One" }], tags: ["a"], pick: { value: "2", label: "" }, n: 3, on: true })).toBe(true);
    for (const wrong of [{ a: [[1]] }, { a: [{ value: "" }] }, { a: Array(17).fill("x") }, { a: { value: "1", deep: {} } }, { a: [1] }, { A: 1 }])
      expect(pluginOptionsShape(wrong)).toBe(false);
    const big = Object.fromEntries([0, 1, 2, 3, 4].map((i) => [`o${i}`, [0, 1, 2, 3].map((j) => ({ value: `${i}${j}`, label: "l".repeat(60) }))]));
    expect(optionsFit(big)).toBe(false);
    expect(pluginOptionsShape(big)).toBe(false);
    expect(PLUGIN_OPTIONS_BYTES).toBe(1280);
  });

  it("adds a pick of the plugin's own list with the words it shows, takes one off, and stops at its most", async () => {
    const wrapper = list(kinds, { kinds: [] });
    wrapper.findComponent(UiPicker).vm.$emit("pick", "single");
    expect(wrapper.emitted("change")?.[0]).toEqual([[{ value: "single", label: "Singles" }]]);
    await wrapper.setProps({ values: { kinds: [{ value: "single", label: "Singles" }, { value: "album", label: "Albums" }] } });
    expect(wrapper.findAll(".plugin-list-item b").map((b) => b.text())).toEqual(["Singles", "Albums"]);
    expect(wrapper.findComponent(UiPicker).exists()).toBe(false);   // two of two: nothing more to add
    await wrapper.findAll(".plugin-list-item button.x")[0].trigger("click");
    expect(wrapper.emitted("change")?.[1]).toEqual([[{ value: "album", label: "Albums" }]]);
  });

  it("searches through the add-on with the other options as they are kept, a moment after the last key", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    const values = { artists: [], kinds: [{ value: "album", label: "Albums" }], walk: 3 };
    const wrapper = list(artists, values);
    const picker = wrapper.findComponent(UiPicker);
    expect(picker.props("remote")).toBe(true);
    picker.vm.$emit("search", "b");
    vi.advanceTimersByTime(400);
    await nextTick();
    expect(asked).toEqual([]);                                   // one letter asks nothing
    picker.vm.$emit("search", "bil");
    picker.vm.$emit("search", "bill");
    vi.advanceTimersByTime(400);
    await nextTick();
    vi.useRealTimers();
    await flushPromises();
    expect(asked).toEqual([["api/plugins/music/choices/artist_search", "POST",
      { options: { kinds: [{ value: "album", label: "Albums" }], walk: 3 }, search: "bill" }]]);
    expect(wrapper.findComponent(UiPicker).props("items")).toEqual([{ id: "9635624", name: "Billie Eilish" }]);
    wrapper.findComponent(UiPicker).vm.$emit("pick", "9635624");
    expect(wrapper.emitted("change")?.[0]).toEqual([[{ value: "9635624", label: "Billie Eilish" }]]);
  });

  it("types texts in, each once, and refuses what would not fit the screen's message", async () => {
    const wrapper = list(tags, { tags: ["a"] });
    await wrapper.find("input").setValue("b");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("change")?.[0]).toEqual([["a", "b"]]);
    await wrapper.find("input").setValue("a");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("change")).toHaveLength(1);           // already there
    const full = Object.fromEntries([0, 1, 2, 3].map((i) => [`o${i}`, [0, 1, 2, 3].map((j) => ({ value: `${i}${j}`, label: "l".repeat(60) }))]));
    await wrapper.setProps({ values: { ...full, tags: ["a"] } });
    await wrapper.find("input").setValue("x".repeat(64));
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("change")).toHaveLength(1);
    expect(wrapper.find(".help.warn").exists()).toBe(true);
  });
});
