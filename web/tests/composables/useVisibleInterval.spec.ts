// Something the page does every few seconds while it is in sight (composables/useVisibleInterval.ts).
import { describe, expect, it, vi } from "vitest";
import { nextTick, ref } from "vue";
import { useVisibleInterval } from "../../src/composables/useVisibleInterval";
import { setHidden } from "../helpers/browser";
import { useFakeClock } from "../helpers/clock";
import { inScope } from "../helpers/with-setup";

describe("an interval while the page is in sight", () => {
  it("runs every interval, none while the tab is hidden, and counts again from when it is shown", async () => {
    const clock = useFakeClock(), run = vi.fn();
    const { stop } = inScope(() => useVisibleInterval(run, 1000));
    await clock.tick(3000);
    expect(run).toHaveBeenCalledTimes(3);
    setHidden(true);
    await nextTick();
    await clock.tick(10000);
    expect(run).toHaveBeenCalledTimes(3);
    await clock.tick(500);
    setHidden(false);
    await nextTick();
    await clock.tick(999);
    expect(run).toHaveBeenCalledTimes(3);
    await clock.tick(1);
    expect(run).toHaveBeenCalledTimes(4);
    stop();
    expect(clock.timers()).toBe(0);
  });
  it("runs only while `when` holds", async () => {
    const clock = useFakeClock(), run = vi.fn(), open = ref(false);
    inScope(() => useVisibleInterval(run, 1000, { when: open }));
    await clock.tick(5000);
    expect(run).not.toHaveBeenCalled();
    open.value = true;
    await nextTick();
    await clock.tick(2000);
    expect(run).toHaveBeenCalledTimes(2);
    open.value = false;
    await nextTick();
    await clock.tick(5000);
    expect(run).toHaveBeenCalledTimes(2);
  });
});
