// The live stream from the add-on (stores/inventory.ts): the page follows the inventory over it, polls while it is down
// (closer while something builds), reads the whole catalogue every five minutes and when the tab is shown again, asks
// nothing while the tab is hidden, says when the add-on cannot be reached, and opens a new stream when the browser has
// given the old one up, as after an add-on restart that ingress answered with 502. Its stop leaves nothing running.
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FakeEventSource, lastStream, setHidden } from "./helpers/browser";
import { FULL_REFRESH_MS, useInventoryStore } from "../src/stores/inventory";

let asked: string[] = [], answer: () => Response;
const ok = () => new Response(JSON.stringify({ csrf: "t", connected: true, screens: [], entities: [] }), { status: 200, headers: { "Content-Type": "application/json" } });
const inventories = () => asked.filter((url) => url.startsWith("api/inventory"));

beforeEach(() => {
  asked = [];
  answer = ok;
  vi.useFakeTimers();
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    asked.push(String(url));
    return answer();
  }));
});

describe("the live stream", () => {
  it("follows the add-on over the stream, and polls only while it is down", async () => {
    const inventory = useInventoryStore();
    const stop = inventory.start();
    expect(inventory.start()).toBe(stop);
    await vi.advanceTimersByTimeAsync(0);
    expect(FakeEventSource.streams).toHaveLength(1);
    expect(inventories()).toEqual(["api/inventory"]);
    lastStream()!.open();
    lastStream()!.send({ connected: false });
    expect(inventory.connected).toBe(false);
    const open = inventories().length;
    await vi.advanceTimersByTimeAsync(50000);
    expect(inventories()).toHaveLength(open);
    // Broken for a moment: the browser opens it again by itself, and the page polls every ten seconds meanwhile.
    lastStream()!.fail();
    await vi.advanceTimersByTimeAsync(30000);
    expect(FakeEventSource.streams).toHaveLength(1);
    expect(inventories()).toHaveLength(open + 3);
    expect(inventories().slice(open)).toEqual(Array(3).fill("api/inventory?light=1"));
    stop();
  });

  it("polls every three seconds while something builds, as it is told", async () => {
    let building = true;
    const stop = useInventoryStore().start({ busy: () => building });
    await vi.advanceTimersByTimeAsync(0);
    lastStream()!.fail();
    const before = inventories().length;
    await vi.advanceTimersByTimeAsync(9000);
    expect(inventories().length - before).toBe(3);
    // Done: the poll already set comes three seconds later, then every ten.
    building = false;
    await vi.advanceTimersByTimeAsync(20000);
    expect(inventories().length - before).toBe(5);
    stop();
  });

  it("reads the whole catalogue every five minutes, even while the stream is open", async () => {
    const stop = useInventoryStore().start();
    await vi.advanceTimersByTimeAsync(0);
    lastStream()!.open();
    await vi.advanceTimersByTimeAsync(FULL_REFRESH_MS - 60000);
    expect(inventories()).toEqual(["api/inventory"]);
    await vi.advanceTimersByTimeAsync(60000);
    expect(inventories()).toEqual(["api/inventory", "api/inventory"]);
    stop();
  });

  it("asks nothing while the tab is hidden, takes no message then, and reads everything again when it is shown", async () => {
    const inventory = useInventoryStore();
    const stop = inventory.start();
    await vi.advanceTimersByTimeAsync(0);
    lastStream()!.fail();
    setHidden(true);
    const before = inventories().length;
    await vi.advanceTimersByTimeAsync(60000);
    expect(inventories()).toHaveLength(before);
    lastStream()!.send({ connected: false });
    expect(inventory.connected).toBe(true);
    setHidden(false);
    await vi.advanceTimersByTimeAsync(0);
    expect(inventories().slice(before)).toEqual(["api/inventory"]);
    stop();
  });

  it("says when the add-on cannot be reached, and keeps what it had", async () => {
    const inventory = useInventoryStore();
    const stop = inventory.start();
    await vi.advanceTimersByTimeAsync(0);
    expect([inventory.reachable, inventory.connected]).toEqual([true, true]);
    lastStream()!.fail();
    answer = () => new Response("Bad gateway", { status: 502 });
    await vi.advanceTimersByTimeAsync(10000);
    expect([inventory.reachable, inventory.connected]).toEqual([false, true]);
    answer = ok;
    await vi.advanceTimersByTimeAsync(10000);
    expect(inventory.reachable).toBe(true);
    stop();
  });

  it("opens a new stream when the browser gave the old one up, later each time, and sooner again once one opens", async () => {
    const inventory = useInventoryStore();
    const stop = inventory.start();
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
    lastStream()!.send({ connected: false });
    expect(inventory.connected).toBe(false);
    const count = FakeEventSource.streams.length;
    lastStream()!.fail(true);
    await vi.advanceTimersByTimeAsync(1000);
    expect(FakeEventSource.streams).toHaveLength(count + 1);
    // Stopped, nothing opens again, nothing is asked and no timer is left.
    lastStream()!.fail(true);
    stop();
    const after = asked.length;
    await vi.advanceTimersByTimeAsync(600000);
    expect(FakeEventSource.streams).toHaveLength(count + 1);
    expect(asked).toHaveLength(after);
    expect(vi.getTimerCount()).toBe(0);
    expect(lastStream()!.readyState).toBe(FakeEventSource.CLOSED);
  });

  it("knows the add-on is back as soon as a new stream opens, and reads what changed meanwhile at once", async () => {
    const inventory = useInventoryStore();
    const stop = inventory.start();
    await vi.advanceTimersByTimeAsync(0);
    lastStream()!.open();
    // The add-on restarts: the stream is given up, the poll fails.
    answer = () => new Response("Bad gateway", { status: 502 });
    lastStream()!.fail(true);
    await vi.advanceTimersByTimeAsync(10000);
    expect(inventory.reachable).toBe(false);
    answer = ok;
    const before = inventories().length;
    // Back: the next stream opens before the next poll, and the page reads the inventory at once.
    lastStream()!.open();
    await vi.advanceTimersByTimeAsync(0);
    expect([inventory.reachable, inventories().length - before]).toEqual([true, 1]);
    // A message on the stream says so as well.
    inventory.reachable = false;
    lastStream()!.send({ connected: true });
    expect(inventory.reachable).toBe(true);
    stop();
  });

  it("opens no new stream while the tab is hidden, and opens it when the tab is shown", async () => {
    const stop = useInventoryStore().start();
    await vi.advanceTimersByTimeAsync(0);
    setHidden(true);
    const count = FakeEventSource.streams.length;
    lastStream()!.fail(true);
    await vi.advanceTimersByTimeAsync(120000);
    expect(FakeEventSource.streams).toHaveLength(count);
    setHidden(false);
    await vi.advanceTimersByTimeAsync(0);
    expect(FakeEventSource.streams).toHaveLength(count + 1);
    stop();
  });
});
