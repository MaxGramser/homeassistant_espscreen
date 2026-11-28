<script setup lang="ts">
// A card two rows tall or more, as the screen draws it (firmware 0.3.1 render_tall). One that only switches or only runs
// is one big key (firmware 0.17.0 big_key): a large circle, the name and the state, and the whole card is the key. Any
// other keeps its head (an album cover behind it, from the add-on) over its body: a blind's slats beside its own control,
// a thermostat's setpoint with what it measures and its modes, or the value it stands large, and under it the control.
import { computed } from "vue";
import { bits } from "../../model/catalogue";
import { glyph } from "../../model/topbar";
import { textEms } from "../../model/ui-scale";
import type { TileCardView } from "../../composables/useTileCard";
import CoverTilePreview from "../CoverTilePreview.vue";
import MarqueeText from "../MarqueeText.vue";
import ModeBar from "../ModeBar.vue";
import RangeChip from "./RangeChip.vue";
import PresetDisc from "./PresetDisc.vue";
import { levelShown } from "../../model/light-presets";

const props = defineProps<{ card: TileCardView }>();
// The same card for as long as this face stands (useTileCard): read without going through the props each time.
const card = props.card;
// A tall card's slider has a white mark where its fill ends.
const rangeStyle = computed(() => ({ ...card.sliderStyle, "--fill": `${card.fill}%` }));
// A player's volume beside its keys: standing at the right on a card wider than high, over the keys on a narrower one
// (runtime_tiles render_tall, media_standing).
const volume = computed(() => card.face.tallControls === "volume_playback" && Boolean(card.features & bits("media_player", "VOLUME_SET")));
const standing = computed(() => volume.value && card.shape.columns >= 2 && card.shape.columns >= card.shape.rows);
const standStyle = computed(() => ({ background: `linear-gradient(to top, ${card.palette.accent} ${card.fill}%, ${card.palette.track} ${card.fill}%)`, "--fill": `${card.fill}%` }));
</script>

