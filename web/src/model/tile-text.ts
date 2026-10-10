// What a card on the mockup writes, in the screens' words: the line under its name, the second line chosen in the tile
// panel, the value a large card stands tall, a range's chip and the setpoint between its -/+, the word on a run key and
// a Go to page tile's link. The screens decide these in runtime_tiles and tile_controls. Where the editor writes what a
// rule of the firmware writes (temperature_text, humidity_text, reading_text, status_text, climate_card_status,
// binary_state_text), the rule is ported one to one, and tests/test_editor_parity.py runs both on the same values.
// Pure: the words come from the translations through `t`, in the screens' language and number format (ScreenWords).
import { numberText, t, te, type NumberMarks } from "../i18n";
import { bits } from "./catalogue";
import { modeColor } from "./tile-palette";
import { textEms, widestSetpoint } from "./ui-scale";

/** What Home Assistant reports of an entity, as the add-on hands it to the editor (api/states): its state, the
 * attributes a card shows and, for a state the screens have no word of their own for, Home Assistant's word. */
export type Live = { state: string; a?: Record<string, any>; word?: string | null };
/** How the screens write: their language, their number marks ("1,234.5" or "1.234,5"), and whether "%" stands apart
 * from its number (Home Assistant's rule for the language: "54 %" in German and French). */
export type ScreenWords = { locale: string; marks: NumberMarks; percentSpace?: boolean };

/** Whether two ways of writing are the same. */
export const sameWords = (a: ScreenWords, b: ScreenWords) => a.locale === b.locale && Boolean(a.percentSpace) === Boolean(b.percentSpace)
  && a.marks.decimal === b.marks.decimal && a.marks.group === b.marks.group && a.marks.from === b.marks.from;
/** Whether two reports of an entity say the same: its state, its word and the very same attributes (or none). */
export const sameLive = (a: Live, b: Live) => a === b || (a.state === b.state && (a.word ?? null) === (b.word ?? null)
  && (a.a === b.a || (isEmpty(a.a) && isEmpty(b.a))));
const isEmpty = (attributes: Record<string, any> | undefined) => !attributes || Object.keys(attributes).length === 0;
/** A text as the screens show it, in their language. */
export const screenText = (words: ScreenWords, key: string, named: Record<string, unknown> = {}) => t(key, named, { locale: words.locale });
// A text the screens have, asked in English: every language falls back to it.
const has = (key: string) => te(key);
/** A number as Home Assistant sends it ("1234.5", "-3"), written as the screens write numbers; any other text as it is. */
export const numberOf = (value: unknown, words: ScreenWords) => numberText(value as string | number, words.marks);
/** What follows a number for its unit, as Home Assistant spaces it: "°", "%" or " %" by the language, " kWh"
 * (screen_text::unit_suffix). */
export function unitSuffix(unit: string | undefined | null, percentSpace = false) {
  if (!unit || unit === "°") return unit || "";
  if (unit === "%") return percentSpace ? " %" : "%";
  return ` ${unit}`;
}
const percentSign = (words: ScreenWords) => unitSuffix("%", words.percentSpace);
/** A value of an entity with a unit, a number of a domain that is one, or the state as it is (runtime_tiles value_text). */
const NUMERIC = ["number", "input_number", "counter"];

// ---- The firmware's own number rules (screen_text.h, tile_controls.h), on the float the screen holds ----
// The screen keeps a value Home Assistant sends as a float, and writes it with printf: rounded the way C rounds a tie
// (to the even digit, 41.25 to "41.2"), where JavaScript's toFixed takes the larger one.
const float = Math.fround;
function printfFixed(value: number, digits: number) {
  const x = float(value), scaled = x * 10 ** digits;
  if (Number.isFinite(scaled) && Math.abs(scaled) < 2 ** 52 && Math.abs(scaled % 1) === 0.5) {
    const down = Math.floor(scaled), even = down % 2 === 0 ? down : down + 1;
    return (even / 10 ** digits).toFixed(digits);
  }
  return x.toFixed(digits);
}
/** A value with so many decimals and the screens' decimal mark (screen_text::decimal). */
export const decimalText = (value: number, digits: number, words: ScreenWords) => printfFixed(value, digits).replace(".", words.marks.decimal);
// C's lround: a half away from zero.
const lround = (value: number) => Math.sign(value) * Math.round(Math.abs(value));
/** A temperature a thermostat reports, written as Home Assistant writes the number it sends: 73°, 21.5°, 21.25°
 * (tile_controls::temperature_text). */
