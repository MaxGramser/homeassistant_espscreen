import { editorLayout } from "./store";
const { grid, arrange, pageOf, reorderPages } = editorLayout;
// Pointer-based drag & drop, mouse and touch, from the library into the mockup, between
// cells, and a whole page to another place in the row (app 0.2.121). Touch starts after a
// short hold so the page still scrolls. While dragging, the
// mockup already shows where everything ends up; the drop confirms exactly that, and a
// drop off the grid changes nothing. A finished drag never doubles as a click.
import type { Directive } from "vue";
import { entriesOf, newTile, pageOrder } from "./model/layout";
import { commitArrangement, keyToCell, loadCapabilities, movePage, pagesShown, placeKey, placeTile, state, toast } from "./store";
import type { Tile } from "./types";
import rules from "./model/page-rules.json";
import { t } from "./i18n";

export type DragSource = { kind: "tile"; tile: Tile } | { kind: "entity"; id: string } | { kind: "page"; page: number };
type Drag = {
  source: DragSource | null; element: HTMLElement | null; ghost: HTMLElement | null; timer: number;
  start: { x: number; y: number } | null; offset: { x: number; y: number }; pointerId: number | null;
  suppressUntil: number; last: { x: number; y: number } | null; scroller: number; target: number | null; lastSlot: number | null;
};
const drag: Drag = { source: null, element: null, ghost: null, timer: 0, start: null, offset: { x: 0, y: 0 }, pointerId: null, suppressUntil: 0, last: null, scroller: 0, target: null, lastSlot: null };

export const vDrag: Directive<HTMLElement, DragSource | null> = {
  mounted(element, binding) {
    (element as any).__dragSource = binding.value;
    element.dataset.drag = "";
    element.addEventListener("pointerdown", (e: PointerEvent) => {
      const source = (element as any).__dragSource as DragSource;
      // A press belongs to the innermost button or draggable under it: a bedside clock's key, its empty place and a
      // card's remove key are pressed, not the card around them. The card that took the pointer here also took the
      // click, so a key could never be opened (GitHub #93).
      const owner = (e.target as HTMLElement).closest("button, [data-drag]");
      if (!source || owner !== element || e.button !== 0 || (element as HTMLButtonElement).disabled) return;
      // No text selection while the mouse drags; touch keeps its default so the page can scroll.
      if (e.pointerType !== "touch") e.preventDefault();
      Object.assign(drag, { source, element, start: { x: e.clientX, y: e.clientY }, pointerId: e.pointerId });
      // A fast flick may leave the card before its first move event: keep the pointer until the drag begins.
      try { element.setPointerCapture(e.pointerId); } catch {}
      clearTimeout(drag.timer);
      if (e.pointerType === "touch") drag.timer = window.setTimeout(() => beginDrag(e), 260);
    });
    element.addEventListener("pointermove", (e: PointerEvent) => {
      if (state.drag.active || !drag.start || drag.element !== element) return;
      const distance = Math.hypot(e.clientX - drag.start.x, e.clientY - drag.start.y);
      if (e.pointerType === "touch") { if (distance > 10) { clearTimeout(drag.timer); drag.start = null; } return; }
      if (distance >= 6) beginDrag(e);
    });
    const cancel = () => { if (drag.element === element && !state.drag.active) { clearTimeout(drag.timer); drag.start = null; } };
    element.addEventListener("pointerup", cancel);
    element.addEventListener("pointercancel", cancel);
  },
  updated(element, binding) {
    (element as any).__dragSource = binding.value;
  },
};

