// Work a part of the page waits for (a request behind a button, a folder loading): `busy` while any of it runs, so its
// button can say so and wait; runOnce does nothing while it is busy already, for a second press of the same button.
import { computed, shallowRef } from "vue";

export function useBusy() {
  const running = shallowRef(0);
  const busy = computed(() => running.value > 0);
  async function run<T>(work: () => Promise<T>): Promise<T> {
    running.value++;
    try { return await work(); } finally { running.value--; }
  }
  /** As run, but nothing (undefined) while the work is busy already. */
  async function runOnce<T>(work: () => Promise<T>): Promise<T | undefined> {
    return busy.value ? undefined : run(work);
  }
  return { busy, run, runOnce };
}
