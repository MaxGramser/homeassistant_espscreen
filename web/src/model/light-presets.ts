// A light's presets (module light_presets, docs/LIGHT_PRESETS.md) in the editor: up to four round keys on a light's tile,
// each a brightness with a white shade or a colour, kept in the tile's options as `presets` and checked by the add-on's
// light_presets.py. The colours, the match with the light's state and the row the keys stand in are the firmware's
// (module_light_presets.h), ported here number for number; tests/test_editor_parity.py compares the two.
import { touchMin, uiScale, type Shape } from "./ui-scale";

export const MAX = 4;
/** The white shades a preset may name, in kelvin (light_presets.KELVIN). */
export const KELVIN = [1000, 15000] as const;
export const OPTION = "presets";
/** Whether each disc shows its brightness (light_presets.LEVELS): stored only when it does. */
export const LEVELS = "preset_levels";

/** A setting of the light's device (a row of its effects page): a select's option, or a number's value. */
export type RowValue = string | number;
/** A preset as the tile's options keep it: {"b": 80, "k": 2700}, {"b": 60, "h": 280, "s": 41}, {"b": 30}; with an effect of
 * the light's (`fx`) and settings of its device (`rw`: a WLED's colour palette, speed, intensity) where it has them, or
 * settings alone: a preset of the lamp itself ({"rw": {"select.desk_preset": "Film"}}), which sets everything by itself. */
export type Preset = { b?: number; k?: number; h?: number; s?: number; fx?: string; rw?: Record<string, RowValue> };
export type PresetKind = "level" | "white" | "colour";
export const kindOf = (p: Preset): PresetKind => p.k !== undefined ? "white" : p.h !== undefined ? "colour" : "level";
/** The settings of the light's device a preset may set, at most (light_presets.ROWS); a name's longest. */
export const ROWS = 4;
const NAME_LIMIT = 64;
const ROW_ENTITY = /^(select|number)\.[a-z0-9_]+$/;
/** The device's settings a preset names, in their order. */
export const rowsOf = (p: Preset): [string, RowValue][] => Object.entries(p.rw ?? {});
/** A preset of the lamp itself (Preset::device): its device's settings alone, no brightness. */
export const device = (p: Preset) => p.b === undefined && rowsOf(p).length > 0;
/** No colour of its own (Preset::neutral): an effect making its own colours, or the lamp's own preset. Its key is a plain
 * grey one, told by its name. */
export const neutral = (p: Preset) => kindOf(p) === "level" && (!!p.fx || rowsOf(p).length > 0);

const whole = (value: unknown, low: number, high: number) =>
  typeof value === "number" && Number.isInteger(value) && value >= low && value <= high ? value : null;