function beginDrag(e: PointerEvent) {
  if (state.drag.active || !drag.start || !drag.source || !drag.element) return;
  const source = drag.source;
  // The row as it stands, read before the drag begins: from here on a tile drag adds a page to it.
  const pages = pagesShown();
  state.drag.active = true;
  state.drag.moving = source.kind === "page" ? null : source.kind === "tile" ? source.tile : newTile(source.id);
  // A page keeps its own place until the pointer names another one; the ghost is the label you grabbed it by.
  state.drag.page = source.kind === "page" ? { from: source.page, to: source.page, order: pageOrder(pages, source.page, source.page) } : null;
  state.drag.preview = null;
  drag.target = null;
  getSelection()?.removeAllRanges();
  const rect = drag.element.getBoundingClientRect();
  const ghost = drag.element.cloneNode(true) as HTMLElement;
  ghost.classList.add("drag-ghost");
  ghost.style.width = `${rect.width}px`;
  ghost.style.height = `${rect.height}px`;
  drag.offset = { x: e.clientX - rect.left, y: e.clientY - rect.top };
  document.body.append(ghost);
  drag.ghost = ghost;
  // The mockup re-renders while hovering, so the pointer is followed on the document, not the card.
  document.addEventListener("pointermove", moveDrag);
  document.addEventListener("pointerup", finishDrag);
  document.addEventListener("pointercancel", finishDrag);
  try { drag.element.releasePointerCapture(drag.pointerId!); } catch {}
  try { document.documentElement.setPointerCapture(drag.pointerId!); } catch {}
  document.addEventListener("touchmove", blockScroll, { passive: false });
  // Near the edges the pages scroll along, so every page can be reached.
  drag.scroller = window.setInterval(() => {
    if (!drag.last) return;
    const { x, y } = dragScrollers(document);
    const dx = x ? edgeStep(drag.last.x, visibleSpan(x, "x")) : 0;
    const dy = y ? edgeStep(drag.last.y, visibleSpan(y, "y")) : 0;
    if (dx) x!.scrollBy(dx, 0);
    if (dy) y!.scrollBy(0, dy);
    if (dx || dy) aim(drag.last.x, drag.last.y);
  }, 16);
  if (!state.drag.page) setTarget(-1);
  moveDrag(e);
}
// True when the element scrolls along that axis: more content than room, and an overflow that lets it scroll.
export function scrollsAlong(element: Element | null, axis: "x" | "y") {
  if (!element) return false;
  const more = axis === "x" ? element.scrollWidth > element.clientWidth : element.scrollHeight > element.clientHeight;
  const overflow = getComputedStyle(element)[axis === "x" ? "overflowX" : "overflowY"];
  return more && (overflow === "auto" || overflow === "scroll");
}
// What a drag near an edge scrolls, per axis (app 0.2.78). A wide window scrolls the canvas both ways. At 960 px and
// narrower (a phone, also in the Home Assistant app) the canvas grows with its content: the row of pages scrolls
// sideways and the page itself up and down, so a tile can still reach page 2 and beyond.
export function dragScrollers(doc: Document): { x: Element | null; y: Element | null } {
  const pages = doc.querySelector(".pages"), canvas = doc.querySelector(".canvas");
  return {
    x: scrollsAlong(pages, "x") ? pages : canvas,
    y: scrollsAlong(canvas, "y") ? canvas : doc.scrollingElement,
  };
}
// The part of a scroller on screen along one axis; the page itself is the whole window.
function visibleSpan(element: Element, axis: "x" | "y"): [number, number] {
  const view = axis === "x" ? window.innerWidth : window.innerHeight;
  if (element === element.ownerDocument.scrollingElement) return [0, view];
  const r = element.getBoundingClientRect();
  return axis === "x" ? [Math.max(r.left, 0), Math.min(r.right, view)] : [Math.max(r.top, 0), Math.min(r.bottom, view)];
}
// Within 60 px of either end the scroller moves 12 px per step towards that end.
export function edgeStep(position: number, [start, end]: [number, number]) {
  return position < start + 60 ? -12 : position > end - 60 ? 12 : 0;
}
function blockScroll(e: TouchEvent) { if (state.drag.active) e.preventDefault(); }
function finishDrag(e: PointerEvent) { if (e.pointerId === drag.pointerId) endDrag(e.type === "pointerup"); }
function moveDrag(e: PointerEvent) {
  if (!drag.ghost || e.pointerId !== drag.pointerId) return;
  drag.last = { x: e.clientX, y: e.clientY };
  drag.ghost.style.transform = `translate(${e.clientX - drag.offset.x}px, ${e.clientY - drag.offset.y}px)`;
  aim(e.clientX, e.clientY);
}
// What the pointer is over: a cell for a tile, a place in the row of pages for a page.
function aim(x: number, y: number) {
  if (state.drag.page) return setPageTarget(pageAt(x, y));
  // A key place under a bedside clock takes a tile as a cell does (app 0.4.12); it is checked first, since it lies on
  // the clock's card, which is a cell too.
  const key = keyAt(x, y);
  state.drag.key = key;
  if (key) { drag.target = null; state.drag.preview = null; return; }
  setTarget(slotAt(x, y));
}
// Only a tile that may be a key looks for a key place (rules.keyDomains), and never one of its own clock's.
function keyAt(x: number, y: number) {
  const moving = state.drag.moving;
  if (!moving || !(rules.keyDomains as string[]).includes(moving.entity.split(".")[0])) return null;
  for (const place of document.querySelectorAll<HTMLElement>(".pages [data-key][data-holder]")) {
    if (place.dataset.holder === moving.id) continue;
    const r = place.getBoundingClientRect();
    if (x >= r.left - 6 && x <= r.right + 6 && y >= r.top - 6 && y <= r.bottom + 6)
      return { holder: place.dataset.holder!, key: Number(place.dataset.key) };
  }
  return null;
}
// The cell under the pointer: the nearest card or empty cell (the gaps between them count
// too); on a wide card the left or right half decides. -1 away from the mockup.
export function slotAt(x: number, y: number) {
  let best: { cell: HTMLElement; r: DOMRect } | null = null, nearest = Infinity;
  for (const cell of document.querySelectorAll<HTMLElement>(".pages [data-slot]")) {
    const r = cell.getBoundingClientRect();
    const distance = Math.hypot(Math.max(r.left - x, 0, x - r.right), Math.max(r.top - y, 0, y - r.bottom));
    if (distance < nearest) { nearest = distance; best = { cell, r }; }
  }
  if (!best || nearest > 16) return -1;
  let slot = Number(best.cell.dataset.slot);
  const columns = Number(best.cell.dataset.columns || 1), rows = Number(best.cell.dataset.rows || 1);
  const column = Math.max(0, Math.min(columns - 1, Math.floor((x - best.r.left) / best.r.width * columns)));
  const row = Math.max(0, Math.min(rows - 1, Math.floor((y - best.r.top) / best.r.height * rows)));
  slot += row * grid.columns + column;
  return slot;
}
// The place in the row under the pointer, by the mockups as they stand right now: the page nearest to it, which
// while dragging is the moved page itself as long as the pointer stays on it. -1 away from the row.
function pageAt(x: number, y: number) {
  return nearestRect([...document.querySelectorAll<HTMLElement>(".pages .page:not(.ghost)")].map((page) => page.getBoundingClientRect()), x, y);
}
// The rectangle nearest to a point, or -1 when the nearest one is further off than `tolerance`.
export function nearestRect(rects: { left: number; right: number; top: number; bottom: number }[], x: number, y: number, tolerance = 40) {
  let best = -1, nearest = Infinity;
  rects.forEach((r, index) => {
    const distance = Math.hypot(Math.max(r.left - x, 0, x - r.right), Math.max(r.top - y, 0, y - r.bottom));
    if (distance < nearest) { nearest = distance; best = index; }
  });
  return nearest > tolerance ? -1 : best;
}
// Off the row the page goes back where it came from, so a drop away from the pages changes nothing.
function setPageTarget(place: number) {
  const page = state.drag.page;
  if (!page || !state.layout) return;
  const to = place < 0 ? page.from : place;
  if (to === page.to) return;
  page.to = to;
  page.order = pageOrder(pagesShown(), page.from, to);
  state.drag.preview = reorderPages(entriesOf(state.layout), page.order);
}
function setTarget(slot: number) {
  if (drag.target === slot || !state.layout || !state.drag.moving) return;
  drag.target = slot;
  // A key leaves its clock for an empty cell only: the drop shows nothing moving aside.
  if (state.drag.moving.in !== undefined) { state.drag.preview = null; return; }
  // Off the grid: a tile from the grid shows where it came from; a new one shows nowhere yet.
  state.drag.preview = slot >= 0 ? arrange(state.layout.tiles, state.drag.moving, slot) : null;
  // A page the tile can't land on says so as a whole, instead of showing nothing: a page-filling tile over a page
  // that has tiles, a large one where the tiles around it have nowhere to go.
  state.drag.refused = slot >= 0 && !state.drag.preview ? pageOf(slot) : null;
}
function endDrag(drop: boolean) {
  const preview = state.drag.preview, moving = state.drag.moving, page = state.drag.page, key = state.drag.key, refused = state.drag.refused;
  state.drag.key = null;
  state.drag.refused = null;
  document.removeEventListener("pointermove", moveDrag);
  document.removeEventListener("pointerup", finishDrag);
  document.removeEventListener("pointercancel", finishDrag);
  document.removeEventListener("touchmove", blockScroll);
  try { document.documentElement.releasePointerCapture(drag.pointerId!); } catch {}
  drag.ghost?.remove();
  drag.lastSlot = drag.target;
  Object.assign(drag, { ghost: null, suppressUntil: Date.now() + 400, last: null, start: null, target: null, element: null, source: null });
  clearInterval(drag.scroller);
  state.drag.active = false;
  state.drag.preview = null;
  state.drag.moving = null;
  state.drag.page = null;
  // A page lands exactly where the row showed it; the move takes its title and its Go to page tiles with it.
  if (page) {
    if (drop) movePage(page.from, page.to);
    return;
  }
  if (drop && key && moving && state.layout) {
    const clock = state.layout.tiles.find((tile) => tile.id === key.holder);
    if (clock && moving.entity !== clock.entity && placeKey(moving, clock, key.key)) loadCapabilities([moving.entity]);
    return;
  }
  if (drop && moving?.in !== undefined && drag.lastSlot !== null && drag.lastSlot >= 0) {
    if (keyToCell(moving, drag.lastSlot)) loadCapabilities([moving.entity]);
    return;
  }
  if (drop && preview && moving && state.layout) {
    if (commitArrangement(preview)) loadCapabilities([moving.entity]);
  } else if (drop && moving && refused !== null && refused !== undefined) toast(t("editor.layout.no_room", { page: refused + 1 }));
}
window.addEventListener("click", (e) => { if (Date.now() < drag.suppressUntil) { e.stopPropagation(); e.preventDefault(); } }, true);
export const dragSuppressed = () => Date.now() < drag.suppressUntil;
