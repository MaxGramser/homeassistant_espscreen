// A band dragged with the mouse from beside the tiles chooses every tile it touches (as in the Finder and Keynote): from the
// room around the pages, a page's own room or an empty cell, never from a card, a page's head or its top bar, which drag
// or click on their own. ⌘, Ctrl or Shift held adds to what was chosen. While it is drawn the tiles under it show as
// chosen (the inspector store's band), and the drawer opens once it is let go, so the pages don't make room for the
// drawer while the band is still in the air. Near an edge the pages scroll along, as for a tile carried there. A finger
// scrolls instead: a band is for a mouse or a pen. A click that ends a band is no click.
import { useEventListener } from "@vueuse/core";
import { shallowRef, type Ref } from "vue";
import { dragScrollers, edgeStep, visibleSpan } from "../drag";
import { useInspectorStore } from "../stores/inspector";
import { usePointerDrag } from "./usePointerDrag";

export type Band = { left: number; top: number; width: number; height: number };
// What a band never starts on: the things that have a press of their own.
const OWN_PRESS = ".tile, .round-tile, .section-head, .section-panel, .section-grip, .section-maker, .bar-wrap, .page-head, .map-scroll, .editor-toolbar, .notice, .library, .drawer, .phone-pager, .page-pills, .ghost, a, input, select, textarea, [role='menu'], button:not(.cell)";

/** Whether two rectangles share any point. */
export function touches(a: { left: number; top: number; right: number; bottom: number }, b: { left: number; top: number; right: number; bottom: number }) {
  return a.left <= b.right && b.left <= a.right && a.top <= b.bottom && b.top <= a.bottom;
}

export function useBandSelect(area: Ref<HTMLElement | null>) {
  const insp = useInspectorStore();
  const band = shallowRef<Band | null>(null);
  // Where it started, as the scrolled content has it (so it stays put while the pages scroll), what was chosen before
  // (kept when a modifier was held), and the pointer now.
  let start = { x: 0, y: 0 }, kept: string[] = [], pointer: { x: number; y: number } | null = null, scroller = 0;
  const scrolled = () => {
    const { x, y } = dragScrollers(document);
    return { x: x?.scrollLeft ?? 0, y: y?.scrollTop ?? 0 };
  };
  function draw() {
    if (!pointer) return;
    const now = scrolled(), x0 = start.x - now.x, y0 = start.y - now.y;
    const rect = { left: Math.min(x0, pointer.x), top: Math.min(y0, pointer.y), right: Math.max(x0, pointer.x), bottom: Math.max(y0, pointer.y) };
    band.value = { left: rect.left, top: rect.top, width: rect.right - rect.left, height: rect.bottom - rect.top };
    const hit = [...document.querySelectorAll<HTMLElement>(".pages .tile[data-tile-id]")]
      .filter((tile) => !tile.classList.contains("placeholder") && touches(rect, tile.getBoundingClientRect())).map((tile) => tile.dataset.tileId!);
    insp.band = [...new Set([...kept, ...hit])];
  }
  const press = usePointerDrag({
    onStart: (e) => {
      const now = scrolled();
      start = { x: e.clientX + now.x, y: e.clientY + now.y };
      kept = e.metaKey || e.ctrlKey || e.shiftKey ? insp.chosenTiles.map((tile) => tile.id!).filter(Boolean) : [];
      getSelection()?.removeAllRanges();
      scroller = window.setInterval(() => {
        if (!pointer) return;
        const { x, y } = dragScrollers(document);
        const dx = x ? edgeStep(pointer.x, visibleSpan(x, "x")) : 0, dy = y ? edgeStep(pointer.y, visibleSpan(y, "y")) : 0;
        if (dx) x!.scrollBy(dx, 0);
        if (dy) y!.scrollBy(0, dy);
        if (dx || dy) draw();
      }, 16);
    },
    onMove: (e) => { pointer = { x: e.clientX, y: e.clientY }; draw(); },
    onEnd: ({ dragged }) => {
      clearInterval(scroller);
      const chosen = insp.band;
      band.value = null; pointer = null; insp.band = null;
      if (dragged && chosen) insp.selectTiles(chosen);
    },
  });
  useEventListener(area, "pointerdown", (e: PointerEvent) => {
    if (e.button !== 0 || e.pointerType === "touch" || (e.target as HTMLElement).closest(OWN_PRESS)) return;
    // No text is selected while the band is drawn; the click that may follow still comes.
    e.preventDefault();
    press.start(e);
  });
  useEventListener(area, "click", (e: MouseEvent) => press.suppressClick(e), { capture: true });
  return { band };
}
