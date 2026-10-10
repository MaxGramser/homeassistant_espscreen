<script setup lang="ts">
// A card of one row, or one over the whole page, as the screen draws it: the icon on the left, the name and its line
// beside it (a page's link, a Big number's value), the small slider underneath, and on a wide or full card its control
// beside the name, with the keys the screen draws for this entity (tile_controls::keys_for). A sensor's graph stands
// under its head.
import { glyph } from "../../model/topbar";
import { textEms } from "../../model/ui-scale";
import type { TileCardView } from "../../composables/useTileCard";
import ModeBar from "../ModeBar.vue";
import SensorHistory from "../SensorHistory.vue";
import RangeChip from "./RangeChip.vue";

const props = defineProps<{ card: TileCardView }>();
// The same card for as long as this face stands (useTileCard): read without going through the props each time.
const card = props.card;
</script>

<template>
  <template v-if="card.face.kind === 'graph'">
    <span class="head"><span class="ic mdi">{{ glyph(card.icon) }}</span><span class="tx"><span class="nm">{{ card.texts.name }}</span><span class="st">{{ card.texts.line }}</span></span></span>
    <SensorHistory :entity="card.tile.entity" :hours="Number(card.tile.options?.history_hours || 24)" />
  </template>
  <template v-else-if="card.face.kind === 'full'">
    <span class="ic mdi" :class="{ lit: card.lit, thumb: card.face.display === 'live' || card.face.display === 'cover' }">{{ glyph(card.icon) }}</span>
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
      <span v-else class="range" :style="card.sliderStyle"></span>
    </span>
  </template>
  <template v-else-if="card.face.kind === 'wide'">
    <span class="lead">
      <span class="ic mdi" :class="{ lit: card.lit, thumb: card.face.display === 'live' || card.face.display === 'cover' }">{{ glyph(card.icon) }}</span>
      <span class="tx">
        <span class="nm">{{ card.texts.name }}</span>
        <span v-if="card.goesTo" class="goto">{{ card.texts.pageLink }}</span>
        <span v-else-if="card.face.display === 'watch'" class="big">{{ card.texts.value }}<small v-if="card.texts.unit && !card.gone">{{ card.texts.unit }}</small></span>
        <span v-else-if="card.texts.line" class="st" :class="{ off: card.gone }">{{ card.texts.line }}</span>
      </span>
    </span>
    <span v-if="card.tile.options?.inline === 'slider'" class="mini-slider" :style="card.sliderStyle"></span>
    <span v-if="card.face.controls" class="ctl" :class="{ fill: card.face.fillsCell }">
      <span v-if="card.face.controls === 'toggle'" class="tog" :class="{ off: !card.on }"></span>
      <span v-else-if="card.face.controls === 'setpoint'" class="stp"><span class="mdi">{{ card.key("minus") || "−" }}</span><RangeChip v-if="card.chip" :chip="card.chip" :icon="card.key(card.chip.icon)" :wide="card.wideFit" :glass="card.glassScale" /><b v-else :style="{ '--pill-ems': textEms(card.texts.setpoint + '8') }">{{ card.texts.setpoint }}</b><span class="mdi">{{ card.key("plus") || "+" }}</span></span>
      <template v-else-if="card.face.controls === 'stepper' && card.domain.endsWith('select')"><span class="key mdi">{{ card.key("chevron-left") }}</span><span class="key mdi">{{ card.key("chevron-right") }}</span></template>
      <span v-else-if="card.face.controls === 'stepper'" class="stp"><span class="mdi">{{ card.key("minus") || "−" }}</span><b>{{ card.texts.value }}</b><span class="mdi">{{ card.key("plus") || "+" }}</span></span>
      <ModeBar v-else-if="card.face.modeBar" :a="card.current?.a || {}" :mode="card.current?.state || ''" :domain="card.domain" place="row" :columns="card.shape.columns" /><template v-else-if="card.face.panelKeys.length"><span v-for="(control, i) in card.face.panelKeys" :key="i" class="key mdi" :class="{ primary: control.primary, disabled: control.disabled, active: control.mode === card.current?.state }">{{ card.key(control.icon) }}</span></template>
      <template v-else-if="card.face.controls === 'volume'"><span class="range" :style="card.sliderStyle"></span><span class="key mdi">{{ card.key("volume-high") }}</span></template>
      <span v-else-if="card.face.controls === 'run'" class="run">{{ card.texts.runText }}</span>
      <span v-else class="range" :style="card.sliderStyle"></span>
    </span>
  </template>
  <template v-else>
    <!-- As the screen draws it: the icon on the left, the name and the value beside it. A watch
         card puts the name on top and the big value under it; the small slider runs underneath. -->
    <span class="head" :class="{ top: card.face.display === 'watch' }">
      <span class="ic mdi" :class="{ lit: card.lit, thumb: card.face.display === 'live' || card.face.display === 'cover' }">{{ glyph(card.icon) }}</span>
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
