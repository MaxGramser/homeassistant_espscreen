// A list whose rows are dragged into another order (the screensaver's steps and its players, a top bar's items): the
// rows follow the pointer, the place it passes is the place the row takes (model/reorder.ts dropIndex), and the new order
// is kept when the row is let go, not when the drag is cancelled. A press on a row's control is no drag; with a `grip`,
// a finger on it drags at once and a mouse on it selects no text, without one every mouse press on a row selects no
// text. The arrow keys move the focused row a place up or down. With `away`, a row pulled off the list and let go there
// is taken off it, as an icon pulled out of a menu bar (the top bar's items). On usePointerDrag.
import { nextTick, ref, shallowRef } from "vue";
import { dropIndex, moved } from "../model/reorder";
import { usePointerDrag } from "./usePointerDrag";

export type SortableRowsOptions<T> = {
  /** The rows on the page, in their order. */
  rows: string;
  /** The list as it is now. */
  items: () => readonly T[];
  /** Keeps a new order. */
  commit: (list: T[]) => void;
  /** A press on this inside a row is no drag (the row's own controls). */
  skip?: string;
  /** A finger on this drags at once. */
  grip?: string;
  /** Whether the list can be reordered now. */
  enabled?: () => boolean;
  /** The dragged row took another place. */
  onMove?: (from: number, to: number) => void;
  /** Rows side by side (the top bar at the head of its inspector, app 0.4.89): the row the pointer is over is the place. */
  axis?: "x" | "y";
  /** Let go this far (AWAY_PX) outside the element `from` names, the row is taken off: `remove` gets its place before the drag. */
  away?: { from: string; remove: (index: number) => void };
};

// How far beyond the list a row is pulled before letting it go takes it off.
export const AWAY_PX = 32;

export function useSortableRows<T>(options: SortableRowsOptions<T>) {
  const drag = ref({ index: -1, active: false, away: false });
  // The row's place when the press began: what is taken off when it is let go away from the list.
  let origin = -1;
  const live = shallowRef<T[] | null>(null);
  const rows = () => [...document.querySelectorAll<HTMLElement>(options.rows)];
  const pointer = usePointerDrag({
    onStart: () => { drag.value.active = true; live.value = [...options.items()]; },
    onMove: (e) => {
      const area = options.away && document.querySelector(options.away.from)?.getBoundingClientRect();
      drag.value.away = Boolean(area && (e.clientX < area.left - AWAY_PX || e.clientX > area.right + AWAY_PX
        || e.clientY < area.top - AWAY_PX || e.clientY > area.bottom + AWAY_PX));
      if (drag.value.away) return;
      const from = drag.value.index, boxes = rows().map((row) => row.getBoundingClientRect());
      // Side by side, and wrapping onto more lines when there are many: the place the pointer is over.
      const over = boxes.findIndex((box) => e.clientX >= box.left && e.clientX <= box.right && e.clientY >= box.top && e.clientY <= box.bottom);
      const to = options.axis === "x" ? (over < 0 ? from : over) : dropIndex(boxes, from, e.clientY);
      if (to === from || !live.value) return;
      live.value = moved(live.value, from, to);
      drag.value.index = to;
      options.onMove?.(from, to);
    },
    onEnd: ({ dragged, dropped }) => {
      const list = live.value, before = options.items(), away = drag.value.away;
      live.value = null;
      drag.value = { index: -1, active: false, away: false };
      if (dragged && dropped && away) options.away?.remove(origin);
      else if (dragged && dropped && list && list.some((item, i) => item !== before[i])) options.commit(list);
    },
  });
  function down(e: PointerEvent, index: number) {
    const target = e.target as HTMLElement;
    if (e.button !== 0 || !(options.enabled?.() ?? true) || pointer.pressed() || (options.skip && target.closest(options.skip))) return;
    const onGrip = Boolean(options.grip && target.closest(options.grip));
    if (onGrip) e.stopPropagation();
    if (e.pointerType !== "touch" && (onGrip || !options.grip)) e.preventDefault();
    drag.value = { index, active: false, away: false };
    origin = index;
    pointer.start(e, { now: onGrip && e.pointerType === "touch" });
  }
  // A drag that ends on the row it started on is no click: the row doesn't open after it.
  const click = (e: MouseEvent) => pointer.suppressClick(e);
  function key(e: KeyboardEvent, index: number) {
    if (e.target !== e.currentTarget) return;
    const step = ({ ArrowUp: -1, ArrowDown: 1 } as Record<string, number>)[e.key];
    const list = options.items();
    if (!step || index + step < 0 || index + step >= list.length) return;
    e.preventDefault();
    e.stopPropagation();
    options.commit(moved(list, index, index + step));
    // The focus goes with the row, once the list is drawn in its new order.
    nextTick(() => rows()[index + step]?.focus());
  }
  return { drag, live, down, key, click };
}
