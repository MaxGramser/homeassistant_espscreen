import { seedLayout, seedTiles, seedPages, seedTitles, appendTiles, screenFixture, documentFixture, current } from "./page-fixtures";
// Language & region (app 0.2.90): one place for every screen's language, clock and numbers, the update it takes, and
// the top bar that points there.
import { flushPromises, mount } from "@vue/test-utils";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import AppSettingsView from "../src/components/AppSettingsView.vue";
import Sidebar from "../src/components/Sidebar.vue";
import TopbarInspector from "../src/components/TopbarInspector.vue";
import { loadLanguage } from "../src/i18n";
import { state } from "../src/store";
import type { Languages } from "../src/types";
import { useUiStore } from "../src/stores/ui";

const GUIDE = "https://github.com/MaxGramser/homeassistant_espscreen/blob/main/docs/TRANSLATING.md";
function language(extra: Partial<Languages> = {}): Languages {
  return {
    setting: "auto", effective: "nl", ha: "nl", clock: "auto", clock_effective: "24", numbers: "auto", numbers_effective: "comma",
    clock_auto: "24", numbers_auto: "comma", group_min: 1, group_min_auto: 1, percent_space: false,
    languages: [
      { code: "en", name: "English (US)", english: "English (US)", checked: true },
      { code: "en-GB", name: "English (UK)", english: "English (UK)", checked: true },
      { code: "nl", name: "Nederlands", english: "Dutch", checked: true },
      { code: "de", name: "Deutsch", english: "German", checked: false },
    ],
    ...extra,
  };
}
// The add-on: PUT api/language answers with the new state, or refuses; the inventory keeps what it has.
function addOn(answer: (body: any) => Response) {
  const fetch = vi.fn(async (url: string, options: RequestInit = {}) => {
    if (url === "api/language") return answer(JSON.parse(String(options.body)));
    if (url.startsWith("api/inventory")) return new Response(JSON.stringify(state.inventory), { status: 200 });
    return new Response("{}", { status: 200 });
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
const options = (view: ReturnType<typeof mount>, id: string) => view.findAll(`#${id} option`).map((o) => o.text());

// The screens' language here is Dutch: its own number marks come with its file.
beforeAll(() => loadLanguage("nl"));
beforeEach(() => {
  vi.unstubAllGlobals();
  state.inventory = { screens: [], entities: [], updates: { target: "0.2.80", pending: 0 }, language: language() } as any;
});

describe("the Language & region card", () => {
  it("is missing while the add-on has no languages", () => {
    delete state.inventory.language;
    expect(mount(AppSettingsView).find("#language").exists()).toBe(false);
  });
  it("offers Home Assistant's language by its own name, every language, and marks the unchecked ones", () => {
    const view = mount(AppSettingsView);
    expect(view.find("#language h2").text()).toBe("Language & region");
    expect(options(view, "screen-language")).toEqual([
      "Home Assistant's language (Nederlands)", "English (US)", "English (UK)", "Nederlands", "Deutsch · not checked yet, help welcome",
    ]);
    expect((view.find("#screen-language").element as HTMLSelectElement).value).toBe("auto");
    expect(view.find("#language-ha-missing").exists()).toBe(false);
    expect(view.find("#language-help").exists()).toBe(false);
    expect(view.find("#language").text()).toContain("The editor itself follows the language of your Home Assistant profile.");
    expect(options(view, "time-format")).toEqual(["Automatic, follows the language (24 hour)", "24 hour", "12 hour"]);
    expect(options(view, "number-format")).toEqual(["Automatic, follows the language (1.234,5)", "1,234.5", "1.234,5", "1 234,5"]);
  });
  it("says when Home Assistant's language isn't there yet, and asks for help with an unchecked one", () => {
    state.inventory.language = language({ ha: "fy", effective: "en" });
    let view = mount(AppSettingsView);
    expect(options(view, "screen-language")[0]).toBe("Home Assistant's language");
    expect(view.find("#language-ha-missing").text()).toBe("The screens use English until Home Assistant's language is available.");
    // A regional variant takes its base language, as the editor does.
    state.inventory.language = language({ ha: "nl-BE" });
    expect(options(mount(AppSettingsView), "screen-language")[0]).toBe("Home Assistant's language (Nederlands)");
    state.inventory.language = language({ setting: "de", effective: "de" });
    view = mount(AppSettingsView);
    expect(view.find("#language-help").text()).toBe("Deutsch is not checked yet, help welcome: how to translate");
    expect(view.find("#language-help a").attributes("href")).toBe(GUIDE);
  });
  it("saves a choice, and every screen takes the language with its next update", async () => {
    const fetch = addOn((body) => new Response(JSON.stringify({ language: language({ setting: body.setting, effective: body.setting }) }), { status: 200 }));
    const view = mount(AppSettingsView);
    await view.find("#screen-language").setValue("de");
    await flushPromises();
    const put = fetch.mock.calls.find(([url]) => url === "api/language")!;
    expect(put[1]!.method).toBe("PUT");
    expect(JSON.parse(String(put[1]!.body))).toEqual({ setting: "de" });
    expect(state.inventory.language!.setting).toBe("de");
    expect(useUiStore().notice?.message).toBe("Saved. Every screen takes the new language with its next update.");
    // The screens' update state comes with the inventory again.
    expect(fetch.mock.calls.some(([url]) => url === "api/inventory")).toBe(true);
    await view.find("#time-format").setValue("12");
    await flushPromises();
    expect(JSON.parse(String(fetch.mock.calls.filter(([url]) => url === "api/language").pop()![1]!.body))).toEqual({ clock: "12" });
    expect(useUiStore().notice?.message).toBe("Saved.");
  });
  it("shows the add-on's refusal and keeps the stored choice", async () => {
    addOn(() => new Response(JSON.stringify({ error: "That language isn't there." }), { status: 400 }));
    const view = mount(AppSettingsView);
    await view.find("#number-format").setValue("space");
    await flushPromises();
    expect(useUiStore().notice?.message).toBe("That language isn't there.");
    expect((view.find("#number-format").element as HTMLSelectElement).value).toBe("auto");
    expect(state.inventory.language!.numbers).toBe("auto");
  });
  it("offers the clock and numbers of the user's Home Assistant profile when they differ", async () => {
    const hass = { locale: { language: "nl", time_format: "12", number_format: "comma_decimal" } };
    const parent = { document: { documentElement: { lang: "nl" }, querySelector: (tag: string) => (tag === "home-assistant" ? { hass } : null) } };
    vi.stubGlobal("parent", parent);
    const fetch = addOn((body) => new Response(JSON.stringify({ language: language({ clock: body.clock, clock_effective: body.clock, numbers: body.numbers, numbers_effective: body.numbers }) }), { status: 200 }));
    let view = mount(AppSettingsView);
    expect(view.find("#language-profile small").text()).toBe("Your Home Assistant profile: 12 hour · 1,234.5");
    await view.find("#language-profile button").trigger("click");
    await flushPromises();
    expect(JSON.parse(String(fetch.mock.calls.find(([url]) => url === "api/language")![1]!.body))).toEqual({ clock: "12", numbers: "point" });
    expect(view.find("#language-profile").exists()).toBe(false);
    // A profile that follows the language names nothing.
    hass.locale = { language: "nl", time_format: "language", number_format: "language" };
    view = mount(AppSettingsView);
    expect(view.find("#language-profile").exists()).toBe(false);
  });
});

describe("the update a new language takes", () => {
  const screen = (update: object, firmware = "0.2.80") => ({ id: "living", name: "Living room", online: true, firmware, layout: { title: "", tiles: [] }, update } as any);
  it("says the new language when the firmware stays the same", async () => {
    state.inventory.screens = [screen({ language: true, target: "0.2.80", profile: "living.yaml", host: "10.0.0.2" })];
    const sidebar = mount(Sidebar);
    expect(sidebar.find(".update-pill").attributes("title")).toContain("New language: Nederlands");
    await sidebar.find("#screens .nav-item").trigger("click");
    await sidebar.find(".details-toggle").trigger("click");
    expect(sidebar.find(".screen-details .facts").text()).toBe("Firmware0.2.80");
    expect(sidebar.find(".whatsnew").exists()).toBe(false);
  });
  it("puts it first in What's new when the firmware is new too", async () => {
    state.inventory.screens = [screen({ available: true, language: true, target: "0.2.81", profile: "living.yaml" })];
    state.inventory.updates = { target: "0.2.81", pending: 1 };
    state.inventory.changelog = [{ app: "0.2.91", firmware: "0.2.81", lines: ["Faster."] }];
    const sidebar = mount(Sidebar);
    expect(sidebar.find(".update-pill").attributes("title")).toContain("Update 0.2.81");
    await sidebar.find("#screens .nav-item").trigger("click");
    await sidebar.find(".details-toggle").trigger("click");
    expect(sidebar.find(".screen-details .facts dd").text()).toBe("0.2.80 → 0.2.81");
    expect(sidebar.findAll(".whatsnew li").map((li) => li.text())).toEqual(["New language: Nederlands", "Faster."]);
  });
});

describe("the top bar's clock", () => {
  it("points to Language & region instead of a clock of its own", () => {
    seedLayout({ title: "Living room", tiles: [], header: { items: [{ type: "clock" }] } });
    let drawer = mount(TopbarInspector, { props: { index: 0 } });
    expect(drawer.find(".seg").exists()).toBe(false);
    expect(drawer.find("#topbar-clock").text()).toBe("24 hour clock · change under Settings → Language & region");
    expect(drawer.find("#topbar-clock a").attributes("href")).toBe("#settings");
    state.inventory.language = language({ clock_effective: "12" });
    drawer = mount(TopbarInspector, { props: { index: 0 } });
    expect(drawer.find("#topbar-clock").text()).toBe("12 hour clock · change under Settings → Language & region");
  });
});
