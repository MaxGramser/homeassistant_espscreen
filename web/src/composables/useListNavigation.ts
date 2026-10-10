// The arrow keys walking a list of results from the field above it (⌘K, the library, a field's suggestions), and Enter
// taking the one in focus, while the cursor stays in the field. `wrap` goes on from the last to the first and back (the
// library, the suggestions); without it the focus stops at the ends (⌘K). A new search starts at the first again
// (resetOn), and onMove lets the list bring the one in focus into view.
import { computed, ref, toValue, watch, type MaybeRefOrGetter, type WatchSource } from "vue";

export type ListNavigationOptions<T> = {
  wrap?: boolean;
  /** Enter on the one in focus; false when it is not taken, so the key goes on as it would. */
  onPick?: (item: T, index: number) => boolean | void;
  /** Back to the first when any of these change. */
  resetOn?: WatchSource<unknown> | WatchSource<unknown>[];
  /** The focus moved to `index`. */
  onMove?: (index: number) => void;
};

export function useListNavigation<T>(items: MaybeRefOrGetter<readonly T[]>, options: ListNavigationOptions<T> = {}) {
  const active = ref(0);
  const current = computed<T | undefined>(() => toValue(items)[active.value]);
  function move(step: number) {
    const count = toValue(items).length;
    if (!count) return;
    active.value = options.wrap ? (active.value + step + count) % count : Math.min(count - 1, Math.max(0, active.value + step));
    options.onMove?.(active.value);
  }
  /** The arrows and Enter; true when the key was taken (and its default prevented). */
  function onKey(e: KeyboardEvent) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      move(e.key === "ArrowDown" ? 1 : -1);
      return true;
    }
    if (e.key !== "Enter" || current.value === undefined || !options.onPick) return false;
    if (options.onPick(current.value, active.value) === false) return false;
    e.preventDefault();
    return true;
  }
  if (options.resetOn) watch(options.resetOn, () => { active.value = 0; });
  return { active, current, move, onKey };
}
