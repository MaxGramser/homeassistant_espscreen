<script setup lang="ts">
// Layoutbot (docs/LAYOUTBOT.md): a small bot that floats over the corner of the pages and opens a chat. Shown only
// where Home Assistant has an AI Task that makes data (stores/layoutbot.ts available). While it thinks, the pages shine
// and take no edit, and the bot's face scans; its answer lands on the pages as one step of undo, which the chat can
// take back.
import { useElementBounding } from "@vueuse/core";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useStickToBottom } from "../composables/useStickToBottom";
import { editorLanguage, t } from "../i18n";
import { useLayoutbotStore, type Elsewhere } from "../stores/layoutbot";
import { useScreenStore } from "../stores/screen";
import Icon from "./ui/Icon.vue";
import UiSelect from "./ui/UiSelect.vue";

const bot = useLayoutbotStore();
const scr = useScreenStore();
const canvas = ref<HTMLElement | null>(null);
onMounted(() => { canvas.value = document.getElementById("canvas"); });
const box = useElementBounding(canvas);
const canvasBox = computed(() => ({ left: `${box.left.value}px`, top: `${box.top.value}px`, width: `${box.width.value}px`, height: `${box.height.value}px` }));
// The bot stands in the window's lower right corner, as a chat does, and the chat opens above it with the window's
// height; the shine covers the pages (#canvas) wherever they are.
const chatWidth = computed(() => Math.min(380, window.innerWidth - 24));

const draft = ref("");
const field = ref<HTMLTextAreaElement | null>(null);
const list = ref<HTMLElement | null>(null);
useStickToBottom(list, () => bot.messages.length + (bot.busy ? 1 : 0));
// A new message grows into place (its enter transition): follow it to the end once it stands.
watch(() => bot.messages.length, () => setTimeout(() => list.value?.scrollTo({ top: list.value.scrollHeight, behavior: "smooth" }), 340));

const sections = computed(() => Boolean(scr.currentScreen?.sections));
const suggestions = computed(() => (sections.value
  ? ["lights_sections", "covers_sections", "media", "climate"]
  : ["lights", "covers", "media", "climate"]).map((key) => t(`editor.layoutbot.suggest.${key}`)));

function toggle() {
  bot.open = !bot.open;
  if (bot.open) nextTick(() => field.value?.focus());
}
function submit(text = draft.value) {
  if (!text.trim() || bot.busy) return;
  draft.value = "";
  void bot.ask(text);
}
function onKey(event: KeyboardEvent) {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); submit(); }
}
// The textarea grows with what is typed, up to five lines.
watch(draft, () => nextTick(() => {
  const el = field.value;
  if (!el) return;
  el.style.height = "auto";
  el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
}));

// While it thinks the pages take no edit: no key reaches the editor but Escape, which stops waiting.
function guard(event: KeyboardEvent) {
  if (!bot.busy) return;
  if (event.key === "Escape") { event.preventDefault(); bot.stop(); return; }
  if ((event.target as HTMLElement | null)?.closest?.(".bot-chat")) return;
  event.preventDefault();
  event.stopPropagation();
}
onMounted(() => window.addEventListener("keydown", guard, true));
onBeforeUnmount(() => window.removeEventListener("keydown", guard, true));