export function temperatureText(value: number, words: ScreenWords) {
  let digits = 0;
  for (let scaled = float(value); digits < 2 && Math.abs(float(scaled - Math.round(scaled))) > float(0.01); scaled = float(scaled * 10)) ++digits;
  return `${decimalText(value, digits, words)}°`;
}
/** A humidity, as Home Assistant writes it beside a humidifier: whole, or with the one decimal a sensor sends (45.5%)
 * (tile_controls::humidity_text). */
export function humidityText(value: unknown, words: ScreenWords) {
  const v = float(Number(value));
  if (Math.abs(float(v - Math.round(v))) < float(0.05)) return `${lround(v)}${percentSign(words)}`;
  return `${decimalText(v, 1, words)}${percentSign(words)}`;
}
/** What a thermostat measures, in its own unit: degrees, or a humidifier's humidity (tile_controls::reading_text). */
export const readingText = (domain: string, value: unknown, words: ScreenWords) =>
  domain === "humidifier" ? humidityText(value, words) : temperatureText(Number(value), words);

// ---- A state in words ----
// The screens' own words for a state where Home Assistant hands us none (screen.ha, Home Assistant's words in the
// screens' language, app 0.2.90): a binary sensor's by its device class, on and off, and the states of the domains
// the screen names itself. A weather's windy-variant is windy there too.
const HA_WORDS: Record<string, string> = { climate: "climate", cover: "cover", media_player: "media", person: "person", sun: "sun", vacuum: "vacuum", weather: "weather", alarm_control_panel: "alarm", lock: "lock" };
export function haWord(domain: string, live: Live, words: ScreenWords) {
  const word = (path: string) => (has(`screen.ha.${path}`) ? screenText(words, `screen.ha.${path}`) : "");
  const value = live.state === "windy-variant" ? "windy" : live.state.replace(/-/g, "_");
  if (domain === "binary_sensor" && ["on", "off"].includes(value)) return word(`binary.${live.a?.device_class}_${value}`) || word(value);
  if (HA_WORDS[domain]) return word(`${HA_WORDS[domain]}.${value}`) || (["on", "off"].includes(value) ? word(value) : "");
  return ["on", "off"].includes(value) ? word(value) : "";
}
const capital = (text: string) => text.charAt(0).toUpperCase() + text.slice(1).replace(/_/g, " ");

/** A thermostat's line as the screen writes it: with a control on the tile, what it is doing and the room's temperature
 * (tile_controls::status_text); without one the temperature it is set to, and otherwise Home Assistant's own tile line,
 * its state and the room's temperature (runtime_tiles' value line). */
export function climateLine(live: Live, word: string, controlled: boolean, words: ScreenWords) {
  const a = live.a || {};
  const now = a.current_temperature != null ? ` · ${temperatureText(Number(a.current_temperature), words)}` : "";
  const doing = has(`screen.ha.hvac_action.${a.hvac_action}`) ? screenText(words, `screen.ha.hvac_action.${a.hvac_action}`) : "";
  if (controlled) return `${doing || word}${now}`;
  if (live.state !== "off" && a.temperature != null) return temperatureText(Number(a.temperature), words);
  return `${word}${now}`;
}
/** A humidifier's line as the screen writes it (tile_controls::climate_card_status, brief): Home Assistant's word for
 * what it is doing (Off while it is off), else On or Off, and the humidity it measures. Home Assistant's tile line. */
export function humidifierLine(live: Live, words: ScreenWords) {
  const a = live.a || {}, off = live.state !== "on", action = off ? "off" : String(a.action ?? "");
  const key = `screen.ha.humidifier_action.${action}`;
  const word = action && has(key) ? screenText(words, key) : screenText(words, off ? "screen.ha.off" : "screen.ha.on");
  return a.current_humidity != null ? `${word} · ${humidityText(a.current_humidity, words)}` : word;
}

/** A scene, script or button has no state worth a word: its state is the moment it last ran. */
export const NO_STATUS = ["scene", "script", "button", "input_button"];
/** Nothing Home Assistant can tell of it: no value, or one it calls unavailable or unknown. */
export const isGone = (live: Live | null | undefined) => !live || ["unavailable", "unknown", ""].includes(live.state);
/** A number of a domain with a unit, or of a domain that is a number itself, as the screens write it; an id-like
 * "1234" without a unit stays as it is (runtime_tiles value_text). */
export function valueText(domain: string, state: string, unit: string | undefined, words: ScreenWords) {
  return unit || NUMERIC.includes(domain) ? `${numberOf(state, words)}${unitSuffix(unit, words.percentSpace)}` : state;
}