const named = (value: unknown): value is string => typeof value === "string" && value.trim() !== "" && [...value].length <= NAME_LIMIT;
/** One preset in its stored form, or null where the add-on refuses it (light_presets.preset). */
export function cleanPreset(item: unknown): Preset | null {
  if (!item || typeof item !== "object" || Array.isArray(item)) return null;
  const o = item as Record<string, unknown>;
  if (Object.keys(o).some((key) => !["b", "k", "h", "s", "fx", "rw"].includes(key))) return null;
  // The settings of the light's device: a select's option or a number's value each, by entity.
  let rw: Record<string, RowValue> | undefined;
  if ("rw" in o) {
    const rows = o.rw;
    if (!rows || typeof rows !== "object" || Array.isArray(rows)) return null;
    const entries = Object.entries(rows as Record<string, unknown>);
    if (!entries.length || entries.length > ROWS) return null;
    rw = {};
    for (const [entity, value] of entries) {
      if (!ROW_ENTITY.test(entity)) return null;
      if (entity.startsWith("select.") ? !named(value) : typeof value !== "number" || !Number.isFinite(value)) return null;
      rw[entity] = value as RowValue;
    }
  }
  if ("fx" in o && !named(o.fx)) return null;
  const extra = { ...(named(o.fx) ? { fx: o.fx } : {}), ...(rw ? { rw } : {}) };
  // A preset of the lamp itself needs no brightness; every other one has one.
  if (!("b" in o) && rw && !["k", "h", "s", "fx"].some((key) => key in o)) return { rw };
  const b = whole(o.b, 1, 100);
  if (b === null) return null;
  if ("k" in o) {
    const k = whole(o.k, KELVIN[0], KELVIN[1]);
    return k === null || "h" in o || "s" in o ? null : { b, k, ...extra };
  }
  if ("h" in o || "s" in o) {
    const h = whole(o.h, 0, 360), s = whole(o.s, 0, 100);
    return h === null || s === null ? null : { b, h: h % 360, s, ...extra };
  }
  return { b, ...extra };
}
/** The presets a tile keeps, those the screen can take. */
export function presetsOf(options: Record<string, unknown> | undefined): Preset[] {
  const list = options?.[OPTION];
  return Array.isArray(list) ? list.slice(0, MAX).map(cleanPreset).filter((p): p is Preset => p !== null) : [];
}
/** The device's settings a tile's presets name: their states are read beside the light's, for the ring. */
export const presetRowEntities = (options: Record<string, unknown> | undefined) =>
  [...new Set(presetsOf(options).flatMap((p) => rowsOf(p).map(([entity]) => entity)))];

// ---- What its key writes ----
/** A number as Home Assistant's action takes it (effects_page::number_text): "128", "12.5". */
export function numberText(value: number) {
  const text = value.toFixed(3).replace(/0+$/, "");
  return text.endsWith(".") ? text.slice(0, -1) : text;
}
export const rowText = (value: RowValue) => (typeof value === "number" ? numberText(value) : value);
/** The first two characters of a name ("Fi" of "Film"), whole characters (light_presets::initials). */
export const initials = (name: string) => Array.from(name).slice(0, 2).join("");
/** What a key writes in its middle (Presets::label): a plain key its name's first characters (its effect, else its first
 * setting), a brightness alone its brightness, any other its brightness where the tile asks for it; else nothing. */
export function presetLabel(p: Preset, levels: boolean) {
  if (neutral(p)) return initials(p.fx || rowText(rowsOf(p)[0][1]));
  return p.b !== undefined && (levels || kindOf(p) === "level") ? String(p.b) : "";
}

// ---- Its colour, as Home Assistant draws a favourite colour ----
const clamp8 = (v: number) => Math.round(Math.min(255, Math.max(0, v)));
/** convert-light-color.ts temperature2rgb (light_presets::kelvin_rgb), as 0xRRGGBB. */
export function kelvinRgb(kelvin: number) {
  const t = kelvin / 100;
  const r = t <= 66 ? 255 : 329.698727446 * Math.pow(t - 60, -0.1332047592);
  const g = t <= 66 ? 99.4708025861 * Math.log(t) - 161.1195681661 : 288.1221695283 * Math.pow(t - 60, -0.0755148492);
  const b = t >= 66 ? 255 : t <= 19 ? 0 : 138.5177312231 * Math.log(t - 10) - 305.0447927307;
  return (clamp8(r) << 16) | (clamp8(g) << 8) | clamp8(b);
}
/** convert-color.ts hs2rgb (light_presets::hs_rgb): the hue at the saturation, full value. */
export function hsRgb(hue: number, saturation: number) {
  const s = saturation / 100;
  const f = (n: number) => {
    const k = (n + hue / 60) % 6;
    return 255 - 255 * s * Math.max(Math.min(k, 4 - k, 1), 0);
  };
  return (clamp8(f(5)) << 16) | (clamp8(f(3)) << 8) | clamp8(f(1));
}
/** The disc's colour; a brightness alone has none (the key stands on the light's pale amber). */
export const presetRgb = (p: Preset): number | null =>
  p.k !== undefined ? kelvinRgb(p.k) : p.h !== undefined ? hsRgb(p.h, p.s ?? 0) : null;
