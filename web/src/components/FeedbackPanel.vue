<script setup lang="ts">
// Does this screen work as you expect (app 0.3.10)? The quiet card above a screen a day after it first worked, and the
// same question for good under Settings. Only a click on an answer sends anything; the add-on keeps the board's key,
// numbers the revisions and retries, so this page only says what the owner chose.
import { computed, ref } from "vue";
import { t } from "../i18n";
import { feedbackAction, state } from "../store";
import type { FeedbackAnswer, FeedbackIssue, Screen } from "../types";

const props = defineProps<{ screen: Screen; mode: "card" | "settings" }>();
const ISSUES: FeedbackIssue[] = ["display", "touch", "connection", "installation", "other"];

const fb = computed(() => props.screen.feedback!);
// ask: the question; details: what goes wrong, after an answer went out; done: the card has said its thanks.
const step = ref<"summary" | "ask" | "details" | "thanks" | "done">(props.mode === "card" ? "ask" : "summary");
const outcome = ref<FeedbackAnswer["outcome"] | null>(null);
const issues = ref<FeedbackIssue[]>([]);
const comment = ref("");
const busy = ref(false);
const note = ref("");
const uid = `feedback-${props.mode}`;

// The card shows while it asks, and stays for the thanks and details once someone answered on it. Never while a
// screen is updating or offline: then there are other things to read.
const engaged = ref(false);
const visible = computed(() => props.mode === "settings" || (
  !state.updating.includes(props.screen.id) && (engaged.value ? step.value !== "done" : fb.value.ask && props.screen.online)));

const current = computed(() => fb.value.pending || fb.value.shared);
const answerText = (answer: FeedbackAnswer | null) => answer
  ? [t(`editor.feedback.shared.${answer.outcome}`), ...(answer.issues || []).map((issue) => t(`editor.feedback.issues.${issue}`))].join(" · ")
  : "";

const status = computed(() => {
  const f = fb.value;
  if (busy.value) return t("editor.feedback.status.sending");
  if (f.state === "waiting") return t("editor.feedback.status.waiting");
  if (f.state === "failed") return t("editor.feedback.status.failed");
  if (f.state === "deleting") return t("editor.feedback.status.deleting");
  if (f.state === "delete_failed") return t("editor.feedback.status.delete_failed");
  if (f.problem) return t(`editor.feedback.status.${f.problem}`);
  if (note.value) return note.value;
  if (f.deleted && !f.shared) return t("editor.feedback.status.deleted");
  return "";
});

function startDetails(chosen: FeedbackAnswer["outcome"]) {
  const before = fb.value.pending || fb.value.shared;
  outcome.value = chosen;
  issues.value = before?.outcome === chosen ? [...(before.issues || [])] : [];
  comment.value = before?.outcome === chosen ? before.comment || "" : "";
}

async function run(body: Record<string, unknown>) {
  if (busy.value) return false;
  busy.value = true;
  note.value = "";
  try {
    return await feedbackAction(props.screen, body);
  } finally {
    busy.value = false;
  }
}

// Yes and Not quite send at once, so an answer without details counts too; details are a new revision of it.
async function answer(chosen: FeedbackAnswer["outcome"]) {
  engaged.value = true;
  startDetails(chosen);
  if (!(await run({ action: "answer", outcome: chosen, issues: [] }))) return;
  if (fb.value.state === "idle" && !fb.value.problem) note.value = t("editor.feedback.status.received");
  step.value = chosen === "not_working" ? "details" : props.mode === "card" ? "thanks" : "summary";
}
async function addDetails() {
  if (!outcome.value) return;
  if (!(await run({ action: "answer", outcome: outcome.value, issues: outcome.value === "working" ? [] : issues.value, comment: comment.value }))) return;
  if (fb.value.state === "idle" && !fb.value.problem) note.value = t("editor.feedback.status.received");
  finish();
}
function finish() {
  step.value = props.mode === "card" ? "done" : "summary";
}
async function later() {
  engaged.value = false;
  await run({ action: "later" });
}
async function never() {
  engaged.value = false;
  await run({ action: "never" });
}
const cancel = () => run({ action: "cancel" });
const retry = () => run({ action: "retry" });
async function remove() {
  if (await run({ action: "delete" })) step.value = "summary";
}
function change() {
  step.value = "ask";
}
const toggle = (issue: FeedbackIssue) => {
  issues.value = issues.value.includes(issue) ? issues.value.filter((i) => i !== issue) : [...issues.value, issue];
};
</script>

