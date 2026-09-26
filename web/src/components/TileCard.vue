<script setup lang="ts">
import { editorLayout } from "../store";
const { grid, pageOf } = editorLayout;

// A card on the mockup, drawn with what Home Assistant reports right now. A placeholder is the tile being
// dragged, drawn where it will land.
import { computed, nextTick, ref, watch } from "vue";
import { vDrag } from "../drag";
import { numberText, t, te } from "../i18n";
import { dimensions, sizeOf, inlineControlKind, displayName, effectiveControls, isFull, isWide, pageTarget } from "../model/layout";
import { clockText, glyph } from "../model/topbar";
import { clock24, entityName, isSelected, liveOf, numberMarks, openTile, placeTile, removeTile, screenBuiltinName, screenText, state, tileIconCp, unitSuffix } from "../store";
import { tilePalette, tileActive } from "../model/tile-palette";
import type { Tile } from "../types";
import TileResize from "./TileResize.vue";
import { availableControl, controlKeys } from "../model/tall-controls";
import { coverPrimary, hasCoverTilt } from "../model/tall-controls";
import CoverTilePreview from "./CoverTilePreview.vue";
import MarqueeText from "./MarqueeText.vue";
import SensorHistory from './SensorHistory.vue';

const props = defineProps<{ tile: Tile; slot: number; placeholder?: boolean; preview?: boolean }>();
const emit = defineEmits<{ navigate: [tileId: string] }>();
function activate() {
  if (props.preview) { if (goesTo.value && props.tile.id) emit('navigate', props.tile.id); }
  else if (live.value) openTile(props.tile);
}
// A built-in card is named as the screens name it, in their language (app 0.2.90).
const name = computed(() => props.tile.name || (domain.value === "screen" && screenBuiltinName(props.tile.entity)) || entityName(props.tile.entity));
const shape = computed(() => dimensions(sizeOf(props.tile), grid));
const climateModes = computed(() => domain.value === 'climate' && effectiveControls(props.tile, state.inventory) === 'setpoint_mode' && shape.value.rows > 1);
const tall = computed(() => shape.value.rows > 1 && (!full.value || coverExtended.value || climateModes.value) && ["standard", "cover"].includes(display.value));
const full = computed(() => isFull(props.tile));
const wide = computed(() => isWide(props.tile) && !full.value);
const tallAction = computed(() => tall.value && (props.tile.entity === "screen.settings" || !!goesTo.value));
const goesTo = computed(() => pageTarget(props.tile.entity));
const background = computed(() => state.inventory.backgrounds?.[props.tile.options?.background || ""]?.color);
const bare = computed(() => props.tile.options?.background === "none");
// A settings card stays a plain card, as the screen draws it, even when an older layout gave it a clock face (GitHub #47).
const display = computed(() => props.tile.entity === "screen.settings" ? "standard" : props.tile.options?.display || "standard");
const note = computed(() => (display.value !== "standard" ? displayName(display.value) : ""));
const controls = computed(() => {
  const selected = effectiveControls(props.tile, state.inventory);
  // A card one row high draws the setpoint alone, as the screen does (resolve_controls).
  if (selected === 'setpoint_mode' && shape.value.rows < 2) return 'setpoint';
  if (domain.value !== 'cover') return selected;
  const primary = coverPrimary(selected);
  return primary === 'none' ? null : primary;
});
const coverExtended = computed(() => domain.value === 'cover' && hasCoverTilt(effectiveControls(props.tile, state.inventory)) && shape.value.rows > 1);
const tallControls = computed(() => availableControl(domain.value,
  props.tile.options?.inline === 'slider' ? inlineControlKind(domain.value) : controls.value,
  current.value?.state || '', current.value?.a || {}));
