// The listeners of one gesture (composables/useGesture.ts): added when it begins, gone when it ends, when another
// begins, or when the component goes in the middle of it.
import { useEventListener } from "@vueuse/core";
import { describe, expect, it } from "vitest";
import { useGesture } from "../../src/composables/useGesture";
import { liveListeners } from "../helpers/browser";
import { inScope } from "../helpers/with-setup";

describe("a gesture's listeners", () => {
  it("live from its beginning to its end, and one gesture at a time", () => {
    const live = liveListeners(window), moves: number[] = [];
    const { result: gesture } = inScope(() => useGesture());
    gesture.begin(() => useEventListener(window, "pointermove", () => moves.push(1)));
    expect([live(), gesture.active()]).toEqual([["pointermove"], true]);
    gesture.add(() => useEventListener(window, "keydown", () => {}, { capture: true }));
    expect(live()).toEqual(["keydown:capture", "pointermove"]);
    gesture.begin(() => useEventListener(window, "pointerup", () => {}));
    expect(live()).toEqual(["pointerup"]);
    window.dispatchEvent(new Event("pointermove"));
    expect(moves).toEqual([]);
    gesture.end();
    expect([live(), gesture.active()]).toEqual([[], false]);
  });
  it("go with the component in the middle of a gesture", () => {
    const live = liveListeners(window);
    const { result: gesture, stop } = inScope(() => useGesture());
    gesture.begin(() => useEventListener(window, "pointermove", () => {}));
    stop();
    expect(live()).toEqual([]);
  });
});