const now = ref(Date.now());
let timer: ReturnType<typeof setInterval> | undefined;
watch(() => bot.busy, (busy) => {
  clearInterval(timer);
  if (busy) timer = setInterval(() => { now.value = Date.now(); }, 250);
  else nextTick(() => field.value?.focus());
});
onBeforeUnmount(() => clearInterval(timer));
const elapsed = computed(() => Math.max(0, Math.floor((now.value - bot.started) / 1000)));
const names = (list: string[]) => new Intl.ListFormat(editorLanguage(), { type: "conjunction" }).format(list);
function whatOf(other: Elsewhere) {
  const sum = other.summary;
  if (!sum) return "";
  return [sum.pages ? t("editor.layoutbot.what.pages", { n: sum.pages }, sum.pages) : "",
    sum.added ? t("editor.layoutbot.what.added", { n: sum.added }, sum.added) : "",
    sum.removed ? t("editor.layoutbot.what.removed", { n: sum.removed }, sum.removed) : "",
    sum.changed.length ? t("editor.layoutbot.what.changed", { pages: names(sum.changed.map(String)) }, sum.changed.length) : ""]
    .filter(Boolean).join(", ");
}
// The AI integrations of Home Assistant that give an AI Task, each started with a my link (its config flow).
const PROVIDERS = [
  { domain: "openai_conversation", name: "OpenAI", note: "cloud" },
  { domain: "anthropic", name: "Anthropic", note: "cloud" },
  { domain: "google_generative_ai_conversation", name: "Google Gemini", note: "cloud" },
  { domain: "ollama", name: "Ollama", note: "local" },
];
const checking = ref(false);
async function recheck() { checking.value = true; try { await bot.recheck(); } finally { checking.value = false; } }
const agentChoices = computed(() => bot.agents.map((agent) => [agent.id, agent.name] as const));
</script>

