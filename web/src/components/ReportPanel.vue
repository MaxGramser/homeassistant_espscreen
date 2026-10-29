<script setup lang="ts">
// "My screen doesn't work right": a troubleshooting report of one screen, in steps. The add-on collects what it knows
// (the board and versions, the screen's live log, the lines of Home Assistant's log about it, its own log, the last
// build log, the last crash), the person reads every file here, and only Send takes it to Tessera, with a note and
// an email if they give one. The screen is in the address (#/screens/<id>/report, router.ts); the add-on's answers
// are the contract's (types.ts, Report*). A report sent before shows its reference again when the page is reopened.
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { api, getJson, send } from "../api";
import { useBusy } from "../composables/useBusy";
import { editorLanguage, t } from "../i18n";
import { agoText } from "../model/topbar";
import Icon from "./ui/Icon.vue";
import SwitchRow from "./ui/SwitchRow.vue";
import { useInventoryStore } from "../stores/inventory";
import { useUiStore } from "../stores/ui";
import type { Report, ReportFile, ReportOffer, ReportSendResult } from "../types";

const ui = useUiStore();
const inv = useInventoryStore();

// The bug report on GitHub, the same form FeedbackPanel fills in: the reference and the board go in the text, so the
// report can be found. Issues are written in English, whatever the editor speaks.
const ISSUES = "https://github.com/MaxGramser/homeassistant_espscreen/issues/new";
const DISCORD = "https://discord.gg/M7x96AUzC";
const POLL_MS = 1500;

const id = computed(() => ui.reportScreen || "");
const screen = computed(() => inv.inventory.screens.find((s) => s.id === id.value));
const title = computed(() => screen.value ? t("editor.report.title_named", { name: screen.value.name }) : t("editor.report.title"));

// start: what will be collected, the last crash, the note and the email, Collect. collecting: the add-on's step and
// progress. ready: the facts, the files to read, Download and Send. sent: the reference. failed: why, and Try again.
type Stage = "start" | "collecting" | "ready" | "sent" | "failed";
const stage = ref<Stage>("start");
const offer = ref<ReportOffer | null>(null);
const offerError = ref("");
const report = ref<Report | null>(null);
const failure = ref("");
const reference = ref("");
// What the person chose, kept across the steps: the depth, the note, the email and whether to remember it.
const full = ref(false);
const note = ref("");
const email = ref("");
const remember = ref(false);
const consent = ref(false);
const sendError = ref("");
const editing = ref(false);
// The file open to read, by its name in the list.
const opened = ref<{ name: string; text: string } | null>(null);
const { busy, runOnce } = useBusy();
const referenceEl = ref<HTMLElement | null>(null);
// Once a new report was started here, a reopened page's `last` no longer wins over it.
let started = false;

// ---- The offer: what the add-on knows of this screen before anything is collected ----
async function load() {
  offerError.value = "";
  try {
    const data = await getJson<ReportOffer>(`screens/${encodeURIComponent(id.value)}/report`);
    offer.value = data;
    if (data.email && !email.value) { email.value = data.email; remember.value = true; }
    if (data.last && !started && stage.value === "start") {
      reference.value = data.last.reference;
      stage.value = "sent";
      // The facts of the sent report, for the GitHub issue; a report the add-on no longer keeps leaves them out.
      try { report.value = await getJson<Report>(`reports/${encodeURIComponent(data.last.id)}`); } catch { /* gone: the reference stands alone */ }
    }
  } catch (e: any) {
    offerError.value = e.message;
  }
}
const blockers = computed(() => offer.value?.blockers ?? []);
const crashWhen = (at: string) => agoText(Math.floor(Date.parse(at) / 1000), Math.floor(Date.now() / 1000), editorLanguage());

