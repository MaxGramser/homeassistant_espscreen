// One press that may become a drag (composables/usePointerDrag.ts): a mouse past 6 px, a finger after a 260 ms hold, a
// finger that scrolls first is no drag, the page followed only while a press lasts, and the click after a drag swallowed.
import { describe, expect, it, vi } from "vitest";
import { usePointerDrag } from "../../src/composables/usePointerDrag";
import { liveListeners } from "../helpers/browser";
import { useFakeClock } from "../helpers/clock";
import { inScope } from "../helpers/with-setup";
import { pointer } from "./pointer";

const following = (live: () => string[]) => live().filter((name) => /^(pointer|touch)/.test(name));

describe("a press that may become a drag", () => {
  it("drags a mouse once it moved 6 px, follows it on the page, and lets go of the page when it is let go", () => {
    const live = liveListeners(document), started = vi.fn(), moved = vi.fn(), ended = vi.fn();
    const { result: drag } = inScope(() => usePointerDrag({ onStart: started, onMove: moved, onEnd: ended }));
    expect(drag.start(pointer("pointerdown", { x: 10, y: 10 }))).toBe(true);
    expect(following(live)).toEqual(["pointercancel", "pointermove", "pointerup"]);
    document.dispatchEvent(pointer("pointermove", { x: 14, y: 10 }));
    expect(started).not.toHaveBeenCalled();
    document.dispatchEvent(pointer("pointermove", { x: 16, y: 10 }));
    expect([drag.dragging.value, moved.mock.calls.length]).toEqual([true, 1]);
    document.dispatchEvent(pointer("pointerup", { x: 30, y: 10 }));
    expect(ended).toHaveBeenCalledWith(expect.objectContaining({ dragged: true, dropped: true }));
    expect(following(live)).toEqual([]);
    // The click that follows a drag is the drag's.
    const click = new MouseEvent("click", { cancelable: true });
    expect(drag.suppressClick(click)).toBe(true);
    expect(click.defaultPrevented).toBe(true);
  });

  it("drags a finger after it held still, and not one that scrolled first", async () => {
    const clock = useFakeClock(), started = vi.fn(), ended = vi.fn();
    const live = liveListeners(document);
    const { result: drag } = inScope(() => usePointerDrag({ onStart: started, onEnd: ended }));
    drag.start(pointer("pointerdown", { kind: "touch" }));
    await clock.tick(259);
    expect(started).not.toHaveBeenCalled();
    await clock.tick(1);
    expect(started).toHaveBeenCalledTimes(1);
    expect(following(live)).toContain("touchmove");
    document.dispatchEvent(pointer("pointercancel", { kind: "touch" }));
    expect(ended).toHaveBeenLastCalledWith(expect.objectContaining({ dragged: true, dropped: false }));
    // A finger that moves 10 px before its hold is scrolling.
    drag.start(pointer("pointerdown", { kind: "touch", id: 2 }));
    document.dispatchEvent(pointer("pointermove", { kind: "touch", id: 2, y: 11 }));
    await clock.tick(1000);
    expect(started).toHaveBeenCalledTimes(1);
    document.dispatchEvent(pointer("pointerup", { kind: "touch", id: 2 }));
    expect(ended).toHaveBeenLastCalledWith(expect.objectContaining({ dragged: false }));
    expect(drag.suppressClick()).toBe(false);
  });

  it("drags at once when asked, follows only its own pointer, and lets go of the page when its scope ends", async () => {
    const clock = useFakeClock(), live = liveListeners(document), ended = vi.fn();
    const { result: drag, stop } = inScope(() => usePointerDrag({ onEnd: ended }));
    drag.start(pointer("pointerdown", { kind: "touch" }), { now: true });
    expect(drag.dragging.value).toBe(true);
    expect(drag.start(pointer("pointerdown", { id: 2 }))).toBe(false);
    document.dispatchEvent(pointer("pointerup", { id: 2 }));
    expect(drag.dragging.value).toBe(true);
    stop();
    expect(ended).toHaveBeenCalledWith({ event: null, dragged: true, dropped: false });
    expect(following(live)).toEqual([]);
    await clock.tick(1000);
    expect(clock.timers()).toBe(0);
  });
});
