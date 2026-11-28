<script setup lang="ts">
// A robot vacuum's larger tile (docs/VACUUM.md, "A larger tile") on the mockup: a small app screen on the tile, as the
// screen draws it. A header with status chips, a hero in a frame (the robot's own map as the add-on draws it, the rooms
// as icon tiles, the routines), and a control dock with the cleaning mode as icons, Dock, and Start as the focal point.
// Placed by model/vacuum-tile.ts in glass pixels in the room the card has, in the screens' own letters.
import { computedAsync, useResizeObserver } from "@vueuse/core";
import { computed, ref } from "vue";
import theme from "virtual:esp-screens-theme";
import { glyph } from "../../model/topbar";
import { dotted, textPx } from "../../model/text-fit";
import { frameOf } from "../../model/ui-scale";
import { MODE_ICONS, tileModes, vacuumLayout, type Box } from "../../model/vacuum-tile";
import type { TileCardView } from "../../composables/useTileCard";
import { useDocumentStore } from "../../stores/document";

const props = defineProps<{ card: TileCardView }>();
const card = props.card;
const doc = useDocumentStore();
const hex = (role: string) => `#${theme.roles[role].light.toString(16).padStart(6, "0")}`;
const ha = (name: string) => `#${theme.ha[name].toString(16).padStart(6, "0")}`;
const INK = hex("INK"), MUTED = hex("MUTED"), TRACK = hex("TRACK"), LINE = hex("LINE"), ACCENT = hex("ACCENT");
const ON_ACCENT = hex("ON_ACCENT"), CARD = hex("CARD"), SLATE = hex("SLATE"), TEAL = ha("TEAL");
const INKS: Record<string, string> = { teal: TEAL, charging: ha("CHARGING"), slate: SLATE, red: ha("RED") };

const root = ref<HTMLElement | null>(null);
const room = ref({ width: 0, height: 0 });
useResizeObserver(root, ([entry]) => { room.value = { width: entry.contentRect.width, height: entry.contentRect.height }; });
const glass = computed(() => card.glassScale || 1);
const px = (n: number) => `${(n * glass.value).toFixed(2)}px`;
// The face takes the card's content box as the glass has it: inside the board's own TILE_PAD.
const inset = computed(() => px(frameOf(doc.screenShape).tile_pad));
const place = (b: Box) => ({ left: px(b.x), top: px(b.y), width: px(b.w), height: px(b.h) });
const font = (size: number, weight = 400) => ({ fontSize: px(size), fontWeight: weight, lineHeight: px(Math.round(size * 1.172)) });

// What the robot has, as a screen with the card's module gets it (api/vacuum/preview): its map, rooms and routines.
type Preview = { map: boolean; mark: string; rooms: [string, string][]; routines: string[]; unmapped: boolean; modes: string; mode: number };
const preview = computedAsync<Preview | null>(async () => {
  try {
    const answer = await fetch(`api/vacuum/preview?entity=${encodeURIComponent(card.tile.entity)}`);
    return answer.ok ? await answer.json() : null;
  } catch { return null; }
}, null);
const state = computed(() => String(card.current?.state || ""));
const cleaning = computed(() => state.value === "cleaning");
const face = computed(() => card.face.tallControls || "map");
// The cleaning mode's segments by kind (two to four of their own), and the one in use.
const modes = computed(() => tileModes(preview.value?.modes ?? ""));
const battery = computed(() => {
  const level = Number(card.current?.a?.battery_level);
  return Number.isFinite(level) ? Math.round(level) : null;
});

