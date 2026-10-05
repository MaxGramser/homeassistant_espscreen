<script setup lang="ts">
import { editorLayout } from "../store";
const { grid: editorGrid } = editorLayout;

// A card on the mockup, drawn with what Home Assistant reports right now. A placeholder is the tile being
// dragged, drawn where it will land.
import { computed, nextTick, ref, watch } from "vue";
import { vDrag } from "../drag";
import { numberText, t, te } from "../i18n";
import { dimensions, sizeOf, inlineControlKind, displayName, effectiveControls, isFull, isWide, keysOf, pageTarget } from "../model/layout";
import { clockText, glyph } from "../model/topbar";
import { clock24, currentScreen, deviceStyle, pageBarShown, screenShape, isCompact, supports, pictures, entityName, isSelected, liveOf, numberMarks, openTile, placeTile, removeTile, screenBuiltinName, screenText, state, tileIconCp, toast, unitSuffix } from "../store";
import { energyPaints, modeColor, tilePalette, tileActive } from "../model/tile-palette";
import { cardContent, cardHeight, textEms, watchCard, watchPadding, wideChip, widestSetpoint } from "../model/ui-scale";
import { bits, drawable } from "../model/catalogue";
import type { Tile } from "../types";
import TileResize from "./TileResize.vue";
import { availableControl, controlKeys } from "../model/tall-controls";
import { coverPrimary, hasCoverTilt } from "../model/tall-controls";
import CoverTilePreview from "./CoverTilePreview.vue";
import ModeBar from "./ModeBar.vue";
import MarqueeText from "./MarqueeText.vue";
import SensorHistory from './SensorHistory.vue';
import rules from "../model/page-rules.json";

// `grid`: another screen's grid, for a card of that screen's home page on the overview (app 0.4.0); the editor's own
// screen otherwise.
// `round`: a key of a bedside clock (app 0.4.12), the same card in its round form. `keys`: a clock's keys where the card
// is drawn outside the editor's own layout (the overview).
const props = defineProps<{ tile: Tile; slot: number; placeholder?: boolean; preview?: boolean; grid?: { columns: number; rows: number; slots: number };
  round?: boolean; keys?: Tile[] }>();
const grid = computed(() => props.grid ?? editorGrid);
// A card of another screen, on the overview: drawn only, never picked up, focused or opened.
const foreign = computed(() => Boolean(props.grid));
const emit = defineEmits<{ navigate: [tileId: string] }>();
function activate() {
  if (props.preview) { if (goesTo.value && props.tile.id) emit('navigate', props.tile.id); }
  else if (live.value) openTile(props.tile);
}
// A built-in card is named as the screens name it, in their language (app 0.2.90).
// A favourite (app 0.4.42) is named after what it plays until it has a name of its own.
const favoritePlay = computed(() => display.value === 'favorite' && domain.value === 'media_player' ? (props.tile.options?.play as Record<string, string> | undefined) : undefined);
const name = computed(() => props.tile.name || favoritePlay.value?.title || (domain.value === "screen" && screenBuiltinName(props.tile.entity)) || entityName(props.tile.entity));
const shape = computed(() => dimensions(sizeOf(props.tile), grid.value));
// A thermostat: a climate, or a humidifier drawn with its parts in percent (firmware 0.42.0+, tile_controls::thermostat).
const thermostat = computed(() => domain.value === 'climate' || domain.value === 'humidifier');
const climateModes = computed(() => thermostat.value && effectiveControls(props.tile, state.inventory) === 'setpoint_mode' && shape.value.rows > 1);
const tall = computed(() => shape.value.rows > 1 && (!full.value || coverExtended.value || climateModes.value) && ["standard", "cover"].includes(display.value));
const full = computed(() => isFull(props.tile));
const wide = computed(() => isWide(props.tile) && !full.value);
const tallAction = computed(() => tall.value && (props.tile.entity === "screen.settings" || !!goesTo.value));
const goesTo = computed(() => pageTarget(props.tile.entity));
const background = computed(() => state.inventory.backgrounds?.[props.tile.options?.background || ""]?.color);
const bare = computed(() => props.tile.options?.background === "none");
// A settings card stays a plain card, as the screen draws it, even when an older layout gave it a clock face (GitHub #47).
// The bedside clock (app 0.4.12): big digits over its three key places, as the screen draws it.
const bedside = computed(() => props.tile.entity === "screen.nightstand");
// The energy card (app 0.4.77): the screen draws the house live from Home Assistant's Energy settings, as its own live view
// does; the mockup shows the diagram's shape, the sources around the house, in their paints.
const energyTile = computed(() => props.tile.entity === "screen.energy");
const energy = energyPaints();
const bedsideKeys = computed(() => props.keys ?? keysOf(state.layout, props.tile));
// As many places as the add-on lets this clock hold (page-rules.json, keyHolders).
const keyPlaces = computed(() => Array.from({ length: (rules.keyHolders as Record<string, number>)[props.tile.entity] || 0 }, (_, key) =>
  ({ key, tile: bedsideKeys.value.find((tile) => tile.key === key) }))
  .filter((place) => place.tile || !props.preview));
function markKey(key: number) {
  const marked = state.insertKey?.holder === props.tile.id && state.insertKey?.key === key;
  state.insertKey = marked ? null : { holder: props.tile.id!, key };
  if (state.insertKey) document.querySelector<HTMLInputElement>("#search")?.focus();
}
// What a key shows in its circle: its value where that is what it is for (a temperature), else its icon.
const roundValue = computed(() => ["sensor", "number", "input_number"].includes(domain.value) && current.value && !gone.value ? bigValue.value + ((unit.value || "").startsWith("°") ? "°" : unit.value === "%" ? "%" : "") : "");
const display = computed(() => props.tile.entity === "screen.settings" ? "standard" : props.tile.options?.display || "standard");
const note = computed(() => (display.value !== "standard" ? displayName(display.value) : ""));
// The screen draws a thermostat's range on its -/+ (firmware 0.19.0+); an older one gets such a thermostat without them.
const rangeReady = computed(() => currentScreen.value?.climate_range !== false);
const controls = computed(() => {
  // What the screen draws for this entity (model/catalogue.ts drawable, as the add-on sends it): an older screen gets a
  // thermostat with only a range without its -/+, one without a temperature to set never has them.
  const chosen = effectiveControls(props.tile, state.inventory);
  const drawn = chosen ? drawable(domain.value, chosen, current.value?.a || {}, rangeReady.value ? null : new Set<string>()) : null;
  const selected = drawn === 'none' ? null : drawn;
  // A card one row high draws the setpoint alone, as the screen does (resolve_controls).
  if (selected === 'setpoint_mode' && shape.value.rows < 2) return 'setpoint';
  if (domain.value !== 'cover') return selected;
  const primary = coverPrimary(selected);
  return primary === 'none' ? null : primary;
});
const coverExtended = computed(() => domain.value === 'cover' && hasCoverTilt(effectiveControls(props.tile, state.inventory)) && shape.value.rows > 1);
const tallControls = computed(() => availableControl(domain.value,
  props.tile.options?.inline === 'slider' ? inlineControlKind(domain.value) : controls.value,
  current.value?.state || '', current.value?.a || {}, rangeReady.value));
