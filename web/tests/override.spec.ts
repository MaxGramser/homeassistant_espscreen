// A screen's YAML override (OverrideView): Save & check saves it and follows ESPHome's check of the whole profile until it
// ends, by its build in the add-on's build line (it may first wait its turn behind a screen's build), every 1.2 seconds
// while the page is in sight, and says what ESPHome found, from the check's own log.
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { nextTick } from "vue";
import OverrideView from "../src/components/OverrideView.vue";
import { setHidden } from "./helpers/browser";
import { useFakeClock } from "./helpers/clock";
import { answerDialogs } from "./helpers/dialogs";
import { fakeApi } from "./helpers/fake-api";
import { useInventoryStore } from "../src/stores/inventory";
import { useUiStore } from "../src/stores/ui";

type Step = { state: string; stage?: string; logs?: string[] };
const check = (now: Step) => ({ id: 3, by: "check", file: "hall.yaml", action: "validate", state: now.state,
  asked: 1, started: now.state === "queued" ? null : 2, finished: null, ...(now.stage ? { stage: now.stage } : {}),
  ...(now.state === "queued" ? { place: 1, after: "desk.yaml" } : {}) });
// The add-on: the check waits in its build line, which every live answer carries (the inventory's `line`); the firmware
// answer has ESPHome's log of what runs, and a check that ended keeps its own.
function addOn(first: Step, ended: Step = first) {
  return fakeApi({
    "GET firmware/profiles/:file/override": { override_file: "hall.override.yaml", attached: true, exists: true, content: "display: []\n" },
    "PUT firmware/profiles/:file/override": { override_file: "hall.override.yaml" },
    "POST firmware/jobs": () => check(first),
    "GET inventory": () => ({ screens: [], line: [check(first)] }),
    "GET firmware": () => ({ job: { file: "hall.yaml", action: "validate", state: "running", started: 3 }, logs: [] }),
    "GET firmware/builds/:id/log": () => ({ build: check(ended), logs: ended.logs || [] }),
  });
}
// The add-on's next live answer, as its stream brings it.
const push = async (now: Step) => { useInventoryStore().applyLive({ line: [check(now) as any] }); await flushPromises(); };

describe("checking an override", () => {
  it("follows ESPHome's check from the build line until it ends, and then asks no more", async () => {
    const clock = useFakeClock();
    await useUiStore().openOverride("hall.yaml");
    const api = addOn({ state: "queued" });
    const view = mount(OverrideView);
    await flushPromises();
    await view.find("#override-check").trigger("click");
    await clock.settle();
    expect(api.count("POST firmware/jobs")).toBe(1);
    // Behind a screen's build first, then ESPHome's own check.
    expect(view.find("#override-status").text()).toBe("Waiting for the build that runs now, then checking…");
    await push({ state: "running" });
    expect(view.find("#override-status").text()).toBe("ESPHome is checking the profile…");
    await push({ state: "running", stage: "validating" });
    expect(view.find("#override-status").text()).toBe("ESPHome is checking the profile… validating");
    await push({ state: "success" });
    expect(view.find("#override-status").text()).toBe("The complete profile is valid. Safe to build and install.");
    const asked = api.count("GET firmware");
    await clock.tick(30000);
    expect(api.count("GET firmware")).toBe(asked);
  });

  it("asks nothing while the tab is hidden, and says the line of the check's own log that names the error", async () => {
    const clock = useFakeClock();
    await useUiStore().openOverride("hall.yaml");
    const api = addOn({ state: "running" }, { state: "failed", logs: ["INFO Reading", "ERROR display: unknown model", "Failed config"] });
    const view = mount(OverrideView);
    await flushPromises();
    await view.find("#override-check").trigger("click");
    await clock.settle();
    setHidden(true);
    await nextTick();
    const before = api.count("GET firmware");
    await clock.tick(30000);
    expect(api.count("GET firmware")).toBe(before);
    setHidden(false);
    await nextTick();
    await push({ state: "failed" });
    await clock.settle();
    expect(view.find("#override-status").text()).toBe("ERROR display: unknown model");
    expect(view.find("#override-status").classes()).toContain("error");
  });
});

describe("the override's example and Clear", () => {
  it("ask before they replace what is typed, in the editor's own dialog, and keep it when told no", async () => {
    await useUiStore().openOverride("hall.yaml");
    addOn({ state: "running" });
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