// The words' widths in the screens' Roboto, as the screen measures its glyphs (text-fit: measured again once it arrives).
const measure = (text: string, size: number, bold = false) => Math.ceil(textPx(text, size, bold ? 700 : 400));
const frame = computed(() => frameOf(doc.screenShape));
// A word cut as the glass cuts it, with LVGL's three dots, in a box `w` glass pixels wide.
const cut = (text: string, size: number, w: number, bold = false) => dotted(text, size, bold ? 700 : 400, w);
const layout = computed(() => room.value.width > 0 ? vacuumLayout(doc.screenShape, {
  face: face.value, width: room.value.width / glass.value, height: room.value.height / glass.value,
  rooms: (preview.value?.rooms ?? []).map(([name]) => name), routines: preview.value?.routines ?? [], map: Boolean(preview.value?.map),
  modes: modes.value.length, second: true, state: state.value, battery: battery.value, charging: state.value === "docked", progress: null,
  // The tile's corner (boards.json spacing.radius), so the frame's corners run with it.
  radius: frame.value.radius, pad: frame.value.tile_pad, measure }) : null);
const stateLine = computed(() => {
  const words = card.texts.status;
  return layout.value && !layout.value.chips.length && battery.value !== null ? `${words} · ${battery.value} %` : words;
});
// The map as the add-on draws it for the screen, on its frame's grey, asked in steps of 16 pixels.
const mapSrc = computed(() => {
  const b = layout.value?.map, p = preview.value;
  if (!b || !p?.map) return "";
  const scale = glass.value * (window.devicePixelRatio || 1), step = (n: number) => Math.max(16, Math.round((n * scale) / 16) * 16);
  return `api/vacuum/map?entity=${encodeURIComponent(card.tile.entity)}&w=${step(b.w)}&h=${step(b.h)}&ground=${TRACK.slice(1)}&v=${encodeURIComponent(p.mark)}`;
});
const roomName = (i: number) => preview.value?.rooms[i]?.[0] ?? "";
const roomIcon = (i: number) => glyph(preview.value?.rooms[i]?.[1] || "F0FE6");
</script>

<template>
  <div ref="root" class="vacuum-face" :style="{ inset }">
    <template v-if="layout">
      <span class="vc-circle mdi" :style="{ ...place({ x: 0, y: (layout.head - layout.circle) / 2, w: layout.circle, h: layout.circle }), fontSize: px(layout.fonts.icon) }">{{ glyph('F070D') }}</span>
      <span class="vc-text" :style="{ left: px(layout.text.x), width: px(layout.text.w), top: '0', height: px(layout.head) }">
        <b :style="font(layout.fonts.label, 700)">{{ cut(card.texts.name, layout.fonts.label, layout.text.w, true) }}</b>
        <small :style="font(layout.fonts.small)">{{ cut(stateLine, layout.fonts.small, layout.text.w) }}</small>
      </span>
      <span v-for="chip in layout.chips" :key="chip.icon" class="vc-chip" :style="{ ...place(chip.box), ...font(layout.fonts.small) }">
        <i class="mdi" :style="{ color: INKS[chip.ink], fontSize: px(layout.fonts.watchIcon) }">{{ glyph(chip.icon) }}</i>{{ chip.words }}
      </span>
      <span class="vc-frame" :style="{ ...place(layout.frame), borderRadius: px(layout.frameRadius) }"></span>
      <img v-if="mapSrc" class="vc-map" :src="mapSrc" alt="" :style="place(layout.map!)" />
      <span v-for="tile in layout.rooms" :key="tile.index" class="vc-room" :style="{ ...place(tile), borderRadius: px(layout.tileRadius), ...font(layout.fonts.small) }">
        <i class="mdi" :style="{ fontSize: px(layout.bigIcons ? layout.fonts.icon : layout.fonts.mini) }">{{ roomIcon(tile.index) }}</i>
        <span>{{ cut(roomName(tile.index), layout.fonts.small, tile.w - 12) }}</span>
      </span>
      <span v-if="layout.more" class="vc-room more" :style="{ ...place(layout.more), borderRadius: px(layout.tileRadius), ...font(layout.fonts.small) }">
        <i class="mdi" :style="{ fontSize: px(layout.bigIcons ? layout.fonts.icon : layout.fonts.mini) }">{{ glyph('F01D8') }}</i>
        <span>+{{ layout.more.count }}</span>
      </span>
      <span v-for="row in layout.routines" :key="row.index" class="vc-routine" :style="{ ...place(row), borderRadius: px(layout.tileRadius), ...font(layout.fonts.small) }">
        <i class="mdi" :style="{ width: px(row.h - 12), height: px(row.h - 12), fontSize: px(layout.fonts.watchIcon) }">{{ glyph('F040A') }}</i>{{ preview?.routines[row.index] }}
      </span>
      <span v-if="layout.routinesMore" class="vc-routine more" :style="{ ...place(layout.routinesMore), borderRadius: px(layout.tileRadius), ...font(layout.fonts.small) }">+{{ layout.routinesMore.count }} more</span>
      <span v-if="layout.mode" class="vc-mode" :style="place(layout.mode)">
        <span v-for="(kind, i) in modes" :key="i" class="mdi" :class="{ on: i === preview?.mode }" :style="{ fontSize: px(layout.fonts.mini) }">
          <template v-for="mark in MODE_ICONS[kind]" :key="mark">{{ glyph(mark) }}</template>
        </span>
      </span>
      <span v-if="layout.dock" class="vc-key mdi" :style="{ ...place(layout.dock), fontSize: px(layout.fonts.mini) }">{{ glyph('F05F8') }}</span>
      <span class="vc-key start mdi" :style="{ ...place(layout.start), fontSize: px(layout.fonts.mini) }">{{ glyph(cleaning ? 'F03E4' : 'F040A') }}</span>
    </template>
  </div>
