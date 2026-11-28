// The feedback card (app 0.3.10): "Not quite" goes on to the bug report on GitHub (app 0.4.13), filled in with the board,
// the versions, the chosen problems and the note (app 0.4.78), so only a log is left to add. A yes does not.
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { router } from "../src/router";
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
  it("sends a problem on to the troubleshooting report, or the manual", async () => {
    const card = mount(FeedbackPanel, { props: { screen: screen(), mode: "card" } });
    expect(card.find(".fb-report").exists()).toBe(false);
    await card.findAll(".fb-actions .btn")[1].trigger("click");  // Not quite
    await flushPromises();
    await card.findAll(".fb-issue input")[1].setValue(true);  // Touch
    await card.find(".fb-comment textarea").setValue("Taps land a bit to the left.");
    await card.find(".fb-actions .btn.primary").trigger("click");  // Add details
    await flushPromises();
    expect(card.find(".fb-report").exists()).toBe(true);
    const manual = card.find(".fb-actions a.btn");
    expect(manual.attributes("target")).toBe("_blank");
    expect(manual.attributes("href")).toBe("https://tessera-maxgramser.on-forge.com/docs/troubleshooting");
    await card.find(".fb-actions .btn.primary").trigger("click");  // Send a report
    await flushPromises();
    expect(String(router.currentRoute.value.name)).toBe("report");
    expect(router.currentRoute.value.params.id).toBe(screen().id);
  });
  it("offers the two ways without details too", async () => {
    const card = mount(FeedbackPanel, { props: { screen: screen(), mode: "card" } });
    await card.findAll(".fb-actions .btn")[1].trigger("click");  // Not quite
    await flushPromises();
    await card.findAll(".fb-actions .btn")[1].trigger("click");  // Done
    expect(card.find(".fb-actions .btn.primary").exists()).toBe(true);
    expect(card.find(".fb-actions a.btn").attributes("href")).toContain("/docs/troubleshooting");
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
