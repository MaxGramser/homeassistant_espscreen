// The editor's questions (composables/useConfirm.ts) answered by a test, as a person would in the dialog: every question
// asked from now until the test ends gets `reply` (or what `reply` says for it), and is kept in the list returned, in the
// order asked. A question nobody answers stays open, as an unanswered dialog does.
import { onTestFinished } from "vitest";
import { watch } from "vue";
import { answer, question, type Question } from "../../src/composables/useConfirm";

export function answerDialogs(reply: boolean | string | null | ((question: Question) => boolean | string | null) = true) {
  const asked: Question[] = [];
  const stop = watch(question, (now) => {
    if (!now) return;
    asked.push(now);
    answer(typeof reply === "function" ? reply(now) : reply);
  }, { flush: "sync", immediate: true });
  onTestFinished(stop);
  return asked;
}
