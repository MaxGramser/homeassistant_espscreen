<script setup lang="ts">
// Layoutbot (docs/LAYOUTBOT.md): a small bot that opens a chat. On a wider page it floats over the corner of the pages
// and its chat opens above it; on a phone its key stands in the phone's dock (LayoutBotKey in ScreenView.vue) and its chat
// is a sheet from the bottom (UiSheet), which lowers while it thinks and while its question waits, so the page above
// shows what it did. Whether the chat is open is the address's (`?chat=layoutbot`, ui.openChat). While it thinks, the
// pages shine and take no edit, and the bot's face scans; its answer lands on the pages as one step of undo, which the
// chat can take back.
import { useElementBounding } from "@vueuse/core";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { t } from "../i18n";
import { useLayoutbotStore } from "../stores/layoutbot";
import { useUiStore } from "../stores/ui";
import LayoutBotChat from "./LayoutBotChat.vue";
import LayoutBotKey from "./LayoutBotKey.vue";
import UiSheet from "./ui/UiSheet.vue";

const bot = useLayoutbotStore();
const ui = useUiStore();
const canvas = ref<HTMLElement | null>(null);
onMounted(() => { canvas.value = document.getElementById("canvas"); });
const box = useElementBounding(canvas);
const canvasBox = computed(() => ({ left: `${box.left.value}px`, top: `${box.top.value}px`, width: `${box.width.value}px`, height: `${box.height.value}px` }));
// The bot stands in the window's lower right corner, as a chat does, and the chat opens above it with the window's
// height; the shine covers the pages (#canvas) wherever they are.
const chatWidth = computed(() => Math.min(380, window.innerWidth - 24));
// On a phone the sheet rests low while the bot thinks or sends, and while its question (send it?) waits for an answer.
const low = computed(() => Boolean(bot.busy || bot.delivering || bot.messages.at(-1)?.send === "ask"));

// While it thinks the pages take no edit: no key reaches the editor but Escape, which stops waiting.
function guard(event: KeyboardEvent) {
  if (!bot.busy) return;
  if (event.key === "Escape") { event.preventDefault(); bot.stop(); return; }
  if ((event.target as HTMLElement | null)?.closest?.(".bot-chat-body")) return;
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
});
onBeforeUnmount(() => clearInterval(timer));
const elapsed = computed(() => Math.max(0, Math.floor((now.value - bot.started) / 1000)));
</script>

<template>
  <Teleport v-if="bot.shown" to="body">
    <Transition name="bot-shine">
      <div v-if="bot.busy || bot.delivering" class="bot-shine" :style="canvasBox" @pointerdown.stop.prevent @click.stop.prevent @wheel.prevent>
        <div class="bot-shine-sweep" aria-hidden="true"></div>
        <div class="bot-shine-pill" role="status" aria-live="polite">
          <span class="bot-spark" aria-hidden="true"></span>
          <span>{{ bot.delivering ? t("editor.layoutbot.send.to", { name: bot.delivering }) : t("editor.layoutbot.busy") }}</span>
          <span class="bot-secs">{{ t("editor.layoutbot.seconds", { n: elapsed }) }}</span>
          <button type="button" class="bot-stop" @click="bot.stop()">{{ t("editor.layoutbot.stop") }}</button>
        </div>
      </div>
    </Transition>

    <UiSheet v-if="ui.phone" :open="bot.open" :title="t('editor.layoutbot.name')" :low="low" @update:open="bot.open = $event">
      <LayoutBotChat phone />
    </UiSheet>
    <template v-else>
      <Transition name="bot-chat">
        <section v-if="bot.open" class="bot-chat" :style="{ width: `${chatWidth}px` }" role="dialog" :aria-label="t('editor.layoutbot.name')">
          <LayoutBotChat />
        </section>
      </Transition>
      <LayoutBotKey />
    </template>
  </Teleport>
</template>

<style scoped>
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

/* ---- the chat's window on a wider page ---- */
.bot-chat { position: fixed; z-index: 61; right: 24px; bottom: 92px; display: flex; flex-direction: column; max-height: min(600px, calc(100vh - 116px));
  background: var(--surface); color: var(--ink); border-radius: 20px; overflow: hidden;
  box-shadow: 0 24px 64px rgba(20, 24, 40, .22), 0 2px 8px rgba(20, 24, 40, .08), 0 0 0 1px var(--line); transform-origin: 92% 100%; }
.bot-chat-enter-active { transition: opacity .22s, transform .32s cubic-bezier(.2, 1.3, .4, 1); }
.bot-chat-leave-active { transition: opacity .16s, transform .18s ease-in; }
.bot-chat-enter-from, .bot-chat-leave-to { opacity: 0; transform: translateY(14px) scale(.92); }

@media (prefers-reduced-motion: reduce) {
  .bot-shine-sweep, .bot-spark { animation: none !important; }
  .bot-shine-sweep { display: none; }
}
</style>
