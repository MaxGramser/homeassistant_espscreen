// A key that steps again and again while it is held, faster after a while, like the -/+ keys on the screen: the first
// repeat after `delay` ms, then one every `interval` ms until it is let go. The click that ends a hold is the hold's, not
// one more step (click() says so). One key at a time: a press takes over from the one before.
import { useIntervalFn, useTimeoutFn } from "@vueuse/core";

export type PressRepeatOptions = { delay?: number; interval?: number };

export function usePressRepeat({ delay = 450, interval = 180 }: PressRepeatOptions = {}) {
  let press: { target: EventTarget | null; step: (repeats: number) => void; repeats: number; held: boolean } | null = null;
  const repeat = () => {
    if (!press) return;
    press.held = true;
    press.repeats += 1;
    press.step(press.repeats);
  };
  const every = useIntervalFn(repeat, interval, { immediate: false });
  const wait = useTimeoutFn(() => { repeat(); every.resume(); }, delay, { immediate: false });
  /** The key is pressed: `step` runs with the count of repeats so far, once the hold has lasted. */
  function down(e: PointerEvent, step: (repeats: number) => void) {
    const key = e.currentTarget as HTMLButtonElement | null;
    if (key?.disabled || e.button !== 0) return;
    up();
    press = { target: key, step, repeats: 0, held: false };
    wait.start();
  }
  /** Let go, cancelled, or the pointer left the key. */
  function up() {
    wait.stop();
    every.pause();
  }
  /** Whether the click on a key ends a hold of that key; then it steps no more. */
  function click(e: MouseEvent) {
    if (!press || press.target !== e.currentTarget || !press.held) return false;
    press.held = false;
    return true;
  }
  return { down, up, click };
}
