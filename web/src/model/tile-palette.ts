import theme from "virtual:esp-screens-theme";

type Value = { state: string; a?: Record<string, any> } | null | undefined;
const c = theme.ha;
const alarms = new Set(["battery", "carbon_monoxide", "gas", "heat", "lock", "moisture", "problem", "safety", "smoke", "sound", "tamper"]);
const weather: Record<string, number> = { sunny: c.AMBER, "clear-night": c.DEEP_PURPLE, partlycloudy: c.BLUE_GREY, cloudy: c.LIGHT_GREY,
  fog: c.GREY, rainy: c.BLUE, pouring: c.INDIGO, snowy: c.ICE, "snowy-rainy": c.LIGHT_BLUE, hail: c.CYAN,
  lightning: c.YELLOW, "lightning-rainy": c.LIME, windy: c.GREEN, "windy-variant": c.GREEN, exceptional: c.RED };
const modes: Record<string, number> = { heat: c.DEEP_ORANGE, cool: c.BLUE, heat_cool: c.AMBER, auto: c.GREEN, fan_only: c.CYAN, dry: c.ORANGE };
const hex = (color: number) => `#${color.toString(16).padStart(6, "0")}`;
/** Home Assistant's colour for a climate mode, as tile_controls::mode_color gives it. */
export const modeColor = (mode: string) => hex(modes[mode] ?? c.GREY);
/** The colour of the mode a thermostat is in on its mode bar: a climate mode's own, a humidifier's blue for every mode
 * (Home Assistant gives its modes no colour of their own; runtime_tiles mode_segment, firmware 0.42.0+). */
export const thermostatModeColor = (domain: string, mode: string) => (domain === "humidifier" ? hex(c.BLUE) : modeColor(mode));
const mix = (a: number, b: number, weight: number) => [16, 8, 0].reduce((out, shift) =>
  out | Math.floor((((a >> shift) & 255) * weight + ((b >> shift) & 255) * (255 - weight)) / 255) << shift, 0);

/** Mirrors Tile::active and tile_controls::accent, with paints read from theme.h. `runs`: an automation whose tap runs
 * its actions (Tile::runs), coloured only while they run, like a script. */
export function tileActive(entity: string, value: Value, runs = false) {
  const domain = entity.split(".")[0], state = value?.state;
  if (domain === "screen") return true;
  if (!state || state === "unavailable") return false;
  if (["scene", "button", "input_button", "image"].includes(domain)) return true;
  if (runs && domain === "automation") return Number(value?.a?.current) > 0;
  if (["unknown", "off"].includes(state)) return false;
  if (domain === "cover") return state !== "closed";
  if (domain === "person") return state !== "not_home";
  if (domain === "media_player") return state !== "standby";
  if (domain === "vacuum") return !["idle", "docked", "paused"].includes(state);
  if (domain === "timer") return state === "active";
  if (domain === "camera") return ["streaming", "recording"].includes(state);
  if (domain === "alarm_control_panel") return state !== "disarmed";
  if (domain === "lock") return state !== "locked";
  return true;
}
/** LVGL's lv_color_hsv_to_rgb step for step (tile_controls::hsv_rgb), so a lamp's colour is the screen's to the last bit. */
function hsvRgb(h: number, s: number, v: number) {
  h = Math.floor((h * 255) / 360); s = Math.floor((s * 255) / 100); v = Math.floor((v * 255) / 100);
  if (s === 0) return (v << 16) | (v << 8) | v;
  const region = Math.floor(h / 43), remainder = (h - region * 43) * 6;
  const p = (v * (255 - s)) >> 8, q = (v * (255 - ((s * remainder) >> 8))) >> 8, t = (v * (255 - ((s * (255 - remainder)) >> 8))) >> 8;
  const [r, g, b] = [[v, t, p], [q, v, p], [p, v, t], [p, q, v], [t, p, v]][region] ?? [v, p, q];
  return ((r & 255) << 16) | ((g & 255) << 8) | (b & 255);
}
/** A lamp's own colour through Home Assistant's contrast rule (tile_controls::lamp_color): under 10 % saturation the
 * amber of a lamp that is on, else at least 40 %. Hue and saturation in whole degrees and percent. */
