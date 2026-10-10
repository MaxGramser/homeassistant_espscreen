// Something the page does every few seconds while it is in sight: a hidden tab does none of it, and the count starts
// again when the tab is shown. `when` narrows it further (a screen open, nothing being dragged). On VueUse's
// useIntervalFn and useDocumentVisibility; it stops with the component or scope that started it.
import { useDocumentVisibility, useIntervalFn } from "@vueuse/core";
import { computed, toValue, watch, type MaybeRefOrGetter } from "vue";

export type VisibleIntervalOptions = {
  /** Only while this holds, besides the page being in sight. */
  when?: MaybeRefOrGetter<boolean>;
};

export function useVisibleInterval(callback: () => void, interval: MaybeRefOrGetter<number>, options: VisibleIntervalOptions = {}) {
  const visible = useDocumentVisibility();
  const { isActive, pause, resume } = useIntervalFn(callback, interval, { immediate: false });
  const running = computed(() => visible.value === "visible" && toValue(options.when ?? true));
  watch(running, (on) => (on ? resume() : pause()), { immediate: true });
  return { isActive, running };
}