const tallKeys = computed(() => controlKeys(domain.value, tallControls.value, current.value?.state || '', current.value?.a || {}));
// As many mode keys as the screen fits: a wider card holds more (firmware 0.3.1 render_tall).
const modeKeys = computed(() => tallControls.value === 'setpoint_mode' ? controlKeys('climate', 'mode', current.value?.state || '', current.value?.a || {}, shape.value.columns > 1 ? 5 : 3) : []);
// An on/off card stands as one centred stack, like the built-in action cards (firmware 0.3.1 render_tall).
const tallStack = computed(() => tall.value && tallControls.value === 'toggle');
// The value the body shows large; the same words are not repeated under the name (a second line of your own stays).
const bodyText = computed(() => {
  if (!tall.value || tallAction.value || tallStack.value || gone.value || coverExtended.value) return '';
  if (domain.value === 'media_player') return String(current.value?.a?.media_title || '');
  if (domain.value === 'climate' || domain.value === 'screen') return '';
  return domain.value === 'light' && isOn.value ? `${fill.value}%` : status.value;
});
const headStatus = computed(() => bodyText.value && (status.value === bodyText.value || status.value.startsWith(bodyText.value + ' ')) ? '' : status.value);
const domain = computed(() => props.tile.entity.split(".")[0]);
const cp = computed(() => state.inventory.icons?.controls || {});
const key = (n: string) => (cp.value[n] ? glyph(cp.value[n]) : "");
const chosen = computed(() => isSelected(props.tile) && state.inspector?.kind === "tile");
const live = computed(() => !props.placeholder && state.layout?.tiles.some((tile) => tile.id === props.tile.id));
const label = computed(() => t("editor.tile_card.label", { name: name.value, slot: (props.slot % grid.slots) + 1, page: pageOf(props.slot) + 1 }));
const now = computed(() => new Date(state.now));
const hourAngle = computed(() => (now.value.getHours() % 12 + now.value.getMinutes() / 60) * 30);
const minuteAngle = computed(() => now.value.getMinutes() * 6);
// The flip clock's two blocks, as the screen draws them: "07" "12" on 24 hours, "7" "12" with AM or PM on 12.
const flipHours = computed(() => clock24.value ? String(now.value.getHours()).padStart(2, "0") : String(now.value.getHours() % 12 || 12));
const flipMinutes = computed(() => String(now.value.getMinutes()).padStart(2, "0"));
const amPm = computed(() => screenText(`screen.time.${now.value.getHours() < 12 ? "am" : "pm"}`));
const clockDate = computed(() => screenText('screen.date.full', {
  weekday: screenText(`screen.date.weekdays.${now.value.getDay()}`),
  day: now.value.getDate(),
  month: screenText(`screen.date.months.${now.value.getMonth()}`),
}));

