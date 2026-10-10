// A list whose rows are dragged into another order (the screensaver's steps and its players, a top bar's items): the
// rows follow the pointer, the place it passes is the place the row takes (model/reorder.ts dropIndex), and the new order
// is kept when the row is let go, not when the drag is cancelled. A press on a row's control is no drag; with a `grip`,
// a finger on it drags at once and a mouse on it selects no text, without one every mouse press on a row selects no
// text. The arrow keys move the focused row a place up or down. On usePointerDrag.
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
};

export function useSortableRows<T>(options: SortableRowsOptions<T>) {
  const drag = ref({ index: -1, active: false });
  const live = shallowRef<T[] | null>(null);
  const rows = () => [...document.querySelectorAll<HTMLElement>(options.rows)];
  const pointer = usePointerDrag({
    onStart: () => { drag.value.active = true; live.value = [...options.items()]; },
    onMove: (e) => {
      const from = drag.value.index, to = dropIndex(rows().map((row) => row.getBoundingClientRect()), from, e.clientY);
      if (to === from || !live.value) return;
      live.value = moved(live.value, from, to);
      drag.value.index = to;
      options.onMove?.(from, to);
    },
    onEnd: ({ dragged, dropped }) => {
      const list = live.value, before = options.items();
      if (dragged && dropped && list && list.some((item, i) => item !== before[i])) options.commit(list);
      live.value = null;
      drag.value = { index: -1, active: false };
    },
  });
  function down(e: PointerEvent, index: number) {
    const target = e.target as HTMLElement;
    if (e.button !== 0 || !(options.enabled?.() ?? true) || pointer.pressed() || (options.skip && target.closest(options.skip))) return;
    const onGrip = Boolean(options.grip && target.closest(options.grip));
    if (onGrip) e.stopPropagation();
    if (e.pointerType !== "touch" && (onGrip || !options.grip)) e.preventDefault();
    drag.value = { index, active: false };
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
