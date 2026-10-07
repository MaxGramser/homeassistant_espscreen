// The feedback card (app 0.3.10): "Not quite" goes on to the bug report on GitHub (app 0.4.13), filled in with the board,
// the versions, the chosen problems and the note (app 0.4.78), so only a log is left to add. A yes does not.
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import FeedbackPanel from "../src/components/FeedbackPanel.vue";
import type { Screen } from "../src/types";

function screen(): Screen {
  return {
    id: "living", name: "Living room", online: true, board: "guition", layout: { title: "Living room", tiles: [] },
    feedback: {
      available: true, ask: true, answered: false, shared: null, pending: null, state: "idle", problem: null, deleted: false,
      board: "guition", model: "ESP32-S3-4848S040", privacy: "https://example.com/privacy",
      versions: { firmware_version: "0.47.0", addon_version: "0.4.78" },
    },
  } as unknown as Screen;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify({ feedback: {} }), { status: 200 }))));
});

describe("feedback card", () => {
  it("sends a problem on to a GitHub bug report, filled in", async () => {
    const card = mount(FeedbackPanel, { props: { screen: screen(), mode: "card" } });
    expect(card.find(".fb-report").exists()).toBe(false);
    await card.findAll(".fb-actions .btn")[1].trigger("click");  // Not quite
    await flushPromises();
    await card.findAll(".fb-issue input")[1].setValue(true);  // Touch
    await card.find(".fb-comment textarea").setValue("Taps land a bit to the left.");
    await card.find(".fb-actions .btn.primary").trigger("click");  // Add details
    await flushPromises();
    const report = card.find(".fb-actions a.btn");
    expect(report.exists()).toBe(true);
    expect(report.attributes("target")).toBe("_blank");
    const url = new URL(report.attributes("href")!);
    expect(url.origin + url.pathname).toBe("https://github.com/MaxGramser/homeassistant_espscreen/issues/new");
    expect(url.searchParams.get("template")).toBe("bug_report.yml");
    expect(url.searchParams.get("title")).toBe("[Bug]: Touch on ESP32-S3-4848S040");
    expect(url.searchParams.get("versions")).toBe("add-on 0.4.78, firmware 0.47.0");
    expect(url.searchParams.get("what-happened")).toBe("Taps land a bit to the left.\n\nBoard: ESP32-S3-4848S040 (guition)\nProblem: Touch");
  });
  it("offers the report without details too", async () => {
    const card = mount(FeedbackPanel, { props: { screen: screen(), mode: "card" } });
    await card.findAll(".fb-actions .btn")[1].trigger("click");  // Not quite
    await flushPromises();
    await card.findAll(".fb-actions .btn")[1].trigger("click");  // Done
    const url = new URL(card.find(".fb-actions a.btn").attributes("href")!);
    expect(url.searchParams.get("title")).toBeNull();
    expect(url.searchParams.get("what-happened")).toBe("Board: ESP32-S3-4848S040 (guition)");
  });
  it("does not after a yes", async () => {
    const card = mount(FeedbackPanel, { props: { screen: screen(), mode: "card" } });
    await card.findAll(".fb-actions .btn")[0].trigger("click");  // Yes, works well
    await flushPromises();
    await card.find(".fb-link").trigger("click");  // Add something
    expect(card.find(".fb-comment").exists()).toBe(true);
    expect(card.find(".fb-report").exists()).toBe(false);
  });
});
