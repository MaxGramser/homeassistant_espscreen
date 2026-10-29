// Which live camera tiles of a page keep their stills (docs/PLATFORM_PLAN.md 4.1): a screen streams at most as many
// live tiles at once as its hello's capability record says (caps.live_tiles, firmware hw.h), the first in tile order on
// the page, as the firmware's runtime_tiles live_tiles_round counts them, and the others show a picture every 15
// seconds. A live tile is a camera or an image with Display Live and the pace Live (0, the default on a screen that
// streams). Pure, so the editor's tests run it (tests/live-tiles.spec.ts).
import type { Tile } from "../types";

export function isLiveTile(tile: Tile, liveByDefault: boolean): boolean {
  const domain = tile.entity.split(".")[0];
  if (domain !== "camera" && domain !== "image") return false;
  if (tile.options?.display !== "live") return false;
  const refresh = tile.options?.refresh;
  return refresh === undefined ? liveByDefault : Number(refresh) === 0;
}

// The ids of the live tiles beyond the cap, page by page (`slots` a page); none without a cap.
export function pausedLive(tiles: Tile[], cap: number | null | undefined, slots: number, liveByDefault: boolean): Set<string> {
  const paused = new Set<string>();
  if (cap === null || cap === undefined || cap < 0 || slots <= 0) return paused;
  const pages = new Map<number, Tile[]>();
  for (const tile of tiles) {
    if (!tile.id || !isLiveTile(tile, liveByDefault)) continue;
    const page = Math.floor(tile.slot / slots);
    pages.set(page, [...(pages.get(page) ?? []), tile]);
  }
  for (const live of pages.values()) {
    live.sort((a, b) => a.slot - b.slot);
    for (const tile of live.slice(cap)) paused.add(tile.id!);
  }
  return paused;
}