// ---- Live values ----
const current = computed(() => (domain.value === "screen" ? null : liveOf(props.tile.entity)));
const palette = computed(() => tilePalette(props.tile.entity, current.value));
const gone = computed(() => !current.value || ["unavailable", "unknown", ""].includes(current.value.state));
const on = computed(() => tileActive(props.tile.entity, current.value));
const isOn = computed(() => ["light", "switch", "input_boolean", "fan"].includes(domain.value) && current.value?.state === "on");
const unit = computed(() => current.value?.a?.unit_of_measurement as string | undefined);
const capital = (text: string) => text.charAt(0).toUpperCase() + text.slice(1).replace(/_/g, " ");
// Numbers as the screens write them, "1,234.5" or "1.234,5" (app 0.2.90): a state only with a unit, or of an entity
// that is a number itself, as the firmware does (value_text); an id-like "1234" without a unit stays as it is.
const num = (value: unknown) => numberText(value as string | number, numberMarks.value);
const NUMERIC = ["number", "input_number", "counter"];
const value = (state: string) => (unit.value || NUMERIC.includes(domain.value) ? `${num(state)}${unitSuffix(unit.value)}` : state);
// The screens' own words for a state where Home Assistant hands us none (screen.ha, Home Assistant's words in the
// screens' language, app 0.2.90): a binary sensor's by its device class, on and off, and the states of the domains
// the screen names itself. A weather's windy-variant is windy there too.
const HA_WORDS: Record<string, string> = { climate: "climate", cover: "cover", media_player: "media", person: "person", sun: "sun", vacuum: "vacuum", weather: "weather", alarm_control_panel: "alarm" };
function haWord(c: { state: string; a: Record<string, any> }) {
  const key = (path: string) => (te(`screen.ha.${path}`) ? screenText(`screen.ha.${path}`) : "");
  const value = c.state === "windy-variant" ? "windy" : c.state.replace(/-/g, "_");
  if (domain.value === "binary_sensor" && ["on", "off"].includes(value)) return key(`binary.${c.a?.device_class}_${value}`) || key(value);
  if (HA_WORDS[domain.value]) return key(`${HA_WORDS[domain.value]}.${value}`) || (["on", "off"].includes(value) ? key(value) : "");
  return ["on", "off"].includes(value) ? key(value) : "";
}
// A scene, script or button has no state worth a word: its state is the moment it last ran.
const NO_STATUS = ["scene", "script", "button", "input_button"];
// The text under the name: Home Assistant's word where it has one, the value with its unit for a sensor.
const status = computed(() => {
  const c = current.value;
  if (!c || NO_STATUS.includes(domain.value)) return note.value;
  if (gone.value) return screenText(c.state === "unknown" ? "editor.mockup.unknown" : "screen.ha.unavailable");
  const a = c.a || {};
  const word = c.word || haWord(c) || capital(c.state);
  if (domain.value === "climate") return `${a.current_temperature !== undefined ? `${num(a.current_temperature)}° · ` : ""}${word}`;
  if (domain.value === "weather") return `${word}${a.temperature !== undefined ? ` · ${num(a.temperature)}°` : ""}`;
  if (domain.value === "cover" && a.current_position !== undefined && a.current_position > 0 && a.current_position < 100) return `${word} · ${a.current_position}${unitSuffix("%")}`;
  if (domain.value === "media_player" && a.media_title) return `${word} · ${a.media_title}`;
  if (domain.value === "sensor" || NUMERIC.includes(domain.value)) return value(c.state);
  return word;
});
// The big value of the watch display; its unit sits beside it in small letters.
const bigValue = computed(() => (current.value && !gone.value ? (unit.value || NUMERIC.includes(domain.value) ? num(current.value.state) : current.value.state) : "—"));
// The small slider's fill, from what the entity reports; off is empty, like the screen's grey fill.
const fill = computed(() => {
  const c = current.value;
  if (!c || gone.value) return 0;
  const a = c.a || {};
  if (domain.value === "light") return c.state === "on" ? (a.brightness !== undefined ? Math.round((a.brightness / 255) * 100) : 100) : 0;
  if (domain.value === "fan") return c.state === "on" ? (a.percentage ?? 100) : 0;
  // A blind's bar fills with its closed part, as on the screen (firmware 0.2.66+) and in Home Assistant's cover dialog.
  if (domain.value === "cover") return 100 - (a.current_position ?? (c.state === "open" ? 100 : 0));
  if (domain.value === "media_player") return Math.round((a.volume_level ?? 0) * 100);
  if (domain.value === "number" || domain.value === "input_number") {
    const value = Number(c.state), min = Number(a.min ?? 0), max = Number(a.max ?? 100);
    return Number.isFinite(value) && max > min ? Math.round(((value - min) / (max - min)) * 100) : 0;
  }
  return 0;
});
// The key on a scene, script or button, and the page a navigation tile opens, as the screen labels them.
const runText = computed(() => screenText(`screen.ha.button.${({ scene: "activate", script: "run" } as Record<string, string>)[domain.value] || "press"}`));
const pageLink = computed(() => `${screenText("screen.tile.page", { n: goesTo.value })} ›`);
const sliderStyle = computed(() => ({ background: `linear-gradient(to right, ${palette.value.accent} ${fill.value}%, ${palette.value.track} ${fill.value}%)` }));
const volumeStyle = sliderStyle;
// The add-on prepares artwork; source URLs and HA credentials stay server-side.
const artwork = computed(() => tall.value && display.value === 'cover' && domain.value === 'media_player' && current.value?.a?.artwork_mark
  ? `api/media-art?entity=${encodeURIComponent(props.tile.entity)}&v=${encodeURIComponent(String(current.value.a.artwork_mark))}` : '');
const artworkLoaded = ref(false);
watch(artwork, () => { artworkLoaded.value = false; });
// A live camera on a 1x2 or 2x2 tile fills the card (app 0.3.8): the add-on's picture, cut the way the tile asks, with
// the name at the bottom or nothing on it. Until the picture is here, the head as on the screen.
const cameraCard = computed(() => shape.value.rows > 1 && !full.value && display.value === 'live' && ['camera', 'image'].includes(domain.value));
const cameraPicture = computed(() => cameraCard.value ? `api/camera-preview?entity=${encodeURIComponent(props.tile.entity)}` : '');
const cameraLoaded = ref(false);
watch(cameraPicture, () => { cameraLoaded.value = false; });
const mediaSubtitle = computed(() => [current.value?.a?.media_artist, current.value?.a?.media_album_name].filter(Boolean).join(' · '));
const features = computed(() => Number(current.value?.a?.supported_features || 0));
// The screens give a control that fills its room the content width of one cell, so its edges stand where the
// cards above and below have theirs (runtime_tiles::cell_content_width); keys, a switch and a run key keep their
// own size. A double-width card is two cells, so that is half its room minus the gap and the paddings.
const FILLS_CELL = ["brightness", "speed", "position", "slider", "volume", "setpoint"];
const fillsCell = computed(() => FILLS_CELL.includes(controls.value || "") || (controls.value === "stepper" && !domain.value.endsWith("select")));
const setpoint = computed(() => {
  const temperature = current.value?.a?.temperature;
  return temperature !== undefined && temperature !== null ? `${num(temperature)}°` : "—";
});