export type StateTextOptions = {
  /** An automation that runs on a tap (Tile::runs): Running while its actions run, Off while nothing starts it. */
  runs?: boolean;
  /** What a face other than the standard one says where the entity has no state worth a word: its name. */
  note?: string;
  /** A control on the card: a thermostat then says what it is doing (tile_controls::status_text). */
  controlled?: boolean;
};
/** The text under the name: Home Assistant's word where it has one, the value with its unit for a sensor. */
export function stateText(entity: string, live: Live | null | undefined, options: StateTextOptions, words: ScreenWords) {
  const domain = entity.split(".")[0], note = options.note || "";
  if (!live || NO_STATUS.includes(domain)) return note;
  const gone = isGone(live);
  // A run button says Running while its actions run and Off while nothing starts it on its own, as on the screen.
  if (options.runs && !gone) return Number(live.a?.current) > 0 ? screenText(words, "screen.script.running") : live.state === "off" ? screenText(words, "screen.ha.off") : note;
  if (gone) return screenText(words, live.state === "unknown" ? "editor.mockup.unknown" : "screen.ha.unavailable");
  const a = live.a || {};
  const word = live.word || haWord(domain, live, words) || capital(live.state);
  if (domain === "climate") return climateLine(live, word, Boolean(options.controlled), words);
  if (domain === "humidifier") return humidifierLine(live, words);
  if (domain === "weather") return `${word}${a.temperature !== undefined ? ` · ${numberOf(a.temperature, words)}°` : ""}`;
  if (domain === "cover" && a.current_position !== undefined && a.current_position > 0 && a.current_position < 100) return `${word} · ${a.current_position}${percentSign(words)}`;
  if (domain === "media_player" && a.media_title) return `${word} · ${a.media_title}`;
  // A remote that runs an activity names it (firmware 0.22.0+), as the screen does.
  if (domain === "remote" && live.state === "on" && a.current_activity) return String(a.current_activity);
  if (domain === "sensor" || NUMERIC.includes(domain)) return valueText(domain, live.state, a.unit_of_measurement, words);
  return word;
}
/** The second line as chosen in the tile panel (app 0.2.105; drawn on the mockup since app 0.4.1): the screen's own
 * line, nothing, words of your own, or a value of the entity. A value Home Assistant does not report leaves the line to
 * the screen, as on the glass. */
export function subLine(sub: string, live: Live | null | undefined, status: string, words: ScreenWords) {
  if (sub === "none") return "";
  if (sub.startsWith("text:")) return sub.slice(5);
  if (sub.startsWith("attr:")) {
    const value = live?.a?.[sub.slice(5)];
    if (value !== undefined && value !== null && value !== "") return typeof value === "number" ? numberOf(value, words) : String(value);
  }
  return status;
}
/** The big value of a Big number card; its unit stands beside it in small letters. */
export function bigValue(domain: string, live: Live | null | undefined, words: ScreenWords) {
  if (!live || isGone(live)) return "—";
  return live.a?.unit_of_measurement || NUMERIC.includes(domain) ? numberOf(live.state, words) : live.state;
}
/** What a bedside clock's key shows in its circle: its value where that is what it is for (a temperature), else nothing
 * (its icon). */
export function roundValue(domain: string, live: Live | null | undefined, words: ScreenWords) {
  if (!["sensor", "number", "input_number"].includes(domain) || !live || isGone(live)) return "";
  const unit = String(live.a?.unit_of_measurement || "");
  return bigValue(domain, live, words) + (unit.startsWith("°") ? "°" : unit === "%" ? "%" : "");
}

/** The small slider's fill in percent, from what the entity reports; off is empty, like the screen's grey fill. */
export function fillPercent(domain: string, live: Live | null | undefined) {
  if (!live || isGone(live)) return 0;
  const a = live.a || {};
  if (domain === "light") return live.state === "on" ? (a.brightness !== undefined ? Math.round((a.brightness / 255) * 100) : 100) : 0;
  if (domain === "fan") return live.state === "on" ? (a.percentage ?? 100) : 0;
  // A blind's bar fills with its closed part, as on the screen (firmware 0.2.66+) and in Home Assistant's cover dialog.
  if (domain === "cover") return 100 - (a.current_position ?? (live.state === "open" ? 100 : 0));
  if (domain === "media_player") return Math.round((a.volume_level ?? 0) * 100);
  // A humidifier's slider is the humidity it is set to over its own range (runtime_tiles slider_value), on or off.
  if (domain === "humidifier") {
    const target = Number(a.humidity), min = Number(a.min_humidity ?? 0), max = Number(a.max_humidity ?? 100);
    return a.humidity != null && Number.isFinite(target) && max > min ? Math.round(Math.min(1, Math.max(0, (target - min) / (max - min))) * 100) : 0;
  }
  if (domain === "number" || domain === "input_number") {
    const value = Number(live.state), min = Number(a.min ?? 0), max = Number(a.max ?? 100);
    return Number.isFinite(value) && max > min ? Math.round(((value - min) / (max - min)) * 100) : 0;
  }
  return 0;
}

