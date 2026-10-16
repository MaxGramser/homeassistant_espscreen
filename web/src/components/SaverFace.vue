<script setup lang="ts">
// One of the screensaver clock's faces in miniature (app: Screensaver, Clock), in the glass's own proportions and drawn
// by the firmware's rules (model/clock-faces.ts): Glass, Classic or Bauhaus. Its letters are the browser's, so only the
// places, the sizes and the colours are the screen's.
import { computed } from "vue";
import { bauhaus, faceInk, ringEdge, type SaverFaceKind } from "../model/clock-faces";

const props = defineProps<{
  kind: Exclude<SaverFaceKind, "digital">; dark: boolean; numerals: number; seconds: boolean; width: number; height: number; at: Date;
  /** Classic's day beside or under its dial, in the screen's words. */
  weekday?: string; day?: number; month?: string; short?: string;
}>();

const W = computed(() => props.width), H = computed(() => props.height), S = computed(() => Math.min(props.width, props.height));
const k = computed(() => faceInk(props.dark));
const hourA = computed(() => ((props.at.getHours() % 12) + props.at.getMinutes() / 60) * (Math.PI / 6));
const minuteA = computed(() => props.at.getMinutes() * (Math.PI / 30));
const secondA = computed(() => props.at.getSeconds() * (Math.PI / 30));
const ray = (cx: number, cy: number, a: number, from: number, to: number) =>
  ({ x1: cx + Math.sin(a) * from, y1: cy - Math.cos(a) * from, x2: cx + Math.sin(a) * to, y2: cy - Math.cos(a) * to });

// The hands of Glass and Classic: a stem, then a capsule, a dark rim on a pale face, and the seconds in orange.
function handsOf(cx: number, cy: number, hour: number, minute: number, second: number, tail: number, blade: number) {
  const out: { x1: number; y1: number; x2: number; y2: number; w: number; c: string }[] = [];
  const rim = props.dark ? 0 : Math.max(1, blade / 7);
  for (const [a, len] of [[hourA.value, hour], [minuteA.value, minute]] as const) {
    const stem = Math.max(S.value * 0.012, len * 0.16);
    if (rim) out.push({ ...ray(cx, cy, a, 0, stem), w: blade / 3 + 2 * rim, c: k.value.edge }, { ...ray(cx, cy, a, stem, len), w: blade + 2 * rim, c: k.value.edge });
    out.push({ ...ray(cx, cy, a, 0, stem), w: blade / 3, c: k.value.hand }, { ...ray(cx, cy, a, stem, len), w: blade, c: k.value.hand });
  }
  if (props.seconds) out.push({ ...ray(cx, cy, secondA.value, -tail, second), w: Math.max(1, S.value * 0.0055), c: k.value.accent });
  return { lines: out, cx, cy, r: blade * 0.62, rim };
}

// ---- Glass
const glass = computed(() => {
  const s = S.value, cx = W.value / 2, cy = H.value / 2, m = s * 0.03, hx = cx - m, hy = cy - m;
  const major = s * 0.075, minor = s * 0.034, n = props.numerals;
  const ticks: { x1: number; y1: number; x2: number; y2: number; w: number; c: string }[] = [];
  for (let i = 0; i < 60; i++) {
    const hour = i % 5 === 0, num = i / 5 || 12;
    if (hour && n && (n === 12 || num % 3 === 0)) continue;
    const a = (i * Math.PI) / 30, e = ringEdge(a, hx, hy);
    ticks.push({ ...ray(cx, cy, a, e, e - (hour ? major : minor)), w: hour ? s * 0.0095 : s * 0.0042, c: hour ? k.value.tick : k.value.minor });
  }
  // The numerals: their digits a share of the short side, moved in until no tick comes within a clear gap.
  const digitH = s * (n === 4 ? 0.13 : 0.085), size = digitH / 0.72, air = s * 0.012;
  const numerals: { x: number; y: number; text: string }[] = [];
  if (n) for (let num = 1; num <= 12; num++) {
    if (n === 4 && num % 3) continue;
    const a = (num * Math.PI) / 6, dx = Math.sin(a), dy = -Math.cos(a), e = ringEdge(a, hx, hy), w = String(num).length * size * 0.56;
    let d = e - minor - air - (Math.abs(dx) * w) / 2 - (Math.abs(dy) * digitH) / 2;
    const hits = (x: number, y: number) => ticks.some((t) => [0, 0.25, 0.5, 0.75, 1].some((f) => {
      const px = t.x1 + (t.x2 - t.x1) * f, py = t.y1 + (t.y2 - t.y1) * f, g = air + t.w / 2;
      return px >= x - w / 2 - g && px <= x + w / 2 + g && py >= y - digitH / 2 - g && py <= y + digitH / 2 + g;
    }));
    while (d > 0 && hits(cx + dx * d, cy + dy * d)) d -= s * 0.004;
    numerals.push({ x: cx + dx * d, y: cy + dy * d, text: String(num) });
  }
  const inner = Math.min(hx, hy), blade = Math.max(3, s * 0.036);
  return { ticks, numerals, size, hands: handsOf(cx, cy, inner * 0.62, inner - major * 0.35, inner - minor * 0.4, s * 0.06, blade) };
});