const tallKeys = computed(() => controlKeys(domain.value, tallControls.value, current.value?.state || '', current.value?.a || {}));
// The keys of a wide or full-page card's control, as the screen draws them for this entity (tile_controls::keys_for):
// only what it supports, in its state, never a fixed set.
const panelKeys = computed(() => controls.value && !['toggle', 'setpoint', 'volume', 'run', 'stepper', 'slider', 'brightness', 'speed', 'position'].includes(controls.value)
  ? controlKeys(domain.value, controls.value, current.value?.state || '', current.value?.a || {}) : []);
// As many mode keys as the screen fits: a wider card holds more (firmware 0.3.1 render_tall).
// A range's chip as the screen draws it (runtime_tiles range_chip, firmware 0.19.0): its number as large as the widest
// temperature allows on its own, and its heat or cool icon beside it only where that fits at the same size; otherwise
// the number alone in its end's colour. Measured whenever the chip changes size or text.
const chipObservers = new WeakMap<HTMLElement, ResizeObserver>();
function fitChip(el: HTMLElement) {
  const number = el.querySelector("b");
  if (!number || !el.clientWidth) return;
  // The glass's rule in the mockup's pixels: icon + half a gap + the widest number + a gap within the chip.
  const style = getComputedStyle(el), icon = parseFloat(style.getPropertyValue("--chip-icon")) || 0;
  const pad = parseFloat(style.getPropertyValue("--chip-pad")) || 0, ems = parseFloat(el.style.getPropertyValue("--chip-ems")) || 2;
  el.classList.toggle("lone", icon + 1.5 * pad + ems * parseFloat(getComputedStyle(number).fontSize) > el.clientWidth);
}
const vChipFit = {
  mounted(el: HTMLElement) {
    fitChip(el);
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => fitChip(el));
    observer.observe(el);
    chipObservers.set(el, observer);
  },
  updated: fitChip,
  unmounted(el: HTMLElement) { chipObservers.get(el)?.disconnect(); },
};
// A wide card's chip as the glass works it out (ui-scale wideChip): its face and whether its icon fits.
const glassScale = computed(() => Number(deviceStyle.value["--glass"]) || 1);
const wideFit = computed(() => rangeChip.value && wide.value
  ? wideChip(screenShape.value, state.documentGrid?.columns ?? screenShape.value.columns, widestSetpoint(current.value?.a || {})) : null);
// A thermostat's modes on a card of one row or the whole page: its mode bar (ModeBar), as the screen draws it.
const modeBar = computed(() => thermostat.value && controls.value === 'mode');
// An on/off card stands as one centred stack, like the built-in action cards (firmware 0.3.1 render_tall).
const tallStack = computed(() => tall.value && tallControls.value === 'toggle');
// A card that only switches or only runs, two rows tall, is one big key (firmware 0.17.0 big_key): a large circle, the
// name and the state, and the whole card is the key. A slider or another control keeps the head and its controls.
const BIG_KEY_DOMAINS = ["light", "switch", "input_boolean", "fan", "script", "scene", "button", "input_button"];
const bigKey = computed(() => tall.value && !full.value && supports(0, 17, 0) && BIG_KEY_DOMAINS.includes(domain.value)
  && props.tile.options?.inline !== "slider" && (!tallControls.value || tallControls.value === "toggle" || tallControls.value === "run"));
// The flip clock on a card two columns wide and two rows tall, or a whole page (firmware 0.17.0): the blocks share the
// width and the day and AM or PM stand on one line under them.
const flipWide = computed(() => (full.value || (shape.value.columns > 1 && shape.value.rows > 1)) && supports(0, 17, 0));
// The day under the wide flip clock, as the screen writes it: "Tuesday 29 Sep".
const flipDay = computed(() => `${screenText(`screen.date.weekdays.${now.value.getDay()}`)} ${screenText("screen.date.day_month", {
  day: now.value.getDate(), month: screenText(`screen.date.months_short.${now.value.getMonth()}`) })}`);
