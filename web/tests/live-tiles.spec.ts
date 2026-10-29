import { describe, expect, it } from "vitest";
import { isLiveTile, pausedLive } from "../src/model/live-tiles";
import type { Tile } from "../src/types";

const camera = (id: string, slot: number, options: Tile["options"] = { display: "live" }): Tile =>
  ({ id, entity: `camera.${id}`, name: "", slot, options });

describe("live tiles a screen streams at once", () => {
  it("are cameras and images with Display Live and the pace Live", () => {
    expect(isLiveTile(camera("a", 0), true)).toBe(true);
    expect(isLiveTile(camera("a", 0), false)).toBe(false);
    expect(isLiveTile(camera("a", 0, { display: "live", refresh: 0 }), false)).toBe(true);
    expect(isLiveTile(camera("a", 0, { display: "live", refresh: 15 }), true)).toBe(false);
    expect(isLiveTile(camera("a", 0, { display: "standard" }), true)).toBe(false);
    expect(isLiveTile({ id: "l", entity: "light.a", name: "", slot: 0, options: { display: "live" } }, true)).toBe(false);
  });

  it("keep the stills of those beyond the cap, page by page, in tile order", () => {
    const tiles = [camera("e", 14), camera("a", 0), camera("b", 2), camera("c", 10), camera("d", 12), camera("f", 25)];
    expect([...pausedLive(tiles, 4, 25, true)]).toEqual(["e"]);
    expect([...pausedLive(tiles, 2, 25, true)].sort()).toEqual(["c", "d", "e"]);
    expect(pausedLive(tiles, null, 25, true).size).toBe(0);
    expect(pausedLive(tiles, 4, 25, false).size).toBe(0);
  });
});