/** WCAG relative luminance (rgb.ts luminosity). */
export function luminosity(c: number) {
  const lin = (v: number) => { const s = v / 255; return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4); };
  return 0.2126 * lin((c >> 16) & 255) + 0.7152 * lin((c >> 8) & 255) + 0.0722 * lin(c & 255);
}
/** Home Assistant gives a disc over 0.8 a hairline; a brightness alone stands on pale amber and has one too. */
export const pale = (p: Preset) => { const c = presetRgb(p); return c === null || luminosity(c) > 0.8; };
/** Dark ink where it reads better than white (0.179: where both are equal), white on a deep colour. */
export const darkInk = (p: Preset) => { const c = presetRgb(p); return c === null || luminosity(c) > 0.179; };
/** Whether a disc writes its brightness: where the tile asks for it, and always on a brightness alone, which has no colour
 * to tell it by; never on a plain key, which writes its name (presetLabel). */
export const levelShown = (p: Preset, levels: boolean) => !neutral(p) && p.b !== undefined && (levels || kindOf(p) === "level");
export const hex = (c: number) => `#${c.toString(16).padStart(6, "0")}`;

// ---- Which preset the light shows now ----
/** The light as its tile holds it (runtime_tiles preset_light): `white` while Home Assistant reports a colour
 * temperature, `level` its brightness 1-100 (100 where it reports none), the effect it runs and its device's settings as
 * they stand (`now`, by entity: a select's option, a number's value). */
export type LightNow = { on: boolean; white: boolean; level: number; kelvin: number; hue: number; saturation: number;
  effect?: string; now?: Record<string, RowValue> };
export function lightNow(live: { state?: string; a?: Record<string, any> } | null | undefined): LightNow {
  const a = live?.a || {}, brightness = Number(a.brightness), kelvin = Number(a.color_temp_kelvin);
  const hs = Array.isArray(a.hs_color) ? a.hs_color.map(Number) : [];
  const white = a.color_temp_kelvin != null && Number.isFinite(kelvin);
  return { on: live?.state === "on", white, effect: typeof a.effect === "string" ? a.effect : "",
    level: a.brightness != null && Number.isFinite(brightness) ? Math.min(100, Math.max(1, Math.round((brightness * 100) / 255))) : 100,
    kelvin: white ? Math.round(Math.min(15000, Math.max(1000, kelvin))) : 0,
    hue: Number.isFinite(hs[0]) ? Math.round(Math.min(360, Math.max(0, hs[0]))) : 0,
    saturation: Number.isFinite(hs[0]) && Number.isFinite(hs[1]) ? Math.round(Math.min(100, Math.max(0, hs[1]))) : 0 };
}
/** The effect and the device's settings a preset names, standing as it names them (light_presets::settings_show): a
 * select at the same option, a number within half a step. */
export function settingsShow(p: Preset, l: LightNow) {
  if (p.fx && (l.effect ?? "") !== p.fx) return false;
  return rowsOf(p).every(([entity, value]) => {
    const now = l.now?.[entity];
    if (now === undefined) return false;
    return typeof value === "number" ? typeof now === "number" && Math.abs(now - value) <= 0.5 : rowText(now) === value;
  });
}
/** The preset the light shows (light_presets::shows): a percent of brightness, 50 K of white, 3 of hue and saturation, its
 * effect and settings standing; the lamp's own preset by its settings alone. */
