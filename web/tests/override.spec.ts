// A screen's YAML override (OverrideView): Save & check saves it and follows ESPHome's check of the whole profile until it
// ends, every 1.2 seconds while the page is in sight, and says what ESPHome found.
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { nextTick } from "vue";
import OverrideView from "../src/components/OverrideView.vue";
import { setHidden } from "./helpers/browser";
import { useFakeClock } from "./helpers/clock";
import { answerDialogs } from "./helpers/dialogs";
import { fakeApi } from "./helpers/fake-api";
import { useUiStore } from "../src/stores/ui";

function addOn(states: { state: string; stage?: string; logs?: string[] }[]) {
  let turn = 0;
  return fakeApi({
    "GET firmware/profiles/:file/override": { override_file: "hall.override.yaml", attached: true, exists: true, content: "display: []\n" },
    "PUT firmware/profiles/:file/override": { override_file: "hall.override.yaml" },
    "POST firmware/jobs": { file: "hall.yaml", action: "validate", state: "running" },
    "GET firmware": () => {
      const now = states[Math.min(turn++, states.length - 1)];
      return { job: { file: "hall.yaml", action: "validate", state: now.state, stage: now.stage }, logs: now.logs || [] };
    },
  });
}

describe("checking an override", () => {
  it("follows ESPHome's check until it ends, and then asks no more", async () => {
    const clock = useFakeClock();
    useUiStore().overrideProfile = "hall.yaml";
    const api = addOn([{ state: "running" }, { state: "running", stage: "validating" }, { state: "success" }]);
    const view = mount(OverrideView);
    await flushPromises();
    await view.find("#override-check").trigger("click");
    await clock.settle();
    expect(api.count("POST firmware/jobs")).toBe(1);
    expect(view.find("#override-status").text()).toBe("ESPHome is checking the profile…");
    await clock.tick(1200);
    expect(view.find("#override-status").text()).toBe("ESPHome is checking the profile… validating");
    await clock.tick(1200);
    expect(view.find("#override-status").text()).toBe("The complete profile is valid. Safe to build and install.");
    const asked = api.count("GET firmware");
    await clock.tick(30000);
    expect(api.count("GET firmware")).toBe(asked);
  });

  it("asks nothing while the tab is hidden, and says the line of the log that names the error", async () => {
    const clock = useFakeClock();
    useUiStore().overrideProfile = "hall.yaml";
    const api = addOn([{ state: "running" }, { state: "failed", logs: ["INFO Reading", "ERROR display: unknown model", "Failed config"] }]);
    const view = mount(OverrideView);
    await flushPromises();
    await view.find("#override-check").trigger("click");
    await clock.settle();
    setHidden(true);
    await nextTick();
    await clock.tick(30000);
    expect(api.count("GET firmware")).toBe(1);
    setHidden(false);
    await nextTick();
    await clock.tick(1200);
    expect(view.find("#override-status").text()).toBe("ERROR display: unknown model");
    expect(view.find("#override-status").classes()).toContain("error");
  });
});

describe("the override's example and Clear", () => {
  it("ask before they replace what is typed, in the editor's own dialog, and keep it when told no", async () => {
    useUiStore().overrideProfile = "hall.yaml";
    addOn([{ state: "running" }]);
    const view = mount(OverrideView);
    await flushPromises();
    const typed = () => (view.find("#override-editor").element as HTMLTextAreaElement).value;
    let yes = false;
    const asked = answerDialogs(() => yes);
    await view.find("#override-example").trigger("click");
    await flushPromises();
    expect(typed()).toBe("display: []\n");
    yes = true;
    await view.find("#override-example").trigger("click");
    await flushPromises();
    expect(typed()).toContain("id: !extend my_display");
    await view.find("#override-empty").trigger("click");
    await flushPromises();
    expect(typed()).toBe("");
    expect(asked).toEqual([
      { kind: "confirm", message: "Replace the current text with the example?", confirm: "Replace with example", danger: true },
      { kind: "confirm", message: "Replace the current text with the example?", confirm: "Replace with example", danger: true },
      { kind: "confirm", message: "Clear the local override?", confirm: "Clear override", danger: true }]);
  });
});
