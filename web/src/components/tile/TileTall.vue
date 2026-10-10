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

const props = defineProps<{ card: TileCardView }>();
// The same card for as long as this face stands (useTileCard): read without going through the props each time.
const card = props.card;
// A tall card's slider has a white mark where its fill ends.
const rangeStyle = computed(() => ({ ...card.sliderStyle, "--fill": `${card.fill}%` }));
</script>

<template>
  <template v-if="card.face.kind === 'big-key'">
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
    <CoverTilePreview v-if="card.face.coverExtended" :primary="card.face.tallControls" :entity-state="card.current?.state || ''" :attributes="card.current?.a || {}" />
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
      <span v-if="card.face.tallControls" class="ctl" :class="{ playback: card.face.tallControls === 'playback' }">
        <span v-if="card.face.tallControls === 'toggle'" class="tog" :class="{ off: !card.on }"></span>
        <span v-else-if="card.face.tallControls === 'setpoint'" class="stp"><span class="mdi">{{ card.key("minus") || "−" }}</span><RangeChip v-if="card.chip" :chip="card.chip" :icon="card.key(card.chip.icon)" /><b v-else :style="{ '--pill-ems': textEms(card.texts.setpoint + '8') }">{{ card.texts.setpoint }}</b><span class="mdi">{{ card.key("plus") || "+" }}</span></span>
        <ModeBar v-else-if="card.face.tallControls === 'mode' && card.face.thermostat" :a="card.current?.a || {}" :mode="card.current?.state || ''" :domain="card.domain" place="tall" :columns="card.shape.columns" />
        <template v-else-if="card.face.tallKeys.length"><span v-for="(control, i) in card.face.tallKeys" :key="i" class="key mdi" :class="{ primary: control.primary, disabled: control.disabled, active: control.mode === card.current?.state }">{{ card.key(control.icon) }}</span></template>
        <span v-else-if="card.face.tallControls === 'stepper'" class="stp"><span class="mdi">{{ card.key("minus") || "−" }}</span><b>{{ card.texts.value }}</b><span class="mdi">{{ card.key("plus") || "+" }}</span></span>
        <template v-else-if="card.face.tallControls === 'volume'"><span v-if="card.features & bits('media_player', 'VOLUME_SET')" class="range" :style="rangeStyle"></span><span v-if="card.features & bits('media_player', 'VOLUME_MUTE')" class="key mdi">{{ card.key(card.current?.a?.is_volume_muted ? 'volume-off' : 'volume-high') }}</span></template>
        <span v-else-if="card.face.tallControls === 'run'" class="run">{{ card.texts.runText }}</span>
        <span v-else class="range" :style="rangeStyle"></span>
      </span>
    </template>
  </template>
</template>

<style scoped src="./parts.css"></style>
<style scoped>
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