export function shows(p: Preset, l: LightNow) {
  if (device(p)) return settingsShow(p, l);
  if (!l.on || p.b === undefined || Math.abs(l.level - p.b) > 1 || !settingsShow(p, l)) return false;
  if (p.k !== undefined) return l.white && Math.abs(l.kelvin - p.k) <= 50;
  if (p.h !== undefined) {
    const d = Math.abs(l.hue - p.h) % 360;
    return !l.white && Math.min(d, 360 - d) <= 3 && Math.abs(l.saturation - (p.s ?? 0)) <= 3;
  }
  return true;
}
/** The first preset the light shows, or -1. */
export const shown = (list: readonly Preset[], l: LightNow) => list.findIndex((p) => shows(p, l));

// ---- A light group, lamp by lamp (light_presets::group_shows) ----
// Home Assistant's group reports the average of its lamps, a lamp in a white shade with the hue of that shade, so a
// colour preset on a group with a lamp that only takes white shades never matched the average. Read as Home Assistant
// carries the call out: every lamp on at the brightness, every lamp that can show the white shade or colour showing it.
type Live = { state?: string; a?: Record<string, any> } | null | undefined;
const COLOUR_MODES = ["hs", "rgb", "rgbw", "rgbww", "xy"];
export type Lamp = { on: boolean; unavailable: boolean; dims: boolean; color: boolean; temperature: boolean;
  level: number; hue: number; saturation: number; kelvin: number };
export function lampNow(live: Live): Lamp {
  const a = live?.a || {}, modes: string[] = Array.isArray(a.supported_color_modes) ? a.supported_color_modes : [];
  const now = lightNow(live), temperature = modes.includes("color_temp");
  return { on: now.on, unavailable: !live || live.state === "unavailable" || live.state === "unknown",
    dims: !modes.length || modes.some((m) => m !== "onoff"), color: modes.some((m) => COLOUR_MODES.includes(m)), temperature,
    level: now.level, hue: now.hue, saturation: now.saturation, kelvin: temperature && now.white ? now.kelvin : 0 };
}
export function lampShows(p: Preset, l: Lamp) {
  if (l.unavailable) return true;
  if (!l.on || p.b === undefined) return false;
  if (l.dims && Math.abs(l.level - p.b) > 1) return false;
  if (p.k !== undefined && l.temperature) return l.kelvin > 0 && Math.abs(l.kelvin - p.k) <= 50;
  if (p.h !== undefined && l.color) {
    const d = Math.abs(l.hue - p.h) % 360;
    return !l.kelvin && Math.min(d, 360 - d) <= 3 && Math.abs(l.saturation - (p.s ?? 0)) <= 3;
  }
  return true;
}
export const groupShows = (p: Preset, lamps: readonly Lamp[]) => lamps.every((l) => lampShows(p, l)) && lamps.some((l) => !l.unavailable);
/** The device's settings the presets name, as their entities stand now: a number's value, a select's option. */
export function rowsNow(list: readonly Preset[], liveOf: (entity: string) => Live) {
  const now: Record<string, RowValue> = {};
  for (const [entity] of list.flatMap(rowsOf)) {
    const state = liveOf(entity)?.state;
    if (state === undefined || state === "unavailable" || state === "unknown") continue;
    if (!entity.startsWith("number.")) now[entity] = state;
    else if (state !== "" && Number.isFinite(Number(state))) now[entity] = Number(state);
  }
  return now;
}
/** The preset a light shows (runtime_tiles::preset_lit): a light group's lamp by lamp, any other light by its own state;
 * the effect and the device's settings the light's own (a group's effect is the group's). */
export function presetLit(list: readonly Preset[], live: Live, liveOf: (entity: string) => Live) {
  const light = { ...lightNow(live), now: rowsNow(list, liveOf) };
  const members = Array.isArray(live?.a?.entity_id) ? (live!.a!.entity_id as unknown[]).filter((e): e is string => typeof e === "string" && e.startsWith("light.")) : [];
  const lives = members.map((e) => liveOf(e));
  // Without each lamp's own state (its modes) the group is read by itself, as a single light.
  if (!members.length || lives.some((l) => !Array.isArray(l?.a?.supported_color_modes) && l?.state !== "unavailable")) return shown(list, light);
  const lamps = lives.map((l) => lampNow(l));
  return list.findIndex((p) => (device(p) ? settingsShow(p, light) : groupShows(p, lamps) && settingsShow(p, light)));
}