<template>
  <Teleport v-if="bot.shown" to="body">
    <Transition name="bot-shine">
      <div v-if="bot.busy" class="bot-shine" :style="canvasBox" @pointerdown.stop.prevent @click.stop.prevent @wheel.prevent>
        <div class="bot-shine-sweep" aria-hidden="true"></div>
        <div class="bot-shine-pill" role="status" aria-live="polite">
          <span class="bot-spark" aria-hidden="true"></span>
          <span>{{ t("editor.layoutbot.busy") }}</span>
          <span class="bot-secs">{{ t("editor.layoutbot.seconds", { n: elapsed }) }}</span>
          <button type="button" class="bot-stop" @click="bot.stop()">{{ t("editor.layoutbot.stop") }}</button>
        </div>
      </div>
    </Transition>

    <Transition name="bot-chat">
      <section v-if="bot.open" class="bot-chat" :style="{ width: `${chatWidth}px` }" role="dialog" :aria-label="t('editor.layoutbot.name')">
        <header class="bot-head">
          <span class="bot-avatar" :class="{ busy: bot.busy }" aria-hidden="true">
            <svg viewBox="0 0 40 40"><rect x="7" y="11" width="26" height="21" rx="7" class="face" /><rect class="eye" x="13" y="18" width="4" height="6" rx="2" /><rect class="eye" x="23" y="18" width="4" height="6" rx="2" /><line x1="20" y1="11" x2="20" y2="6" class="stalk" /><circle cx="20" cy="5" r="2.4" class="bulb" /></svg>
          </span>
          <div class="bot-title">
            <strong>{{ t("editor.layoutbot.name") }}</strong>
            <UiSelect v-if="agentChoices.length > 1 && bot.agent" v-model="bot.agent" :options="agentChoices" inline class="bot-agent" />
            <small v-else>{{ bot.ready ? bot.agentName : t("editor.layoutbot.connect.short") }}</small>
          </div>
          <button type="button" class="icon-btn" :aria-label="t('editor.layoutbot.close')" @click="bot.open = false"><Icon name="close" /></button>
        </header>

        <div v-if="!bot.ready" class="bot-list bot-connect">
          <div class="msg bot">
            <p><strong>{{ t("editor.layoutbot.connect.title") }}</strong></p>
            <p>{{ t("editor.layoutbot.connect.body") }}</p>
          </div>
          <div class="bot-providers">
            <a v-for="provider in PROVIDERS" :key="provider.domain" class="provider" target="_top"
              :href="`/_my_redirect/config_flow_start?domain=${provider.domain}`">
              <strong>{{ provider.name }}</strong><small>{{ t(`editor.layoutbot.connect.${provider.note}`) }}</small>
            </a>
          </div>
          <p class="fine">{{ t("editor.layoutbot.connect.after") }}</p>
          <button type="button" class="chip again" :disabled="checking" @click="recheck"><Icon name="refresh" />{{ t("editor.layoutbot.connect.again") }}</button>
        </div>
        <div v-else ref="list" class="bot-list">
          <div class="msg bot">
            <p>{{ t("editor.layoutbot.hello") }}</p>
            <p class="fine">{{ t("editor.layoutbot.privacy", { agent: bot.agentName }) }}</p>
          </div>
          <div v-if="!bot.messages.length" class="bot-suggest">
            <button v-for="text in suggestions" :key="text" type="button" :disabled="bot.busy" @click="submit(text)">{{ text }}</button>
          </div>
          <TransitionGroup name="msg">
            <template v-for="message in bot.messages" :key="message.id">
              <div class="msg" :class="[message.from, { error: message.error }]">
                <p>{{ message.text }}</p>
                <ul v-if="message.notes?.length" class="notes"><li v-for="note in message.notes" :key="note">{{ note }}</li></ul>
                <ul v-if="message.elsewhere?.length" class="elsewhere">
                  <li v-for="other in message.elsewhere" :key="other.id"><Icon name="monitor-eye" /><span><b>{{ other.name }}</b> {{ [other.error, whatOf(other), ...(other.notes ?? [])].filter(Boolean).join(" ") }}</span></li>
                </ul>
                <div v-if="message.page || bot.undoable(message) || message.undone" class="msg-actions">
                  <button v-if="message.page && !message.undone" type="button" class="chip" @click="bot.show(message)"><Icon name="eye-outline" />{{ t("editor.layoutbot.show") }}</button>
                  <button v-if="bot.undoable(message)" type="button" class="chip" @click="bot.undo(message)"><Icon name="undo" />{{ t("editor.layoutbot.undo") }}</button>
                  <span v-if="message.undone" class="undone">{{ t("editor.layoutbot.undone") }}</span>
                </div>
              </div>
              <!-- After every real change the editor itself asks, never the model: send it to the screens? -->
              <div v-if="message.send && (message.send !== 'ask' || bot.targets(message).length)" :key="`${message.id}-send`" class="msg bot send">
                <template v-if="message.send === 'ask'">
                  <p>{{ t("editor.layoutbot.send.ask", { which: names(bot.targets(message)) }, bot.targets(message).length) }}</p>
                  <div class="msg-actions">
                    <button type="button" class="send-yes" :disabled="bot.busy" @click="bot.deliver(message)">{{ t("editor.layoutbot.send.yes") }}</button>
                    <button type="button" class="chip" @click="bot.decline(message)">{{ t("editor.layoutbot.send.no") }}</button>
                  </div>
                </template>
                <p v-else-if="message.send === 'sending'" class="send-state"><span class="bot-spark" aria-hidden="true"></span>{{ t("editor.layoutbot.send.sending") }}</p>
                <p v-else-if="message.send === 'sent'" class="send-state ok"><Icon name="check" />{{ t("editor.layoutbot.send.sent") }}</p>
                <p v-else-if="message.send === 'declined'" class="send-state">{{ t("editor.layoutbot.send.declined") }}</p>
                <p v-else class="send-state">{{ t("editor.layoutbot.send.not_all") }}</p>
              </div>
            </template>
          </TransitionGroup>
          <div v-if="bot.busy" class="msg bot typing" aria-hidden="true"><i></i><i></i><i></i></div>
        </div>

        <form v-if="bot.ready" class="bot-compose" @submit.prevent="submit()">
          <textarea ref="field" v-model="draft" rows="1" :disabled="bot.busy" :placeholder="t('editor.layoutbot.placeholder')" maxlength="500" @keydown="onKey"></textarea>
          <button type="submit" class="bot-send" :disabled="bot.busy || !draft.trim()" :aria-label="t('editor.layoutbot.send')"><Icon name="arrow-up" /></button>
        </form>
      </section>
    </Transition>

    <button type="button" class="bot-fab" :class="{ busy: bot.busy, open: bot.open, asleep: !bot.ready }"
      :aria-label="t('editor.layoutbot.open')" :aria-expanded="bot.open" :title="t('editor.layoutbot.open')" @click="toggle">
      <span class="bot-ring" aria-hidden="true"></span>
      <svg class="bot-body" viewBox="0 0 40 40" aria-hidden="true">
        <line x1="20" y1="11" x2="20" y2="6" class="stalk" />
        <circle cx="20" cy="5" r="2.6" class="bulb" />
        <rect x="6" y="11" width="28" height="22" rx="8" class="face" />
        <g class="eyes"><rect class="eye" x="12.5" y="18" width="4.5" height="7" rx="2.25" /><rect class="eye" x="23" y="18" width="4.5" height="7" rx="2.25" /></g>
        <rect class="scan" x="10" y="20.5" width="20" height="2.2" rx="1.1" />
      </svg>
      <span v-if="!bot.ready" class="bot-z" aria-hidden="true">z</span>
    </button>
  </Teleport>
