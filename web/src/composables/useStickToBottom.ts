// A log that follows its last line as lines come in (a build's log): it scrolls to the bottom once the new lines are
// drawn. With `near`, only while the reader is at the bottom (within that many pixels): someone who scrolled up to
// read stays where they are. `changes` is whatever changes when lines come in: their number, or the lines themselves
// for a log the add-on keeps only the newest of (its live log holds 300, build_logs.Tee), whose number stops growing.
import { nextTick, toValue, watch, type MaybeRefOrGetter } from "vue";

export function useStickToBottom(element: MaybeRefOrGetter<HTMLElement | null | undefined>, changes: MaybeRefOrGetter<unknown>, options: { near?: number } = {}) {
  watch(() => toValue(changes), () => {
    const box = toValue(element);
    if (!box) return;
    if (options.near !== undefined && box.scrollHeight - box.scrollTop - box.clientHeight > options.near) return;
    nextTick(() => { box.scrollTop = box.scrollHeight; });
  });
}
