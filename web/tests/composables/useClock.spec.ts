// The editor's clock (composables/useClock.ts): it ticks while the page is in sight, holds while hidden or while `when`
// says so, and reads the time at once when the tab is shown again.
import { describe, expect, it } from "vitest";
import { nextTick, ref } from "vue";
import { useClock } from "../../src/composables/useClock";
import { setHidden } from "../helpers/browser";
import { MOMENT, useFakeClock } from "../helpers/clock";
import { inScope } from "../helpers/with-setup";

describe("the clock", () => {
  it("ticks every interval while the page is in sight, and reads the time at once when it is shown again", async () => {
    const clock = useFakeClock();
    const { result: now, stop } = inScope(() => useClock(1000));
    expect(now.value).toBe(MOMENT);
    await clock.tick(2500);
    expect(now.value).toBe(MOMENT + 2000);
    setHidden(true);
    await nextTick();
    await clock.tick(60000);
    expect(now.value).toBe(MOMENT + 2000);
    setHidden(false);
    await nextTick();
    expect(now.value).toBe(MOMENT + 62500);
    stop();
    expect(clock.timers()).toBe(0);
  });
  it("holds still while `when` says so, and keeps the time in the ref it is given", async () => {
    const clock = useFakeClock(), kept = ref(0), dragging = ref(true);
    inScope(() => useClock(30000, { now: kept, when: () => !dragging.value }));
    await clock.tick(60000);
    expect(kept.value).toBe(0);
    dragging.value = false;
    await nextTick();
    await clock.tick(30000);
    expect(kept.value).toBe(MOMENT + 90000);
  });
});