</template>

<style scoped>
/* ---- the bot ---- */
.bot-fab { position: fixed; z-index: 60; right: 24px; bottom: 24px; width: 56px; height: 56px; border: 0; border-radius: 50%; padding: 0; cursor: pointer;
  display: grid; place-items: center; color: white; background: linear-gradient(140deg, var(--bot-a), var(--bot-b));
  box-shadow: 0 10px 28px color-mix(in srgb, var(--bot-b) 38%, transparent), 0 2px 6px rgba(20, 24, 40, .18);
  animation: bot-float 3.6s ease-in-out infinite; transition: transform .2s cubic-bezier(.3, 1.4, .5, 1), box-shadow .2s; }
.bot-fab:hover { transform: translateY(-2px) scale(1.06); }
.bot-fab:active { transform: scale(.96); }
.bot-fab:focus-visible { outline: none; box-shadow: var(--focus), 0 10px 28px color-mix(in srgb, var(--bot-b) 38%, transparent); }
.bot-fab.open { animation: none; }
.bot-body { width: 36px; height: 36px; overflow: visible; }
.bot-body .face { fill: rgba(255, 255, 255, .16); stroke: white; stroke-width: 2.2; }
.bot-body .stalk { stroke: white; stroke-width: 2.2; stroke-linecap: round; }
.bot-body .bulb { fill: white; animation: bot-glow 2.4s ease-in-out infinite; }
.bot-body .eye { fill: white; transform-box: fill-box; transform-origin: center; animation: bot-blink 5.2s infinite; }
.bot-body .scan { fill: white; opacity: 0; }
.bot-ring { position: absolute; inset: -4px; border-radius: 50%; opacity: 0; transition: opacity .3s;
  background: conic-gradient(from 0deg, transparent 0 55%, var(--bot-c) 75%, white 82%, transparent 90%);
  -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 3px), black calc(100% - 2px));
  mask: radial-gradient(farthest-side, transparent calc(100% - 3px), black calc(100% - 2px)); }
.bot-fab.asleep { animation-duration: 5.5s; filter: saturate(.75); }
.bot-fab.asleep .eye { animation: none; transform: scaleY(.18); }
.bot-fab.asleep .bulb { animation: none; opacity: .55; }
.bot-z { position: absolute; top: -4px; right: -2px; width: 20px; height: 20px; border-radius: 50%; display: grid; place-items: center;
  background: var(--surface); color: var(--bot-b); font-size: 12px; font-weight: 800; box-shadow: 0 2px 6px rgba(20, 24, 40, .18);
  animation: bot-z 2.6s ease-in-out infinite; }