// The line under a big key's name, as the screen draws it: a lamp that is on says how bright, a script or scene when it
// last ran, anything else its state.
const bigKeyLine = computed(() => {
  if (domain.value === "light" && isOn.value && !gone.value) return `${fill.value}%`;
  if (NO_STATUS.includes(domain.value)) return current.value && !current.value.a?.last_triggered && ["script", "automation"].includes(domain.value) ? screenText("screen.script.never_run") : line.value;
  return line.value;
});
// The value the body shows large; the same words are not repeated under the name (a second line of your own stays).
const bodyText = computed(() => {
  if (!tall.value || tallAction.value || tallStack.value || gone.value || coverExtended.value) return '';
  if (domain.value === 'media_player') return String(current.value?.a?.media_title || '');
  if (thermostat.value || domain.value === 'screen') return '';
  return domain.value === 'light' && isOn.value ? `${fill.value}%` : status.value;
});
// The second line as chosen in the tile panel (app 0.2.105; drawn on the mockup since app 0.4.1): the screen's own
// line, nothing, words of your own, or a value of the entity. A value Home Assistant does not report leaves the
// line to the screen, as on the glass.
const sub = computed(() => String(props.tile.options?.sub ?? "auto"));
const line = computed(() => {
  if (sub.value === "none") return "";
  if (sub.value.startsWith("text:")) return sub.value.slice(5);
  if (sub.value.startsWith("attr:")) {
    const value = current.value?.a?.[sub.value.slice(5)];
    if (value !== undefined && value !== null && value !== "") return typeof value === "number" ? num(value) : String(value);
  }
  return status.value;
});
const headStatus = computed(() => bodyText.value && (line.value === bodyText.value || line.value.startsWith(bodyText.value + ' ')) ? '' : line.value);
const domain = computed(() => props.tile.entity.split(".")[0]);
const cp = computed(() => state.inventory.icons?.controls || {});
const key = (n: string) => (cp.value[n] ? glyph(cp.value[n]) : "");
const chosen = computed(() => isSelected(props.tile) && state.inspector?.kind === "tile");
const live = computed(() => !props.placeholder && state.layout?.tiles.some((tile) => tile.id === props.tile.id));
const label = computed(() => t("editor.tile_card.label", { name: name.value, slot: (props.slot % grid.value.slots) + 1, page: Math.floor(props.slot / grid.value.slots) + 1 }));
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
// An automation set to run on a tap looks like a script's button (firmware 0.7.0+, Tile::runs): coloured while it runs.
const runs = computed(() => domain.value === "automation" && props.tile.options?.tap === "run");
const palette = computed(() => tilePalette(props.tile.entity, current.value, runs.value));
const gone = computed(() => !current.value || ["unavailable", "unknown", ""].includes(current.value.state));
const on = computed(() => tileActive(props.tile.entity, current.value, runs.value));
const isOn = computed(() => (["light", "switch", "input_boolean", "fan", "remote", "humidifier"].includes(domain.value) || domain.value === "automation" && !runs.value) && current.value?.state === "on");
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
const HA_WORDS: Record<string, string> = { climate: "climate", cover: "cover", media_player: "media", person: "person", sun: "sun", vacuum: "vacuum", weather: "weather", alarm_control_panel: "alarm", lock: "lock" };
function haWord(c: { state: string; a: Record<string, any> }) {
  const key = (path: string) => (te(`screen.ha.${path}`) ? screenText(`screen.ha.${path}`) : "");
  const value = c.state === "windy-variant" ? "windy" : c.state.replace(/-/g, "_");
  if (domain.value === "binary_sensor" && ["on", "off"].includes(value)) return key(`binary.${c.a?.device_class}_${value}`) || key(value);
  if (HA_WORDS[domain.value]) return key(`${HA_WORDS[domain.value]}.${value}`) || (["on", "off"].includes(value) ? key(value) : "");
  return ["on", "off"].includes(value) ? key(value) : "";
}
// A thermostat set to a range (firmware 0.19.0), decided as Home Assistant's thermostat card decides it: a single target
// it supports and reports comes first, else a range it supports with both ends. The screen puts a chip between its -
// and +: the end they move, heat or cool, with its icon in that mode's colour; the low end first, as the screen does.
const rangeChip = computed(() => {
  const a = current.value?.a || {}, f = Number(a.supported_features || 0);
  if (domain.value !== "climate" || !rangeReady.value || (f & bits("climate", "TARGET_TEMPERATURE") && a.temperature != null) || !(f & bits("climate", "TARGET_TEMPERATURE_RANGE")) || a.target_temp_low == null || a.target_temp_high == null) return null;
  const digits = Number(a.target_temp_step || 0.5) >= 1 ? 0 : 1;
  return { icon: "fire", color: modeColor("heat"), text: `${num(Number(a.target_temp_low).toFixed(digits))}°`, ems: textEms(widestSetpoint(a)) };
});
// A thermostat's line as the screen writes it: with a control on the tile, what it is doing and the room's temperature
// (tile_controls::status_text); without one the temperature it is set to, and otherwise Home Assistant's own tile line,
// its state and the room's temperature (runtime_tiles' value line). Both temperatures as Home Assistant sends them.
function climateLine(c: { state: string; a?: Record<string, any> }, word: string) {
  const a = c.a || {};
  const now = a.current_temperature != null ? ` · ${num(String(a.current_temperature))}°` : "";
  const doing = te(`screen.ha.hvac_action.${a.hvac_action}`) ? screenText(`screen.ha.hvac_action.${a.hvac_action}`) : "";
  if (controls.value && controls.value !== "none") return `${doing || word}${now}`;
  if (c.state !== "off" && a.temperature != null) return `${num(String(a.temperature))}°`;
  return `${word}${now}`;
}
// A humidity as the screen writes it beside a humidifier (tile_controls::humidity_text): whole, or with the one decimal a
// sensor sends (45.5%).
const humidityText = (value: unknown) => {
  const v = Number(value);
  return `${num(Math.abs(v - Math.round(v)) < 0.05 ? Math.round(v) : Math.round(v * 10) / 10)}${unitSuffix("%")}`;
};
// What a thermostat measures, in its own unit: degrees, or a humidifier's humidity (tile_controls::reading_text).
const reading = (value: unknown) => (domain.value === "humidifier" ? humidityText(value) : `${num(value)}°`);
const measured = computed(() => current.value?.a?.[domain.value === "humidifier" ? "current_humidity" : "current_temperature"]);
// A humidifier's line as the screen writes it (tile_controls::climate_card_status, brief): Home Assistant's word for what
// it is doing (Off while it is off), else On or Off, and the humidity it measures. Home Assistant's tile line for it.
function humidifierLine(c: { state: string; a?: Record<string, any> }) {
  const a = c.a || {}, off = c.state !== "on", action = off ? "off" : String(a.action ?? "");
  const key = `screen.ha.humidifier_action.${action}`;
  const word = action && te(key) ? screenText(key) : screenText(off ? "screen.ha.off" : "screen.ha.on");
  return a.current_humidity != null ? `${word} · ${humidityText(a.current_humidity)}` : word;
}
// A scene, script or button has no state worth a word: its state is the moment it last ran.
const NO_STATUS = ["scene", "script", "button", "input_button"];
// The text under the name: Home Assistant's word where it has one, the value with its unit for a sensor.
const status = computed(() => {
  const c = current.value;
  if (!c || NO_STATUS.includes(domain.value)) return note.value;
  // A run button says Running while its actions run and Off while nothing starts it on its own, as on the screen.
  if (runs.value && !gone.value) return Number(c.a?.current) > 0 ? screenText("screen.script.running") : c.state === "off" ? screenText("screen.ha.off") : note.value;
  if (gone.value) return screenText(c.state === "unknown" ? "editor.mockup.unknown" : "screen.ha.unavailable");
  const a = c.a || {};
  const word = c.word || haWord(c) || capital(c.state);
  if (domain.value === "climate") return climateLine(c, word);
  if (domain.value === "humidifier") return humidifierLine(c);
  if (domain.value === "weather") return `${word}${a.temperature !== undefined ? ` · ${num(a.temperature)}°` : ""}`;
  if (domain.value === "cover" && a.current_position !== undefined && a.current_position > 0 && a.current_position < 100) return `${word} · ${a.current_position}${unitSuffix("%")}`;
  if (domain.value === "media_player" && a.media_title) return `${word} · ${a.media_title}`;
  // A remote that runs an activity names it (firmware 0.22.0+), as the screen does.
  if (domain.value === "remote" && c.state === "on" && a.current_activity) return String(a.current_activity);
  if (domain.value === "sensor" || NUMERIC.includes(domain.value)) return value(c.state);
  return word;
});
// The big value of the watch display; its unit sits beside it in small letters.
const bigValue = computed(() => (current.value && !gone.value ? (unit.value || NUMERIC.includes(domain.value) ? num(current.value.state) : current.value.state) : "—"));
// A Big number card as the glass lays it out in this card's room on this grid (ui-scale watchCard, app 0.4.74): the
// icon and the name above the number in the largest face that fits, or in a low cell the name small in the corner
// and the number under it. Before, the mockup stacked a head and a number of its own sizes, and in a low cell the
// number was cut off at its middle (GitHub #167). A card of another screen (the overview) keeps the old drawing.
const watchFace = computed(() => {
  if (display.value !== "watch" || full.value || foreign.value || props.round || goesTo.value || props.slot < 0) return null;
  const s = screenShape.value, g = grid.value, cell = props.slot % g.slots, pad = watchPadding(s, g.rows);
  const width = cardContent(s, g.columns, shape.value.columns, cell % g.columns);
  const height = cardHeight(s, g.rows, shape.value.rows, Math.floor(cell / g.columns), pageBarShown.value) - 2 * (pad + 1);
  return { pad, ...watchCard(s, width, height, bigValue.value, unit.value && !gone.value ? unit.value : "", pad) };
});
const glassPx = (n: number) => `${(n * glassScale.value).toFixed(2)}px`;
const watchStyle = computed(() => {
  const w = watchFace.value;
  if (!w) return null;
  const text = (box: { x: number; y: number; width: number; size: number; line: number }) =>
    ({ left: glassPx(box.x), top: glassPx(box.y), width: glassPx(box.width), fontSize: glassPx(box.size), lineHeight: glassPx(box.line) });
  const unit = w.unit && { fontSize: glassPx(w.unit.size), lineHeight: glassPx(w.unit.line) };
  // Under a head the number stands at the left and its unit at the right edge, as wide as its own letters. Alone, the
  // two are one row in the middle of the card, their bottoms in line, so the browser's letters cannot push either out.
  return { pad: { paddingBlock: glassPx(w.pad) },
    circle: { left: glassPx(w.circle.x), top: glassPx(w.circle.y), width: glassPx(w.circle.size), height: glassPx(w.circle.size), fontSize: glassPx(w.circle.icon) },
    title: text(w.title), value: w.stacked ? text(w.value) : { fontSize: glassPx(w.value.size), lineHeight: glassPx(w.value.line) },
    row: { top: glassPx(w.value.y), height: glassPx(w.value.line), gap: glassPx(w.unitGap) },
    unit: unit && (w.stacked ? { ...unit, right: "0", top: glassPx(w.unit!.y) } : unit) };
});
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
  // A humidifier's slider is the humidity it is set to over its own range (runtime_tiles slider_value), on or off.
  if (domain.value === "humidifier") {
    const target = Number(a.humidity), min = Number(a.min_humidity ?? 0), max = Number(a.max_humidity ?? 100);
    return a.humidity != null && Number.isFinite(target) && max > min ? Math.round(Math.min(1, Math.max(0, (target - min) / (max - min))) * 100) : 0;
  }
  if (domain.value === "number" || domain.value === "input_number") {
    const value = Number(c.state), min = Number(a.min ?? 0), max = Number(a.max ?? 100);
    return Number.isFinite(value) && max > min ? Math.round(((value - min) / (max - min)) * 100) : 0;
  }
  return 0;
});
// The key on a scene, script or button, and the page a navigation tile opens, as the screen labels them.
const runText = computed(() => screenText(`screen.ha.button.${({ scene: "activate", script: "run", automation: "run" } as Record<string, string>)[domain.value] || "press"}`));
const pageLink = computed(() => `${screenText("screen.tile.page", { n: goesTo.value })} ›`);
const sliderStyle = computed(() => ({ background: `linear-gradient(to right, ${palette.value.accent} ${fill.value}%, ${palette.value.track} ${fill.value}%)` }));
const volumeStyle = sliderStyle;
// The add-on prepares artwork; source URLs and HA credentials stay server-side.
const artwork = computed(() => pictures.value && tall.value && display.value === 'cover' && domain.value === 'media_player' && current.value?.a?.artwork_mark
  ? `api/media-art?entity=${encodeURIComponent(props.tile.entity)}&v=${encodeURIComponent(String(current.value.a.artwork_mark))}` : '');
