// The add-on's firmware job (api/firmware) is asked for once every few seconds, whoever follows it: New screen, Firmware &
// USB and the build log's poll of the store share the answer instead of each asking, and nothing asks while the tab is
// hidden.
import { mount } from "@vue/test-utils";
import { readFileSync } from "node:fs";
import { beforeEach, describe, expect, it, vi } from "vitest";
import FirmwareView from "../src/components/FirmwareView.vue";
import InstallerView from "../src/components/InstallerView.vue";
import { followBuilds } from "../src/composables/useFirmwareJob";
import { startStore, state } from "../src/store";
import { setHidden } from "./helpers/browser";
import { useBuildsStore } from "../src/stores/builds";

const SHAPES = JSON.parse(readFileSync("../screen_manager/app/boards.json", "utf8"));
const BOARDS = Object.fromEntries(Object.entries(SHAPES).filter(([key, shape]: [string, any]) => shape.board === key)
  .map(([key, shape]: [string, any]) => [key, { orientations: shape.orientations, width: shape.width, height: shape.height, dpi: shape.dpi, ...shape.catalog }]));
const building = { hall: { by: "update", state: "running", file: "hall.yaml" } };
const firmware = { available: true, ports: [], profiles: [{ file: "hall.yaml" }], logs: ["INFO Compiling"], wifi: { state: "ready" }, boards: BOARDS,
  taken: { nodes: [], prefixes: [] }, job: { file: "hall.yaml", action: "install", state: "running", started: 1 } };
let asked: string[] = [];
const firmwareAsks = () => asked.filter((url) => url === "api/firmware").length;

beforeEach(() => {
  asked = [];
  vi.useFakeTimers();
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    asked.push(String(url));
    const body = String(url) === "api/firmware" ? firmware
      : String(url).startsWith("api/inventory") ? { csrf: "t", connected: true, screens: [{ id: "hall", name: "Hall", online: true, layout: { title: "Hall", tiles: [] } }], entities: [], builds: building }
      : {};
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  }));
});

describe("the firmware job", () => {
  it("is asked for every three seconds by New screen, and not while the tab is hidden", async () => {
    mount(InstallerView);
    await vi.advanceTimersByTimeAsync(0);
    expect(firmwareAsks()).toBe(1);
    await vi.advanceTimersByTimeAsync(9000);
    expect(firmwareAsks()).toBe(4);
    setHidden(true);
    await vi.advanceTimersByTimeAsync(30000);
    expect(firmwareAsks()).toBe(4);
    setHidden(false);
    await vi.advanceTimersByTimeAsync(3000);
    expect(firmwareAsks()).toBe(5);
  });

  it("is asked for every three seconds by Firmware & USB, and not while the tab is hidden", async () => {
    mount(FirmwareView);
    await vi.advanceTimersByTimeAsync(9000);
    expect(firmwareAsks()).toBe(4);
    setHidden(true);
    await vi.advanceTimersByTimeAsync(30000);
    expect(firmwareAsks()).toBe(4);
  });

  it("is asked for once, not twice, while a view follows it during a build the store follows too", async () => {
    const stop = startStore(), stopBuilds = followBuilds();
    await vi.advanceTimersByTimeAsync(0);
    expect(Object.keys(state.inventory.builds || {})).toEqual(["hall"]);
    // The store alone: its build poll asks every three seconds for the build log.
    await vi.advanceTimersByTimeAsync(9000);
    expect(firmwareAsks()).toBe(3);
    expect(useBuildsStore().firmwareJob?.logs).toEqual(["INFO Compiling"]);
    // New screen opens between two turns of the store: its first look, then one answer every three seconds for both
    // (before, each asked every three seconds: 21).
    await vi.advanceTimersByTimeAsync(1500);
    const before = firmwareAsks();
    mount(InstallerView);
    await vi.advanceTimersByTimeAsync(30000);
    expect(firmwareAsks() - before).toBe(11);
    // Hidden, nobody asks.
    setHidden(true);
    const hidden = firmwareAsks();
    await vi.advanceTimersByTimeAsync(30000);
    expect(firmwareAsks()).toBe(hidden);
    stopBuilds(); stop();
  });
});