// ---- Where the keys go ----
export type Row = { count: number; size: number; gap: number; length: number };
/** A row of `count` round keys in `length` x `across` (light_presets::row): each `wanted` where that fits, smaller down to
 * `least`, `gap` apart; as many as fit, the first first. */
export function row(length: number, across: number, count: number, wanted: number, least: number, gap: number): Row {
  const none = { count: 0, size: 0, gap: 0, length: 0 };
  if (count <= 0 || length <= 0 || across <= 0) return none;
  const size = Math.min(wanted, across);
  for (let n = Math.min(count, MAX); n > 0; --n) {
    const fit = Math.min(size, Math.trunc((length - (n - 1) * gap) / n));
    if (fit >= Math.min(least, size)) return { count: n, size: fit, gap, length: n * fit + (n - 1) * gap };
  }
  return none;
}
/** ui::mm on this glass. */
export const mm = (shape: Shape, n: number) => Math.floor(((shape.dpi || (shape.look === "compact" ? 143 : 170)) * n + 12) / 25);
/** The keys' sizes on this glass (module_light_presets.h): Home Assistant's 40 px disc is 6 mm, never below 5 mm, a card's a
 * finger wide; the ring stands its pad outside the disc and is `ringWidth` wide, `ring` the room it takes round a key. */
export function presetSizes(shape: Shape) {
  const { large, px } = uiScale(shape), ringPad = Math.max(2, px(3)), ringWidth = Math.max(2, px(2));
  return { tileKey: mm(shape, 6), cardKey: touchMin(shape), least: mm(shape, 5), gap: px(large ? 10 : 6), ringPad, ringWidth, ring: ringPad + ringWidth };
}
/** The keys a light's panel lays out in `room` x `across` (runtime_tiles layout_panel, presets): the row inside the ring's
 * room, its width and height with that room round it, and each key's place in it. */
export function presetPanel(shape: Shape, count: number, room: number, across: number) {
  const z = presetSizes(shape), r = row(room - 2 * z.ring, across, count, z.tileKey, z.least, z.gap), ring = r.count ? z.ring : 0;
  return { row: r, ring, width: r.length + 2 * ring, height: r.count ? r.size + 2 * ring : 0,
    keys: Array.from({ length: r.count }, (_, n) => ({ x: ring + n * (r.size + r.gap), y: ring, size: r.size })) };
}

// ---- What the light can be set to ----
/** What a light's supported_color_modes allow a preset: a white shade (color_temp) and a colour (hs, rgb, rgbw, rgbww, xy). */
export function lightModes(a: Record<string, any> | undefined) {
  const modes: string[] = Array.isArray(a?.supported_color_modes) ? a!.supported_color_modes.map(String) : [];
  return { white: modes.includes("color_temp"), colour: modes.some((m) => ["hs", "rgb", "rgbw", "rgbww", "xy"].includes(m)) };
}
/** The white shades the light takes (its min and max colour temperature), within what a screen keeps. */
export function kelvinRange(a: Record<string, any> | undefined): [number, number] {
  const low = Number(a?.min_color_temp_kelvin), high = Number(a?.max_color_temp_kelvin);
  const lo = Number.isFinite(low) && low > 0 ? Math.max(KELVIN[0], Math.round(low)) : 2000;
  const hi = Number.isFinite(high) && high > 0 ? Math.min(KELVIN[1], Math.round(high)) : 6500;
  return lo < hi ? [lo, hi] : [2000, 6500];
}
/** A preset of what the light shows now: its brightness, and its white shade or colour where it has one to set. */
export function fromLight(live: { state?: string; a?: Record<string, any> } | null | undefined): Preset {
  const a = live?.a || {}, l = lightNow(live), modes = lightModes(a), b = live?.state === "on" ? l.level : 100;
  if (live?.state === "on" && l.white && modes.white) return { b, k: Math.min(KELVIN[1], Math.max(KELVIN[0], l.kelvin)) };
  if (live?.state === "on" && Array.isArray(a.hs_color) && modes.colour) return { b, h: l.hue % 360, s: l.saturation };
  return startPreset(live);
}
/** A sensible first preset where the light is off: full brightness, in the light's own warm white where it has whites. */
export function startPreset(live: { state?: string; a?: Record<string, any> } | null | undefined): Preset {
  const a = live?.a || {}, modes = lightModes(a);
  if (modes.white) { const [lo, hi] = kelvinRange(a); return { b: 100, k: Math.min(hi, Math.max(lo, 2700)) }; }
  return { b: 100 };
}