export const lampColor = (hue: number, saturation: number) =>
  saturation < 10 ? c.AMBER : hsvRgb(((hue % 360) + 360) % 360, Math.min(100, Math.max(40, saturation)), 100);
/** Home Assistant's colour for the state, as tile_controls::accent gives it (and a lamp's own colour while it is on). */
export function accent(entity: string, value: Value) {
  const domain = entity.split(".")[0], state = value?.state || "", a = value?.a || {};
  if (domain === "binary_sensor") return alarms.has(a.device_class) ? c.RED : c.AMBER;
  // A lamp's own colour while it is on (runtime_tiles: tile_controls::lamp_color of the hue and saturation the screen
  // rounds them to, page_receiver.cpp).
  if (domain === "light" && tileActive(entity, value) && Array.isArray(a.hs_color)) {
    const [hue, saturation] = a.hs_color;
    if (typeof hue === "number" && typeof saturation === "number" && Number.isFinite(hue) && Number.isFinite(saturation))
      return lampColor(Math.round(Math.min(360, Math.max(0, hue))), Math.round(Math.min(100, Math.max(0, saturation))));
  }
  if (["light", "switch", "input_boolean", "script", "automation", "remote", "timer", "camera"].includes(domain)) return c.AMBER;
  if (domain === "climate") return modes[state] || c.AMBER;
  if (domain === "vacuum") return state === "error" ? c.RED : c.TEAL;
  if (domain === "fan") return c.CYAN;
  // A humidifier is Home Assistant's blue while it is on (--state-humidifier-on-color), drying or humidifying alike.
  if (domain === "humidifier") return c.BLUE;
  if (["cover", "scene"].includes(domain)) return c.PURPLE;
  if (domain === "media_player") return c.LIGHT_BLUE;
  if (["select", "input_select"].includes(domain)) return c.INDIGO;
  if (["number", "input_number"].includes(domain)) return c.TEAL;
  if (domain === "weather") return weather[state] || c.AMBER;
  if (domain === "sun") return state === "above_horizon" ? c.AMBER : c.INDIGO;
  if (domain === "person") return state === "home" ? c.GREEN : c.BLUE;
  if (domain === "alarm_control_panel") return state === "triggered" ? c.RED : ["arming", "pending", "disarming"].includes(state) ? c.ORANGE : c.GREEN;
  if (domain === "lock") return state === "locked" ? c.GREEN : ["locking", "unlocking", "opening"].includes(state) ? c.ORANGE : c.RED;
  if (domain === "sensor") {
    // A number to its last letter, as strtof reads it on the screen: an empty state is none.
    const charge = /\S$/.test(state) ? Number(state) : NaN;
    if (a.device_class === "battery" && Number.isFinite(charge)) return charge >= 70 ? c.GREEN : charge >= 30 ? c.ORANGE : c.RED;
    if (a.unit_of_measurement === "lx") return c.AMBER;
    if (["°C", "°F"].includes(a.unit_of_measurement)) return c.DEEP_ORANGE;
    if (["kWh", "Wh"].includes(a.unit_of_measurement)) return c.PURPLE;
    if (a.unit_of_measurement === "%") return c.TEAL;
  }
  return c.BLUE;
}
export function tilePalette(entity: string, value: Value, runs = false) {
  const available = entity.startsWith("screen.") || Boolean(value?.state && !["unknown", "unavailable"].includes(value.state));
  // A locked lock is inactive in Home Assistant and still green (--state-lock-locked-color), as on the screen.
  const color = accent(entity, value), active = tileActive(entity, value, runs) || (entity.startsWith("lock.") && available), state = active ? color : c.GREY;
  const fill = available && (entity.startsWith("cover.") || active) ? color : c.GREY;
  return {
    icon: hex(available ? mix(state, theme.iconBase, theme.iconWeight) : theme.roles.OFF.light),
    circle: hex(available ? mix(state, theme.roles.CARD.light, 38) : theme.roles.TRACK.light),
    accent: hex(fill), track: hex(mix(fill, theme.roles.CARD.light, 51)),
  };
}