// ---- Classic
const classic = computed(() => {
  const s = S.value, w = W.value, h = H.value, m = s * 0.05, D = s - 2 * m, R = D / 2;
  const side = w >= h * 1.3, under = h >= w * 1.3;
  const group = side ? D + Math.max(m, w * 0.05) + w * 0.24 : D;
  const cx = side ? Math.max(m, (w - group) / 2) + R : w / 2, cy = under ? Math.max(m, (h - (D + h * 0.25)) / 2) + R : h / 2;
  const ro = R * 0.94, major = R * 0.09, minor = R * 0.045;
  const ticks = Array.from({ length: 60 }, (_, i) => {
    const hour = i % 5 === 0, a = (i * Math.PI) / 30;
    return { ...ray(cx, cy, a, ro, ro - (hour ? major : minor)), w: hour ? R * 0.022 : R * 0.008, c: hour ? k.value.tick : k.value.minor };
  });
  const digitH = R * 0.15, size = digitH / 0.72, inset = ro - major - R * 0.07, window = !side && !under;
  const numerals = Array.from({ length: 12 }, (_, i) => i + 1).filter((n) => !(window && n === 3)).map((n) => {
    const a = (n * Math.PI) / 6, dx = Math.sin(a), dy = -Math.cos(a), wd = String(n).length * size * 0.56;
    const d = inset - (Math.abs(dx) * wd) / 2 - (Math.abs(dy) * digitH) / 2;
    return { x: cx + dx * d, y: cy + dy * d, text: String(n) };
  });
  const blade = Math.max(3, R * 0.055);
  return { cx, cy, R, ticks, numerals, size, side, under, window, inset,
    hands: handsOf(cx, cy, R * 0.48, R * 0.78, R * 0.86, R * 0.14, blade) };
});

// ---- Bauhaus
const art = computed(() => bauhaus(W.value, H.value, props.at, props.dark));
</script>

