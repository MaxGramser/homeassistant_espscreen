import theme from "virtual:esp-screens-theme";

type Value = { state: string; a?: Record<string, any> } | null | undefined;
const c = theme.ha;
const alarms = new Set(["battery", "carbon_monoxide", "gas", "heat", "lock", "moisture", "problem", "safety", "smoke", "sound", "tamper"]);
const weather: Record<string, number> = { sunny: c.AMBER, "clear-night": c.DEEP_PURPLE, partlycloudy: c.BLUE_GREY, cloudy: c.LIGHT_GREY,
  fog: c.GREY, rainy: c.BLUE, pouring: c.INDIGO, snowy: c.ICE, "snowy-rainy": c.LIGHT_BLUE, hail: c.CYAN,
  lightning: c.YELLOW, "lightning-rainy": c.LIME, windy: c.GREEN, "windy-variant": c.GREEN, exceptional: c.RED };
const modes: Record<string, number> = { heat: c.DEEP_ORANGE, cool: c.BLUE, heat_cool: c.AMBER, auto: c.GREEN, fan_only: c.CYAN, dry: c.ORANGE };
const hex = (color: number) => `#${color.toString(16).padStart(6, "0")}`;
const mix = (a: number, b: number, weight: number) => [16, 8, 0].reduce((out, shift) =>
  out | Math.floor((((a >> shift) & 255) * weight + ((b >> shift) & 255) * (255 - weight)) / 255) << shift, 0);

/** Mirrors Tile::active and tile_controls::accent, with paints read from theme.h. */
export function tileActive(entity: string, value: Value) {
  const domain = entity.split(".")[0], state = value?.state;
  if (domain === "screen") return true;
  if (!state || state === "unavailable") return false;
  if (["scene", "button", "input_button", "image"].includes(domain)) return true;
  if (["unknown", "off"].includes(state)) return false;
  if (domain === "cover") return state !== "closed";
  if (domain === "person") return state !== "not_home";
  if (domain === "media_player") return state !== "standby";
  if (domain === "vacuum") return !["idle", "docked", "paused"].includes(state);
  if (domain === "timer") return state === "active";
  if (domain === "camera") return ["streaming", "recording"].includes(state);
  if (domain === "alarm_control_panel") return state !== "disarmed";
  return true;
}
function accent(entity: string, value: Value) {
  const domain = entity.split(".")[0], state = value?.state || "", a = value?.a || {};
  if (domain === "binary_sensor") return alarms.has(a.device_class) ? c.RED : c.AMBER;
  if (domain === "light" && tileActive(entity, value) && Array.isArray(a.hs_color) && a.hs_color[1] >= 10) {
    const hue = Number(a.hs_color[0]) % 360, saturation = Math.max(40, Number(a.hs_color[1])) / 100;
    // HSV at full value, matching the firmware's minimum-saturation contrast rule.
    const channel = (n: number) => { const k = (n + hue / 60) % 6; return Math.round(255 * (1 - saturation * Math.max(0, Math.min(k, 4 - k, 1)))); };
    return (channel(5) << 16) | (channel(3) << 8) | channel(1);
  }
  if (["light", "switch", "input_boolean", "script", "timer", "camera"].includes(domain)) return c.AMBER;
  if (domain === "climate") return modes[state] || c.AMBER;
  if (domain === "vacuum") return state === "error" ? c.RED : c.TEAL;
  if (domain === "fan") return c.CYAN;
  if (["cover", "scene"].includes(domain)) return c.PURPLE;
  if (domain === "media_player") return c.LIGHT_BLUE;
  if (["select", "input_select"].includes(domain)) return c.INDIGO;
  if (["number", "input_number"].includes(domain)) return c.TEAL;
  if (domain === "weather") return weather[state] || c.AMBER;
  if (domain === "sun") return state === "above_horizon" ? c.AMBER : c.INDIGO;
  if (domain === "person") return state === "home" ? c.GREEN : c.BLUE;
  if (domain === "alarm_control_panel") return state === "triggered" ? c.RED : ["arming", "pending", "disarming"].includes(state) ? c.ORANGE : c.GREEN;
  if (domain === "sensor") {
    const charge = Number(state);
    if (a.device_class === "battery" && Number.isFinite(charge)) return charge >= 70 ? c.GREEN : charge >= 30 ? c.ORANGE : c.RED;
    if (a.unit_of_measurement === "lx") return c.AMBER;
    if (["°C", "°F"].includes(a.unit_of_measurement)) return c.DEEP_ORANGE;
    if (["kWh", "Wh"].includes(a.unit_of_measurement)) return c.PURPLE;
    if (a.unit_of_measurement === "%") return c.TEAL;
  }
  return c.BLUE;
}
export function tilePalette(entity: string, value: Value) {
  const available = entity.startsWith("screen.") || Boolean(value?.state && !["unknown", "unavailable"].includes(value.state));
  const color = accent(entity, value), active = tileActive(entity, value), state = active ? color : c.GREY;
  const fill = available && (entity.startsWith("cover.") || active) ? color : c.GREY;
  return {
    icon: hex(available ? mix(state, theme.iconBase, theme.iconWeight) : theme.roles.OFF.light),
    circle: hex(available ? mix(state, theme.roles.CARD.light, 38) : theme.roles.TRACK.light),
    accent: hex(fill), track: hex(mix(fill, theme.roles.CARD.light, 51)),
  };
}