@keyframes bot-z { 0%, 100% { transform: translateY(0); opacity: 1; } 50% { transform: translateY(-3px); opacity: .6; } }
.bot-connect { padding-bottom: 14px; }
.bot-providers { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.provider { display: flex; flex-direction: column; gap: 2px; padding: 10px 12px; border-radius: 14px; text-decoration: none; color: var(--ink);
  border: 1px solid color-mix(in srgb, var(--bot-b) 30%, var(--line)); background: var(--surface); transition: border-color .15s, transform .15s, background .15s; }
.provider:hover { border-color: var(--bot-b); background: color-mix(in srgb, var(--bot-b) 6%, var(--surface)); transform: translateY(-1px); }
.provider strong { font-size: 13.5px; }
.provider small { color: var(--muted); font-size: 12px; }
.bot-connect > .fine { margin: 2px 2px 0; color: var(--muted); font-size: 12px; line-height: 1.45; }
.again { align-self: flex-start; }
.bot-fab.busy { animation: bot-think 1.2s ease-in-out infinite; }
.bot-fab.busy .bot-ring { opacity: 1; animation: bot-spin 1.1s linear infinite; }
.bot-fab.busy .eyes { opacity: 0; }
.bot-fab.busy .scan { opacity: 1; animation: bot-scan 1.1s ease-in-out infinite; }
.bot-fab.busy .bulb { animation-duration: .6s; }

@keyframes bot-float { 0%, 100% { transform: translateY(0) rotate(0); } 50% { transform: translateY(-5px) rotate(-2deg); } }
@keyframes bot-think { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.05); } }
@keyframes bot-blink { 0%, 92%, 100% { transform: scaleY(1); } 95% { transform: scaleY(.1); } }
@keyframes bot-glow { 0%, 100% { opacity: 1; } 50% { opacity: .45; } }
@keyframes bot-spin { to { transform: rotate(1turn); } }
@keyframes bot-scan { 0%, 100% { transform: translateY(-3px); } 50% { transform: translateY(3px); } }

/* ---- the pages while it thinks: a veil with light sweeping over it, and no edit gets through ---- */
.bot-shine { position: fixed; z-index: 55; cursor: progress; overflow: hidden; border-radius: 6px;
  background: color-mix(in srgb, var(--surface) 38%, transparent); backdrop-filter: saturate(1.15);
  box-shadow: inset 0 0 0 2px color-mix(in srgb, var(--bot-b) 45%, transparent), inset 0 0 60px color-mix(in srgb, var(--bot-a) 22%, transparent); }
.bot-shine-sweep { position: absolute; inset: -50%; animation: bot-sweep 2.2s cubic-bezier(.45, .05, .35, 1) infinite;
  background: linear-gradient(110deg, transparent 38%, color-mix(in srgb, var(--bot-c) 22%, transparent) 46%,
    color-mix(in srgb, white 55%, transparent) 50%, color-mix(in srgb, var(--bot-a) 22%, transparent) 54%, transparent 62%); }
@keyframes bot-sweep { from { transform: translateX(-45%); } to { transform: translateX(45%); } }
.bot-shine-pill { position: absolute; top: 18px; left: 50%; transform: translateX(-50%); display: flex; align-items: center; gap: 10px;
  padding: 8px 8px 8px 14px; border-radius: 999px; background: var(--surface); color: var(--ink); font-size: 13px; font-weight: 550;
  box-shadow: var(--pop-shadow); white-space: nowrap; cursor: default; }
.bot-spark { width: 10px; height: 10px; border-radius: 50%; background: linear-gradient(140deg, var(--bot-a), var(--bot-b));
  box-shadow: 0 0 0 0 color-mix(in srgb, var(--bot-b) 60%, transparent); animation: bot-pulse 1.4s ease-out infinite; }
@keyframes bot-pulse { to { box-shadow: 0 0 0 10px transparent; } }
.bot-secs { color: var(--muted); font-weight: 450; font-variant-numeric: tabular-nums; }
.bot-stop { border: 0; border-radius: 999px; padding: 5px 12px; background: var(--seg); color: var(--ink-2); font: inherit; font-weight: 500; cursor: pointer; }
.bot-stop:hover { background: var(--line); }
.bot-shine-enter-active, .bot-shine-leave-active { transition: opacity .35s; }
.bot-shine-enter-from, .bot-shine-leave-to { opacity: 0; }

