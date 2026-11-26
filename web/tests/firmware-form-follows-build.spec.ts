// Firmware & USB opened while a build runs: the form names the screen that builds, not the first profile, so its
// address and its buttons go with the log under them. With nothing building it starts at the first profile, and a
// profile the person chose stays chosen through every answer.
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import FirmwareView from "../src/components/FirmwareView.vue";

let job: Record<string, unknown> | null = null;
const answer = () => ({ available: true, ports: [], profiles: [{ file: "bigdisplay-cyd.yaml" }, { file: "entrance.yaml" }, { file: "guition.yaml" }],
  logs: ["INFO Compiling"], wifi: { state: "ready" }, taken: { nodes: [], prefixes: [] }, job });

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const body = String(url) === "api/firmware" ? answer() : String(url) === "api/firmware/logs" ? { logs: [] } : {};
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  }));
});
afterEach(() => vi.useRealTimers());

async function open() {
  const view = mount(FirmwareView);
  await flushPromises(); await vi.advanceTimersByTimeAsync(0);
  return view;
}
const profile = (view: Awaited<ReturnType<typeof open>>) => (view.get("#firmware-file").element as HTMLSelectElement).value;
const host = (view: Awaited<ReturnType<typeof open>>) => view.get("#firmware-host").attributes("placeholder");

describe("the profile Firmware & USB opens on", () => {
  it("is the one of the build that runs, with its address", async () => {
    job = { file: "entrance.yaml", action: "install", state: "running", started: 1 };
    const view = await open();
    expect(profile(view)).toBe("entrance.yaml");
    expect(host(view)).toBe("entrance.local");
    expect(view.get("#firmware-status").text()).toContain("entrance.yaml");
    view.unmount();
  });

  it("is the first with nothing building, or when the last build ended", async () => {
    job = null;
    let view = await open();
    expect(profile(view)).toBe("bigdisplay-cyd.yaml");
    view.unmount();
    job = { file: "entrance.yaml", action: "install", state: "success", started: 1 };
    view = await open();
    expect(profile(view)).toBe("bigdisplay-cyd.yaml");
    view.unmount();
  });

  it("is the first when the build that runs has no profile here", async () => {
    job = { file: "gone.yaml", action: "install", state: "running", started: 1 };
    const view = await open();
    expect(profile(view)).toBe("bigdisplay-cyd.yaml");
    view.unmount();
  });

  it("stays the person's choice while the build goes on", async () => {
    job = { file: "entrance.yaml", action: "install", state: "running", started: 1 };
    const view = await open();
    await view.get("#firmware-file").setValue("guition.yaml");
    await vi.advanceTimersByTimeAsync(9000); await flushPromises();
    expect(profile(view)).toBe("guition.yaml");
    view.unmount();
  });
});
