// The editor's own questions, in place of the browser's confirm and prompt: before a change that can't be taken back
// (unsaved changes left behind, a layout replaced, the calibration started), for a new name, and for a text the
// clipboard would not take, shown selected to copy by hand. ConfirmDialog (in App.vue) asks them in the editor's look,
// one at a time in the order they were asked; each answer settles its promise. A store's action asks with askConfirm and
// goes on with the answer; a component takes the three from useConfirm().
import { computed, shallowRef } from "vue";

export type Question =
  /** Yes or no; `confirm` names the button that says yes (OK when it is not named). */
  | { kind: "confirm"; message: string; confirm?: string }
  /** A text, starting at `value`; null when the question is cancelled. */
  | { kind: "prompt"; message: string; value: string; confirm?: string }
  /** A text shown selected, for the person to copy. */
  | { kind: "copy"; message: string; value: string };
type Asked = Question & { reply: (answer: boolean | string | null) => void };

const asked = shallowRef<readonly Asked[]>([]);
/** The question the dialog shows now, or none. */
export const question = computed<Question | null>(() => {
  const first = asked.value[0];
  if (!first) return null;
  const { reply: _reply, ...shown } = first;
  return shown;
});

function ask<T extends boolean | string | null>(next: Question): Promise<T> {
  return new Promise((resolve) => { asked.value = [...asked.value, { ...next, reply: resolve as (answer: boolean | string | null) => void }]; });
}
/** The answer to the question shown now: true or false to a question, the text or null to a prompt. */
export function answer(value: boolean | string | null) {
  const [first, ...rest] = asked.value;
  if (!first) return;
  asked.value = rest;
  first.reply(first.kind === "prompt" ? (typeof value === "string" ? value : null) : value === true || typeof value === "string");
}

/** Asks yes or no; true for yes. */
export const askConfirm = (message: string, options: { confirm?: string } = {}) => ask<boolean>({ kind: "confirm", message, ...options });
/** Asks for a text, `value` to start with; the text, or null when cancelled. */
export const askText = (message: string, value = "", options: { confirm?: string } = {}) => ask<string | null>({ kind: "prompt", message, value, ...options });
/** Shows a text selected, for the person to copy; done when it is closed. */
export const showText = (message: string, value: string) => ask<boolean>({ kind: "copy", message, value });

export function useConfirm() {
  return { confirm: askConfirm, prompt: askText, show: showText, question, answer };
}

/** Every question still open cancelled (between tests, tests/setup.ts), so no promise waits into the next one. */
export function cancelQuestions() {
  const open = asked.value;
  asked.value = [];
  for (const one of open) one.reply(one.kind === "prompt" ? null : false);
}