async function onKey(e: KeyboardEvent) {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); activate(); return; }
  if (props.preview) return;
  // Up and down are a row of the screen's grid, whatever its columns; left and right one cell.
  const step = ({ ArrowLeft: -1, ArrowRight: 1, ArrowUp: -grid.columns, ArrowDown: grid.columns } as Record<string, number>)[e.key];
  if (!step) return;
  e.preventDefault();
  // A wide card owns its row: every arrow means the row above or below. A full card moves by the page.
  if (placeTile(props.tile, props.tile.slot + (full.value ? Math.sign(step) * grid.slots : step))) {
    await nextTick();
    document.querySelector<HTMLElement>(`.pages [data-slot="${props.tile.slot}"]`)?.focus();
  }
}
</script>

<template>
  <div class="tile" :class="{ wide, full, tall, 'tall-action': tallAction || tallStack, photo: artworkLoaded && !!artwork, camera: cameraCard && cameraLoaded, bare, placeholder: placeholder || !live, chosen }" :data-slot="slot" :data-tile-id="tile.id" :data-columns="shape.columns" :data-rows="shape.rows"
    :style="{ gridColumn: `${slot % grid.columns + 1} / span ${shape.columns}`, gridRow: `${Math.floor(slot % grid.slots / grid.columns) + 1} / span ${shape.rows}`, ...(background && !bare ? { backgroundColor: background } : {}), '--tile-icon': palette.icon, '--tile-circle': palette.circle, '--tile-accent': palette.accent }"
    :tabindex="(preview ? goesTo : live) ? 0 : -1" :role="(preview ? goesTo : live) ? 'button' : undefined" :aria-label="live ? label : undefined"
    v-drag="preview ? null : { kind: 'tile', tile }" @click="activate" @keydown="live && onKey($event)">
    <template v-if="display === 'analog'">
      <svg class="clockface" viewBox="0 0 60 60" aria-hidden="true">
        <circle cx="30" cy="30" r="27" fill="#fff" stroke="#c9ccd1" />
        <line v-for="a in [0, 90, 180, 270]" :key="a" x1="30" y1="5" x2="30" y2="9" stroke="#1b1b1b" stroke-width="1.5" :transform="`rotate(${a} 30 30)`" />
        <line x1="30" y1="30" x2="30" y2="16" stroke="#1b1b1b" stroke-width="2.4" stroke-linecap="round" :transform="`rotate(${hourAngle} 30 30)`" />
        <line x1="30" y1="30" x2="30" y2="11" stroke="#1b1b1b" stroke-width="1.6" stroke-linecap="round" :transform="`rotate(${minuteAngle} 30 30)`" />
        <circle cx="30" cy="30" r="1.8" fill="#1b1b1b" />
      </svg>
      <span v-if="wide" class="lead"><span class="tx"><span class="nm">{{ name }}</span><span class="st">{{ note }}</span></span></span>
    </template>
    <template v-else-if="display === 'dial' && domain === 'screen'">
      <span class="face-clock" :class="{ upright: !wide || tall || full }">
        <svg class="calm-dial" viewBox="0 0 60 60" aria-hidden="true">
          <circle cx="30" cy="30" r="29" fill="#1b1b1b" />
          <line v-for="a in [0, 90, 180, 270]" :key="a" x1="30" y1="4" x2="30" y2="11" stroke="#fff" stroke-width="3" stroke-linecap="round" :transform="`rotate(${a} 30 30)`" />
          <circle v-for="a in [30, 60, 120, 150, 210, 240, 300, 330]" :key="a" cx="30" cy="6" r="1.6" fill="#9e9e9e" :transform="`rotate(${a} 30 30)`" />
          <line x1="30" y1="30" x2="30" y2="15" stroke="#fff" stroke-width="4.5" stroke-linecap="round" :transform="`rotate(${hourAngle} 30 30)`" />
          <line x1="30" y1="30" x2="30" y2="8" stroke="#2196f3" stroke-width="3" stroke-linecap="round" :transform="`rotate(${minuteAngle} 30 30)`" />
          <circle cx="30" cy="30" r="3.6" fill="#2196f3" />
        </svg>
        <span v-if="wide || tall || full" class="face-text"><span class="big">{{ clockText(clock24, now) }}</span><span class="st">{{ clockDate }}</span></span>
      </span>
    </template>
    <template v-else-if="display === 'flip' && domain === 'screen'">
      <span class="face-clock flip">
        <span class="blocks"><span class="block">{{ flipHours }}</span><span class="block">{{ flipMinutes }}</span><small v-if="!clock24">{{ amPm }}</small></span>
        <span v-if="wide && !tall && !full" class="face-text"><span class="st">{{ clockDate }}</span></span>
      </span>
    </template>
    <template v-else-if="display === 'digital' && domain === 'screen'">
      <span class="digital-clock"><span class="big">{{ clockText(clock24, now) }}</span><span class="st">{{ clockDate }}</span></span>
    </template>
    <template v-else-if="display === 'graph' && domain === 'sensor'">
      <span class="head"><span class="ic mdi">{{ glyph(tileIconCp(tile)) }}</span><span class="tx"><span class="nm">{{ name }}</span><span class="st">{{ status }}</span></span></span>
      <SensorHistory :entity="tile.entity" :hours="Number(tile.options?.history_hours || 24)" />
    </template>
    <template v-else-if="cameraCard">
      <img v-if="cameraPicture" :key="cameraPicture" class="camera-art" :class="tile.options?.fit === 'contain' ? 'contain' : 'fill'" :src="cameraPicture" alt="" @load="cameraLoaded = true" @error="cameraLoaded = false" />
      <span v-if="!cameraLoaded" class="head"><span class="ic mdi">{{ glyph(tileIconCp(tile)) }}</span><span class="tx"><span class="nm">{{ name }}</span><span v-if="status" class="st" :class="{ off: gone }">{{ status }}</span></span></span>
      <span v-else-if="tile.options?.overlay !== 'none'" class="camera-name"><span>{{ name }}</span></span>
    </template>
    <template v-else-if="full && !tall">
      <span class="ic mdi" :class="{ lit: isOn, thumb: display === 'live' || display === 'cover' }">{{ glyph(tileIconCp(tile)) }}</span>
      <span class="lead">
        <span class="nm">{{ name }}</span>
        <span v-if="goesTo" class="goto">{{ pageLink }}</span>
        <span v-else-if="display === 'watch'" class="big">{{ bigValue }}<small v-if="unit && !gone">{{ unit }}</small></span>
        <span v-else-if="status" class="st" :class="{ off: gone }">{{ status }}</span>
      </span>
      <span v-if="tile.options?.inline === 'slider'" class="mini-slider" :style="sliderStyle"></span>
      <span v-if="controls" class="ctl">
        <span v-if="controls === 'toggle'" class="tog" :class="{ off: !on }"></span>
        <span v-else-if="controls === 'setpoint'" class="stp"><span class="mdi">{{ key("minus") || "−" }}</span><b>{{ setpoint }}</b><span class="mdi">{{ key("plus") || "+" }}</span></span>
        <template v-else-if="controls === 'volume'"><span class="range" :style="volumeStyle"></span><span class="key mdi">{{ key("volume-high") }}</span></template>
        <template v-else-if="controls === 'playback'"><span class="key mdi">{{ key("skip-previous") }}</span><span class="key mdi">{{ key(on ? "pause" : "play") || key("play") }}</span><span class="key mdi">{{ key("skip-next") }}</span></template>
        <template v-else-if="controls === 'buttons' && domain === 'cover'"><span class="key mdi">{{ key("arrow-expand-horizontal") }}</span><span class="key mdi">{{ key("stop") }}</span><span class="key mdi">{{ key("arrow-collapse-horizontal") }}</span></template>
        <span v-else-if="controls === 'run'" class="run">{{ runText }}</span>
        <span v-else class="range" :style="sliderStyle"></span>
      </span>
    </template>
    <template v-else-if="tall">
      <img v-if="artwork" :key="artwork" class="tall-art" :src="artwork" alt="" @load="artworkLoaded = true" @error="artworkLoaded = false" />
      <span class="head">
        <span class="ic mdi">{{ glyph(tileIconCp(tile)) }}</span>
        <span class="tx"><span class="nm">{{ name }}</span><span v-if="headStatus" class="st" :class="{ off: gone }">{{ headStatus }}</span></span>
      </span>
      <CoverTilePreview v-if="coverExtended" :primary="tallControls" :entity-state="current?.state || ''" :attributes="current?.a || {}" />
      <span v-else-if="domain === 'climate' && (tallControls === 'setpoint' || tallControls === 'setpoint_mode')" class="tall-setpoint">
        <span class="target"><span class="key mdi">{{ key('minus') || '−' }}</span><b>{{ setpoint }}</b><span class="key mdi">{{ key('plus') || '+' }}</span></span>
        <span class="st">{{ current?.a?.current_temperature !== undefined ? screenText('screen.climate.now', { value: `${num(current.a.current_temperature)}°` }) : status }}</span>
        <span v-if="modeKeys.length" class="ctl modes"><span v-for="(control, i) in modeKeys" :key="i" class="key mdi" :class="{ active: control.mode === current?.state }">{{ key(control.icon) }}</span></span>
      </span>
      <template v-else>
        <span v-if="!tallAction" class="tall-body">
          <template v-if="domain === 'media_player' && !gone">
            <MarqueeText class="track-title" :text="String(current?.a?.media_title || '')" /><span v-if="mediaSubtitle" class="st">{{ mediaSubtitle }}</span>
          </template>
          <span v-else-if="domain === 'climate' && !gone" class="target-value">{{ current?.a?.current_temperature !== undefined ? `${num(current.a.current_temperature)}°` : '—' }}</span>
          <span v-else-if="domain !== 'screen' && !gone && tallControls !== 'toggle'" class="target-value">{{ domain === 'light' && isOn ? `${fill}%` : status }}</span>
        </span>
      <span v-if="tallControls" class="ctl" :class="{ playback: tallControls === 'playback' }">
        <span v-if="tallControls === 'toggle'" class="tog" :class="{ off: !on }"></span>
        <span v-else-if="tallControls === 'setpoint'" class="stp"><span class="mdi">{{ key("minus") || "−" }}</span><b>{{ setpoint }}</b><span class="mdi">{{ key("plus") || "+" }}</span></span>
        <template v-else-if="tallKeys.length"><span v-for="(control, i) in tallKeys" :key="i" class="key mdi" :class="{ primary: control.primary, disabled: control.disabled, active: control.mode === current?.state }">{{ key(control.icon) }}</span></template>
        <span v-else-if="tallControls === 'stepper'" class="stp"><span class="mdi">{{ key("minus") || "−" }}</span><b>{{ bigValue }}</b><span class="mdi">{{ key("plus") || "+" }}</span></span>
        <template v-else-if="tallControls === 'volume'"><span v-if="features & 4" class="range" :style="volumeStyle"></span><span v-if="features & 8" class="key mdi">{{ key(current?.a?.is_volume_muted ? 'volume-off' : 'volume-high') }}</span></template>
        <span v-else-if="tallControls === 'run'" class="run">{{ runText }}</span>
        <span v-else class="range" :style="sliderStyle"></span>
      </span>
      </template>
    </template>
    <template v-else-if="wide">
      <span class="lead">
        <span class="ic mdi" :class="{ lit: isOn, thumb: display === 'live' || display === 'cover' }">{{ glyph(tileIconCp(tile)) }}</span>
        <span class="tx">
          <span class="nm">{{ name }}</span>
          <span v-if="goesTo" class="goto">{{ pageLink }}</span>
          <span v-else-if="display === 'watch'" class="big">{{ bigValue }}<small v-if="unit && !gone">{{ unit }}</small></span>
          <span v-else-if="status" class="st" :class="{ off: gone }">{{ status }}</span>
        </span>
      </span>
      <span v-if="tile.options?.inline === 'slider'" class="mini-slider" :style="sliderStyle"></span>
      <span v-if="controls" class="ctl" :class="{ fill: fillsCell }">
        <span v-if="controls === 'toggle'" class="tog" :class="{ off: !on }"></span>
        <span v-else-if="controls === 'setpoint'" class="stp"><span class="mdi">{{ key("minus") || "−" }}</span><b>{{ setpoint }}</b><span class="mdi">{{ key("plus") || "+" }}</span></span>
        <template v-else-if="controls === 'stepper' && domain.endsWith('select')"><span class="key mdi">{{ key("chevron-left") }}</span><span class="key mdi">{{ key("chevron-right") }}</span></template>
        <span v-else-if="controls === 'stepper'" class="stp"><span class="mdi">{{ key("minus") || "−" }}</span><b>{{ bigValue }}</b><span class="mdi">{{ key("plus") || "+" }}</span></span>
        <template v-else-if="controls === 'mode'"><span class="key mdi">{{ key("power") }}</span><span class="key mdi">{{ key("fire") }}</span><span class="key mdi">{{ key("snowflake") }}</span></template>
        <template v-else-if="controls === 'volume'"><span class="range" :style="volumeStyle"></span><span class="key mdi">{{ key("volume-high") }}</span></template>
        <template v-else-if="controls === 'playback'"><span class="key mdi">{{ key("skip-previous") }}</span><span class="key mdi">{{ key(on ? "pause" : "play") || key("play") }}</span><span class="key mdi">{{ key("skip-next") }}</span></template>
        <template v-else-if="controls === 'buttons' && domain === 'cover'"><span class="key mdi">{{ key("arrow-expand-horizontal") }}</span><span class="key mdi">{{ key("stop") }}</span><span class="key mdi">{{ key("arrow-collapse-horizontal") }}</span></template>
        <template v-else-if="controls === 'buttons' && domain === 'vacuum'"><span class="key mdi">{{ key("play") }}</span><span class="key mdi">{{ key("stop") }}</span><span class="key mdi">{{ key("home-map-marker") }}</span></template>
        <template v-else-if="controls === 'buttons' && domain === 'timer'"><span class="key mdi">{{ key("play") }}</span><span class="key mdi">{{ key("close") }}</span></template>
        <span v-else-if="controls === 'run'" class="run">{{ runText }}</span>
        <span v-else class="range" :style="sliderStyle"></span>
      </span>
    </template>
    <template v-else>
      <!-- As the screen draws it: the icon on the left, the name and the value beside it. A watch
           card puts the name on top and the big value under it; the small slider runs underneath. -->
      <span class="head" :class="{ top: display === 'watch' }">
        <span class="ic mdi" :class="{ lit: isOn, thumb: display === 'live' || display === 'cover' }">{{ glyph(tileIconCp(tile)) }}</span>
        <span class="tx">
          <span class="nm">{{ name }}</span>
          <span v-if="goesTo" class="goto">{{ pageLink }}</span>
          <span v-else-if="display !== 'watch' && status" class="st" :class="{ off: gone }">{{ status }}</span>
        </span>
      </span>
      <span v-if="display === 'watch'" class="big">{{ bigValue }}<small v-if="unit && !gone">{{ unit }}</small></span>
      <span v-if="tile.options?.inline === 'slider'" class="mini-slider" :style="sliderStyle"></span>
    </template>
    <TileResize v-if="live && !preview && !placeholder" :tile="tile" />
    <button v-if="live && !preview" type="button" class="remove" :title="t('editor.tile_card.remove')" :aria-label="t('editor.tile_card.remove_named', { name })" @click.stop="removeTile(tile)">✕</button>
  </div>
