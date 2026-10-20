// The stars card (docs/PLUGINS.md, "Likes, ratings and counting"): it waits for the board's card, asks once whether to
// count, sends only on Send, and after the stars offers a heart for a good plugin or the plugin's issues for a poor one.
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PluginRatingCard from "../src/components/PluginRatingCard.vue";
import type { Screen } from "../src/types";

type Call = { url: string; method: string; body: any };
let calls: Call[] = [];

function screen(changes: Partial<Screen> = {}): Screen {
  return {
    id: "kitchen", name: "Kitchen", online: true, board: "cyd", layout: { title: "Kitchen", tiles: [] }, feedback: null,
    plugin_ask: {
      plugin: "waste_collection", name: { en: "Waste collection" }, version: "1.0.7", days: 5, maintainer: "MaxGramser",
      tessera: false, issues: "https://github.com/maxgramser/tessera-plugins/issues/new", image: null, board: "cyd",
      ask_counting: true, privacy: "https://example.com/privacy",
    },
    ...changes,
  } as unknown as Screen;
}

beforeEach(() => {
  calls = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init: RequestInit = {}) => {
    const body = init.body ? JSON.parse(String(init.body)) : null;
    calls.push({ url: String(url), method: init.method || "GET", body });
    const sharing = { consented: false, counting: Boolean(body?.on), counting_asked: true, asking: true, counted: null, usable: true };
    const answer = String(url).endsWith("/rating") ? { stars: body.stars, rating: null, ratings: 1, homes: 0 }
      : String(url).endsWith("/like") ? { liked: true, likes: 4 } : { likes: sharing };
    return Promise.resolve(new Response(JSON.stringify(answer), { status: 200 }));
  }));
});

const sent = () => calls.map((c) => [c.method, c.url.replace(/^.*api\//, ""), c.body]);

describe("stars card", () => {
  it("waits while the board's card asks, and while the screen is offline", () => {
    expect(mount(PluginRatingCard, { props: { screen: screen({ feedback: { ask: true } as any }) } }).find("#plugin-rate-card").exists()).toBe(false);
    expect(mount(PluginRatingCard, { props: { screen: screen({ online: false }) } }).find("#plugin-rate-card").exists()).toBe(false);
    const card = mount(PluginRatingCard, { props: { screen: screen() } });
    expect(card.find("#plugin-rate-title").text()).toBe("Waste collection has run on Kitchen for 5 days. How do you like it?");
    expect(card.find("#plugin-rate-send").attributes("disabled")).toBeDefined();
  });

  it("asks to count only once stars are chosen, sends both on Send, then offers a heart", async () => {
    const card = mount(PluginRatingCard, { props: { screen: screen() } });
    expect(card.find("#plugin-rate-count").exists()).toBe(false);
    await card.find('[data-star="5"]').trigger("click");
    expect(calls).toEqual([]);
    await card.find("#plugin-rate-count").trigger("click");
    await card.find("#plugin-rate-send").trigger("click");
    await flushPromises();
    expect(sent()).toEqual([
      ["PUT", "plugins/waste_collection/rating", { stars: 5, screen: "kitchen" }],
      ["PUT", "plugins/counting", { on: true }],
    ]);
    expect(card.find("#plugin-rate-thanks").text()).toContain("Your stars are with Waste collection");
    await card.find("#plugin-rate-heart").trigger("click");
    await flushPromises();
    expect(sent().at(-1)).toEqual(["PUT", "plugins/waste_collection/like", { like: true, consent: true }]);
    expect(card.find("#plugin-rate-heart").attributes("aria-pressed")).toBe("true");
  });

  it("says no to counting when the switch stays off, and sends a poor plugin to its issues", async () => {
    const card = mount(PluginRatingCard, { props: { screen: screen() } });
    await card.find('[data-star="2"]').trigger("click");
    await card.find("#plugin-rate-send").trigger("click");
    await flushPromises();
    expect(sent()).toEqual([
      ["PUT", "plugins/waste_collection/rating", { stars: 2, screen: "kitchen" }],
      ["POST", "plugins/waste_collection/ask", { action: "asked_counting" }],
    ]);
    expect(card.find("#plugin-rate-heart").exists()).toBe(false);
    const url = new URL(card.find("#plugin-rate-issue").attributes("href")!);
    expect(url.origin + url.pathname).toBe("https://github.com/maxgramser/tessera-plugins/issues/new");
    expect(url.searchParams.get("title")).toBe("[waste_collection] ");
    expect(url.searchParams.get("body")).toBe("Plugin: waste_collection 1.0.7\nScreen: cyd\n\nWhat goes wrong:");
  });

  it("puts the plugin off with Later, and asks nothing about counting once it was asked", async () => {
    const asked = screen();
    asked.plugin_ask!.ask_counting = false;
    const card = mount(PluginRatingCard, { props: { screen: asked } });
    await card.find("#plugin-rate-later").trigger("click");
    await flushPromises();
    expect(sent()).toEqual([["POST", "plugins/waste_collection/ask", { action: "later" }]]);
    await card.find('[data-star="4"]').trigger("click");
    expect(card.find("#plugin-rate-count").exists()).toBe(false);
  });

  it("moves the stars with the arrow keys", async () => {
    const card = mount(PluginRatingCard, { props: { screen: screen() }, attachTo: document.body });
    await card.find('[data-star="3"]').trigger("click");
    (card.find('[data-star="3"]').element as HTMLElement).focus();
    await card.find('[data-star="3"]').trigger("keydown", { key: "ArrowRight" });
    await flushPromises();
    expect(document.activeElement).toBe(card.find('[data-star="4"]').element);
    expect(card.find('[data-star="4"]').attributes("aria-checked")).toBe("true");
    expect(card.findAll('.star[data-state="active"]')).toHaveLength(4);
  });
});
