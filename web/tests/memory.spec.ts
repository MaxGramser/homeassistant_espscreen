import { describe, expect, it } from "vitest";
import fixture from "../../tests/fixtures/memory-conformance.json";
import { TILE, TYPES } from "../src/model/catalogue";
import { kilobytes, layoutCost, memoryCrossing, memoryUse, NEARLY_FULL, tileCost } from "../src/model/memory";
import type { ScreenMemory } from "../src/types";

// A screen's memory for tiles (firmware 0.34.0+): priced by the tile catalogue as the screen and the add-on price it
// (tile_memory::cost, core.tile_cost), so the meter says what a save will meet.
const said: ScreenMemory = { room: 10000, used: 3000, psram: true, tile: 524, extra: 1056 };
const price = (domain: string) => TYPES[domain].memory.bytes;

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
  it("shows kilobytes, what is needed rounded up and what there is rounded down", () => {
    expect([kilobytes(2049, true), kilobytes(2049)]).toEqual([3, 2]);
  });
});

describe("the memory of pages", () => {
  it("answers every page case the screen and the add-on answer", async () => {
    const { pageCost } = await import("../src/model/memory");
    const cases = (fixture as Record<string, unknown>[]).filter((c) => "page_entities" in c) as { page_entities: number; psram: boolean; page: number; cost: number }[];
    expect(cases.length).toBeGreaterThan(5);
    for (const c of cases) {
      const trailing = [{ type: "clock" }, { type: "clock" }, ...Array.from({ length: c.page_entities }, () => ({ type: "entity" }))];
      expect(pageCost({ topbar: { trailing } }, c), JSON.stringify(c)).toBe(c.cost);
    }
  });
});