<template>
  <section v-if="visible" class="feedback" :class="mode === 'card' ? 'feedback-card' : 'set-card'" :id="uid" :aria-labelledby="`${uid}-title`">
    <h4 v-if="mode === 'settings'" :id="`${uid}-title`">{{ t("editor.feedback.settings_title") }}</h4>

    <!-- The question: on the card, and under Settings once the owner asks for it. -->
    <template v-if="step === 'ask'">
      <component :is="mode === 'card' ? 'h2' : 'p'" :id="mode === 'card' ? `${uid}-title` : undefined" class="fb-question">{{ t("editor.feedback.question") }}</component>
      <p class="hint">{{ t("editor.feedback.intro") }}</p>
      <div class="fb-actions">
        <button type="button" class="btn primary" :disabled="busy" @click="answer('working')">{{ t("editor.feedback.yes") }}</button>
        <button type="button" class="btn quiet" :disabled="busy" @click="answer('not_working')">{{ t("editor.feedback.no") }}</button>
        <button v-if="mode === 'card'" type="button" class="btn quiet" :disabled="busy" @click="later">{{ t("editor.feedback.later") }}</button>
        <button v-else type="button" class="btn quiet" :disabled="busy" @click="step = 'summary'">{{ t("editor.common.cancel") }}</button>
        <button v-if="mode === 'card'" type="button" class="fb-link" :disabled="busy" @click="never">{{ t("editor.feedback.never") }}</button>
      </div>
    </template>

    <!-- After an answer: what goes wrong (or anything to add), as a new revision of the same answer. -->
    <template v-else-if="step === 'details'">
      <template v-if="outcome === 'not_working'">
        <p class="fb-question" :id="mode === 'card' ? `${uid}-title` : undefined">{{ t("editor.feedback.issues_question") }}</p>
        <div class="fb-issues" role="group" :aria-label="t('editor.feedback.issues_question')">
          <label v-for="issue in ISSUES" :key="issue" class="fb-issue">
            <input type="checkbox" :checked="issues.includes(issue)" :disabled="busy" @change="toggle(issue)" />
            <span>{{ t(`editor.feedback.issues.${issue}`) }}</span>
          </label>
        </div>
      </template>
      <p v-else class="fb-question" :id="mode === 'card' ? `${uid}-title` : undefined">{{ t("editor.feedback.add_something") }}</p>
      <label class="fb-comment">
        <span>{{ t("editor.feedback.comment_label") }}</span>
        <textarea v-model="comment" rows="3" maxlength="1000" :disabled="busy" :aria-describedby="`${uid}-comment-hint`"></textarea>
        <small :id="`${uid}-comment-hint`">{{ t("editor.feedback.comment_hint") }}</small>
      </label>
      <div class="fb-actions">
        <button type="button" class="btn primary" :disabled="busy" @click="addDetails">{{ t("editor.feedback.add_details") }}</button>
        <button type="button" class="btn quiet" :disabled="busy" @click="finish">{{ t("editor.feedback.done") }}</button>
      </div>
    </template>

    <!-- The card after a yes: thanks, and a small way to add something. -->
    <div v-else-if="step === 'thanks'" class="fb-actions">
      <button type="button" class="fb-link" @click="step = 'details'">{{ t("editor.feedback.add_something") }}</button>
      <button type="button" class="btn quiet" @click="finish">{{ t("editor.common.close") }}</button>
    </div>

    <!-- Settings: what this screen shared, and changing or deleting it. -->
    <template v-else-if="step === 'summary'">
      <p v-if="current" class="fb-shared">{{ answerText(current) }}<span v-if="current.comment" class="fb-note">“{{ current.comment }}”</span></p>
      <p v-else class="hint">{{ fb.answered ? t("editor.feedback.none_now") : t("editor.feedback.none_yet") }}</p>
      <div class="fb-actions">
        <button type="button" class="btn quiet" :disabled="busy || fb.state === 'deleting' || fb.state === 'delete_failed'" @click="change">
          {{ current ? t("editor.feedback.change") : t("editor.feedback.share") }}</button>
        <button v-if="fb.answered && (current || fb.state === 'delete_failed' || fb.state === 'deleting')" type="button" class="btn quiet danger"
          :disabled="busy || fb.state === 'deleting'" @click="remove">{{ t("editor.feedback.delete") }}</button>
      </div>
    </template>

    <p class="fb-status" role="status" aria-live="polite">
      <span>{{ status }}</span>
      <button v-if="fb.state === 'waiting' || fb.state === 'failed'" type="button" class="fb-link" :disabled="busy" @click="cancel">{{ t("editor.common.cancel") }}</button>
      <button v-if="fb.state === 'failed' || fb.state === 'delete_failed'" type="button" class="fb-link" :disabled="busy" @click="retry">{{ t("editor.feedback.retry") }}</button>
    </p>

    <div class="fb-foot">
    <details class="fb-what">
      <summary>{{ t("editor.feedback.what_title") }}</summary>
      <ul>
        <li>{{ t("editor.feedback.what.model", { model: fb.model ? `${fb.model} (${fb.board})` : fb.board }) }}</li>
        <li>{{ t("editor.feedback.what.answer") }}</li>
        <li v-if="fb.versions.firmware_version">{{ t("editor.feedback.what.firmware", { version: fb.versions.firmware_version }) }}</li>
        <li v-if="fb.versions.addon_version">{{ t("editor.feedback.what.addon", { version: fb.versions.addon_version }) }}</li>
      </ul>
      <p class="hint">{{ t("editor.feedback.what.nothing_else") }}</p>
    </details>
    <a class="fb-privacy" :href="fb.privacy" target="_blank" rel="noopener noreferrer">{{ t("editor.feedback.privacy") }}</a>
    </div>
  </section>
