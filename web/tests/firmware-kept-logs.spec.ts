// Firmware & USB: the log of the build that runs, then every kept build log under it (GitHub #473). The panel is a grid
// that scrolls with auto rows, and a box that scrolls in such a row may shrink to nothing (its automatic minimum height
// is 0): with 40 kept logs the page was taller than the window and the live log was one line. jsdom lays nothing out,
// so this test holds the page's order and the rule that keeps each row at its own height; the height itself is measured
// in a browser (the pull request for #473 says how).
import { flushPromises, mount } from "@vue/test-utils";
import { readFileSync } from "node:fs";
import { beforeEach, describe, expect, it, vi } from "vitest";
import FirmwareView from "../src/components/FirmwareView.vue";

const LINES = Array.from({ length: 200 }, (_, i) => `INFO Compiling src/esphome/components/part_${i}.cpp.o`);
const firmware = { available: true, ports: [], profiles: [{ file: "entrance.yaml" }, { file: "bigdisplay-cyd.yaml" }], logs: LINES,
  wifi: { state: "ready" }, taken: { nodes: [], prefixes: [] }, job: { file: "entrance.yaml", action: "install", state: "running", started: 1 } };
const kept = Array.from({ length: 40 }, (_, i) => ({ key: `20261125-2259${String(i).padStart(2, "0")}-entrance`, by: "plugins",
  file: "entrance.yaml", started: 1764111540 - i * 600, state: i ? "succeeded" : "running", size: 1000 }));

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const body = String(url) === "api/firmware" ? firmware : String(url) === "api/firmware/logs" ? { logs: kept } : {};
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  }));
});

/** What a stylesheet gives a selector, as written: the rule that starts a line with it. */
function rule(css: string, selector: string) {
  const found = new RegExp(`^${selector.replace(/[.#\\]/g, "\\$&")} \\{([^}]*)\\}`, "m").exec(css);
  expect(found, selector).not.toBeNull();
  return found![1];
}

describe("Firmware & USB with many kept build logs", () => {
  it("shows the running build's log first, then every kept log, both straight in the panel", async () => {
    const view = mount(FirmwareView);
    await flushPromises();
    const panel = view.get("#firmware-dialog").element;
    const log = view.get("#firmware-log").element;
    const list = view.get("#firmware-kept-logs").element;
    expect(log.textContent).toContain(LINES[0]);
    expect(log.textContent).toContain(LINES[199]);
    expect(view.findAll("#firmware-kept-logs li")).toHaveLength(40);
    // Both are rows of the panel's grid, the live log above the list: the rows the rule below keeps at their height.
    expect(log.parentElement).toBe(panel);
    expect(list.parentElement).toBe(panel);
    expect(log.compareDocumentPosition(list) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    view.unmount();
  });

  it("keeps the panel's rows at their own height, so the live log is never squeezed to a line", () => {
    const css = readFileSync("src/styles/app.css", "utf8");
    // The condition of the bug: a panel is a grid that scrolls, and the live log is a box that scrolls, up to 320 px.
    expect(rule(css, ".panel")).toMatch(/overflow: auto;/);
    expect(rule(css, ".panel")).toMatch(/display: grid;/);
    expect(rule(css, ".log")).toMatch(/max-height: 320px;/);
    // The fix: rows as tall as what is in them, so the page scrolls instead of the log shrinking.
    expect(rule(css, "#firmware-dialog")).toMatch(/grid-auto-rows: max-content;/);
  });
});