const artworkLoaded = ref(false);
watch(artwork, () => { artworkLoaded.value = false; });
// A live camera fills its card on every size (app 0.3.13; 1x2 and 2x2 since 0.3.8): the add-on's picture, cut the way
// the tile asks, with the name at the bottom or nothing on it. Until the picture is here, the head as on the screen.
const cameraCard = computed(() => display.value === 'live' && ['camera', 'image'].includes(domain.value));
// A favourite (app 0.4.42): what it plays fills the card, dimmed as an album cover over a card is, with its name, its
// line and a round play key; on a screen without pictures the ordinary tile with the icon of what it plays.
const favoriteCard = computed(() => Boolean(favoritePlay.value) && !full.value);
const favoritePicture = computed(() => favoriteCard.value && pictures.value && favoritePlay.value?.thumb
  ? `api/media/picture?entity=${encodeURIComponent(props.tile.entity)}&url=${encodeURIComponent(favoritePlay.value.thumb)}` : '');
const favoriteLoaded = ref(false);
watch(favoritePicture, () => { favoriteLoaded.value = false; });
const FAVORITE_ICONS: Record<string, string> = { album: 'F0025', playlist: 'F0CB8', artist: 'F0803', track: 'F0387', podcast: 'F0994', episode: 'F0994', channel: 'F0439' };
const favoriteIcon = computed(() => props.tile.options?.icon && props.tile.options.icon !== 'auto' ? tileIconCp(props.tile) : FAVORITE_ICONS[favoritePlay.value?.class || ''] || 'F024B');
const favoriteLine = computed(() => {
  const kind = favoritePlay.value?.class, speaker = props.tile.options?.speaker as string | undefined;
  const word = kind && te(`addon.screen.media.${kind}`) ? screenText(`addon.screen.media.${kind}`) : '';
  return [word, speaker].filter(Boolean).join(' · ');
});
const cameraPicture = computed(() => cameraCard.value ? `api/camera-preview?entity=${encodeURIComponent(props.tile.entity)}` : '');
const cameraLoaded = ref(false);
watch(cameraPicture, () => { cameraLoaded.value = false; });
const mediaSubtitle = computed(() => [current.value?.a?.media_artist, current.value?.a?.media_album_name].filter(Boolean).join(' · '));
const features = computed(() => Number(current.value?.a?.supported_features || 0));
// The screens give a control that fills its room the content width of one cell, so its edges stand where the
// cards above and below have theirs (runtime_tiles::cell_content_width); keys, a switch and a run key keep their
// own size. A double-width card is two cells, so that is half its room minus the gap and the paddings.
const FILLS_CELL = ["brightness", "speed", "position", "slider", "volume", "setpoint", "mode"];
const fillsCell = computed(() => FILLS_CELL.includes(controls.value || "") || (controls.value === "stepper" && !domain.value.endsWith("select")));
const setpoint = computed(() => {
  if (rangeChip.value) return rangeChip.value.text;
  // A humidifier's number is the humidity it is set to, in percent (tile_controls::setpoint_suffix).
  if (domain.value === "humidifier") return current.value?.a?.humidity != null ? `${num(current.value.a.humidity)}${unitSuffix("%")}` : "—";
  const temperature = current.value?.a?.temperature;
  return temperature !== undefined && temperature !== null ? `${num(temperature)}°` : "—";
});

