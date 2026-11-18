<script setup lang="ts">
// Layoutbot's chat (docs/LAYOUTBOT.md): its head, the conversation, the choice of this screen or all, and the field. It
// stands in a window over the corner of a wider page and in a sheet on a phone (LayoutBot.vue chooses), the same in
// both. Without an AI Task it says how to connect one.
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useStickToBottom } from "../composables/useStickToBottom";
import { editorLanguage, t } from "../i18n";
import { useInventoryStore } from "../stores/inventory";
import { useLayoutbotStore, type Elsewhere } from "../stores/layoutbot";
import { useScreenStore } from "../stores/screen";
import Icon from "./ui/Icon.vue";
import UiSelect from "./ui/UiSelect.vue";
import Segmented from "./Segmented.vue";

// On a phone the field takes no focus by itself (that would raise the keyboard over the conversation) and is 16 px, so
// focusing it never zooms the page.
const props = defineProps<{ phone?: boolean }>();
const bot = useLayoutbotStore();
const scr = useScreenStore();
const inv = useInventoryStore();

const draft = ref("");
const field = ref<HTMLTextAreaElement | null>(null);
const list = ref<HTMLElement | null>(null);
useStickToBottom(list, () => bot.messages.length + (bot.busy ? 1 : 0));
// A new message grows into place (its enter transition): follow it to the end once it stands.
watch(() => bot.messages.length, () => setTimeout(() => list.value?.scrollTo?.({ top: list.value.scrollHeight, behavior: "smooth" }), 340));
const focus = () => { if (!props.phone) nextTick(() => field.value?.focus()); };
// The field in view once the keyboard is up. The sheet stands on the keyboard where the page learns of it (UiSheet, the
// visual viewport), but inside Home Assistant's frame (its Companion app) the frame may never hear of the keyboard: the
// browser is asked as well to bring the field into view, through the frame, as it does for any field.
const compose = ref<HTMLFormElement | null>(null);
function inView() {
  if (!props.phone) return;
  for (const ms of [320, 700]) setTimeout(() => compose.value?.scrollIntoView?.({ block: "nearest" }), ms);
}
onMounted(focus);
watch(() => bot.busy, (busy) => { if (!busy) focus(); });

const sections = computed(() => Boolean(scr.currentScreen?.sections));
const suggestions = computed(() => (sections.value
  ? ["lights_sections", "covers_sections", "media", "climate"]
  : ["lights", "covers", "media", "climate"]).map((key) => t(`editor.layoutbot.suggest.${key}`)));

