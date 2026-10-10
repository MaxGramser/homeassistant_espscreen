// The live stream from the add-on (api/events): the page follows the inventory over it, polls while it is down, and opens
// a new one when the browser has given the old one up, as after an add-on restart that ingress answered with 502.
import { beforeEach, describe, expect, it, vi } from "vitest";
import { startStore, state } from "../src/store";
import { FakeEventSource, lastStream } from "./helpers/browser";

let asked: string[] = [];
const inventories = () => asked.filter((url) => url.startsWith("api/inventory")).length;

beforeEach(() => {
  asked = [];
  vi.useFakeTimers();
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    asked.push(String(url));
    return new Response(JSON.stringify({ csrf: "t", connected: true, screens: [], entities: [] }), { status: 200, headers: { "Content-Type": "application/json" } });
  }));
});

describe("the live stream", () => {
  it("follows the add-on over the stream, and polls only while it is down", async () => {
    const stop = startStore();
    await vi.advanceTimersByTimeAsync(0);
    expect(FakeEventSource.streams).toHaveLength(1);
    lastStream()!.open();
    lastStream()!.send({ connected: false });
    expect(state.connected).toBe(false);
    const open = inventories();
    await vi.advanceTimersByTimeAsync(50000);
    expect(inventories()).toBe(open);
    // Broken for a moment: the browser opens it again by itself, and the page polls every ten seconds meanwhile.
    lastStream()!.fail();
    await vi.advanceTimersByTimeAsync(30000);
    expect(FakeEventSource.streams).toHaveLength(1);
    expect(inventories()).toBe(open + 3);
    stop();
  });

  it("opens a new stream when the browser gave the old one up, later each time, and sooner again once one opens", async () => {
    const stop = startStore();
    await vi.advanceTimersByTimeAsync(0);
    lastStream()!.open();
    // The add-on restarts: ingress answers 502 and the browser closes the stream for good.
    const waits: number[] = [];
    for (let i = 0; i < 6; i++) {
      const count = FakeEventSource.streams.length, before = Date.now();
      lastStream()!.fail(true);
      for (let waited = 0; FakeEventSource.streams.length === count && waited < 60000; waited += 500) await vi.advanceTimersByTimeAsync(500);
      waits.push(FakeEventSource.streams.length === count ? -1 : Date.now() - before);
    }
    expect(waits).toEqual([1000, 2000, 5000, 10000, 30000, 30000]);
    expect(FakeEventSource.streams.slice(0, -1).every((stream) => stream.readyState === FakeEventSource.CLOSED)).toBe(true);
    expect(lastStream()!.url).toBe("api/events?language=en");
    // Back: the stream opens, the page follows it again, and a next restart starts at a second.
    lastStream()!.open();
    lastStream()!.send({ connected: true });
    expect(state.connected).toBe(true);
    const count = FakeEventSource.streams.length;
    lastStream()!.fail(true);
    await vi.advanceTimersByTimeAsync(1000);
    expect(FakeEventSource.streams).toHaveLength(count + 1);
    // Stopped, nothing opens again.
    lastStream()!.fail(true);
    stop();
    await vi.advanceTimersByTimeAsync(60000);
    expect(FakeEventSource.streams).toHaveLength(count + 1);
  });
});
