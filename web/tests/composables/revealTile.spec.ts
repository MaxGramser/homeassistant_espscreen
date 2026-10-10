// A tile brought into sight (composables/revealTile.ts): the row of pages around it scrolls across to it, never the window.
import { describe, expect, it, vi } from "vitest";
import { revealTile } from "../../src/composables/revealTile";

const box = (rect: Partial<DOMRect>) => () => ({ left: 0, top: 0, width: 0, height: 0, right: 0, bottom: 0, x: 0, y: 0, toJSON() {}, ...rect }) as DOMRect;
describe("revealTile", () => {
  it("scrolls the row of pages to put the tile in its middle, and leaves a tile in sight where it is", async () => {
    document.body.innerHTML = `<div class="canvas"><div class="pages" style="overflow-x: auto"><div data-tile-id="00aa"></div></div></div>`;
    const row = document.querySelector<HTMLElement>(".pages")!, tile = document.querySelector<HTMLElement>("[data-tile-id]")!;
    Object.defineProperties(row, { scrollWidth: { value: 3000 }, clientWidth: { value: 1000 } });
    row.getBoundingClientRect = box({ left: 0, width: 1000, top: 0, bottom: 800 });
    tile.getBoundingClientRect = box({ left: 1900, width: 200, top: 100, bottom: 200 });
    row.scrollBy = vi.fn() as any;
    const page = vi.fn();
    vi.stubGlobal("scrollBy", page);
    await revealTile("00aa");
    expect(row.scrollBy).toHaveBeenCalledWith({ left: 1500, behavior: "smooth" });
    expect(page).not.toHaveBeenCalled();
    // Not on the mockup (another view is open): nothing moves.
    await revealTile("ffff");
    expect(row.scrollBy).toHaveBeenCalledTimes(1);
  });
});