async function onKey(e: KeyboardEvent) {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); activate(); return; }
  if (props.preview) return;
  // Delete or Backspace removes the focused card (app 0.4.32); Undo brings it back.
  if ((e.key === "Delete" || e.key === "Backspace") && live.value) { e.preventDefault(); removeTile(props.tile); return; }
  // Up and down are a row of the screen's grid, whatever its columns; left and right one cell.
  const step = ({ ArrowLeft: -1, ArrowRight: 1, ArrowUp: -grid.value.columns, ArrowDown: grid.value.columns } as Record<string, number>)[e.key];
  if (!step) return;
  e.preventDefault();
  // A wide card owns its row: every arrow means the row above or below. A full card moves by the page.
  const to = props.tile.slot + (full.value ? Math.sign(step) * grid.value.slots : step);
  if (!placeTile(props.tile, to)) {
    // Nowhere to go without pushing a tile off its page (app 0.4.2): say so instead of doing nothing.
    if (to >= 0 && to < grid.value.slots * 8) toast(t("editor.layout.no_room", { page: Math.floor(to / grid.value.slots) + 1 }));
    return;
  }
  // The card that moved, found by its id: the cards are keyed by their place, so the one under the old place is
  // another tile now, and focusing that sent the next arrow key to the neighbour (app 0.4.1).
  await nextTick();
  document.querySelector<HTMLElement>(`.pages [data-tile-id="${props.tile.id}"]`)?.focus();
}
</script>

