import { describe, expect, it } from "vitest";
import fixture from "../../tests/fixtures/memory-conformance.json";
import { TILE, TYPES } from "../src/model/catalogue";
import { barEntities, kilobytes, layoutCost, measuring, memoryCrossing, memoryLine, memoryUse, proposalHolds, NEARLY_FULL, noRoom, NO_ROOM_SHARE, tileCost } from "../src/model/memory";
import type { ScreenMemory } from "../src/types";

// A screen's memory for tiles (firmware 0.34.0+): priced by the tile catalogue as the screen and the add-on price it
// (tile_memory::cost, core.tile_cost), so the meter says what a save will meet.
const said: ScreenMemory = { room: 10000, used: 3000, psram: true, tile: 524, extra: 1056 };
const price = (domain: string) => TYPES[domain].memory.bytes;

describe("the line a change crosses", () => {
  const use = (share: number, level: "fine" | "close" | "full" | "over" = "fine") => ({ need: share * 100, room: 100, share, level });
  it("is the one rule of an add, a paste and a first layout: close at nine tenths, over past all, nothing once past", () => {
    expect(memoryLine(use(0.5), use(0.8, "close"))).toBeNull();
    expect(memoryLine(use(0.5), use(0.92, "close"))?.line).toBe("close");
    expect(memoryLine(use(0.95, "close"), use(0.97, "close"))).toBeNull();
    expect(memoryLine(use(0.95, "close"), use(1.2, "over"))?.line).toBe("over");
    expect(memoryLine(use(1.2, "over"), use(1.4, "over"))).toBeNull();
  });
});

describe("what a proposal may add", () => {
  const use = (share: number, level: "fine" | "close" | "full" | "over" = "fine") => ({ need: share * 100, room: 100, share, level });
  it("below nine tenths: stays below them", () => {
    expect(proposalHolds(use(0.5), use(0.85, "close"))).toBe(true);
    expect(proposalHolds(use(0.5), use(0.91, "close"))).toBe(false);
  });
  it("between nine tenths and all of the room: stays within the room, where an add would not be asked again", () => {
    expect(proposalHolds(use(0.92, "close"), use(0.99, "full"))).toBe(true);
    expect(proposalHolds(use(0.92, "close"), use(1.05, "over"))).toBe(false);
  });
  it("past all of the room: nothing more that costs memory", () => {
    expect(proposalHolds(use(1.2, "over"), use(1.2, "over"))).toBe(true);
    expect(proposalHolds(use(1.2, "over"), use(1.21, "over"))).toBe(false);
  });
});