// ---- What a preset may set beside its colour (the add-on's api/light-choices, light_effects.choices) ----
/** A row of the light's effects page with every choice it has: a select's options, a number's range; `key` its
 * translation key (color_palette, preset, playlist, speed, intensity, ...), `value` where it stands. */
export type ChoiceRow = { e: string; n: string; key: string; kind: "select" | "number"; options?: string[]; min?: number; max?: number; step?: number;
  value?: RowValue | null };
/** The light's effects ("Solid" first on a WLED) and its device's rows; a light group has effects at most. */
export type LightChoices = { effects: string[]; rows: ChoiceRow[] };
/** The selects that are the lamp's own presets (a WLED's preset and playlist): chosen as a preset of the lamp itself. */
export const DEVICE_KEYS = ["preset", "playlist"];
export const deviceRows = (c: LightChoices | null | undefined) =>
  (c?.rows ?? []).filter((r) => r.kind === "select" && DEVICE_KEYS.includes(r.key) && (r.options?.length ?? 0) > 0);
/** The rows an effect goes with (a colour palette, speed, intensity): every other one, as many as a preset keeps. */
export const settingRows = (c: LightChoices | null | undefined) => (c?.rows ?? []).filter((r) => !DEVICE_KEYS.includes(r.key)).slice(0, ROWS);
/** A row's value to start from: where it stands (`now`, else what the choices said), within what it takes. */
export function rowStart(row: ChoiceRow, now?: RowValue | null): RowValue | null {
  const value = now ?? row.value;
  if (row.kind === "select") {
    const options = row.options ?? [];
    return typeof value === "string" && options.includes(value) ? value : options[0] ?? null;
  }
  const low = row.min ?? 0, high = row.max ?? 100, n = Number(value);
  return value !== null && value !== undefined && value !== "" && Number.isFinite(n) ? Math.min(high, Math.max(low, n)) : low;
}
/** The preset with the light's effect and its device's settings as they stand: the Effect switch turned on, or the light's
 * state taken. The effect the light runs where it is one of its list, else the first. */
export function withEffect(p: Preset, c: LightChoices, effect: string | undefined, valueOf: (row: ChoiceRow) => RowValue | null | undefined): Preset {
  const rest = withoutEffect(p), fx = effect && c.effects.includes(effect) ? effect : c.effects[0];
  const rw: Record<string, RowValue> = {};
  for (const row of settingRows(c)) {
    const value = rowStart(row, valueOf(row));
    if (value !== null) rw[row.e] = value;
  }
  return { ...rest, ...(fx ? { fx } : {}), ...(Object.keys(rw).length ? { rw } : {}) };
}
/** The preset without an effect or settings of the device: its colour and brightness alone. */
export function withoutEffect(p: Preset): Preset {
  const { fx: _fx, rw: _rw, ...rest } = p;
  return rest;
}
/** A preset of the lamp itself: that select at that option, nothing else. */
export const devicePreset = (row: ChoiceRow, option: string): Preset => ({ rw: { [row.e]: option } });
