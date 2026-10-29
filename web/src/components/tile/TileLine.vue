<script setup lang="ts">
// A card of one row, or one over the whole page, as the screen draws it: the icon on the left, the name and its line
// beside it (a page's link, a Big number's value), the small slider underneath, and on a wide or full card its control
// beside the name, with the keys the screen draws for this entity (tile_controls::keys_for). A sensor's graph stands
// under its head. A cover laid out by its room (firmware 0.57.0) has its controls beside the name on a wide card and
// under it on a card of one cell, where they fit.
import { glyph } from "../../model/topbar";
import { textEms } from "../../model/ui-scale";
import type { TileCardView } from "../../composables/useTileCard";
import CoverTilePreview from "../CoverTilePreview.vue";
import CoverCell from "./CoverCell.vue";
import ModeBar from "../ModeBar.vue";
import SensorHistory from "../SensorHistory.vue";
import RangeChip from "./RangeChip.vue";
import PresetDisc from "./PresetDisc.vue";
import { levelShown } from "../../model/light-presets";

const props = defineProps<{ card: TileCardView }>();
// The same card for as long as this face stands (useTileCard): read without going through the props each time.
const card = props.card;
</script>

<template>
  <!-- A player's album cover over the whole card, dimmed (runtime_tiles::card_art, one row too since the picture
       system): the card's words light on it and the icon in a dark circle, as on a taller card. -->
  <img v-if="card.artwork" :key="card.artwork" class="line-art" :src="card.artwork" alt="" @load="card.loaded.artwork = true" @error="card.loaded.artwork = false" />
  <template v-if="card.face.kind === 'graph'">
    <span class="head"><span class="ic mdi">{{ glyph(card.icon) }}</span><span class="tx"><span class="nm">{{ card.texts.name }}</span><span class="st">{{ card.texts.line }}</span></span></span>
    <SensorHistory :entity="card.tile.entity" :hours="Number(card.tile.options?.history_hours || 24)" />
  </template>
  <!-- A card over the whole page as the glass lays it out (render_full): one big button, or a player's media card. -->
  <span v-else-if="card.fullStyle" class="glass-head glass-full" :class="card.fullStyle.kind" :style="card.fullStyle.box">
    <span class="ic mdi" :class="{ lit: card.lit }" :style="card.fullStyle.circle">{{ glyph(card.icon) }}</span>
    <span class="nm" :style="card.fullStyle.title">{{ card.fullStyle.name }}</span>
    <span v-if="card.fullStyle.value && card.fullStyle.line" class="st" :class="{ off: card.gone }" :style="card.fullStyle.value">{{ card.fullStyle.line }}</span>
    <template v-if="card.fullStyle.kind === 'media'">
      <span v-if="card.fullStyle.art" class="art mdi" :style="card.fullStyle.art"><img v-if="card.fullStyle.cover" :src="card.fullStyle.cover" alt="" /><template v-else>{{ glyph(card.icon) }}</template></span>
      <span class="track" :style="card.fullStyle.track.style">{{ card.fullStyle.track.text }}</span>
      <span v-if="card.fullStyle.artist" class="words muted" :style="card.fullStyle.artist.style">{{ card.fullStyle.artist.text }}</span>
      <span class="bar" :style="{ ...card.fullStyle.bar, '--fill': card.fullStyle.fill }"></span>
      <span v-if="card.fullStyle.elapsed" class="words subtle" :style="card.fullStyle.elapsed.style">{{ card.fullStyle.elapsed.text }}</span>
      <span v-if="card.fullStyle.total" class="words subtle" :style="card.fullStyle.total.style">{{ card.fullStyle.total.text }}</span>
      <span class="key mdi" :class="{ disabled: card.fullStyle.prevOff }" :style="card.fullStyle.prev">{{ card.key("skip-previous") }}</span>
      <span class="key mdi accent" :style="card.fullStyle.play">{{ card.key(card.fullStyle.playing ? "pause" : "play") }}</span>
      <span class="key mdi" :class="{ disabled: card.fullStyle.nextOff }" :style="card.fullStyle.next">{{ card.key("skip-next") }}</span>
      <template v-if="card.fullStyle.volume">
        <span class="key mdi" :style="card.fullStyle.volume.minus">{{ card.key("minus") || "−" }}</span>
        <span class="volume" :style="card.fullStyle.volume.slider"></span>
        <span class="key mdi" :style="card.fullStyle.volume.plus">{{ card.key("plus") || "+" }}</span>
      </template>
    </template>
  </span>
  <template v-else-if="card.face.kind === 'full'">
    <span class="ic mdi" :class="{ lit: card.lit, thumb: card.face.display === 'live' }">{{ glyph(card.icon) }}</span>
    <span class="lead">
      <span class="nm">{{ card.texts.name }}</span>
      <span v-if="card.goesTo" class="goto">{{ card.texts.pageLink }}</span>
      <span v-else-if="card.face.display === 'watch'" class="big">{{ card.texts.value }}<small v-if="card.texts.unit && !card.gone">{{ card.texts.unit }}</small></span>
      <span v-else-if="card.texts.line" class="st" :class="{ off: card.gone }">{{ card.texts.line }}</span>
    </span>
    <span v-if="card.tile.options?.inline === 'slider'" class="mini-slider" :style="card.sliderStyle"></span>
    <span v-if="card.face.controls" class="ctl">
      <span v-if="card.face.controls === 'toggle'" class="tog" :class="{ off: !card.on }"></span>
      <span v-else-if="card.face.controls === 'setpoint'" class="stp"><span class="mdi">{{ card.key("minus") || "−" }}</span><RangeChip v-if="card.chip" :chip="card.chip" :icon="card.key(card.chip.icon)" /><b v-else :style="{ '--pill-ems': textEms(card.texts.setpoint + '8') }">{{ card.texts.setpoint }}</b><span class="mdi">{{ card.key("plus") || "+" }}</span></span>
      <template v-else-if="card.face.controls === 'volume'"><span class="range" :style="card.sliderStyle"></span><span class="key mdi">{{ card.key("volume-high") }}</span></template>
      <ModeBar v-else-if="card.face.modeBar" :a="card.current?.a || {}" :mode="card.current?.state || ''" :domain="card.domain" place="full" :columns="card.shape.columns" /><template v-else-if="card.face.panelKeys.length"><span v-for="(control, i) in card.face.panelKeys" :key="i" class="key mdi" :class="{ primary: control.primary, disabled: control.disabled, active: control.mode === card.current?.state }">{{ card.key(control.icon) }}</span></template>
      <span v-else-if="card.face.controls === 'run'" class="run">{{ card.texts.runText }}</span>
      <template v-else-if="card.face.controls === 'presets'"><PresetDisc v-for="(preset, i) in card.presets" :key="i" class="dot-loose" :preset="preset" :lit="i === card.presetLit" :level="levelShown(preset, card.tile.options?.preset_levels === true)" /></template>
      <span v-else class="range" :style="card.sliderStyle"></span>
    </span>
  </template>
  <template v-else-if="card.face.kind === 'wide'">
    <span v-if="card.glassStyle.head" class="glass-head" :style="card.glassStyle.head.box">
      <span class="ic mdi" :class="{ lit: card.lit }" :style="card.glassStyle.head.circle">{{ glyph(card.icon) }}</span>
      <span class="nm" :style="card.glassStyle.head.title">{{ card.glassStyle.name }}</span>
      <span v-if="card.glassStyle.head.value" class="st" :class="{ off: card.gone }" :style="card.glassStyle.head.value">{{ card.glassStyle.line }}</span>
    </span>
    <span v-else class="lead">
      <span class="ic mdi" :class="{ lit: card.lit, thumb: card.face.display === 'live' }">{{ glyph(card.icon) }}</span>
      <span class="tx">
        <span class="nm">{{ card.texts.name }}</span>
        <span v-if="card.goesTo" class="goto">{{ card.texts.pageLink }}</span>
        <span v-else-if="card.face.display === 'watch'" class="big">{{ card.texts.value }}<small v-if="card.texts.unit && !card.gone">{{ card.texts.unit }}</small></span>
        <span v-else-if="card.texts.line" class="st" :class="{ off: card.gone }">{{ card.texts.line }}</span>
      </span>
    </span>
    <span v-if="card.tile.options?.inline === 'slider'" class="mini-slider" :style="card.sliderStyle"></span>
    <span v-if="card.face.coverRow" class="ctl cover-row">
      <CoverTilePreview :primary="card.face.coverPrimary" :tilt="card.face.coverRow" :at-half="card.tile.options?.tilt_open === '50'" :standing="false" :entity-state="card.current?.state || ''" :attributes="card.current?.a || {}">
        <template #fallback>
          <span v-if="card.face.controls === 'position'" class="range" :style="card.sliderStyle"></span>
          <template v-else><span v-for="(control, i) in card.face.panelKeys" :key="i" class="key mdi" :class="{ disabled: control.disabled }">{{ card.key(control.icon) }}</span></template>
        </template>
      </CoverTilePreview>
    </span>
    <span v-else-if="card.face.controls" class="ctl" :class="{ fill: card.face.fillsCell, 'glass-panel': !!card.glassStyle.panel }" :style="card.glassStyle.panel ?? undefined">
      <!-- A light's presets (module light_presets): its round keys where its slider would stand, as many as fit. -->
      <template v-if="card.face.controls === 'presets'">
        <template v-if="card.glassStyle.dots"><PresetDisc v-for="dot in card.glassStyle.dots" :key="dot.key" class="dot" :preset="dot.preset" :lit="dot.lit" :level="dot.level" :style="dot.style" /></template>
        <PresetDisc v-for="(preset, i) in card.presets" v-else :key="i" class="dot-loose" :preset="preset" :lit="i === card.presetLit" :level="levelShown(preset, card.tile.options?.preset_levels === true)" />
      </template>
      <span v-else-if="card.face.controls === 'toggle'" class="tog" :class="{ off: !card.on }"></span>
      <span v-else-if="card.face.controls === 'setpoint'" class="stp"><span class="mdi">{{ card.key("minus") || "−" }}</span><RangeChip v-if="card.chip" :chip="card.chip" :icon="card.key(card.chip.icon)" :wide="card.wideFit" :glass="card.glassScale" /><b v-else :style="card.pill ?? { '--pill-ems': textEms(card.texts.setpoint + '8') }">{{ card.texts.setpoint }}</b><span class="mdi">{{ card.key("plus") || "+" }}</span></span>
      <template v-else-if="card.face.controls === 'stepper' && card.domain.endsWith('select')"><span class="key mdi">{{ card.key("chevron-left") }}</span><span class="key mdi">{{ card.key("chevron-right") }}</span></template>
      <span v-else-if="card.face.controls === 'stepper'" class="stp"><span class="mdi">{{ card.key("minus") || "−" }}</span><b>{{ card.texts.value }}</b><span class="mdi">{{ card.key("plus") || "+" }}</span></span>
      <ModeBar v-else-if="card.face.modeBar" :a="card.current?.a || {}" :mode="card.current?.state || ''" :domain="card.domain" place="row" :columns="card.shape.columns" /><template v-else-if="card.face.panelKeys.length"><span v-for="(control, i) in card.face.panelKeys" :key="i" class="key mdi" :class="{ primary: control.primary, disabled: control.disabled, active: control.mode === card.current?.state }">{{ card.key(control.icon) }}</span></template>
      <template v-else-if="card.face.controls === 'volume'"><span class="range" :style="card.sliderStyle"></span><span class="key mdi">{{ card.key("volume-high") }}</span></template>
      <span v-else-if="card.face.controls === 'run'" class="run">{{ card.texts.runText }}</span>
      <span v-else class="range" :style="card.sliderStyle"></span>
    </span>
  </template>
  <CoverCell v-else-if="card.face.coverRow" :card="card" />
  <span v-else-if="card.glassStyle.head" class="glass-head" :style="card.glassStyle.head.box">
    <!-- As the glass lays it out (runtime_tiles head_row): the circle at the left, the name and its line beside it. -->
    <span class="ic mdi" :class="{ lit: card.lit }" :style="card.glassStyle.head.circle">{{ glyph(card.icon) }}</span>
    <span class="nm" :style="card.glassStyle.head.title">{{ card.glassStyle.name }}</span>
    <span v-if="card.glassStyle.head.value" class="st" :class="{ off: card.gone }" :style="card.glassStyle.head.value">{{ card.glassStyle.line }}</span>
  </span>
  <template v-else>
    <!-- As the screen draws it: the icon on the left, the name and the value beside it. A watch
         card puts the name on top and the big value under it; the small slider runs underneath. -->
    <span class="head" :class="{ top: card.face.display === 'watch' }">
      <span class="ic mdi" :class="{ lit: card.lit, thumb: card.face.display === 'live' }">{{ glyph(card.icon) }}</span>
      <span class="tx">
        <span class="nm">{{ card.texts.name }}</span>
        <span v-if="card.goesTo" class="goto">{{ card.texts.pageLink }}</span>
        <span v-else-if="card.face.display !== 'watch' && card.texts.line" class="st" :class="{ off: card.gone }">{{ card.texts.line }}</span>
      </span>
    </span>
    <span v-if="card.face.display === 'watch'" class="big">{{ card.texts.value }}<small v-if="card.texts.unit && !card.gone">{{ card.texts.unit }}</small></span>
    <span v-if="card.tile.options?.inline === 'slider'" class="mini-slider" :style="card.sliderStyle"></span>
  </template>