</template>

<style scoped>
.feedback-card { flex: none; margin: 14px 18px 0; padding: 12px 16px; border: 1px solid var(--line); border-radius: 12px; background: var(--surface); }
.feedback-card .fb-question { font-size: 14px; font-weight: 600; margin: 0 0 4px; }
.set-card .fb-question { font-weight: 600; margin: 4px 0; }
.fb-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 10px 0 4px; }
.fb-link { background: none; border: 0; padding: 4px 2px; color: var(--muted); font-size: 12px; text-decoration: underline; cursor: pointer; }
.fb-link:hover:not(:disabled) { color: var(--ink); }
.fb-issues { display: flex; flex-wrap: wrap; gap: 6px 14px; margin: 6px 0 10px; }
.fb-issue { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; }
.fb-comment { display: grid; gap: 4px; font-size: 12.5px; max-width: 560px; }
.fb-comment textarea { width: 100%; resize: vertical; min-height: 60px; }
.fb-shared { margin: 4px 0; color: var(--ink-2); }
.fb-note { display: block; color: var(--muted); font-size: 12px; margin-top: 2px; overflow-wrap: anywhere; }
.fb-status { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; min-height: 0; margin: 2px 0; font-size: 12px; color: var(--ink-2); }
.fb-status:empty, .fb-status > span:empty { display: none; }
.fb-foot { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 16px; margin-top: 4px; }
.fb-what { font-size: 12px; color: var(--muted); }
.fb-what[open] { flex-basis: 100%; order: 1; }
.fb-what summary { cursor: pointer; display: inline; margin-right: 12px; }
.fb-what ul { margin: 6px 0 4px 18px; padding: 0; }
.fb-privacy { font-size: 12px; color: var(--muted); }
.btn.danger:hover:not(:disabled) { color: var(--danger); background: var(--danger-soft); }
@media (max-width: 640px) {
  .feedback-card { margin: 10px 16px 0; }
  .fb-actions { flex-direction: column; align-items: stretch; }
  .fb-actions .btn { white-space: normal; }
}
</style>