function submit(text = draft.value) {
  if (!text.trim() || bot.busy) return;
  draft.value = "";
  void bot.ask(text);
}
function restructure(scope: "page" | "screen") {
  if (bot.busy) return;
  const words = draft.value;
  draft.value = "";
  void bot.restructure(scope, words);
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
// "This screen" or "All screens", where there is another screen with pages to change.
const otherScreens = computed(() => inv.inventory.screens.some((screen) => screen.id !== scr.selected && screen.page_document?.format === "pages-v2"));
const scopes = computed(() => [[false, t("editor.layoutbot.scope.here")], [true, t("editor.layoutbot.scope.all")]] as const);
const agentChoices = computed(() => bot.agents.map((agent) => [agent.id, agent.name] as const));
</script>

<template>
  <div class="bot-chat-body" :class="{ phone }">
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
        <!-- The model is the AI Task's setting in Home Assistant, never the question's: the advice where to choose it. -->
        <p class="fine model-hint">{{ t("editor.layoutbot.model_hint") }} <a href="/_my_redirect/integrations" target="_top">{{ t("editor.layoutbot.model_link") }}</a></p>
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
              <li v-for="other in message.elsewhere" :key="other.id" :class="other.sent">
                <Icon :name="other.sent === 'sent' ? 'check' : 'monitor-eye'" />
                <span><b>{{ other.name }}</b> {{ [other.error, whatOf(other), ...(other.notes ?? []), other.sent === "failed" ? other.why : ""].filter(Boolean).join(" ") }}
                  <em v-if="other.sent === 'sending'">{{ t("editor.layoutbot.send.sending") }}</em></span>
                <button v-if="other.layout && !other.sent && message.send === 'ask'" type="button" class="chip mini" :disabled="bot.busy" @click="bot.preview(other)">{{ t("editor.layoutbot.preview") }}</button>
              </li>
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
              <p v-if="message.own && !message.undone" class="fine">{{ t("editor.layoutbot.send.own") }}</p>
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

    <!-- Restructuring the person's own tiles (docs/LAYOUTBOT.md, "Restructuring"): this page, or the whole screen. Words in
         the field go along and steer the grouping. -->
    <div v-if="bot.ready" class="bot-tidy">
      <button type="button" class="chip" data-restructure="page" :disabled="bot.busy || !bot.canRestructure('page')" @click="restructure('page')"><Icon name="auto-fix" />{{ t("editor.layoutbot.restructure.page") }}</button>
      <button type="button" class="chip" data-restructure="screen" :disabled="bot.busy || !bot.canRestructure('screen')" @click="restructure('screen')"><Icon name="auto-fix" />{{ t("editor.layoutbot.restructure.screen") }}</button>
    </div>
    <!-- Other screens only when the person chooses them (the add-on's layoutbot.answered holds to it). -->
    <Segmented v-if="bot.ready && otherScreens" class="bot-scope" :choices="scopes" :value="bot.allScreens" :disabled="bot.busy" @pick="bot.allScreens = $event" />
    <form v-if="bot.ready" ref="compose" class="bot-compose" @submit.prevent="submit()">
      <textarea ref="field" v-model="draft" rows="1" :disabled="bot.busy" :placeholder="t('editor.layoutbot.placeholder')" maxlength="500" @keydown="onKey" @focus="inView"></textarea>
      <button type="submit" class="bot-send" :disabled="bot.busy || !draft.trim()" :aria-label="t('editor.layoutbot.ask')"><Icon name="arrow-up" /></button>
    </form>
  </div>
</template>

<style scoped>
.bot-chat-body { flex: 1; min-height: 0; display: flex; flex-direction: column; }
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
.elsewhere li.sent :deep(.ui-icon) { color: var(--good); }
.elsewhere li.failed { color: var(--danger); }
.elsewhere li > span:not(.ui-icon) { flex: 1; }
.elsewhere li > .ui-icon { flex: none; }
.elsewhere em { font-style: normal; color: var(--muted); margin-left: 4px; }
.chip.mini { padding: 2px 8px; font-size: 12px; flex: none; }
.bot-scope { margin: 6px 10px 0; align-self: flex-start; }
.bot-tidy { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 10px 0; }
.bot-tidy .chip:disabled { opacity: .5; cursor: default; }
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
.bot-connect { padding-bottom: 14px; }
.bot-providers { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.provider { display: flex; flex-direction: column; gap: 2px; padding: 10px 12px; border-radius: 14px; text-decoration: none; color: var(--ink);
  border: 1px solid color-mix(in srgb, var(--bot-b) 30%, var(--line)); background: var(--surface); transition: border-color .15s, transform .15s, background .15s; }
.provider:hover { border-color: var(--bot-b); background: color-mix(in srgb, var(--bot-b) 6%, var(--surface)); transform: translateY(-1px); }
.provider strong { font-size: 13.5px; }
.provider small { color: var(--muted); font-size: 12px; }
.bot-connect > .fine { margin: 2px 2px 0; color: var(--muted); font-size: 12px; line-height: 1.45; }
.again { align-self: flex-start; }
@keyframes bot-blink { 0%, 92%, 100% { transform: scaleY(1); } 95% { transform: scaleY(.1); } }
@keyframes bot-scan { 0%, 100% { transform: translateY(-3px); } 50% { transform: translateY(3px); } }
.bot-spark { width: 10px; height: 10px; border-radius: 50%; background: linear-gradient(140deg, var(--bot-a), var(--bot-b));
  box-shadow: 0 0 0 0 color-mix(in srgb, var(--bot-b) 60%, transparent); animation: bot-pulse 1.4s ease-out infinite; flex: none; }
@keyframes bot-pulse { to { box-shadow: 0 0 0 10px transparent; } }

/* On a phone: the sheet's own head is the grab, the letters a little larger, the field 16 px (no zoom on focus), and
   every button a thumb's size. */
.phone .bot-head { background: none; border-bottom: 0; padding: 2px 10px 8px 16px; }
.phone .msg { font-size: 15px; }
.phone .msg .fine, .phone .notes { font-size: 13px; }
.phone .bot-compose { margin: 6px 12px 10px; }
.phone .bot-compose textarea, .phone .bot-compose textarea:hover, .phone .bot-compose textarea:focus-visible { font-size: 16px; }
.phone .bot-send { width: 40px; height: 40px; border-radius: 13px; }
.phone .chip { min-height: 36px; padding: 6px 13px 6px 10px; font-size: 14px; }
.phone .chip.mini { min-height: 32px; padding: 4px 11px; font-size: 13px; }
.phone .send-yes { min-height: 40px; padding: 8px 20px; font-size: 15px; }
.phone .bot-suggest button { font-size: 15px; padding: 10px 14px; }
.phone .bot-scope { margin: 4px 12px 0; }
@media (prefers-reduced-motion: reduce) { .bot-spark, .bot-avatar .eye, .typing i { animation: none !important; } }
</style>
