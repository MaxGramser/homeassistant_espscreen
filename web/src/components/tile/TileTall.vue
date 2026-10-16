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
// A player's volume beside its keys: standing at the right on a card wider than high, over the keys on a narrower one
// (runtime_tiles render_tall, media_standing).
const volume = computed(() => card.face.tallControls === "volume_playback" && Boolean(card.features & bits("media_player", "VOLUME_SET")));
const standing = computed(() => volume.value && card.shape.columns >= 2 && card.shape.columns >= card.shape.rows);
const standStyle = computed(() => ({ background: `linear-gradient(to top, ${card.palette.accent} ${card.fill}%, ${card.palette.track} ${card.fill}%)`, "--fill": `${card.fill}%` }));
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
    <CoverTilePreview v-if="card.face.coverExtended" :primary="card.face.tallControls" :entity-state="card.current?.state || ''" :attributes="card.current?.a || {}">
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
        <span v-else class="range" :style="rangeStyle"></span>
      </span>
    </template>
  </template>
</template>

<style scoped src="./parts.css"></style>
<style scoped>
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
