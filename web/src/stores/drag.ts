// A drag on the mockup as the page draws it: whether one is under way, the tile it carries, where everything would end up
// if it were dropped now, a whole page on its way to another place in the row, the key place under a bedside clock the
// pointer is on, and a page that refuses the tile. The pointer work itself (holding, following the pointer, the ghost,
// scrolling near an edge, the drop) is drag.ts's, which writes here; the mockup, the row of pages and the draft read it.
import { defineStore } from "pinia";
import { ref, shallowRef } from "vue";
import type { Tile } from "../types";

// A whole page on its way to another place in the row (app 0.2.121): where it came from, where it is heading, and the row
// as it stands while it is in the air (`order[position]` is the page drawn there).
export type PageDrag = { from: number; to: number; order: number[] };
// The key place under a bedside clock the pointer is on (app 0.4.12), where a drop puts the tile.
export type KeyPlace = { holder: string; key: number };
export type DragPreview = { tile: Tile; slot: number }[];

export const useDragStore = defineStore("drag", () => {
  const active = ref(false);
  // The tile carried and the arrangement shown are the draft's own tiles, as they are, not copies: the arrangement
  // (model/layout.ts arrange) knows a tile from the grid from a new one by being the same object.
  const moving = shallowRef<Tile | null>(null);
  const preview = shallowRef<DragPreview | null>(null);
  const page = ref<PageDrag | null>(null);
  const key = ref<KeyPlace | null>(null);
  // The page a tile can't land on, said as a whole (a page-filling tile over a page that has tiles).
  const refused = ref<number | null>(null);
  // Nothing in the air any more: a drop, a cancel, or the editor switching between the row and the map.
  function clear() {
    active.value = false; moving.value = null; preview.value = null; page.value = null; key.value = null; refused.value = null;
  }
  return { active, moving, preview, page, key, refused, clear };
});
