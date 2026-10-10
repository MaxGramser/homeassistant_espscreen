// The clock of a test: fake timers from a fixed moment, and a step that also lets every promise the timers set going
// settle, so a poll that asks and waits for its answer has had it before the test looks.
import { vi } from "vitest";

/** 10 October 2026, 10:42:00 in UTC: a moment that reads the same in every test. */
export const MOMENT = Date.UTC(2026, 9, 10, 10, 42, 0);

/** Fake timers (and Date) from `at`; tests/setup.ts puts the real ones back after each test. */
export function useFakeClock(at: number = MOMENT) {
  vi.useFakeTimers({ now: at });
  return {
    /** Moves the clock on by `ms`, running the timers due and the promises they start. */
    tick: (ms = 0) => vi.advanceTimersByTimeAsync(ms),
    /** Runs what is due now and the promises it starts, without moving the clock. */
    settle: () => vi.advanceTimersByTimeAsync(0),
    /** The clock's time. */
    now: () => Date.now(),
    /** How many timers wait. */
    timers: () => vi.getTimerCount(),
  };
}
