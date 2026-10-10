// An edge dragged to resize what it belongs to (the library drawer's top edge, the sidebar's right edge): the edge
// captures the pointer, so the drag goes on wherever the pointer goes, and it ends when the pointer is let go or
// cancelled, or when the edge goes with its component. `selectNothing` keeps the page from selecting text it passes over.
import { tryOnScopeDispose, useEventListener } from "@vueuse/core";
import { shallowRef } from "vue";
import { useGesture } from "./useGesture";

export type ResizeHandleOptions = {
  onStart?: (event: PointerEvent) => void;
  onMove: (event: PointerEvent) => void;
  onEnd?: () => void;
  selectNothing?: boolean;
};

export function useResizeHandle(options: ResizeHandleOptions) {
  const resizing = shallowRef(false);
  const gesture = useGesture();
  function start(event: PointerEvent) {
    if (resizing.value) return;
    const handle = event.currentTarget as HTMLElement;
    event.preventDefault();
    if (options.selectNothing) document.body.style.userSelect = "none";
    try { handle.setPointerCapture(event.pointerId); } catch { /* A pointer the browser no longer has: the drag ends with its up. */ }
    resizing.value = true;
    options.onStart?.(event);
    gesture.begin(() => {
      useEventListener(handle, "pointermove", options.onMove);
      useEventListener(handle, ["pointerup", "pointercancel"], end);
    });
  }
  function end() {
    if (!resizing.value) return;
    gesture.end();
    resizing.value = false;
    if (options.selectNothing) document.body.style.userSelect = "";
    options.onEnd?.();
  }
  tryOnScopeDispose(end);
  return { resizing, start, end };
}
