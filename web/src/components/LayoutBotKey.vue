<script setup lang="ts">
// Layoutbot's key (docs/LAYOUTBOT.md): the small bot that opens its chat. On a wider page it floats in the window's lower
// right corner, as a chat does; on a phone it stands in the phone's dock beside Add tile (`docked`, ScreenView.vue), so
// it never covers the page. Without an AI Task it sleeps (its z), and its chat says how to connect one; while it thinks
// its face scans.
import { t } from "../i18n";
import { useLayoutbotStore } from "../stores/layoutbot";

defineProps<{ docked?: boolean }>();
const bot = useLayoutbotStore();
function toggle() { bot.open = !bot.open; }
</script>

<template>
  <button type="button" class="bot-fab" :class="{ docked, busy: bot.busy, open: bot.open, asleep: !bot.ready }"
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
/* In the phone's dock: as tall as its buttons, still, and its chat is a sheet. */
.bot-fab.docked { position: static; flex: 0 0 50px; width: 50px; height: 50px; border-radius: 14px; animation: none; }
.bot-fab.docked:hover { transform: none; }
.bot-fab.docked .bot-ring { border-radius: 16px; }
.bot-fab.docked.busy { animation: none; }
@media (prefers-reduced-motion: reduce) {
  .bot-fab, .bot-fab.busy, .bot-body .eye, .bot-body .bulb, .bot-ring, .bot-z { animation: none !important; }
}
</style>