// ---- Collecting: asked once, then followed every 1.5 seconds until the add-on is done ----
let timer: ReturnType<typeof setTimeout> | null = null;
function stopPolling() { if (timer) { clearTimeout(timer); timer = null; } }
const collect = () => runOnce(async () => {
  started = true;
  sendError.value = ""; failure.value = ""; opened.value = null; consent.value = false; editing.value = false;
  try {
    const { id: reportId } = await send<{ id: string }>(`screens/${encodeURIComponent(id.value)}/report`, "POST", { depth: full.value ? "full" : "basic" });
    report.value = { id: reportId, screen: id.value, depth: full.value ? "full" : "basic", state: "collecting", step: null, progress: 0,
      files: [], summary: null, warnings: [], size: 0, reference: null, sent_at: null, error: null };
    stage.value = "collecting";
    await poll();
  } catch (e: any) {
    failure.value = e.message;
    stage.value = "failed";
  }
});
async function poll() {
  stopPolling();
  const reportId = report.value?.id;
  if (!reportId) return;
  try {
    const data = await getJson<Report>(`reports/${encodeURIComponent(reportId)}`);
    if (report.value?.id !== reportId) return;
    report.value = data;
    if (data.state === "collecting") { timer = setTimeout(poll, POLL_MS); return; }
    if (data.state === "failed") { failure.value = data.error || t("editor.report.failed_title"); stage.value = "failed"; return; }
    if (data.state === "sent" && data.reference) { reference.value = data.reference; stage.value = "sent"; return; }
    stage.value = "ready";
  } catch (e: any) {
    failure.value = e.message;
    stage.value = "failed";
  }
}
const progress = computed(() => Math.round(Math.min(1, Math.max(0, report.value?.progress ?? 0)) * 100));
const stepText = computed(() => report.value?.step ? t(`editor.report.steps.${report.value.step}`) : t("editor.report.collecting"));

// ---- Ready: the facts, the files and what they hold ----
const facts = computed(() => {
  const s = report.value?.summary;
  if (!s) return [];
  const rows: [string, string][] = [
    [t("editor.report.facts.board"), s.board_name ? `${s.board_name} (${s.board})` : s.board],
    [t("editor.report.facts.firmware"), s.firmware ? (s.channel && s.channel !== "main" ? `${s.firmware} (${s.channel})` : s.firmware) : t("editor.report.facts.unknown")],
    [t("editor.report.facts.addon"), s.addon || t("editor.report.facts.unknown")],
    [t("editor.report.facts.ha"), s.ha || t("editor.report.facts.unknown")],
    [t("editor.report.facts.esphome"), s.esphome || t("editor.report.facts.unknown")],
    [t("editor.report.facts.plugins"), s.plugins.length ? s.plugins.map((p) => `${p.id} ${p.version}`).join(", ") : t("editor.report.facts.none")],
    [t("editor.report.facts.crash"), s.crash ? `${s.crash.reason}, ${crashWhen(s.crash.at)}` : t("editor.report.facts.none")],
  ];
  return rows;
});
function sizeText(bytes: number) {
  if (bytes < 1024) return t("editor.report.size.b", { n: bytes });
  if (bytes < 1024 * 1024) return t("editor.report.size.kb", { n: (bytes / 1024).toFixed(bytes < 10240 ? 1 : 0) });
  return t("editor.report.size.mb", { n: (bytes / 1024 / 1024).toFixed(1) });
}
const downloadUrl = computed(() => report.value ? `api/reports/${encodeURIComponent(report.value.id)}.zip` : "");
async function openFile(file: ReportFile) {
  if (opened.value?.name === file.name) { opened.value = null; return; }
  if (!report.value) return;
  try {
    const response = await api(`reports/${encodeURIComponent(report.value.id)}/files/${encodeURIComponent(file.name)}`);
    opened.value = { name: file.name, text: await response.text() };
  } catch (e: any) {
    ui.toast(e.message);
  }
}

// ---- Send: with consent, the note and the email; an answer that is no "sent" says why and leaves Download open ----
const sendReport = () => runOnce(async () => {
  if (!report.value || !consent.value) return;
  sendError.value = "";
  try {
    const result = await send<ReportSendResult>(`reports/${encodeURIComponent(report.value.id)}/send`, "POST",
      { consent: true, note: note.value.trim(), email: email.value.trim() || null, remember_email: remember.value });
    if (result.state === "sent") { reference.value = result.reference; stage.value = "sent"; }
    else sendError.value = result.error;
  } catch (e: any) {
    sendError.value = e.message;
  }
});

