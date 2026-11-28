// The card that suggests a plugin for hardware a screen's board has (docs/PLUGINS.md, "Plugins a board starts with"): it
// asks once, says why, and a yes or a no goes to the add-on, which keeps it.
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PluginSuggestCard from "../src/components/PluginSuggestCard.vue";
import { t } from "../src/i18n";
import type { Screen } from "../src/types";

type Call = { url: string; method: string; body: any };
let calls: Call[] = [];

function screen(changes: Partial<Screen> = {}): Screen {
  return {
    id: "hall", name: "Hall", online: true, board: "jc8012p4a1v3", layout: { title: "Hall", tiles: [] }, feedback: null, plugin_ask: null,
    plugin_suggest: { update: false, plugins: [{ id: "screen_camera", name: { en: "Screen camera" }, summary: { en: "The camera of the screen." }, version: "0.7.0", why: "camera", image: null }] },
    ...changes,
  } as unknown as Screen;
}

beforeEach(() => {
  calls = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init: RequestInit = {}) => {
    calls.push({ url: String(url), method: init.method || "GET", body: init.body ? JSON.parse(String(init.body)) : null });
    return Promise.resolve(new Response(JSON.stringify({}), { status: 200 }));
  }));
});

const answers = () => calls.filter((c) => c.method === "POST").map((c) => [c.url.replace(/^.*api\//, ""), c.body]);

describe("the card that suggests a plugin for the board", () => {
  it("names the plugin, the screen and the reason, and waits for the other cards and an offline screen", () => {
    const card = mount(PluginSuggestCard, { props: { screen: screen() } });
    expect(card.find("#plugin-suggest-title").text()).toBe("Add Screen camera to Hall?");
    expect(card.find(".suggest-why").text()).toBe(t("editor.plugins.suggest.why.camera"));
    expect(card.find("#plugin-suggest-yes").text()).toBe(t("editor.plugins.suggest.yes"));
    for (const changes of [{ online: false }, { feedback: { ask: true } as any }, { plugin_ask: { plugin: "x" } as any }, { plugin_suggest: null }])
      expect(mount(PluginSuggestCard, { props: { screen: screen(changes) } }).find("#plugin-suggest-card").exists()).toBe(false);
  });

  it("says that a yes comes with the update when one waits", () => {
    const card = mount(PluginSuggestCard, { props: { screen: screen({ plugin_suggest: { ...screen().plugin_suggest!, update: true } }) } });
    expect(card.find("#plugin-suggest-yes").text()).toBe(t("editor.plugins.suggest.yes_update"));
  });

  it("sends a yes and a no to the add-on, and nothing before a key is pressed", async () => {
    const card = mount(PluginSuggestCard, { props: { screen: screen() } });
    expect(answers()).toEqual([]);
    await card.find("#plugin-suggest-yes").trigger("click");
    await flushPromises();
    await card.find("#plugin-suggest-no").trigger("click");
    await flushPromises();
    expect(answers()).toEqual([["screens/hall/plugins/suggested", { plugin: "screen_camera", yes: true }],
      ["screens/hall/plugins/suggested", { plugin: "screen_camera", yes: false }]]);
  });
});
