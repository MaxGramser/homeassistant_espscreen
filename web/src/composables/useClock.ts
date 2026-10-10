// The editor's clock: the time the mockup's clocks, a build's elapsed time and the "last changed" lines read. It ticks
// every `interval` ms while the page is in sight, not in a hidden tab, and reads the time at once when the tab is shown
// again, so nothing waits a whole tick to be right. `when` holds it still meanwhile (a tile being dragged keeps its
// mockup still); `now` is the ref it keeps, when the time lives elsewhere (the store's state.now).
import { useDocumentVisibility } from "@vueuse/core";
import { shallowRef, watch, type MaybeRefOrGetter, type Ref } from "vue";
import { useVisibleInterval } from "./useVisibleInterval";

export type ClockOptions = {
  /** Ticks only while this holds. */
  when?: MaybeRefOrGetter<boolean>;
  /** The ref to keep the time in; a new one otherwise. */
  now?: Ref<number>;
};

export function useClock(interval: MaybeRefOrGetter<number> = 1000, options: ClockOptions = {}): Ref<number> {
  const now = options.now ?? shallowRef(Date.now());
  const read = () => { now.value = Date.now(); };
  useVisibleInterval(read, interval, { when: options.when });
  const visible = useDocumentVisibility();
  watch(visible, (state) => { if (state === "visible") read(); });
  return now;
}