// ---- Sent: the reference, to copy and to quote ----
const issueUrl = computed(() => {
  const s = report.value?.summary;
  const board = s ? `${s.board_name} (${s.board})` : screen.value?.board || "";
  const versions = [s?.addon && `add-on ${s.addon}`, s?.firmware && `firmware ${s.firmware}`].filter(Boolean).join(", ");
  const facts = [`Report reference: ${reference.value}`, board && `Board: ${board}`].filter(Boolean).join("\n");
  const query = new URLSearchParams({ template: "bug_report.yml" });
  if (board) query.set("title", `[Bug]: ${s?.board_name || board}`);
  if (versions) query.set("versions", versions);
  query.set("what-happened", note.value.trim() ? `${note.value.trim()}\n\n${facts}` : facts);
  return `${ISSUES}?${query}`;
});
// Home Assistant over plain http has no Clipboard API: then the reference is selected on the page, to copy by hand.
async function copyReference() {
  try {
    if (!navigator.clipboard || !window.isSecureContext) throw new Error();
    await navigator.clipboard.writeText(reference.value);
    ui.toast(t("editor.report.sent.copied"));
  } catch {
    const range = document.createRange();
    if (referenceEl.value) range.selectNodeContents(referenceEl.value);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
    ui.toast(t("editor.report.sent.selected"));
  }
}
function startOver() {
  stopPolling();
  started = true;
  report.value = null; reference.value = ""; failure.value = ""; sendError.value = ""; opened.value = null; consent.value = false;
  stage.value = "start";
  void load();
}

onMounted(load);
onBeforeUnmount(stopPolling);
</script>

