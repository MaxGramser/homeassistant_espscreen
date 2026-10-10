// An edge dragged to resize (composables/useResizeHandle.ts): it captures the pointer, follows it on the edge until it is
// let go or cancelled, selects nothing on the way, and ends with its component.
import { describe, expect, it, vi } from "vitest";
import { useResizeHandle } from "../../src/composables/useResizeHandle";
import { inScope } from "../helpers/with-setup";
import { pointer } from "./pointer";

function edge() {
  const element = document.createElement("div");
  element.setPointerCapture = vi.fn();
  document.body.append(element);
  return element;
}
// The pointerdown as the edge's listener gets it: currentTarget is the edge.
const press = (element: HTMLElement, y: number) => Object.defineProperty(pointer("pointerdown", { y }), "currentTarget", { value: element });

describe("an edge that resizes", () => {
  it("captures the pointer, follows it until it is let go, and selects nothing meanwhile", () => {
    const element = edge(), moves: number[] = [], ended = vi.fn();
    const { result } = inScope(() => useResizeHandle({ selectNothing: true, onMove: (e) => moves.push(e.clientY), onEnd: ended }));
    const down = press(element, 300);
    result.start(down);
    expect(down.defaultPrevented).toBe(true);
    expect(element.setPointerCapture).toHaveBeenCalledWith(1);
    expect([result.resizing.value, document.body.style.userSelect]).toEqual([true, "none"]);
    element.dispatchEvent(pointer("pointermove", { y: 280 }));
    element.dispatchEvent(pointer("pointerup", { y: 280 }));
    element.dispatchEvent(pointer("pointermove", { y: 200 }));
    expect(moves).toEqual([280]);
    expect([result.resizing.value, document.body.style.userSelect, ended.mock.calls.length]).toEqual([false, "", 1]);
  });
  it("ends when the edge goes with its component in the middle of a drag", () => {
    const element = edge(), ended = vi.fn();
    const { result, stop } = inScope(() => useResizeHandle({ onMove: () => {}, onEnd: ended }));
    result.start(press(element, 300));
    stop();
    expect([result.resizing.value, ended.mock.calls.length]).toEqual([false, 1]);
  });
});
