// A key that steps again and again while it is held (composables/usePressRepeat.ts), as the -/+ keys of a setting do.
import { describe, expect, it } from "vitest";
import { usePressRepeat } from "../../src/composables/usePressRepeat";
import { useFakeClock } from "../helpers/clock";
import { inScope } from "../helpers/with-setup";
import { pointer } from "./pointer";

const on = (target: HTMLElement, type: string) => Object.defineProperty(type === "click" ? new MouseEvent("click") : pointer(type), "currentTarget", { value: target });

describe("a key held down", () => {
  it("steps after 450 ms and every 180 ms after that, until it is let go, and its click is the hold's", async () => {
    const clock = useFakeClock(), key = document.createElement("button"), steps: number[] = [];
    const { result: hold, stop } = inScope(() => usePressRepeat());
    hold.down(on(key, "pointerdown") as PointerEvent, (repeats) => steps.push(repeats));
    await clock.tick(449);
    expect(steps).toEqual([]);
    await clock.tick(1 + 180 * 6);
    expect(steps).toEqual([1, 2, 3, 4, 5, 6, 7]);
    hold.up();
    await clock.tick(1000);
    expect(steps).toHaveLength(7);
    expect(hold.click(on(key, "click") as MouseEvent)).toBe(true);
    // The next click is a step of its own again.
    expect(hold.click(on(key, "click") as MouseEvent)).toBe(false);
    stop();
    expect(clock.timers()).toBe(0);
  });
  it("is a plain click when let go before the hold, and does nothing on a disabled key", async () => {
    const clock = useFakeClock(), key = document.createElement("button"), steps: number[] = [];
    const { result: hold } = inScope(() => usePressRepeat());
    hold.down(on(key, "pointerdown") as PointerEvent, (repeats) => steps.push(repeats));
    await clock.tick(200);
    hold.up();
    expect(hold.click(on(key, "click") as MouseEvent)).toBe(false);
    key.disabled = true;
    hold.down(on(key, "pointerdown") as PointerEvent, (repeats) => steps.push(repeats));
    await clock.tick(2000);
    expect(steps).toEqual([]);
  });
});
