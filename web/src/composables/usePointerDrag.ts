// One press of a pointer that may become a drag, as the editor has always taken one: a mouse drags once it has moved
// 6 px, a finger after it held still for 260 ms, so the page still scrolls under it, and a finger that moves 10 px before
// then is scrolling, not dragging. A press can also drag at once (a finger on a row's grip). While the press lasts the
// pointer is followed on the whole document, and while it drags a finger does not scroll the page. The click the browser
// sends after a drag is no click (suppressClick). Its listeners and its timer live only while a press does, and go with
// the component or scope that made it, so a drawer that closes while a row is held lets go of the page.
// The mockup's own drag (drag.ts) takes the same numbers; it captures the pointer on the card, which a directive does.
import { tryOnScopeDispose, useEventListener, useTimeoutFn } from "@vueuse/core";
import { effectScope, getCurrentScope, shallowRef, type EffectScope } from "vue";

export const HOLD_MS = 260;
export const SLOP_PX = 10;
export const THRESHOLD_PX = 6;
// How long after a drag the browser's click still belongs to it.
export const CLICK_AFTER_DRAG_MS = 400;

export type PressEnd = {
  /** The event that ended it; none when its component or scope went first. */
  event: PointerEvent | null;
  /** Whether it became a drag. */
  dragged: boolean;
  /** Whether it was let go (pointerup), not cancelled. */
  dropped: boolean;
};
export type PointerDragOptions = {
  /** The drag begins: after the hold, past the threshold, or at once. */
  onStart?: (event: PointerEvent) => void;
  /** Every move while it drags. */
  onMove?: (event: PointerEvent) => void;
  /** The press ends, whether it dragged or not. */
  onEnd?: (end: PressEnd) => void;
};

export function usePointerDrag(options: PointerDragOptions = {}) {
  const dragging = shallowRef(false);
  const owner = getCurrentScope();
  let press: { event: PointerEvent; scope: EffectScope; holding: boolean } | null = null;
  let suppressUntil = 0;

  function begin() {
    if (!press || dragging.value) return;
    dragging.value = true;
    press.scope.run(() => useEventListener(document, "touchmove", (e: TouchEvent) => { if (dragging.value) e.preventDefault(); }, { passive: false }));
    options.onStart?.(press.event);
  }
  function move(e: PointerEvent) {
    if (!press || e.pointerId !== press.event.pointerId) return;
    if (!dragging.value) {
      // A finger that moved before its hold was scrolling: the press is followed no further until it lifts.
      if (!press.holding) return;
      const distance = Math.hypot(e.clientX - press.event.clientX, e.clientY - press.event.clientY);
      if (e.pointerType === "touch") { if (distance > SLOP_PX) { press.holding = false; hold?.stop(); } return; }
      if (distance < THRESHOLD_PX) return;
      begin();
    }
    options.onMove?.(e);
  }
  let hold: ReturnType<typeof useTimeoutFn> | null = null;
  function finish(event: PointerEvent | null) {
    if (!press) return;
    const dragged = dragging.value;
    press.scope.stop();
    press = null; hold = null;
    dragging.value = false;
    if (dragged) suppressUntil = Date.now() + CLICK_AFTER_DRAG_MS;
    options.onEnd?.({ event, dragged, dropped: event?.type === "pointerup" });
  }
  /** A press begins (from the element's pointerdown); `now` drags at once. False while another press lasts. */
  function start(e: PointerEvent, { now = false } = {}) {
    if (press) return false;
    // The press's listeners belong to the component or scope that made the drag, and go with it.
    const scope = (owner ? owner.run(() => effectScope()) : effectScope())!;
    press = { event: e, scope, holding: true };
    scope.run(() => {
      useEventListener(document, "pointermove", move);
      useEventListener(document, ["pointerup", "pointercancel"], (end: PointerEvent) => { if (end.pointerId === press?.event.pointerId) finish(end); });
      if (!now && e.pointerType === "touch") hold = useTimeoutFn(begin, HOLD_MS);
    });
    if (now) begin();
    return true;
  }
  /** Whether a click is the one that ends a drag: then it is stopped before anything else sees it. */
  function suppressClick(e?: Event) {
    if (Date.now() >= suppressUntil) return false;
    e?.preventDefault();
    e?.stopPropagation();
    return true;
  }
  tryOnScopeDispose(() => finish(null));
  return { dragging, start, pressed: () => press !== null, cancel: () => finish(null), suppressClick };
}