</template>

<style scoped>
.tile .ic:not(.thumb) { color: var(--tile-icon); background: var(--tile-circle); border-radius: 50%; padding: 5px; }
.tile .tog:not(.off) { background: var(--tile-accent); }
.face-clock { display: flex; align-items: center; gap: 10px; min-width: 0; width: 100%; height: 100%; padding-inline: 2px; }
.face-clock.upright { flex-direction: column; justify-content: center; gap: 4px; }
.face-clock .calm-dial { height: 100%; max-height: 100%; aspect-ratio: 1; flex: none; }
.face-clock.upright .calm-dial { height: auto; width: min(70%, 100%); max-height: 70%; }
.face-clock .face-text { display: grid; gap: 1px; min-width: 0; }
.face-clock.upright .face-text { text-align: center; }
.face-clock .face-text .big { font-size: 22px; font-weight: 500; }
.face-clock .face-text .st { font-size: 9px; }
.face-clock.flip { justify-content: center; }
.face-clock .blocks { display: flex; align-items: baseline; gap: 3px; }
.face-clock .block { background: #f1f1f1; border-radius: 4px; padding: 1px 5px; font-size: 24px; font-weight: 500; line-height: 1.25; background-image: linear-gradient(transparent calc(50% - .5px), #fff calc(50% - .5px), #fff calc(50% + .5px), transparent calc(50% + .5px)); }
.face-clock .blocks small { font-size: 9px; margin-left: 2px; }
.digital-clock { display: grid; gap: 3px; align-content: center; text-align: center; min-width: 0; width: 100%; height: 100%; }
.digital-clock .big { font-size: 28px; font-weight: 400; }
.digital-clock .st { font-size: 9px; }
/* Additional rows extend the existing header and controls. All single-row selectors remain unchanged. */
.tile.tall { flex-direction: column; align-items: stretch; justify-content: start; container-type: size; }
.tile.tall .head { flex: none; }
.tile.full.tall { justify-content: start; text-align: left; }
.tile.tall.tall-action { justify-content: center; }
.tile.tall.tall-action .head { flex-direction: column; justify-content: center; text-align: center; }
.tile.tall.tall-action .tx { flex: none; width: 100%; }
.tile.tall .tog { --toggle-height: clamp(22px, 18cqh, 36px); height: var(--toggle-height); width: calc(2 * var(--toggle-height)); border-radius: 99px; flex: none; }
.tile.tall .tog::after { width: calc(var(--toggle-height) - 6px); height: calc(var(--toggle-height) - 6px); top: 3px; right: 3px; }
.tile.tall .tog.off::after { right: auto; left: 3px; }
.tile.tall .tall-body { flex: 1; min-height: 0; display: flex; flex-direction: column; justify-content: center; overflow: hidden; gap: 3px; }
.track-title { font-weight: 600; font-size: clamp(12px, 9cqh, 21px); line-height: 1.2; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tile.tall .ctl { justify-content: center; width: 100%; }
.tile.tall .range { flex: 1; height: clamp(22px, 18cqh, 36px); border-radius: 10px; position: relative; }
.tile.tall .range::after { content: ''; width: 3px; height: 50%; background: white; border-radius: 2px; position: absolute; left: clamp(4px, v-bind('fill + "%"'), calc(100% - 6px)); top: 25%; }
.tile.tall .key.disabled { opacity: .35; }
.tile.tall .key { width: clamp(22px, 18cqh, 36px); height: clamp(22px, 18cqh, 36px); min-width: 0; padding: 0; border-radius: 50%; }
.tile.tall .playback .key.primary, .tile.tall .key.active { background: var(--tile-accent); color: white; }
.tall-setpoint { flex: 1; display: flex; flex-direction: column; min-height: 0; justify-content: center; gap: 5px; text-align: center; }
.target { flex: 1; display: flex; justify-content: space-between; align-items: center; gap: 6px; }
.target b, .target-value { font-size: clamp(16px, 18cqh, 42px); font-weight: 400; text-align: center; }
.tile.tall .tall-art { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; border-radius: inherit; opacity: 0; filter: brightness(.333); pointer-events: none; }
.tile.tall .head, .tile.tall .tall-body, .tile.tall .ctl, .tile.tall .tall-setpoint { position: relative; }
.tile.tall.photo .tall-art { opacity: 1; }
.tile.tall.photo, .tile.tall.photo .st, .tile.tall.photo .ctl { color: white; }
.tile.tall.photo .ic { background: #333; color: white; }
.tile.tall.photo .playback .key { background: transparent; }
.tile.tall.photo .playback .key.primary { background: white; color: #111; }
.tile .camera-art { position: absolute; inset: 0; width: 100%; height: 100%; border-radius: inherit; background: #000; opacity: 0; pointer-events: none; }
.tile .camera-art.fill { object-fit: cover; }
.tile .camera-art.contain { object-fit: contain; }
.tile.camera { justify-content: end; }
.tile.camera .camera-art { opacity: 1; }
/* The shade the add-on puts under the name (tile_art.FADE_SHARE, FADE_DEPTH). */
.tile .camera-name { position: absolute; inset: auto 0 0 0; height: 42%; padding: 0 9px 8px; display: flex; align-items: end; color: white; font-weight: 700; background: linear-gradient(to bottom, transparent, rgba(0, 0, 0, .59)); border-radius: 0 0 inherit inherit; pointer-events: none; }
.tile .camera-name > span { min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
</style>