<template>
  <div class="panel" id="report-panel">
    <div class="panel-head">
      <div class="tx">
        <span class="eyebrow">{{ t("editor.report.eyebrow") }}</span>
        <h1 id="report-title">{{ title }}</h1>
        <p>{{ t("editor.report.intro") }}</p>
      </div>
      <button type="button" class="btn quiet" id="close-report" @click="ui.go('')">{{ t("editor.common.back") }}</button>
    </div>

    <p v-if="offerError" class="status-line error" role="alert">{{ offerError }}</p>
    <p v-else-if="!offer && stage === 'start'" class="hint">{{ t("editor.report.loading") }}</p>

    <!-- Start: what goes in, the last crash, the choices, Collect. -->
    <template v-if="stage === 'start' && offer">
      <section class="rp-card">
        <h3>{{ t("editor.report.collects_title") }}</h3>
        <p>{{ t("editor.report.collects") }}</p>
        <p class="hint">{{ t("editor.report.nothing_leaves") }}</p>
      </section>
      <section v-if="offer.crash" class="rp-card" id="report-crash">
        <h3>{{ t("editor.report.crash_title") }}</h3>
        <p>{{ t("editor.report.crash_line", { reason: offer.crash.reason, when: crashWhen(offer.crash.at), seen: t("editor.report.crash_seen", offer.crash.count) }) }}</p>
        <details v-if="offer.crash.decoded.length" class="rp-fold">
          <summary>{{ t("editor.report.crash_lines") }}</summary>
          <pre>{{ offer.crash.decoded.join("\n") }}</pre>
        </details>
      </section>
      <section class="rp-card rp-form">
        <label class="rp-check">
          <input type="checkbox" id="report-full" v-model="full" :disabled="busy" />
          <span>{{ t("editor.report.full") }}</span>
        </label>
        <label class="rp-field">
          <span>{{ t("editor.report.note_label") }}</span>
          <textarea id="report-note" v-model="note" rows="4" maxlength="2000" :disabled="busy"></textarea>
          <small>{{ t("editor.report.note_hint") }}</small>
        </label>
        <label class="rp-field">
          <span>{{ t("editor.report.email_label") }}</span>
          <input id="report-email" v-model="email" type="email" maxlength="254" autocomplete="email" :disabled="busy" />
          <small>{{ t("editor.report.email_hint") }}</small>
        </label>
        <SwitchRow :label="t('editor.report.remember_email')" v-model="remember" :disabled="busy || !email.trim()" />
      </section>
      <div v-for="blocker in blockers" :key="blocker" class="notice warn" role="status">
        <Icon name="alert-circle-outline" /><span>{{ t(`editor.report.blockers.${blocker}`) }}</span>
      </div>
      <div class="actions">
        <button type="button" class="btn primary" id="report-collect" :disabled="busy || !offer.ready" @click="collect">{{ t("editor.report.collect") }}</button>
        <button v-if="blockers.includes('collecting')" type="button" class="btn quiet" id="report-check-again" :disabled="busy" @click="load">{{ t("editor.report.check_again") }}</button>
      </div>
    </template>

    <!-- Collecting: the add-on's step and how far it is. -->
    <section v-else-if="stage === 'collecting'" class="rp-card" id="report-collecting">
      <div class="progress-head"><span class="spin small"></span>{{ t("editor.report.collecting") }}</div>
      <div class="progress"><i :style="{ width: `${progress}%` }"></i></div>
      <div class="progress-text"><span id="report-step">{{ stepText }}</span><span>{{ progress }}%</span></div>
      <p class="hint">{{ t("editor.report.collecting_hint") }}</p>
    </section>

    <!-- Ready: the facts, the warnings, the files to read, Download and Send. -->
    <template v-else-if="stage === 'ready' && report">
      <section class="rp-card" id="report-summary">
        <h3>{{ t("editor.report.ready_title") }}</h3>
        <dl class="rp-facts">
          <template v-for="[name, value] in facts" :key="name"><dt>{{ name }}</dt><dd>{{ value }}</dd></template>
        </dl>
        <ul v-if="report.warnings.length" class="rp-warnings" id="report-warnings">
          <li v-for="warning in report.warnings" :key="warning"><Icon name="information-outline" /><span>{{ t(`editor.report.warnings.${warning}`) }}</span></li>
        </ul>
      </section>
      <section class="rp-card" id="report-files">
        <h3>{{ t("editor.report.files_title") }} <small>{{ sizeText(report.size) }}</small></h3>
        <ul class="rp-files">
          <li v-for="file in report.files" :key="file.name">
            <button type="button" class="rp-file" :class="{ open: opened?.name === file.name }" :aria-expanded="opened?.name === file.name ? 'true' : 'false'" @click="openFile(file)">
              <code>{{ file.name }}</code>
              <span class="rp-file-meta">{{ sizeText(file.size) }} · {{ t("editor.report.file_lines", file.lines) }}</span>
              <Icon :name="opened?.name === file.name ? 'chevron-up' : 'chevron-down'" />
            </button>
          </li>
        </ul>
        <div v-if="opened" class="rp-view" id="report-file-view">
          <pre>{{ opened.text }}</pre>
          <button type="button" class="btn quiet mini" @click="opened = null">{{ t("editor.common.close") }}</button>
        </div>
        <div class="actions">
          <a class="btn quiet" id="report-download" :href="downloadUrl" download><Icon name="tray-arrow-down" />{{ t("editor.report.download") }}</a>
        </div>
      </section>
      <section class="rp-card" id="report-send">
        <h3>{{ t("editor.report.send_title") }}</h3>
        <p>{{ t("editor.report.send_text", { days: offer?.retention_days ?? 30 }) }}
          <a v-if="offer?.privacy_url" :href="offer.privacy_url" target="_blank" rel="noopener noreferrer">{{ t("editor.report.privacy") }}</a></p>
        <p v-if="!editing" class="rp-given">
          <span v-if="note.trim()">{{ t("editor.report.with_note") }}</span>
          <span v-if="email.trim()">{{ t("editor.report.with_email", { email: email.trim() }) }}</span>
          <button type="button" class="rp-link" @click="editing = true">{{ t("editor.report.change_note") }}</button>
        </p>
        <div v-else class="rp-form">
          <label class="rp-field">
            <span>{{ t("editor.report.note_label") }}</span>
            <textarea v-model="note" rows="4" maxlength="2000" :disabled="busy"></textarea>
          </label>
          <label class="rp-field">
            <span>{{ t("editor.report.email_label") }}</span>
            <input v-model="email" type="email" maxlength="254" autocomplete="email" :disabled="busy" />
          </label>
          <SwitchRow :label="t('editor.report.remember_email')" v-model="remember" :disabled="busy || !email.trim()" />
        </div>
        <label class="rp-check">
          <input type="checkbox" id="report-consent" v-model="consent" :disabled="busy" />
          <span>{{ t("editor.report.consent") }}</span>
        </label>
        <p v-if="sendError" class="status-line error" id="report-send-error" role="alert">{{ sendError }}</p>
        <div class="actions">
          <button type="button" class="btn primary" id="report-send-button" :disabled="busy || !consent" @click="sendReport">
            <span v-if="busy" class="spin small"></span>{{ busy ? t("editor.report.sending") : t("editor.report.send") }}
          </button>
        </div>
      </section>
    </template>

    <!-- Sent: the reference, to quote on GitHub or Discord. -->
    <template v-else-if="stage === 'sent'">
      <section class="rp-card rp-sent" id="report-sent">
        <h3>{{ t("editor.report.sent.title") }}</h3>
        <div class="rp-reference">
          <code ref="referenceEl" id="report-reference">{{ reference }}</code>
          <button type="button" class="btn quiet mini" id="report-copy" @click="copyReference"><Icon name="content-copy" />{{ t("editor.report.sent.copy") }}</button>
        </div>
        <p>{{ t("editor.report.sent.quote") }}</p>
        <div class="actions">
          <a class="btn quiet" id="report-github" :href="issueUrl" target="_blank" rel="noopener noreferrer">{{ t("editor.report.sent.github") }}</a>
          <a class="btn quiet" id="report-discord" :href="DISCORD" target="_blank" rel="noopener noreferrer">{{ t("editor.report.sent.discord") }}</a>
          <button type="button" class="rp-link" id="report-new" @click="startOver">{{ t("editor.report.sent.new") }}</button>
        </div>
      </section>
    </template>

    <!-- Failed: why, and the way to try again. -->
    <section v-else-if="stage === 'failed'" class="rp-card" id="report-failed">
      <h3>{{ t("editor.report.failed_title") }}</h3>
      <p class="status-line error" role="alert">{{ failure }}</p>
      <div class="actions">
        <button type="button" class="btn primary" id="report-retry" :disabled="busy" @click="startOver">{{ t("editor.report.try_again") }}</button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.rp-card { display: grid; gap: 8px; padding: 12px 16px 14px; border: 1px solid var(--line); border-radius: 12px; background: var(--surface); }