/** Whether a light, switch or the like is on: its circle lit, a big key's line its brightness. An automation that runs
 * on a tap is a key, never lit. */
export const isOn = (domain: string, live: Live | null | undefined, runs = false) =>
  (["light", "switch", "input_boolean", "fan", "remote", "humidifier"].includes(domain) || (domain === "automation" && !runs)) && live?.state === "on";

export type RangeChip = { icon: string; color: string; text: string; ems: number };
/** A thermostat set to a range (firmware 0.19.0), decided as Home Assistant's thermostat card decides it: a single target
 * it supports and reports comes first, else a range it supports with both ends. The screen puts a chip between its -
 * and +: the end they move, heat or cool, with its icon in that mode's colour; the low end first, as the screen does.
 * `ready`: the screen draws a range (firmware 0.19.0+). */
export function rangeChip(domain: string, live: Live | null | undefined, ready: boolean, words: ScreenWords): RangeChip | null {
  const a = live?.a || {}, f = Number(a.supported_features || 0);
  if (domain !== "climate" || !ready || (f & bits("climate", "TARGET_TEMPERATURE") && a.temperature != null) || !(f & bits("climate", "TARGET_TEMPERATURE_RANGE")) || a.target_temp_low == null || a.target_temp_high == null) return null;
  const digits = Number(a.target_temp_step || 0.5) >= 1 ? 0 : 1;
  return { icon: "fire", color: modeColor("heat"), text: `${numberOf(Number(a.target_temp_low).toFixed(digits), words)}°`, ems: textEms(widestSetpoint(a)) };
}
/** The number between a thermostat's -/+: the end of its range, a humidifier's humidity in percent
 * (tile_controls::setpoint_suffix), or the temperature it is set to. */
export function setpointText(domain: string, live: Live | null | undefined, chip: RangeChip | null, words: ScreenWords) {
  if (chip) return chip.text;
  const a = live?.a || {};
  if (domain === "humidifier") return a.humidity != null ? `${numberOf(a.humidity, words)}${percentSign(words)}` : "—";
  return a.temperature !== undefined && a.temperature !== null ? `${numberOf(a.temperature, words)}°` : "—";
}

/** The word on the key of a scene, script, automation that runs, or a button, as the screen labels it. */
export const runText = (domain: string, words: ScreenWords) =>
  screenText(words, `screen.ha.button.${({ scene: "activate", script: "run", automation: "run" } as Record<string, string>)[domain] || "press"}`);
/** The page a Go to page tile opens, as the screen writes it. */
export const pageLink = (page: number, words: ScreenWords) => `${screenText(words, "screen.tile.page", { n: page })} ›`;
/** A favourite's line (app 0.4.42): what kind of thing it plays and on which speaker. */
export function favoriteLine(kind: string | undefined, speaker: string | undefined, words: ScreenWords) {
  const word = kind && has(`addon.screen.media.${kind}`) ? screenText(words, `addon.screen.media.${kind}`) : "";
  return [word, speaker].filter(Boolean).join(" · ");
}
/** Under a playing track on a tall card: its artist and album. */
export const mediaSubtitle = (live: Live | null | undefined) => [live?.a?.media_artist, live?.a?.media_album_name].filter(Boolean).join(" · ");

/** The line under a big key's name, as the screen draws it: a lamp that is on says how bright, a script or automation
 * that never ran says so, anything else its line. */
export function bigKeyLine(domain: string, live: Live | null | undefined, line: string, fill: number, words: ScreenWords) {
  if (domain === "light" && isOn(domain, live) && !isGone(live)) return `${fill}%`;
  if (NO_STATUS.includes(domain)) return live && !live.a?.last_triggered && ["script", "automation"].includes(domain) ? screenText(words, "screen.script.never_run") : line;
  return line;
}
/** The value a tall card's body shows large; the same words are then not repeated under its name (headLine). */
export function bodyText(domain: string, live: Live | null | undefined, plain: boolean, status: string, fill: number) {
  if (!plain || isGone(live)) return "";
  if (domain === "media_player") return String(live?.a?.media_title || "");
  if (domain === "climate" || domain === "humidifier" || domain === "screen") return "";
  return domain === "light" && isOn(domain, live) ? `${fill}%` : status;
}
/** The line under a tall card's name: its own line, unless the body already stands it large (a second line of your
 * own stays). */
export const headLine = (body: string, line: string) => (body && (line === body || line.startsWith(body + " ")) ? "" : line);