/* ---- the chat ---- */
.bot-chat { position: fixed; z-index: 61; right: 24px; bottom: 92px; display: flex; flex-direction: column; max-height: min(600px, calc(100vh - 116px));
  background: var(--surface); color: var(--ink); border-radius: 20px; overflow: hidden;
  box-shadow: 0 24px 64px rgba(20, 24, 40, .22), 0 2px 8px rgba(20, 24, 40, .08), 0 0 0 1px var(--line); transform-origin: 92% 100%; }
.bot-chat-enter-active { transition: opacity .22s, transform .32s cubic-bezier(.2, 1.3, .4, 1); }
.bot-chat-leave-active { transition: opacity .16s, transform .18s ease-in; }
.bot-chat-enter-from, .bot-chat-leave-to { opacity: 0; transform: translateY(14px) scale(.92); }
.bot-head { display: flex; align-items: center; gap: 10px; padding: 12px 10px 12px 14px;
  background: linear-gradient(140deg, color-mix(in srgb, var(--bot-a) 10%, var(--surface)), color-mix(in srgb, var(--bot-b) 12%, var(--surface)));
  border-bottom: 1px solid var(--line); }
.bot-avatar { width: 34px; height: 34px; border-radius: 11px; display: grid; place-items: center; flex: none;
  background: linear-gradient(140deg, var(--bot-a), var(--bot-b)); }