<template>
  <span v-if="round" class="round-tile" :class="{ chosen, placeholder: placeholder || (!live && !foreign), 'just-added': !preview && !!tile.id && state.justAdded === tile.id }" :data-tile-id="tile.id"
    :style="{ '--tile-icon': palette.icon, '--tile-circle': palette.circle }">
    <button type="button" class="round-key" :aria-label="name" :disabled="preview && !live"
      v-drag="preview || foreign ? null : { kind: 'tile', tile }" @click.stop="activate">
      <span class="disc" :class="{ lit: isOn }"><span v-if="roundValue" class="value">{{ roundValue }}</span><span v-else class="mdi">{{ glyph(tileIconCp(tile)) }}</span></span>
      <span v-if="tile.options?.overlay !== 'none' && !isCompact" class="kn">{{ name }}</span>
    </button>
    <!-- The same remove key as on a tile, at the circle's corner. -->
    <button v-if="live && !preview" type="button" class="remove" :title="t('editor.tile_card.remove')" :aria-label="t('editor.tile_card.remove_named', { name })" @click.stop="removeTile(tile)">✕</button>
  </span>
  <div v-else class="tile" :class="{ wide, full, tall, 'watch-card': !!watchFace, 'tall-action': tallAction || tallStack, 'big-key': bigKey, photo: artworkLoaded && !!artwork, camera: (cameraCard && cameraLoaded) || (favoriteCard && favoriteLoaded), bare, placeholder: placeholder || (!live && !foreign), chosen, 'just-added': !preview && !!tile.id && state.justAdded === tile.id }" :data-slot="slot" :data-tile-id="tile.id" :data-columns="shape.columns" :data-rows="shape.rows"
    :style="{ gridColumn: `${slot % grid.columns + 1} / span ${shape.columns}`, gridRow: `${Math.floor(slot % grid.slots / grid.columns) + 1} / span ${shape.rows}`, ...(background && !bare ? { backgroundColor: background } : {}), '--tile-icon': palette.icon, '--tile-circle': palette.circle, '--tile-accent': palette.accent, ...(watchStyle?.pad ?? {}) }"
    :tabindex="!foreign && (preview ? goesTo : live) ? 0 : -1" :role="!foreign && (preview ? goesTo : live) ? 'button' : undefined" :aria-label="live ? label : undefined"
    v-drag="preview || foreign ? null : { kind: 'tile', tile }" @click="activate" @keydown="live && onKey($event)">
    <template v-if="bedside">
      <span class="bedside-clock" :class="{ compact: isCompact }">
        <span class="time"><span class="bedside-time">{{ clockText(clock24, now) }}</span><small v-if="!clock24 && supports(0, 17, 0)" class="am-pm">{{ amPm }}</small></span>
        <span v-if="keyPlaces.length" class="keys">
          <span v-for="place in keyPlaces" :key="place.key" class="key-place" :data-key="preview || placeholder ? undefined : place.key" :data-holder="preview || placeholder ? undefined : tile.id"
            :class="{ 'insert-here': state.insertKey?.holder === tile.id && state.insertKey?.key === place.key, over: state.drag.key?.holder === tile.id && state.drag.key?.key === place.key }">
            <TileCard v-if="place.tile" :tile="place.tile" :slot="-1" round :preview="preview" />
            <button v-else type="button" class="key-empty" :title="t('editor.page.cell.title')" @click.stop="markKey(place.key)"><span>+</span></button>
          </span>
        </span>
      </span>
    </template>
    <template v-else-if="energyTile">
      <svg class="energy-diagram" viewBox="0 0 200 100" aria-hidden="true">
        <g fill="none" stroke-width="1.5">
          <path d="M100 32 V40 Q100 46 106 46 H161" :stroke="energy.solar" />
          <path d="M39 50 H161" :stroke="energy.grid" />
          <path d="M100 68 V60 Q100 54 106 54 H161" :stroke="energy.battery" />
        </g>
        <g fill="#fff" stroke-width="1.5">
          <circle cx="100" cy="18" r="14" :stroke="energy.solar" />
          <circle cx="25" cy="50" r="14" :stroke="energy.grid" />
          <circle cx="100" cy="82" r="14" :stroke="energy.battery" />
          <circle cx="175" cy="50" r="14" :stroke="energy.ink" stroke-width="2" />
        </g>
        <g class="mdi" text-anchor="middle" dominant-baseline="central" font-size="13" :fill="energy.ink">
          <text x="100" y="18">{{ glyph("F0A72") }}</text>
          <text x="25" y="50">{{ glyph("F0D3E") }}</text>
          <text x="100" y="82">{{ glyph("F007F") }}</text>
          <text x="175" y="50">{{ glyph("F02DC") }}</text>
        </g>
      </svg>
    </template>
    <template v-else-if="display === 'analog'">
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
    <template v-else-if="display === 'flip' && domain === 'screen' && flipWide">
      <span class="flip-wide">
        <span class="blocks"><span class="block">{{ flipHours }}</span><span class="block">{{ flipMinutes }}</span></span>
        <span class="under"><span>{{ flipDay }}</span><span v-if="!clock24">{{ amPm }}</span></span>
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
      <span class="head"><span class="ic mdi">{{ glyph(tileIconCp(tile)) }}</span><span class="tx"><span class="nm">{{ name }}</span><span class="st">{{ line }}</span></span></span>
      <SensorHistory :entity="tile.entity" :hours="Number(tile.options?.history_hours || 24)" />
    </template>
    <template v-else-if="favoriteCard">
      <img v-if="favoritePicture" :key="favoritePicture" class="camera-art fill favorite-art" :src="favoritePicture" alt="" @load="favoriteLoaded = true" @error="favoriteLoaded = false" />
      <span v-if="!favoriteLoaded" class="head"><span class="ic mdi">{{ glyph(favoriteIcon) }}</span><span class="tx"><span class="nm">{{ name }}</span><span v-if="favoriteLine" class="st">{{ favoriteLine }}</span></span></span>
      <template v-else>
        <span class="favorite-text"><span class="nm">{{ name }}</span><span v-if="favoriteLine" class="st">{{ favoriteLine }}</span></span>
        <span class="favorite-key mdi" aria-hidden="true">{{ glyph('F040A') }}</span>
      </template>
    </template>
    <template v-else-if="cameraCard">
      <img v-if="cameraPicture" :key="cameraPicture" class="camera-art" :class="tile.options?.fit === 'contain' ? 'contain' : 'fill'" :src="cameraPicture" alt="" @load="cameraLoaded = true" @error="cameraLoaded = false" />
      <span v-if="!cameraLoaded" class="head"><span class="ic mdi">{{ glyph(tileIconCp(tile)) }}</span><span class="tx"><span class="nm">{{ name }}</span><span v-if="line" class="st" :class="{ off: gone }">{{ line }}</span></span></span>
      <span v-else-if="tile.options?.overlay !== 'none'" class="camera-name"><span>{{ name }}</span></span>
    </template>
    <span v-else-if="watchFace && watchStyle" class="watch" :class="{ stacked: watchFace.stacked }">
      <span v-if="watchFace.stacked" class="ic mdi" :class="{ lit: isOn }" :style="watchStyle.circle">{{ glyph(tileIconCp(tile)) }}</span>
      <span class="nm" :style="watchStyle.title">{{ name }}</span>
      <template v-if="watchFace.stacked">
        <span class="big" :style="watchStyle.value">{{ bigValue }}</span>
        <span v-if="watchStyle.unit" class="unit" :style="watchStyle.unit">{{ unit }}</span>
      </template>
      <span v-else class="alone" :style="watchStyle.row">
        <span class="big" :style="watchStyle.value">{{ bigValue }}</span>
        <span v-if="watchStyle.unit" class="unit" :style="watchStyle.unit">{{ unit }}</span>
      </span>
    </span>
    <template v-else-if="full && !tall">
      <span class="ic mdi" :class="{ lit: isOn, thumb: display === 'live' || display === 'cover' }">{{ glyph(tileIconCp(tile)) }}</span>
      <span class="lead">
        <span class="nm">{{ name }}</span>
        <span v-if="goesTo" class="goto">{{ pageLink }}</span>
        <span v-else-if="display === 'watch'" class="big">{{ bigValue }}<small v-if="unit && !gone">{{ unit }}</small></span>
        <span v-else-if="line" class="st" :class="{ off: gone }">{{ line }}</span>
      </span>
      <span v-if="tile.options?.inline === 'slider'" class="mini-slider" :style="sliderStyle"></span>
      <span v-if="controls" class="ctl">
        <span v-if="controls === 'toggle'" class="tog" :class="{ off: !on }"></span>
        <span v-else-if="controls === 'setpoint'" class="stp"><span class="mdi">{{ key("minus") || "−" }}</span><span v-if="rangeChip" v-chip-fit class="range-chip" :style="{ '--end': rangeChip.color, '--chip-ems': rangeChip.ems }"><span class="mdi end-icon">{{ key(rangeChip.icon) }}</span><b>{{ rangeChip.text }}</b></span><b v-else :style="{ '--pill-ems': textEms(setpoint + '8') }">{{ setpoint }}</b><span class="mdi">{{ key("plus") || "+" }}</span></span>
        <template v-else-if="controls === 'volume'"><span class="range" :style="volumeStyle"></span><span class="key mdi">{{ key("volume-high") }}</span></template>
        <ModeBar v-else-if="modeBar" :a="current?.a || {}" :mode="current?.state || ''" :domain="domain" place="full" :columns="shape.columns" /><template v-else-if="panelKeys.length"><span v-for="(control, i) in panelKeys" :key="i" class="key mdi" :class="{ primary: control.primary, disabled: control.disabled, active: control.mode === current?.state }">{{ key(control.icon) }}</span></template>
        <span v-else-if="controls === 'run'" class="run">{{ runText }}</span>
        <span v-else class="range" :style="sliderStyle"></span>
      </span>
    </template>
    <template v-else-if="bigKey">
      <span class="ic mdi" :class="{ lit: isOn }">{{ glyph(tileIconCp(tile)) }}</span>
      <span class="nm">{{ name }}</span>
      <span v-if="bigKeyLine" class="st" :class="{ off: gone }">{{ bigKeyLine }}</span>
    </template>
    <template v-else-if="tall">
      <img v-if="artwork" :key="artwork" class="tall-art" :src="artwork" alt="" @load="artworkLoaded = true" @error="artworkLoaded = false" />
      <span class="head">
        <span class="ic mdi">{{ glyph(tileIconCp(tile)) }}</span>
        <span class="tx"><span class="nm">{{ name }}</span><span v-if="headStatus" class="st" :class="{ off: gone }">{{ headStatus }}</span></span>
      </span>
      <CoverTilePreview v-if="coverExtended" :primary="tallControls" :entity-state="current?.state || ''" :attributes="current?.a || {}" />
      <span v-else-if="thermostat && (tallControls === 'setpoint' || tallControls === 'setpoint_mode')" class="tall-setpoint">
        <span class="target"><span class="key mdi">{{ key('minus') || '−' }}</span><span v-if="rangeChip" v-chip-fit class="range-chip" :style="{ '--end': rangeChip.color, '--chip-ems': rangeChip.ems }"><span class="mdi end-icon">{{ key(rangeChip.icon) }}</span><b>{{ rangeChip.text }}</b></span><b v-else>{{ setpoint }}</b><span class="key mdi">{{ key('plus') || '+' }}</span></span>
        <span class="st">{{ measured != null ? screenText('screen.climate.now', { value: reading(measured) }) : status }}</span>
        <ModeBar v-if="tallControls === 'setpoint_mode'" class="ctl modes" :a="current?.a || {}" :mode="current?.state || ''" :domain="domain" place="tall" :columns="shape.columns" />
      </span>
      <template v-else>
        <span v-if="!tallAction" class="tall-body">
          <template v-if="domain === 'media_player' && !gone">
            <MarqueeText class="track-title" :text="String(current?.a?.media_title || '')" /><span v-if="mediaSubtitle" class="st">{{ mediaSubtitle }}</span>
          </template>
          <span v-else-if="domain === 'climate' && !gone" class="target-value">{{ current?.a?.current_temperature !== undefined ? `${num(current.a.current_temperature)}°` : '—' }}</span>
          <!-- A humidifier stands the humidity it measures large, else its line (runtime_tiles render_tall). -->
          <span v-else-if="domain === 'humidifier' && !gone" class="target-value">{{ measured != null ? reading(measured) : status }}</span>
          <span v-else-if="domain !== 'screen' && !gone && tallControls !== 'toggle'" class="target-value">{{ domain === 'light' && isOn ? `${fill}%` : status }}</span>
        </span>
      <span v-if="tallControls" class="ctl" :class="{ playback: tallControls === 'playback' }">
        <span v-if="tallControls === 'toggle'" class="tog" :class="{ off: !on }"></span>
        <span v-else-if="tallControls === 'setpoint'" class="stp"><span class="mdi">{{ key("minus") || "−" }}</span><span v-if="rangeChip" v-chip-fit class="range-chip" :style="{ '--end': rangeChip.color, '--chip-ems': rangeChip.ems }"><span class="mdi end-icon">{{ key(rangeChip.icon) }}</span><b>{{ rangeChip.text }}</b></span><b v-else :style="{ '--pill-ems': textEms(setpoint + '8') }">{{ setpoint }}</b><span class="mdi">{{ key("plus") || "+" }}</span></span>
        <ModeBar v-else-if="tallControls === 'mode' && thermostat" :a="current?.a || {}" :mode="current?.state || ''" :domain="domain" place="tall" :columns="shape.columns" />
        <template v-else-if="tallKeys.length"><span v-for="(control, i) in tallKeys" :key="i" class="key mdi" :class="{ primary: control.primary, disabled: control.disabled, active: control.mode === current?.state }">{{ key(control.icon) }}</span></template>
        <span v-else-if="tallControls === 'stepper'" class="stp"><span class="mdi">{{ key("minus") || "−" }}</span><b>{{ bigValue }}</b><span class="mdi">{{ key("plus") || "+" }}</span></span>
        <template v-else-if="tallControls === 'volume'"><span v-if="features & bits('media_player', 'VOLUME_SET')" class="range" :style="volumeStyle"></span><span v-if="features & bits('media_player', 'VOLUME_MUTE')" class="key mdi">{{ key(current?.a?.is_volume_muted ? 'volume-off' : 'volume-high') }}</span></template>
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
          <span v-else-if="line" class="st" :class="{ off: gone }">{{ line }}</span>
        </span>
      </span>
      <span v-if="tile.options?.inline === 'slider'" class="mini-slider" :style="sliderStyle"></span>
      <span v-if="controls" class="ctl" :class="{ fill: fillsCell }">
        <span v-if="controls === 'toggle'" class="tog" :class="{ off: !on }"></span>
        <span v-else-if="controls === 'setpoint'" class="stp"><span class="mdi">{{ key("minus") || "−" }}</span><span v-if="rangeChip" class="range-chip" :class="{ lone: wideFit && !wideFit.icon }" :style="{ '--end': rangeChip.color, '--chip-ems': rangeChip.ems, ...(wideFit ? { '--chip-face': `${(wideFit.face * glassScale).toFixed(2)}px` } : {}) }"><span class="mdi end-icon">{{ key(rangeChip.icon) }}</span><b>{{ rangeChip.text }}</b></span><b v-else :style="{ '--pill-ems': textEms(setpoint + '8') }">{{ setpoint }}</b><span class="mdi">{{ key("plus") || "+" }}</span></span>
        <template v-else-if="controls === 'stepper' && domain.endsWith('select')"><span class="key mdi">{{ key("chevron-left") }}</span><span class="key mdi">{{ key("chevron-right") }}</span></template>
        <span v-else-if="controls === 'stepper'" class="stp"><span class="mdi">{{ key("minus") || "−" }}</span><b>{{ bigValue }}</b><span class="mdi">{{ key("plus") || "+" }}</span></span>
        <ModeBar v-else-if="modeBar" :a="current?.a || {}" :mode="current?.state || ''" :domain="domain" place="row" :columns="shape.columns" /><template v-else-if="panelKeys.length"><span v-for="(control, i) in panelKeys" :key="i" class="key mdi" :class="{ primary: control.primary, disabled: control.disabled, active: control.mode === current?.state }">{{ key(control.icon) }}</span></template>
        <template v-else-if="controls === 'volume'"><span class="range" :style="volumeStyle"></span><span class="key mdi">{{ key("volume-high") }}</span></template>
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
          <span v-else-if="display !== 'watch' && line" class="st" :class="{ off: gone }">{{ line }}</span>
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
/* A Big number card: its content box is the glass's (the board's TILE_PAD), and its parts stand where watchCard puts them. */
.tile.watch-card { padding-inline: var(--frame-pad, 8px); }
.tile .watch { position: relative; flex: 1; align-self: stretch; min-width: 0; min-height: 0; }
.tile .watch > * { position: absolute; margin: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tile .watch .alone { left: 0; right: 0; display: flex; justify-content: center; align-items: flex-end; }
.tile .watch .alone > * { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.tile .watch .alone .unit { flex: none; }
.tile .watch .ic:not(.thumb) { display: grid; place-items: center; padding: 0; line-height: 1; }
.tile .watch .big { font-weight: 500; letter-spacing: 0; }
.tile .watch .unit { color: #5a5f66; font-weight: 400; overflow: visible; }
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
.bedside-clock { display: flex; flex-direction: column; align-items: center; justify-content: space-evenly; width: 100%; height: 100%; min-width: 0; container-type: inline-size; }
/* As the screen draws it: the time about as wide as the card, the keys a quarter of its height. */
.bedside-clock .bedside-time { font-size: 32cqw; font-weight: 400; line-height: 1; letter-spacing: -1px; }
/* The compact look (a CYD) draws its display step smaller against the card. */
.bedside-clock.compact .bedside-time { font-size: 24cqw; }
.bedside-clock .round-tile .disc { width: 16cqw; height: 16cqw; font-size: 8cqw; }
.bedside-clock .round-tile .disc .value { font-size: 4cqw; }
.bedside-clock .key-place { width: auto; min-width: min(20cqw, 64px); }
.bedside-clock .round-tile, .bedside-clock .round-key { max-width: none; }
.bedside-clock .time { display: grid; justify-items: end; }
.bedside-clock .am-pm { font-size: min(4cqw, 12px); opacity: .6; margin-top: 4px; }
.flip-wide { display: flex; flex-direction: column; justify-content: center; gap: 6px; width: 100%; height: 100%; min-width: 0; container-type: size; }
/* As the screen draws it: two blocks sharing the width, each about as tall as wide, the digits filling them. */
.flip-wide .blocks { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 3%; height: min(calc(100cqh - 34px), 44cqw); }
.flip-wide .block { display: grid; place-items: center; background: #f1f1f1; border-radius: 8px; font-size: min(36cqw, calc((100cqh - 34px) * .78)); font-weight: 400; line-height: 1;
  background-image: linear-gradient(transparent calc(50% - .5px), #fff calc(50% - .5px), #fff calc(50% + .5px), transparent calc(50% + .5px)); }
.flip-wide .under { display: flex; justify-content: space-between; font-size: 10px; opacity: .7; }
.tile.tall.big-key { flex-direction: column; justify-content: center; align-items: center; text-align: center; gap: 4px; container-type: size; }
.tile.tall.big-key .ic { width: 44cqmin; height: 44cqmin; display: grid; place-items: center; font-size: 24cqmin; padding: 0; }
.tile.tall.big-key .nm { font-size: clamp(12px, 13cqmin, 26px); font-weight: 500; color: #1b1b1b; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tile.tall.big-key .st { font-size: 10px; }
.bedside-clock .keys { display: flex; gap: 14px; }
.key-place { display: grid; place-items: center; width: 64px; min-height: 52px; border-radius: 12px; }
.key-place.over, .key-place.insert-here { outline: 2px dashed var(--accent, #2196f3); outline-offset: 2px; }
.key-empty { width: 36px; height: 36px; border-radius: 50%; border: 1px dashed currentColor; background: transparent; color: inherit; opacity: .45; cursor: pointer; }
.round-tile { position: relative; display: grid; justify-items: center; min-width: 0; max-width: 64px; }
.round-key { display: flex; flex-direction: column; align-items: center; gap: 4px; min-width: 0; max-width: 64px; padding: 0; border: 0; background: transparent; color: inherit; cursor: pointer; font: inherit; }
.round-tile .remove { top: -6px; right: 4px; }
.round-tile .disc { display: grid; place-items: center; width: 36px; height: 36px; border-radius: 50%; background: var(--tile-circle); color: var(--tile-icon); font-size: 19px; }
.round-tile .disc .value { font-size: 10px; color: var(--ink, inherit); }
.round-tile .kn { font-size: 9px; opacity: .7; max-width: 64px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.round-tile.chosen .disc { outline: 2px solid var(--accent, #2196f3); outline-offset: 2px; }
.round-tile.placeholder { opacity: .4; }
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
/* A thermostat's range (firmware 0.19.0, runtime_tiles range_chip): the end the -/+ move as a white chip between them,
   its heat or cool icon in that mode's colour; too narrow for the icon, the number alone in that colour. */
.range-chip { container-type: inline-size; flex: 1; min-width: 0; align-self: stretch; display: flex; align-items: center; justify-content: center; gap: 3px; margin: 2px 0; padding: 0 6px; border-radius: 999px; }
.range-chip .end-icon { color: var(--end); font-size: 12px; }
.range-chip b { font-weight: 600; white-space: nowrap; }
.target .range-chip { margin: 0; }
.target .range-chip b { font-size: clamp(16px, 18cqh, 42px); font-weight: 400; }
.target .range-chip .end-icon { font-size: clamp(12px, 10cqh, 24px); }
/* No room for the icon beside the widest number (vChipFit): the number alone, in its end's colour. */
.range-chip.lone .end-icon { display: none; }
.range-chip.lone b { color: var(--end); }
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
/* A favourite (app 0.4.42): the picture dimmed as the screen dims it (a third of its light), the words and the key over it. */
.tile .favorite-art { filter: brightness(.333); }
.tile .favorite-text { position: absolute; inset: auto 0 0 0; padding: 0 calc(var(--key, 34px) + 14px) 8px 9px; display: flex; flex-direction: column; color: white; pointer-events: none; min-width: 0; }
.tile .favorite-text .nm { font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tile .favorite-text .st { font-size: .85em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tile .favorite-key { position: absolute; right: 8px; bottom: 8px; width: var(--key, 34px); height: var(--key, 34px); border-radius: 50%; background: #f2f2f2; color: #000; display: grid; place-items: center; font-size: 20px; pointer-events: none; }
</style>