<template>
  <!-- As the glass lays it out (runtime_tiles render_tall, model/tall-layout.ts): every part where the glass puts it. -->
  <img v-if="card.tallStyle && card.artwork" :key="card.artwork" class="tall-art" :src="card.artwork" alt="" @load="card.loaded.artwork = true" @error="card.loaded.artwork = false" />
  <span v-if="card.tallStyle" class="glass-head glass-tall" :style="card.tallStyle.box">
    <span v-if="card.tallStyle.circle" class="ic mdi" :class="{ lit: card.lit }" :style="card.tallStyle.circle">{{ glyph(card.icon) }}</span>
    <span v-if="card.tallStyle.title" class="nm" :style="card.tallStyle.title.style">{{ card.tallStyle.title.text }}</span>
    <span v-if="card.tallStyle.value" class="st" :class="{ off: card.gone }" :style="card.tallStyle.value.style">{{ card.tallStyle.value.text }}</span>
    <span v-for="(line, i) in card.tallStyle.body" :key="i" class="words" :class="{ muted: line.muted, 'track-title': line.marquee }" :style="line.style">{{ line.text }}</span>
    <template v-if="card.tallStyle.climate">
      <span v-if="card.tallStyle.climate.stepper" class="pill" :style="card.tallStyle.climate.stepper"></span>
      <span class="key mdi" :class="card.tallStyle.climate.form" :style="{ ...card.tallStyle.climate.minus, fontSize: card.tallStyle.climate.iconSize }">{{ card.key("minus") || "−" }}</span>
      <span class="key mdi" :class="card.tallStyle.climate.form" :style="{ ...card.tallStyle.climate.plus, fontSize: card.tallStyle.climate.iconSize }">{{ card.key("plus") || "+" }}</span>
      <span class="number" :class="{ off: card.current?.state === 'off' }" :style="card.tallStyle.climate.number">
        <RangeChip v-if="card.chip" :chip="card.chip" :icon="card.key(card.chip.icon)" /><template v-else>{{ card.texts.setpoint }}</template></span>
      <span v-if="card.tallStyle.climate.now" class="words muted now" :style="card.tallStyle.climate.now">{{ card.tallStyle.climate.nowText }}</span>
      <span v-if="card.tallStyle.climate.bar" class="bar" :style="card.tallStyle.climate.bar.box">
        <ModeBar :a="card.current?.a || {}" :mode="card.current?.state || ''" :domain="card.domain" place="tall" :columns="card.shape.columns" :fit="card.tallStyle.climate.bar.fit" /></span>
    </template>
    <span v-if="card.tallStyle.panel" class="glass-row" :class="card.tallStyle.panel.kind" :style="card.tallStyle.panel.box">
      <span v-if="card.tallStyle.panel.kind === 'toggle'" class="tog" :class="{ off: !card.on }"></span>
      <ModeBar v-else-if="card.tallStyle.panel.kind === 'mode'" :a="card.current?.a || {}" :mode="card.current?.state || ''" :domain="card.domain" place="tall" :columns="card.shape.columns" />
      <span v-else-if="['setpoint', 'stepper'].includes(card.tallStyle.panel.kind) && !card.face.tallKeys.length" class="stp"><span class="mdi">{{ card.key("minus") || "−" }}</span><b>{{ card.face.thermostat ? card.texts.setpoint : card.texts.value }}</b><span class="mdi">{{ card.key("plus") || "+" }}</span></span>
      <span v-else-if="card.tallStyle.panel.kind === 'run'" class="run">{{ card.texts.runText }}</span>
      <!-- A light's presets (module light_presets): their round keys, under its slider where both are chosen. -->
      <template v-else-if="card.tallStyle.panel.dots">
        <span v-if="card.tallStyle.panel.slider" class="range" :style="{ ...card.tallStyle.panel.slider, ...rangeStyle }"></span>
        <PresetDisc v-for="dot in card.tallStyle.panel.dots" :key="dot.key" class="dot" :preset="dot.preset" :lit="dot.lit" :level="dot.level" :style="dot.style" />
      </template>
      <template v-else-if="card.tallStyle.panel.keys">
        <span v-if="card.tallStyle.panel.slider" class="range" :style="{ ...card.tallStyle.panel.slider, ...rangeStyle }"></span>
        <span class="keys" :style="card.tallStyle.panel.keys"><span v-for="(control, i) in card.face.tallKeys" :key="i" class="key mdi"
          :class="{ primary: control.primary, disabled: control.disabled, active: control.mode === card.current?.state }">{{ control.cp ? glyph(control.cp) : card.key(control.icon) }}</span></span>
      </template>
      <template v-else>
        <span class="range" :style="rangeStyle"></span>
        <span v-if="card.tallStyle.panel.kind === 'volume'" class="key mdi">{{ card.key(card.current?.a?.is_volume_muted ? 'volume-off' : 'volume-high') }}</span>
      </template>
    </span>
    <span v-if="card.tallStyle.panel?.standing" class="vol-glass" :style="{ ...card.tallStyle.panel.standing, ...standStyle }"></span>
  </span>
  <template v-else-if="card.face.kind === 'big-key'">
    <span class="ic mdi" :class="{ lit: card.lit }">{{ glyph(card.icon) }}</span>
    <span class="nm">{{ card.texts.name }}</span>
    <span v-if="card.texts.bigKeyLine" class="st" :class="{ off: card.gone }">{{ card.texts.bigKeyLine }}</span>
  </template>
  <template v-else>
    <img v-if="card.artwork" :key="card.artwork" class="tall-art" :src="card.artwork" alt="" @load="card.loaded.artwork = true" @error="card.loaded.artwork = false" />
    <span class="head">
      <span class="ic mdi">{{ glyph(card.icon) }}</span>
      <span class="tx"><span class="nm">{{ card.texts.name }}</span><span v-if="card.texts.headLine" class="st" :class="{ off: card.gone }">{{ card.texts.headLine }}</span></span>
    </span>
    <CoverTilePreview v-if="card.face.coverExtended" :at-half="card.tile.options?.tilt_open === '50'" :primary="card.face.tallControls" :entity-state="card.current?.state || ''" :attributes="card.current?.a || {}">
      <template #fallback>
        <span v-if="card.face.tallControls === 'position'" class="cover-range" :style="{ '--position': `${100 - (card.current?.a?.current_position ?? 50)}%` }"></span>
        <span v-else-if="card.face.tallKeys.length" class="cover-row"><span v-for="(k, i) in card.face.tallKeys" :key="i" class="key mdi" :class="{ disabled: k.disabled }">{{ card.key(k.icon) }}</span></span>
      </template>
    </CoverTilePreview>
    <span v-else-if="card.face.thermostat && (card.face.tallControls === 'setpoint' || card.face.tallControls === 'setpoint_mode')" class="tall-setpoint">
      <span class="target"><span class="key mdi">{{ card.key('minus') || '−' }}</span><RangeChip v-if="card.chip" :chip="card.chip" :icon="card.key(card.chip.icon)" /><b v-else>{{ card.texts.setpoint }}</b><span class="key mdi">{{ card.key('plus') || '+' }}</span></span>
      <span class="st">{{ card.texts.now || card.texts.status }}</span>
      <ModeBar v-if="card.face.tallControls === 'setpoint_mode'" class="ctl modes" :a="card.current?.a || {}" :mode="card.current?.state || ''" :domain="card.domain" place="tall" :columns="card.shape.columns" />
    </span>
    <template v-else>
      <span v-if="!card.face.tallAction" class="tall-body">
        <template v-if="card.domain === 'media_player' && !card.gone">
          <MarqueeText class="track-title" :text="String(card.current?.a?.media_title || '')" /><span v-if="card.texts.mediaSubtitle" class="st">{{ card.texts.mediaSubtitle }}</span>
        </template>
        <span v-else-if="card.domain === 'climate' && !card.gone" class="target-value">{{ card.texts.reading || '—' }}</span>
        <!-- A humidifier stands the humidity it measures large, else its line (runtime_tiles render_tall). -->
        <span v-else-if="card.domain === 'humidifier' && !card.gone" class="target-value">{{ card.texts.reading || card.texts.status }}</span>
        <span v-else-if="card.domain !== 'screen' && !card.gone && card.face.tallControls !== 'toggle'" class="target-value">{{ card.domain === 'light' && card.lit ? `${card.fill}%` : card.texts.status }}</span>
      </span>
      <!-- A player's volume over its keys (volume_playback): a row of its own above them, as the screen stacks them. -->
      <span v-if="standing" class="vol-stand" :style="standStyle"></span>
      <span v-else-if="volume" class="ctl volume-row"><span class="range" :style="rangeStyle"></span></span>
      <span v-if="card.face.tallControls" class="ctl" :class="{ playback: ['playback', 'volume_playback'].includes(card.face.tallControls) }">
        <span v-if="card.face.tallControls === 'toggle'" class="tog" :class="{ off: !card.on }"></span>
        <span v-else-if="card.face.tallControls === 'setpoint'" class="stp"><span class="mdi">{{ card.key("minus") || "−" }}</span><RangeChip v-if="card.chip" :chip="card.chip" :icon="card.key(card.chip.icon)" /><b v-else :style="{ '--pill-ems': textEms(card.texts.setpoint + '8') }">{{ card.texts.setpoint }}</b><span class="mdi">{{ card.key("plus") || "+" }}</span></span>
        <ModeBar v-else-if="card.face.tallControls === 'mode' && card.face.thermostat" :a="card.current?.a || {}" :mode="card.current?.state || ''" :domain="card.domain" place="tall" :columns="card.shape.columns" />
        <template v-else-if="card.face.tallKeys.length"><span v-for="(control, i) in card.face.tallKeys" :key="i" class="key mdi" :class="{ primary: control.primary, disabled: control.disabled, active: control.mode === card.current?.state }">{{ card.key(control.icon) }}</span></template>
        <span v-else-if="card.face.tallControls === 'stepper'" class="stp"><span class="mdi">{{ card.key("minus") || "−" }}</span><b>{{ card.texts.value }}</b><span class="mdi">{{ card.key("plus") || "+" }}</span></span>
        <template v-else-if="card.face.tallControls === 'volume'"><span v-if="card.features & bits('media_player', 'VOLUME_SET')" class="range" :style="rangeStyle"></span><span v-if="card.features & bits('media_player', 'VOLUME_MUTE')" class="key mdi">{{ card.key(card.current?.a?.is_volume_muted ? 'volume-off' : 'volume-high') }}</span></template>
        <span v-else-if="card.face.tallControls === 'run'" class="run">{{ card.texts.runText }}</span>
        <template v-else-if="['presets', 'brightness_presets'].includes(card.face.tallControls)"><PresetDisc v-for="(preset, i) in card.presets" :key="i" class="dot-loose"
          :preset="preset" :lit="i === card.presetLit" :level="levelShown(preset, card.tile.options?.preset_levels === true)" /></template>
        <span v-else class="range" :style="rangeStyle"></span>
      </span>
    </template>
  </template>