.bot-avatar svg { width: 26px; height: 26px; }
.bot-avatar .face { fill: rgba(255, 255, 255, .16); stroke: white; stroke-width: 2.4; }
.bot-avatar .stalk { stroke: white; stroke-width: 2.4; stroke-linecap: round; }
.bot-avatar .bulb, .bot-avatar .eye { fill: white; }
.bot-avatar .eye { transform-box: fill-box; transform-origin: center; animation: bot-blink 4.6s infinite; }
.bot-avatar.busy .eye { animation: bot-scan 1.1s ease-in-out infinite; }
.bot-title { flex: 1; min-width: 0; display: flex; flex-direction: column; line-height: 1.2; }
.bot-title strong { font-size: 14.5px; font-weight: 650; letter-spacing: -.01em; }
.bot-title small { color: var(--muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bot-agent { margin-top: 2px; max-width: 220px; }

.bot-list { flex: 1; overflow-y: auto; padding: 14px 14px 6px; display: flex; flex-direction: column; gap: 10px; scroll-behavior: smooth; }
.msg { max-width: 86%; padding: 9px 12px; border-radius: 16px; font-size: 13.5px; line-height: 1.45; overflow-wrap: anywhere; }
.msg p { margin: 0; }
.msg.bot { align-self: flex-start; background: var(--surface-2); border: 1px solid var(--line); border-bottom-left-radius: 6px; }
.msg.you { align-self: flex-end; color: white; border-bottom-right-radius: 6px; background: linear-gradient(140deg, var(--bot-a), var(--bot-b)); }
.msg.error { background: var(--danger-soft); border-color: transparent; color: var(--ink); }
.msg .fine { margin-top: 6px; color: var(--muted); font-size: 12px; line-height: 1.4; }
.notes { margin: 6px 0 0; padding-left: 16px; color: var(--ink-2); font-size: 12.5px; }
.msg-actions { display: flex; gap: 6px; margin-top: 8px; align-items: center; flex-wrap: wrap; }
.chip { display: inline-flex; align-items: center; gap: 5px; border: 1px solid var(--line); background: var(--surface); color: var(--ink-2);
  border-radius: 999px; padding: 4px 10px 4px 8px; font: inherit; font-size: 12.5px; font-weight: 550; cursor: pointer; }
.chip:hover { border-color: var(--line-strong); color: var(--ink); }
.undone { color: var(--muted); font-size: 12.5px; }
.elsewhere { list-style: none; margin: 8px 0 0; padding: 0; display: flex; flex-direction: column; gap: 4px; font-size: 12.5px; color: var(--ink-2); }
.elsewhere li { display: flex; gap: 6px; align-items: flex-start; }
.elsewhere li :deep(.ui-icon) { color: var(--bot-b); margin-top: 1px; }
.msg.send { border-color: color-mix(in srgb, var(--bot-b) 35%, var(--line)); background: color-mix(in srgb, var(--bot-b) 6%, var(--surface)); }
.send-yes { border: 0; border-radius: 999px; padding: 6px 14px; font: inherit; font-size: 13px; font-weight: 600; color: white; cursor: pointer;
  background: linear-gradient(140deg, var(--bot-a), var(--bot-b)); box-shadow: 0 4px 12px color-mix(in srgb, var(--bot-b) 30%, transparent);
  transition: transform .15s; }
.send-yes:hover { transform: translateY(-1px); }
.send-yes:disabled { opacity: .5; cursor: default; transform: none; }
.send-state { display: flex; align-items: center; gap: 8px; color: var(--ink-2); }
.send-state.ok { color: var(--good); font-weight: 550; }
.msg-enter-active { transition: opacity .25s, transform .3s cubic-bezier(.2, 1.2, .4, 1); }
.msg-enter-from { opacity: 0; transform: translateY(8px) scale(.97); }

.bot-suggest { display: flex; flex-direction: column; gap: 6px; align-items: flex-start; }
.bot-suggest button { text-align: left; border: 1px solid color-mix(in srgb, var(--bot-b) 30%, var(--line)); background: var(--surface);
  color: var(--ink); border-radius: 14px; padding: 8px 12px; font: inherit; font-size: 13px; cursor: pointer;
  transition: background .15s, border-color .15s, transform .15s; }
.bot-suggest button:hover { background: color-mix(in srgb, var(--bot-b) 8%, var(--surface)); border-color: var(--bot-b); transform: translateX(2px); }

.typing { display: flex; gap: 4px; padding: 12px 14px; }
.typing i { width: 7px; height: 7px; border-radius: 50%; background: var(--muted); animation: bot-dot 1.2s infinite ease-in-out; }
.typing i:nth-child(2) { animation-delay: .15s; }
.typing i:nth-child(3) { animation-delay: .3s; }
@keyframes bot-dot { 0%, 60%, 100% { transform: translateY(0); opacity: .45; } 30% { transform: translateY(-4px); opacity: 1; } }

.bot-compose { display: flex; align-items: flex-end; gap: 8px; margin: 8px 10px 10px; padding: 6px 6px 6px 12px; border-radius: 16px;
  border: 1px solid var(--line-strong); background: var(--surface); transition: border-color .15s, box-shadow .15s; }
.bot-compose:focus-within { border-color: var(--bot-b); box-shadow: 0 0 0 3px color-mix(in srgb, var(--bot-b) 16%, transparent); }
.bot-compose textarea, .bot-compose textarea:hover, .bot-compose textarea:focus-visible { flex: 1; resize: none; border: 0; outline: 0;
  box-shadow: none; border-radius: 0; min-height: 0; width: auto; background: transparent; color: var(--ink); font: inherit;
  font-size: 13.5px; line-height: 1.4; padding: 6px 0; max-height: 120px; }
.bot-send { width: 32px; height: 32px; flex: none; border: 0; border-radius: 11px; display: grid; place-items: center; cursor: pointer;
  color: white; background: linear-gradient(140deg, var(--bot-a), var(--bot-b)); transition: opacity .15s, transform .15s; }
.bot-send:disabled { opacity: .35; cursor: default; }
.bot-send:not(:disabled):hover { transform: translateY(-1px); }

@media (prefers-reduced-motion: reduce) {
  .bot-fab, .bot-fab.busy, .bot-body .eye, .bot-body .bulb, .bot-ring, .bot-shine-sweep, .bot-spark, .bot-avatar .eye, .typing i { animation: none !important; }
  .bot-shine-sweep { display: none; }
}
</style>