</template>

<style scoped src="./parts.css"></style>
<style scoped>
/* A head laid out as the glass does (model/card-layout.ts): every part where runtime_tiles puts it, in the board's faces. */
.tile .glass-head { position: absolute; }
.tile .glass-head > * { position: absolute; margin: 0; white-space: nowrap; overflow: hidden; }
.tile .glass-head .ic:not(.thumb) { display: grid; place-items: center; padding: 0; line-height: 1; }
.tile:not(.photo) .glass-head .nm { color: #1b1b1b; }
.tile .glass-full .art { overflow: hidden; }
.tile .glass-full .art img { width: 100%; height: 100%; object-fit: cover; display: block; }
.tile .glass-full .nm, .tile .glass-full .st { text-align: center; }
.tile .glass-full.media .nm, .tile .glass-full.media .st { text-align: left; }
.tile .glass-full .st { color: var(--muted); }
.tile .glass-full .art { display: grid; place-items: center; background: color-mix(in srgb, var(--media-blue) 20%, white); color: var(--media-blue); line-height: 1; }
.tile .glass-full .track { color: #1b1b1b; }
.tile .glass-full .words.muted { color: var(--muted); }
.tile .glass-full .words.subtle { color: var(--subtle); }
.tile .glass-full .bar { border-radius: 999px; background: linear-gradient(to right, var(--media-accent) var(--fill), var(--track) var(--fill)); }
.tile .glass-full .key { display: grid; place-items: center; border-radius: 50%; background: var(--key); padding: 0; min-width: 0; line-height: 1; }
.tile .glass-full .key.accent { background: var(--media-accent); color: white; }
.tile .glass-full .key.disabled { opacity: .4; }
.tile .glass-full .volume { overflow: visible; border-radius: 999px; background: linear-gradient(to right, var(--media-accent) var(--fill), var(--track) var(--fill)); }
.tile .glass-full .volume::after { content: ""; position: absolute; top: 50%; left: var(--fill); width: var(--knob); height: var(--knob); border-radius: 50%;
  background: #1b1b1b; transform: translate(-50%, -50%); }
/* The control at the card's right at the glass's sizes (layout_panel, panel_metrics). */
.tile .ctl.glass-panel { position: absolute; gap: var(--key-gap); justify-content: flex-end; }
.tile .ctl.glass-panel .tog { width: var(--tog-w); height: var(--tog-h); border-radius: 999px; flex: none; }
.tile .ctl.glass-panel .tog::after { width: var(--knob); height: var(--knob); top: calc((var(--tog-h) - var(--knob)) / 2); right: calc((var(--tog-h) - var(--knob)) / 2); }
.tile .ctl.glass-panel .tog.off::after { right: auto; left: calc((var(--tog-h) - var(--knob)) / 2); }
.tile .ctl.glass-panel > .key { width: var(--key-w); height: var(--key-h); border-radius: var(--key-r); padding: 0; font-size: var(--icon-mini); flex: none; }
.tile .ctl.glass-panel > .range { height: var(--slider-h); border-radius: var(--slider-r); flex: 1; width: auto; }
.tile .ctl.glass-panel > .range + .key { width: var(--key-h); }
.tile .ctl.glass-panel .stp { flex: 1; height: 100%; }
.tile .ctl.glass-panel .run { height: 100%; border-radius: 999px; display: grid; place-items: center; }
.tile .ctl.glass-panel > .dot { position: absolute; }
.tile .ctl.glass-panel { overflow: visible; }
.tile .ctl .dot-loose { width: 22px; height: 22px; flex: none; font-size: 9px; }
</style>