</template>

<style scoped>
/* The header on the tile's white, the hero in a grey frame with white tiles on it, the dock on the white again; blue only
   for Start, the chosen mode and the rooms picked. */
.vacuum-face { position: absolute; color: v-bind(INK); }
.vacuum-face > * { position: absolute; box-sizing: border-box; }
.vacuum-face .mdi { font-style: normal; line-height: 1; }
.vc-circle { display: grid; place-items: center; border-radius: 50%; background: var(--tile-circle); color: var(--tile-icon); padding: 0; }
.vc-text { display: flex; flex-direction: column; justify-content: center; align-items: flex-start; gap: 1px; min-width: 0; text-align: left; }
.vc-text b, .vc-text small { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
.vc-text small { color: v-bind(MUTED); }
.vc-chip { display: flex; align-items: center; gap: .3em; padding: 0 .75em 0 .6em; border-radius: 999px; background: v-bind(TRACK); white-space: nowrap; }
.vc-frame { background: v-bind(TRACK); }
.vc-map { object-fit: contain; }
.vc-room { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: .15em; background: v-bind(CARD); overflow: hidden; }
.vc-room i { color: v-bind(SLATE); }
.vc-room span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; padding: 0 .4em; }
.vc-room.more, .vc-routine.more { color: v-bind(MUTED); }
.vc-routine { display: flex; align-items: center; gap: .6em; padding: 0 .4em; background: v-bind(CARD); white-space: nowrap; overflow: hidden; }
.vc-routine.more { justify-content: center; }
.vc-routine i { display: grid; place-items: center; border-radius: 50%; background: color-mix(in srgb, v-bind(TEAL) 14%, v-bind(CARD)); color: v-bind(TEAL); flex: none; }
.vc-mode { display: flex; padding: 3px; gap: 0; border-radius: 999px; background: v-bind(TRACK); }
.vc-mode span { flex: 1; display: grid; grid-auto-flow: column; place-content: center; gap: 2px; border-radius: 999px; color: v-bind(SLATE); }
.vc-mode span.on { background: v-bind(ACCENT); color: v-bind(ON_ACCENT); }
.vc-key { display: grid; place-items: center; border-radius: 50%; background: v-bind(CARD); border: 1px solid v-bind(LINE); color: v-bind(INK); }
.vc-key.start { background: v-bind(ACCENT); border-color: v-bind(ACCENT); color: v-bind(ON_ACCENT); }
</style>
