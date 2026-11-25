<script setup lang="ts">
// Where the screen's USB cable goes, drawn (app 0.4.103): this computer, a laptop with the editor open on it, or the
// machine Home Assistant runs on, a small box with Home Assistant's mark, each with a cable to the chosen screen in its
// own proportions. The two are drawn alike, so they read as the two answers to one question; the chosen one's cable
// carries a slow pulse towards the screen. Colours come from the editor's tokens (styles/tokens.css).
import { computed } from "vue";
import DeviceArt from "../DeviceArt.vue";
import Icon from "../ui/Icon.vue";

const props = defineProps<{ kind: "here" | "ha"; width: number; height: number; chosen?: boolean }>();
// The cable from this computer's side, or the box's back, to the screen's plug; the screen itself is the same drawing
// as everywhere in New screen (DeviceArt), laid over the right of the picture.
const cable = computed(() => (props.kind === "here" ? "M160 104 C 182 104, 172 66, 196 66" : "M142 70 C 160 70, 170 66, 196 66"));
</script>

<template>
  <div class="cable-art" :class="[kind, { chosen }]" aria-hidden="true">
    <svg viewBox="0 0 264 132" fill="none">
      <template v-if="kind === 'here'">
        <!-- The laptop: its lid with the editor open, and the deck it stands on. -->
        <rect x="20" y="14" width="132" height="86" rx="9" class="ca-body" />
        <rect x="28" y="22" width="116" height="70" rx="3.5" class="ca-glass" />
        <rect x="32" y="26" width="24" height="62" rx="2.5" class="ca-side" />
        <rect x="62" y="28" width="36" height="22" rx="3" class="ca-card" />
        <rect x="102" y="28" width="38" height="22" rx="3" class="ca-card" />
        <rect x="62" y="54" width="36" height="22" rx="3" class="ca-card" />
        <rect x="102" y="54" width="38" height="22" rx="3" class="ca-card" />
        <circle cx="68" cy="34" r="2.2" class="ca-dot a" /><circle cx="108" cy="34" r="2.2" class="ca-dot b" />
        <circle cx="68" cy="60" r="2.2" class="ca-dot c" /><circle cx="108" cy="60" r="2.2" class="ca-dot d" />
        <path d="M8 102 H164 L158 112 Q157 114 154 114 H18 Q15 114 14 112 Z" class="ca-body" />
        <rect x="72" y="102" width="28" height="3" rx="1.5" class="ca-notch" />
      </template>
      <template v-else>
        <!-- The Home Assistant machine: a small box with its mark (laid over the drawing) and a light that is on. -->
        <rect x="24" y="24" width="118" height="92" rx="24" class="ca-body" />
        <rect x="32" y="30" width="102" height="72" rx="18" class="ca-top" />
        <circle cx="126" cy="106" r="2.6" class="ca-led" />
      </template>
      <path :d="cable" class="ca-cable" />
      <path :d="cable" class="ca-pulse" />
      <rect x="194" y="63" width="7" height="6" rx="1.5" class="ca-plug" />
    </svg>
    <span v-if="kind === 'ha'" class="ca-mark"><Icon name="home-assistant" /></span>
    <span class="ca-screen"><DeviceArt :width="width" :height="height" :columns="width >= height ? 3 : 2" :rows="width >= height ? 2 : 3" /></span>
  </div>
</template>

<style scoped>
.cable-art { position: relative; width: 100%; max-width: 264px; aspect-ratio: 2; }
.cable-art svg { display: block; width: 100%; height: 100%; overflow: visible; }
.ca-body { fill: var(--surface); stroke: var(--ink-2); stroke-width: 2.4; stroke-linejoin: round; }
.ca-glass { fill: var(--surface-2); }
.ca-side { fill: var(--surface); }
.ca-card { fill: var(--surface); }
.ca-dot.a { fill: var(--tile-amber); } .ca-dot.b { fill: var(--tile-blue); } .ca-dot.c { fill: var(--tile-purple); } .ca-dot.d { fill: var(--tile-green); }
.ca-notch { fill: var(--line-strong); }
.ca-top { fill: var(--surface-2); }
.ca-led { fill: var(--good); }
.ca-mark { position: absolute; left: 31.4%; top: 50%; translate: -50% -50%; font-size: clamp(30px, 17cqw, 46px); line-height: 1; color: var(--brand-ha); }
.cable-art { container-type: inline-size; }
.ca-cable { stroke: var(--line-strong); stroke-width: 3; stroke-linecap: round; }
.ca-pulse { stroke: var(--accent); stroke-width: 3; stroke-linecap: round; stroke-dasharray: 10 140; opacity: 0; }
.chosen .ca-cable { stroke: color-mix(in srgb, var(--accent) 45%, var(--line-strong)); }
.chosen .ca-pulse { opacity: 1; animation: ca-pulse 2.2s cubic-bezier(0.4, 0, 0.2, 1) infinite; }
@keyframes ca-pulse { from { stroke-dashoffset: 150; } to { stroke-dashoffset: 0; } }
.ca-plug { fill: var(--ink-2); }
.ca-screen { position: absolute; left: 76.5%; right: 0; top: 50%; translate: 0 -50%; height: 52%; display: grid; place-items: center; }
.ca-screen :deep(.device-art) { width: 100%; height: 100%; filter: drop-shadow(0 6px 10px rgba(16, 17, 18, 0.18)); }
@media (prefers-reduced-motion: reduce) { .chosen .ca-pulse { animation: none; opacity: 0; } }
</style>