</template>

<style scoped src="./parts.css"></style>
<style scoped>
/* A tall card laid out as the glass does (model/tall-layout.ts): its parts at their own places, the controls at the
   glass's sizes (layout_panel on a taller card, climate_tile.h). */
.tile .glass-tall { position: absolute; }
.tile .glass-tall > * { position: absolute; margin: 0; white-space: nowrap; overflow: hidden; }
.tile .glass-tall .ic:not(.thumb) { display: grid; place-items: center; padding: 0; line-height: 1; }
.tile .glass-tall .nm { color: #1b1b1b; }
.tile .glass-tall .words { color: #1b1b1b; }
.tile .glass-tall .words.muted, .tile .glass-tall .st { color: var(--muted); }
/* A player's title rolls by on the glass: cut at the edge, no dots. */
.tile .glass-tall .words.track-title { text-overflow: clip; font-size: inherit; line-height: inherit; }
.tile .glass-tall .pill { border-radius: 999px; background: var(--track); }
.tile .glass-tall > .key { display: grid; place-items: center; border-radius: 50%; padding: 0; min-width: 0; line-height: 1; }
.tile .glass-tall > .key.big { background: var(--track); }
.tile .glass-tall > .key.row { background: var(--stepper-key); }
.tile .glass-tall .number { display: flex; align-items: center; justify-content: center; color: #1b1b1b; overflow: visible; }
.tile .glass-tall .number :deep(b) { font-weight: inherit; font-size: inherit; }
.tile .glass-tall .number :deep(.range-chip) { padding: 0; margin: 0; gap: var(--chip-gap); flex: none; }
.tile .glass-tall .number :deep(.end-icon) { font-size: var(--chip-icon); }
.tile .glass-tall .number.off { color: var(--muted); }
.tile .glass-tall .now { text-align: center; }
.tile .glass-tall .bar { display: flex; overflow: visible; }
.tile .glass-tall .glass-row { display: flex; align-items: center; justify-content: center; gap: var(--key-gap); overflow: visible; }
.tile .glass-tall .glass-row .tog { width: var(--tog-w); height: var(--tog-h); border-radius: 999px; flex: none; }
.tile .glass-tall .glass-row .tog::after { width: var(--knob); height: var(--knob); top: calc((var(--tog-h) - var(--knob)) / 2); right: calc((var(--tog-h) - var(--knob)) / 2); }
.tile .glass-tall .glass-row .tog.off::after { right: auto; left: calc((var(--tog-h) - var(--knob)) / 2); }
.tile .glass-tall .glass-row .keys { position: absolute; display: flex; gap: var(--key-gap); }
.tile .glass-tall .glass-row .key { width: var(--key-w); height: var(--key-h); flex: none; padding: 0; min-width: 0; font-size: var(--icon-mini); border-radius: var(--key-r); }
.tile .glass-tall .glass-row .range + .key { width: var(--key-h); }
.tile .glass-tall .glass-row.playback .key, .tile .glass-tall .glass-row.volume_playback .key { border-radius: 50%; background: var(--track); }
.tile .glass-tall .glass-row .key.primary { background: var(--tile-accent); color: white; }
.tile .glass-tall .glass-row .range { height: var(--key-h); flex: 1; border-radius: var(--slider-r); width: auto; }
.tile .glass-tall .glass-row .keys + .range, .tile .glass-tall .glass-row .range[style*="left"] { position: absolute; }
.tile .glass-tall .glass-row .stp { flex: 1; height: 100%; border-radius: 999px; }
.tile .glass-tall .glass-row .run { height: 100%; border-radius: 999px; display: grid; place-items: center; flex: 1; }
.tile .glass-tall .vol-glass { border-radius: 10px; }
.tile .glass-tall .glass-row .dot { position: absolute; }
.tile.tall .ctl .dot-loose { width: 22px; height: 22px; flex: none; font-size: 9px; }
/* Over a player's cover (style_tall): light words, a dark circle, the play key white with a dark glyph. */
.tile.tall.photo .glass-tall .nm, .tile.tall.photo .glass-tall .words, .tile.tall.photo .glass-tall .st { color: white; }
.tile.tall.photo .glass-tall .ic:not(.thumb) { background: var(--camera-track); color: white; }
.tile.tall.photo .glass-tall .glass-row.playback .key, .tile.tall.photo .glass-tall .glass-row.volume_playback .key { background: transparent; color: white; }
.tile.tall.photo .glass-tall .glass-row .key.primary, .tile.tall.photo .glass-tall .glass-row .range + .key { background: white; color: #1b1b1b; }
/* A player's volume standing at the card's right, the whole height of its content; the rest keeps clear of it. */
.vol-stand { position: absolute; top: 8px; bottom: 8px; right: 9px; width: clamp(22px, 18cqh, 36px); border-radius: 10px; }
.vol-stand::after { content: ''; position: absolute; left: 25%; right: 25%; height: 3px; bottom: clamp(4px, var(--fill), calc(100% - 6px)); background: white; border-radius: 2px; }
.tile.tall:has(> .vol-stand) > :not(.vol-stand, .tall-art, .remove, .resize-handle) { margin-right: calc(clamp(22px, 18cqh, 36px) + 8px); }
/* Beside it the keys start at the left, under the track and the name (runtime_tiles render_tall). */
.tile.tall:has(> .vol-stand) > .ctl { justify-content: flex-start; }
</style>
<style scoped>
/* What a cover shows where its slats do not fit (CoverTilePreview's fallback): its position bar, or its keys. */
.cover-range { position: absolute; left: 0; right: 0; bottom: 0; height: min(40%, 34px); border-radius: 10px; background: linear-gradient(to right, var(--tile-accent) var(--position), var(--tile-circle) var(--position)); }
.cover-row { position: absolute; left: 0; right: 0; bottom: 0; display: flex; gap: 6px; justify-content: center; }
.tile.tall.big-key .ic { width: 44cqmin; height: 44cqmin; display: grid; place-items: center; font-size: 24cqmin; padding: 0; }
.tile.tall.big-key .nm { font-size: clamp(12px, 13cqmin, 26px); font-weight: 500; color: #1b1b1b; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tile.tall.big-key .st { font-size: 10px; }
.tile.tall .head { flex: none; }
.tile.tall.tall-action .head { flex-direction: column; justify-content: center; text-align: center; }
.tile.tall.tall-action .tx { flex: none; width: 100%; }
.tile.tall .tog { --toggle-height: clamp(22px, 18cqh, 36px); height: var(--toggle-height); width: calc(2 * var(--toggle-height)); border-radius: 99px; flex: none; }
.tile.tall .tog::after { width: calc(var(--toggle-height) - 6px); height: calc(var(--toggle-height) - 6px); top: 3px; right: 3px; }
.tile.tall .tog.off::after { right: auto; left: 3px; }
.tile.tall .tall-body { flex: 1; min-height: 0; display: flex; flex-direction: column; justify-content: center; overflow: hidden; gap: 3px; }
.track-title { font-weight: 600; font-size: clamp(12px, 9cqh, 21px); line-height: 1.2; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tile.tall .ctl { justify-content: center; width: 100%; }
.tile.tall .range { flex: 1; height: clamp(22px, 18cqh, 36px); border-radius: 10px; position: relative; }
.tile.tall .range::after { content: ''; width: 3px; height: 50%; background: white; border-radius: 2px; position: absolute; left: clamp(4px, var(--fill), calc(100% - 6px)); top: 25%; }
.tile.tall .key.disabled { opacity: .35; }
.tile.tall .key { width: clamp(22px, 18cqh, 36px); height: clamp(22px, 18cqh, 36px); min-width: 0; padding: 0; border-radius: 50%; }
.tile.tall .playback .key.primary, .tile.tall .key.active { background: var(--tile-accent); color: white; }
.tall-setpoint { flex: 1; display: flex; flex-direction: column; min-height: 0; justify-content: center; gap: 5px; text-align: center; }
.target { flex: 1; display: flex; justify-content: space-between; align-items: center; gap: 6px; }
.target b, .target-value { font-size: clamp(16px, 18cqh, 42px); font-weight: 400; text-align: center; }
.tile.tall .tall-art { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; border-radius: inherit; opacity: 0; filter: brightness(.333); pointer-events: none; }
.tile.tall .head, .tile.tall .tall-body, .tile.tall .ctl, .tile.tall .tall-setpoint { position: relative; }
.tile.tall.photo .tall-art { opacity: 1; }
.tile.tall.photo .st, .tile.tall.photo .ctl { color: white; }
.tile.tall.photo .ic { background: #333; color: white; }
.tile.tall.photo .playback .key { background: transparent; }
.tile.tall.photo .playback .key.primary { background: white; color: #111; }
</style>