<template>
  <svg class="saver-face" :viewBox="`0 0 ${W} ${H}`" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
    <rect :width="W" :height="H" :fill="kind === 'bauhaus' ? art.squares[0]?.ground : k.face" />
    <template v-if="kind === 'glass'">
      <line v-for="(t, i) in glass.ticks" :key="i" v-bind="t" :stroke="t.c" :stroke-width="t.w" />
      <text v-for="n in glass.numerals" :key="n.text" :x="n.x" :y="n.y" :font-size="glass.size" :fill="k.ink" text-anchor="middle" dominant-baseline="central">{{ n.text }}</text>
      <line v-for="(l, i) in glass.hands.lines" :key="`h${i}`" v-bind="l" :stroke="l.c" :stroke-width="l.w" stroke-linecap="round" />
      <circle v-if="glass.hands.rim" :cx="glass.hands.cx" :cy="glass.hands.cy" :r="glass.hands.r + glass.hands.rim" :fill="k.edge" />
      <circle :cx="glass.hands.cx" :cy="glass.hands.cy" :r="glass.hands.r" :fill="seconds ? k.accent : k.hand" />
    </template>
    <template v-else-if="kind === 'classic'">
      <circle :cx="classic.cx" :cy="classic.cy" :r="classic.R" :fill="k.raised" />
      <line v-for="(t, i) in classic.ticks" :key="i" v-bind="t" :stroke="t.c" :stroke-width="t.w" />
      <text v-for="n in classic.numerals" :key="n.text" :x="n.x" :y="n.y" :font-size="classic.size" :fill="k.ink" text-anchor="middle" dominant-baseline="central">{{ n.text }}</text>
      <g v-if="classic.window && short">
        <rect :x="classic.cx + classic.inset - classic.R * 0.42" :y="classic.cy - classic.R * 0.08" :width="classic.R * 0.42" :height="classic.R * 0.16"
          :rx="classic.R * 0.02" :fill="k.face" :stroke="k.minor" :stroke-width="Math.max(1, classic.R * 0.008)" />
        <text :x="classic.cx + classic.inset - classic.R * 0.21" :y="classic.cy" :font-size="classic.R * 0.1" font-weight="700" text-anchor="middle" dominant-baseline="central">
          <tspan :fill="k.soft">{{ short }} </tspan><tspan :fill="k.accent">{{ day }}</tspan></text>
      </g>
      <g v-if="classic.side && weekday" :transform="`translate(${classic.cx + classic.R + Math.max(S * 0.05, W * 0.05)} ${H / 2})`">
        <text :y="-S * 0.2" :font-size="S * 0.07" font-weight="600" :fill="k.accent">{{ weekday }}</text>
        <text :y="S * 0.08" :font-size="S * 0.3" :fill="k.ink">{{ day }}</text>
        <text :y="S * 0.2" :font-size="S * 0.07" font-weight="600" :fill="k.soft">{{ month }}</text>
      </g>
      <g v-else-if="classic.under && weekday" :transform="`translate(${W / 2} ${classic.cy + classic.R + S * 0.25})`">
        <text text-anchor="end" :x="-S * 0.02" :font-size="S * 0.22" :fill="k.ink">{{ day }}</text>
        <text :x="S * 0.02" :y="-S * 0.07" :font-size="S * 0.07" font-weight="600" :fill="k.accent">{{ weekday }}</text>
        <text :x="S * 0.02" :y="S * 0.01" :font-size="S * 0.07" font-weight="600" :fill="k.soft">{{ month }}</text>
      </g>
      <line v-for="(l, i) in classic.hands.lines" :key="`h${i}`" v-bind="l" :stroke="l.c" :stroke-width="l.w" stroke-linecap="round" />
      <circle v-if="classic.hands.rim" :cx="classic.hands.cx" :cy="classic.hands.cy" :r="classic.hands.r + classic.hands.rim" :fill="k.edge" />
      <circle :cx="classic.hands.cx" :cy="classic.hands.cy" :r="classic.hands.r" :fill="seconds ? k.accent : k.hand" />
    </template>
    <template v-else>
      <svg v-for="(q, i) in art.squares" :key="i" :x="q.x" :y="q.y" :width="q.w" :height="q.h">
        <rect :width="q.w" :height="q.h" :fill="q.ground" />
        <circle v-if="q.shape === 0" :cx="q.w / 2" :cy="q.h / 2" :r="Math.min(q.w, q.h) * 0.375" :fill="q.fig" />
        <circle v-else-if="q.shape === 1" :cx="q.extra & 1 ? q.w : 0" :cy="q.extra & 2 ? q.h : 0" :r="Math.min(q.w, q.h)" :fill="q.fig" />
        <circle v-else-if="q.shape === 2" :cx="q.w / 2" :cy="q.extra ? 0 : q.h" :r="Math.min(q.w, q.h) / 2" :fill="q.fig" />
        <rect v-else-if="q.shape === 3" :width="q.w / 2" :height="q.h" :fill="q.fig" />
        <g v-else><rect v-for="s in 3" :key="s" :y="((s - 1) * q.h) / 3 + q.h / 12" :width="q.w" :height="q.h / 6" :fill="q.fig" /></g>
      </svg>
      <circle :cx="art.cx" :cy="art.cy" :r="art.r - art.r * 0.0175" :fill="art.dial" :stroke="art.hand" :stroke-width="art.r * 0.035" />
      <circle v-for="i in 12" :key="`d${i}`" :cx="art.cx + Math.sin((i * Math.PI) / 6) * art.r * 0.84" :cy="art.cy - Math.cos((i * Math.PI) / 6) * art.r * 0.84"
        :r="i % 3 ? art.r * 0.025 : art.r * 0.05" :fill="i % 3 ? art.hand : art.red" />
      <line v-bind="ray(art.cx, art.cy, hourA, 0, art.r * 0.48)" :stroke="art.hand" :stroke-width="art.r * 0.09" stroke-linecap="round" />
      <line v-bind="ray(art.cx, art.cy, minuteA, 0, art.r * 0.72)" :stroke="art.hand" :stroke-width="art.r * 0.06" stroke-linecap="round" />
      <line v-if="seconds" v-bind="ray(art.cx, art.cy, secondA, 0, art.r * 0.78)" :stroke="art.red" :stroke-width="art.r * 0.022" stroke-linecap="round" />
      <circle :cx="art.cx" :cy="art.cy" :r="art.r * 0.07" :fill="art.red" />
    </template>
  </svg>
</template>

<style scoped>
.saver-face { display: block; width: 100%; height: 100%; font-family: Roboto, system-ui, sans-serif; }
</style>
