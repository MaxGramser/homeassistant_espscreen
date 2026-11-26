// Firmware & USB: the log of the build that runs follows its newest line, as a screen's build log and New screen's do,
// and stays where a reader who scrolled up to read left it. The add-on sends the newest 300 lines with every answer.
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import FirmwareView from "../src/components/FirmwareView.vue";

let logs: string[] = [];
const answer = () => ({ available: true, ports: [], profiles: [{ file: "entrance.yaml" }], logs, wifi: { state: "ready" },
  taken: { nodes: [], prefixes: [] }, job: { file: "entrance.yaml", action: "install", state: "running", started: 1 } });
const restore: (() => void)[] = [];
// jsdom lays nothing out: the live log is 320 px high and holds 18 px a line.
function measure(name: "scrollHeight" | "clientHeight", value: (element: HTMLElement) => number) {
  // Element's own measure stays; this one, on HTMLElement in front of it, goes again after each test.
  Object.defineProperty(HTMLElement.prototype, name, { configurable: true, get(this: HTMLElement) { return this.id === "firmware-log" ? value(this) : 0; } });
  restore.push(() => { delete (HTMLElement.prototype as any)[name]; });
}

beforeEach(() => {
  vi.useFakeTimers();
  logs = Array.from({ length: 300 }, (_, i) => `INFO Compiling part_${i}.cpp.o`);
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const body = String(url) === "api/firmware" ? answer() : String(url) === "api/firmware/logs" ? { logs: [] } : {};
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  }));
  measure("scrollHeight", (element) => (element.textContent || "").split("\n").length * 18);
  measure("clientHeight", () => 320);
});
afterEach(() => { restore.splice(0).forEach((undo) => undo()); vi.useRealTimers(); });

describe("the live log on Firmware & USB", () => {
  it("opens at its newest line and keeps following it, also once it holds the add-on's 300", async () => {
    const view = mount(FirmwareView, { attachTo: document.body });
    await flushPromises(); await vi.advanceTimersByTimeAsync(0);
    const log = view.get("#firmware-log").element as HTMLElement;
    expect(log.textContent).toContain("part_299");
    expect(log.scrollTop).toBe(300 * 18);
    // The next answer: still 300 lines, the oldest gone and a new one last.
    logs = [...logs.slice(1), "INFO Linking firmware.elf"];
    await vi.advanceTimersByTimeAsync(3000); await flushPromises();
    expect(log.textContent).toContain("Linking firmware.elf");
    expect(log.scrollTop).toBe(300 * 18);
    view.unmount();
  });

  it("stays where a reader scrolled up to", async () => {
    const view = mount(FirmwareView, { attachTo: document.body });
    await flushPromises(); await vi.advanceTimersByTimeAsync(0);
    const log = view.get("#firmware-log").element as HTMLElement;
    log.scrollTop = 1000;
    logs = [...logs.slice(1), "INFO Linking firmware.elf"];
    await vi.advanceTimersByTimeAsync(3000); await flushPromises();
    expect(log.textContent).toContain("Linking firmware.elf");
    expect(log.scrollTop).toBe(1000);
    view.unmount();
  });
});