describe("the memory a layout takes", () => {
  it("answers every case the screen and the add-on answer", () => {
    expect(fixture.length).toBeGreaterThan(50);
    for (const c of (fixture as Record<string, unknown>[]).filter((c) => "domain" in c) as { domain: string; action: boolean; line: boolean; psram: boolean; tile: number; extra: number; cost: number }[]) {
      const options = { ...(c.action ? { tap: "action" } : {}), ...(c.line ? { sub: "attr:battery" } : {}) };
      expect(tileCost({ entity: c.domain.includes(".") ? c.domain : `${c.domain}.thing`, options }, c), JSON.stringify(c)).toBe(c.cost);
    }
  });
  it("costs a type its price, keys included, and a board without PSRAM the tile and its extras", () => {
    expect(layoutCost([{ entity: "weather.home" }, { entity: "switch.b" }], said)).toBe(price("weather") + price("switch"));
    const inside = { ...said, psram: false };
    expect(tileCost({ entity: "weather.home" }, inside)).toBe(price("weather") + 524 + (TYPES.weather.memory.extras ? 1056 : 0));
    expect(tileCost({ entity: "switch.a", options: { tap: "action" } }, said)).toBe(price("switch") + TILE.memory.action);
  });
  it("counts the tiles of the top bar on a screen that gets them, as the add-on does (core.bar_entities)", () => {
    const pages = [{ topbar: { trailing: [{ type: "entity", entity: "switch.coffee" }, { type: "entity", entity: "light.desk" },
      { type: "entity", entity: "switch.coffee" }, { type: "entity", entity: "zone.home" }, { type: "clock" }] } }];
    const tiles = [{ entity: "light.desk" }];
    expect(barEntities(pages, tiles)).toEqual(["switch.coffee"]);
    expect(layoutCost(tiles, { ...said, bar_cards: true }, pages) - layoutCost(tiles, said, pages)).toBe(price("switch"));
  });
  it("is fine, close, full or over", () => {
    const each = price("switch"), room = 25 * each;
    const memory = { ...said, room, used: 0 };
    expect(memoryUse([{ entity: "switch.a" }], memory).level).toBe("fine");
    expect(memoryUse(Array(20).fill({ entity: "switch.a" }), memory).level).toBe("close");
    expect(memoryUse(Array(25).fill({ entity: "switch.a" }), memory).level).toBe("full");
    expect(memoryUse(Array(26).fill({ entity: "switch.a" }), memory).level).toBe("over");
  });
  it("counts a layout that takes no more than the tiles on the screen now as not over", () => {
    const each = price("switch"), shrunk = { ...said, room: 2 * each, used: 3 * each };
    expect(memoryUse(Array(3).fill({ entity: "switch.a" }), shrunk).level).not.toBe("over");
    expect(memoryUse(Array(4).fill({ entity: "switch.a" }), shrunk).level).toBe("over");
    expect(memoryCrossing(Array(2).fill({ entity: "switch.a" }), { entity: "switch.b" }, shrunk)).toBeNull();
    expect(memoryCrossing(Array(3).fill({ entity: "switch.a" }), { entity: "switch.b" }, shrunk)?.line).toBe("over");
  });
  it("asks once when one more tile takes the layout past nine tenths, and once past all of it (GitHub #157)", () => {
    const each = price("switch"), memory = { ...said, room: 10 * each, used: 0 };
    const tiles = (n: number) => Array(n).fill({ entity: "switch.a" });
    expect(NEARLY_FULL).toBe(0.9);
    expect(memoryCrossing(tiles(7), { entity: "switch.b" }, memory)).toBeNull();
    expect(memoryCrossing(tiles(8), { entity: "switch.b" }, memory)?.line).toBe("close");
    expect(memoryCrossing(tiles(9), { entity: "switch.b" }, memory)).toBeNull();
    expect(memoryCrossing(tiles(10), { entity: "switch.b" }, memory)?.line).toBe("over");
    expect(memoryCrossing(tiles(11), { entity: "switch.b" }, memory)).toBeNull();
    // What it is decides: a forecast takes a nearly full screen past all of it where a switch stays under.
    const nearly = { ...said, room: 10 * each + price("weather") - 1, used: 0 };
    expect(memoryCrossing(tiles(10), { entity: "switch.b" }, nearly)).toBeNull();
    expect(memoryCrossing(tiles(10), { entity: "weather.c" }, nearly)?.line).toBe("over");
  });
  it("says in words that a screen has no room, where a share would read 999 % (GitHub #169)", () => {
    const each = price("switch");
    expect(noRoom(memoryUse([{ entity: "switch.a" }], { ...said, room: 0, used: 0 }))).toBe(true);
    expect(noRoom(memoryUse(Array(NO_ROOM_SHARE).fill({ entity: "switch.a" }), { ...said, room: each, used: 0 }))).toBe(true);
    expect(noRoom(memoryUse(Array(NO_ROOM_SHARE - 1).fill({ entity: "switch.a" }), { ...said, room: each, used: 0 }))).toBe(false);
    expect(memoryCrossing([], { entity: "switch.a" }, { ...said, room: 0, used: 0 })?.line).toBe("none");
    expect(memoryCrossing([], { entity: "switch.a" }, { ...said, room: each, used: 0 })?.line).toBe("close");
    expect(memoryCrossing([{ entity: "switch.a" }], { entity: "switch.b" }, { ...said, room: each, used: 0 })?.line).toBe("over");
  });
  it("knows a screen that is still measuring its room (firmware 0.51.0)", () => {
    expect(measuring({ ...said, room: null })).toBe(true);
    expect(measuring({ ...said, room: 0 })).toBe(false);
    expect(measuring(said)).toBe(false);
  });
  it("shows kilobytes, what is needed rounded up and what there is rounded down", () => {
    expect([kilobytes(2049, true), kilobytes(2049)]).toEqual([3, 2]);
  });
});

describe("the memory of pages", () => {
  it("answers every page case the screen and the add-on answer", async () => {
    const { pageCost } = await import("../src/model/memory");
    const cases = (fixture as Record<string, unknown>[]).filter((c) => "page_entities" in c) as
      { page_entities: number; page_sections: number; sections: boolean; psram: boolean; page: number; cost: number }[];
    expect(cases.length).toBeGreaterThan(5);
    expect(cases.some((c) => c.sections && c.page_sections > 0)).toBe(true);
    for (const c of cases) {
      const trailing = [{ type: "clock" }, { type: "clock" }, ...Array.from({ length: c.page_entities }, () => ({ type: "entity" }))];
      const sections = Array.from({ length: c.page_sections }, (_, n) => ({ title: `Section ${n}` }));
      expect(pageCost({ topbar: { trailing }, sections }, c), JSON.stringify(c)).toBe(c.cost);
    }
  });
});