.rp-card h3 { display: flex; align-items: baseline; gap: 8px; font-size: 14px; font-weight: 600; margin: 0; }
.rp-card h3 small { display: inline; font-size: 11.5px; }
.rp-card p { margin: 0; }
.rp-fold summary { cursor: pointer; font-size: 12.5px; color: var(--ink-2); }
.rp-fold pre { margin-top: 8px; max-height: 240px; }
.rp-form { display: grid; gap: 12px; }
.rp-check { display: flex; align-items: flex-start; gap: 8px; font-size: 12.5px; color: var(--ink-2); cursor: pointer; }
.rp-check input { margin-top: 2px; flex: none; }
.rp-field { display: grid; gap: 4px; font-size: 12.5px; max-width: 560px; }
.rp-field > span { font-weight: 500; color: var(--ink); }
.rp-field textarea { resize: vertical; min-height: 72px; }
.rp-link { background: none; border: 0; padding: 4px 2px; color: var(--muted); font-size: 12px; text-decoration: underline; cursor: pointer; }
.rp-link:hover:not(:disabled) { color: var(--ink); }
.notice.warn { align-items: flex-start; }
.notice.warn .ui-icon { font-size: 18px; color: var(--warn); flex: none; }
.rp-facts { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 4px 16px; margin: 2px 0 0; font-size: 12.5px; }
.rp-facts dt { color: var(--muted); }
.rp-facts dd { margin: 0; color: var(--ink); overflow-wrap: anywhere; }
.rp-warnings { list-style: none; margin: 4px 0 0; padding: 0; display: grid; gap: 4px; font-size: 12.5px; color: var(--ink-2); }
.rp-warnings li { display: flex; gap: 6px; align-items: flex-start; }
.rp-warnings .ui-icon { font-size: 16px; color: var(--muted); flex: none; }
.rp-files { list-style: none; margin: 0; padding: 0; display: grid; }
.rp-file { display: flex; align-items: center; gap: 10px; width: 100%; padding: 7px 4px; border: 0; border-bottom: 1px solid var(--line); background: none; text-align: left; color: var(--ink); cursor: pointer; border-radius: 0; }
.rp-files li:last-child .rp-file { border-bottom: 0; }
.rp-file:hover { background: var(--surface-2); }
.rp-file.open code { font-weight: 600; }
.rp-file code { font-size: 12.5px; }
.rp-file-meta { margin-left: auto; font-size: 11.5px; color: var(--muted); white-space: nowrap; }
.rp-file .ui-icon { color: var(--muted); font-size: 16px; flex: none; }
.rp-view { display: grid; gap: 8px; justify-items: start; }
.rp-view pre { width: 100%; max-height: 420px; }
.rp-given { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 12px; font-size: 12.5px; color: var(--ink-2); }
.rp-reference { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
.rp-reference code { font-size: 26px; font-weight: 600; letter-spacing: 0.06em; color: var(--ink); }
.panel .actions a.btn { display: inline-flex; }
@media (max-width: 640px) {
  .panel { padding: 16px 16px 32px; }
  .panel-head { flex-direction: column; }
  .actions { flex-direction: column; align-items: stretch; }
  .actions .btn, .actions a.btn { white-space: normal; }
  .rp-facts { grid-template-columns: 1fr; gap: 0; }
  .rp-facts dt { margin-top: 6px; }
  .rp-file { flex-wrap: wrap; }
  .rp-file-meta { margin-left: 0; flex-basis: 100%; }
}
</style>
