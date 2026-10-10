// A text field that changes the draft as it is typed (a tile's name, a title): the person's spaces stay in the field while
// the draft keeps the text trimmed, a required field left empty keeps its last text until they finish typing, and on
// blur the field shows what the draft holds. A change from elsewhere (undo) shows while the field is not being typed in.
// `required` may be a question, asked on each input. The caller owns the focus-based undo group.
import { ref, toValue, watch, type MaybeRefOrGetter } from "vue";

export function useTextDraft(source: MaybeRefOrGetter<string>, write: (value: string) => void, required: MaybeRefOrGetter<boolean> = false) {
  const value = ref(toValue(source)), focused = ref(false);
  watch(() => toValue(source), (next) => { if (!focused.value) value.value = next; });
  return {
    value,
    focus() { focused.value = true; value.value = toValue(source); },
    input(next: string) { value.value = next; if (!toValue(required) || next.trim()) write(next.trim()); },
    blur() { focused.value = false; value.value = toValue(source); },
  };
}
