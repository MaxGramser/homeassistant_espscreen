// The Plugins page opens on all of its plugins, not on one kind (a person would think the tiles were all there is);
// the tabs by kind still narrow it.
import { mount, flushPromises } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Plugin } from "../src/model/plugins";
import PluginsView from "../src/components/PluginsView.vue";
import { usePluginsStore } from "../src/stores/plugins";

const plugin = (id: string, type: Plugin["type"]): Plugin => ({
  id, name: { en: id }, summary: { en: "" }, icon: "F00E7", maintainer: "x", tessera: true, version: "1.0.0", repo: "",
  license: "MIT", type, boards: "any", requires: {}, flash_kb: 1, permissions: { home_assistant: [], network: [] },
  readme: { en: "" }, languages: ["en"], attributes: [], source: "index",
});

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } })));
  const plugins = usePluginsStore();
  plugins.loaded = true;
  plugins.index = [plugin("rain", "tiles"), plugin("clock", "screensavers"), plugin("timer", "functions"), plugin("relays", "hardware")];
});

describe("the Plugins page", () => {
  it("opens on all of them, and a tab by kind narrows the list", async () => {
    const view = mount(PluginsView);
    await flushPromises();
    const tabs = view.findAll("#plugin-tabs [data-tab]");
    expect(tabs.map((tab) => tab.attributes("data-tab"))).toEqual(["all", "tiles", "screensavers", "functions", "hardware", "in_use"]);
    expect(tabs[0].attributes("aria-selected")).toBe("true");
    expect(tabs[0].text()).toContain("4");
    const shown = () => view.findAll(".plugin-card").map((card) => card.attributes("data-plugin"));
    expect(shown().sort()).toEqual(["clock", "rain", "relays", "timer"]);
    await view.find("#plugin-tabs [data-tab='screensavers']").trigger("click");
    expect(shown()).toEqual(["clock"]);
  });
});
