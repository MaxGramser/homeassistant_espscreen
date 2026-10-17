/** A sensor's meter (firmware 0.56.0, screen_manager/app/meter.py, docs/METER.md): where a value stands in its range,
 * as a ring, a tape or a bar of cells. Its range, its colours and the thresholds between them, as the add-on keeps them
 * (defaults never stored), and the places of its parts on a card of any size for the editor's mockup (TileMeter.vue).
 * Pure: the tile's options, what Home Assistant reports and the card's room come in; nothing is read from a store. */
import rules from "./page-rules.json";
import type { TileOptions } from "../types";

export const METER = rules.meter;
export type MeterStyle = "ring" | "tape" | "bar";
export const METER_STYLES = METER.styles as MeterStyle[];
/** A meter's own choices on a tile's options (meter.KEYS). */
export const METER_KEYS = ["meter", "min", "max", "segments", "colors", "thresholds"] as const;
const COLORS = METER.colors as Record<string, string>;
const DEFAULT_COLORS = METER.defaultColors as Record<string, string[]>;
/** The colours a segment may have: Home Assistant's theme colours by name, with the swatch's colour. */
export const meterColorNames = Object.keys(COLORS);
export const meterHex = (name: string) => COLORS[name];
/** The colour a tape's pointer has without colours of its own: Home Assistant's deep orange. */
export const POINTER = COLORS["deep-orange"];

const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);

/** The meter's look: the ring unless chosen. */
export const meterStyle = (options?: TileOptions): MeterStyle => (METER_STYLES.includes(options?.meter as MeterStyle) ? options!.meter as MeterStyle : "ring");
/** How many colours: one unless chosen. */
export const meterSegments = (options?: TileOptions): number => (METER.segments.includes(options?.segments as number) ? options!.segments as number : 1);
/** The tile's own range, when it has one. */
export const ownRange = (options?: TileOptions): [number, number] | null =>
  finite(options?.min) && finite(options?.max) && options!.min < options!.max ? [options!.min, options!.max] : null;
/** The range from Home Assistant: a percentage runs from 0 to 100, and so does any other value, as Home Assistant's gauge
 * card has it. */
export const haRange = (): [number, number] => [0, 100];
/** The range the meter shows: the tile's own, else Home Assistant's. */
export const meterRange = (options?: TileOptions): [number, number] => ownRange(options) ?? haRange();

/** The colour names of each segment as the screen paints them: the tile's own, or those chosen; null for one segment that
 * keeps the tile's own colour. */
export function meterColors(options?: TileOptions): (string | null)[] {
  const n = meterSegments(options), chosen = options?.colors;
  if (Array.isArray(chosen) && chosen.length === n && chosen.every((name) => typeof name === "string" && name in COLORS)) return chosen as string[];
  return n === 1 ? [null] : DEFAULT_COLORS[String(n)];
}
/** The thresholds between the segments in the sensor's unit: the tile's own, else where the screen puts them (the
 * shares of the range). */
export function meterThresholds(options?: TileOptions): number[] {
  const n = meterSegments(options), own = options?.thresholds;
  if (Array.isArray(own) && own.length === n - 1 && own.every(finite)) return own as number[];
  const [low, high] = meterRange(options);
  return startThresholds(low, high, n);
}

/** A step that reads well for a range this wide: a power of ten about a twentieth of it (400 – 1600 ppm: 10; 16 – 26 °C:
 * 0.1; 0 – 100 %: 1; 0 – 3000 W: 100). */
export function niceStep(span: number) {
  return span > 0 ? 10 ** Math.floor(Math.log10(span / 20)) : 1;
}
const round = (value: number, step: number) => {
  const digits = Math.max(0, -Math.floor(Math.log10(step)));
  return Number((Math.round(value / step) * step).toFixed(digits));
};
/** The thresholds a choice of segments starts from: 80 % and 90 % of the range, rounded to a step that reads well
 * (400 – 1600 ppm: 1360 and 1480; 16 – 26 °C: 24 and 25). Ascending, inside the range, or unrounded where the step is
 * too coarse for it. */
export function startThresholds(low: number, high: number, segments: number): number[] {
  const shares = METER.shares.slice(0, Math.max(0, segments - 1));
  const exact = shares.map((share) => low + share * (high - low));
  const step = niceStep(high - low), rounded = exact.map((value) => round(value, step));
  const ok = rounded.every((value, i) => value > low && value < high && (i === 0 || value > rounded[i - 1]));
  return ok ? rounded : exact;
}

/** The colour a value is painted in: its segment's (the last segment from its threshold up); `own` for one segment that
 * keeps the tile's own colour. */
export function zoneColor(value: number, options: TileOptions | undefined, own: string) {
  const colors = meterColors(options), thresholds = meterThresholds(options);
  let index = thresholds.findIndex((threshold) => value < threshold);
  if (index < 0) index = colors.length - 1;
  const name = colors[index];
  return name ? COLORS[name] : own;
}
/** Where a value stands in the range, from 0 to 1. */
export function share(value: number, [low, high]: [number, number]) {
  return high > low && Number.isFinite(value) ? Math.min(1, Math.max(0, (value - low) / (high - low))) : 0;
}

// ---- A range of your own: what the inspector fills in when a value lies outside Home Assistant's ----
const ladder = (above: number) => {
  // The first of 1, 2, 5 times a power of ten above a number: 840 -> 1000, 21.4 -> 50.
  const power = 10 ** Math.floor(Math.log10(above));
  return [1, 2, 5, 10].map((m) => m * power).find((value) => value > above) ?? 10 * power;
};
/** A range that holds the value: from the lowest to the highest of the last hours where the editor has them, widened to
 * round numbers; else from 0 to a round number above it (or from one below it to 0). */
export function suggestRange(value: number, history?: (number | null)[] | null): [number, number] {
  const known = (history ?? []).filter(finite).concat(finite(value) ? [value] : []);
  if (!known.length) return [0, 100];
  const lo = Math.min(...known), hi = Math.max(...known);
  if (known.length > 1 && hi > lo) {
    const step = ladder((hi - lo) / 5) / 2;
    const low = Math.floor(lo / step) * step, high = Math.ceil(hi / step) * step;
    const digits = Math.max(0, -Math.floor(Math.log10(step)));
    if (high > low) return [Number(low.toFixed(digits)), Number(high.toFixed(digits))];
  }
  if (value > 0) return [0, ladder(value)];
  if (value < 0) return [-ladder(-value), 0];
  return [0, 100];
}

// ---- The options as the add-on keeps them (meter.validate) ----
/** A tile's meter choices without what nothing means: the ring, one segment, the default colours of two or three, no
 * thresholds for one; a range only as both ends, low below high; none of them on a tile whose display is not the meter or
 * that is no sensor. */
export function canonicalMeter(entity: string, out: TileOptions) {
  if (out.display !== "meter" || !entity.startsWith("sensor.")) { for (const key of METER_KEYS) delete out[key]; return; }
  for (const key of METER_KEYS) if (out[key] === undefined) delete out[key];
  if (out.meter === "ring") delete out.meter;
  if (!(finite(out.min) && finite(out.max) && out.min < out.max)) { delete out.min; delete out.max; }
  const n = meterSegments(out);
  if (out.segments === 1 || !METER.segments.includes(out.segments as number)) delete out.segments;
  if (Array.isArray(out.colors) && (out.colors.length !== n || (n > 1 && out.colors.join() === DEFAULT_COLORS[String(n)].join()))) delete out.colors;
  if (n === 1 || (Array.isArray(out.thresholds) && out.thresholds.length !== n - 1)) delete out.thresholds;
}

// ---- The meter on a card of the mockup ----
/** A text's width in em, as near as the mockup needs it: digits and capitals wider than a dot or a space. */
export function ems(text: string) {
  return [...text].reduce((sum, ch) => sum + (/\d/.test(ch) ? 0.6 : /[ .,:'|il]/.test(ch) ? 0.3 : /[A-Z%MWmw@]/.test(ch) ? 0.78 : 0.6), 0);
}
/** A text on the card: its left edge or its centre, its top, the width it has and the size of its letters. */
export type TextBox = { x: number; y: number; w: number; size: number; align: "left" | "center" };
export type MeterInput = {
  style: MeterStyle;
  /** The card's content box in mockup pixels, and how many of them a pixel of the glass is. */
  width: number; height: number; glass: number;
  /** The value with its unit (ring, bar), the number and the unit apart (tape), the name. */
  valueText: string; number: string; unit: string; name: string;
  /** The ends of the range as the tape names them; none on a percentage. */
  ends: [string, string] | null;
  /** The last hours of the value can stand beside a ring. */
  history: boolean;
  /** A text's width in em as the browser draws it, at the value's weight; the estimate (`ems`) without it. */
  measure?: (text: string) => number;
};
export type RingLayout = { kind: "ring"; cx: number; cy: number; r: number; stroke: number; circle: number; icon: number; value: TextBox; name: TextBox | null;
  line: { x: number; y: number; w: number; h: number } | null };
export type TapeLayout = { kind: "tape"; name: TextBox | null; value: TextBox; unitSize: number; x0: number; x1: number; base: number; long: number; short: number;
  pointer: { y1: number; y2: number; width: number }; ends: { y: number; size: number } | null; hair: number };
export type BarLayout = { kind: "bar"; value: TextBox; name: TextBox | null; cells: { x: number; y: number; w: number; h: number; count: number; size: number; gap: number; vertical: boolean } };
export type MeterLayout = RingLayout | TapeLayout | BarLayout;

const LINE = 1.2;
const clamp = (value: number, low: number, high: number) => Math.min(high, Math.max(low, value));
// The largest size of letters up to `most` at which a text fits a width, never under `least` (the text then ends in dots).
// How wide a text is in em: the browser's own measure where the face has one, else the estimate above.
let measure = ems;
const fit = (text: string, width: number, most: number, least: number) => clamp(Math.min(most, width / Math.max(measure(text), 0.5)), least, most);

/** Where each part of the meter stands on a card of this room: every box inside the card, the texts apart. */
export function meterLayout(input: MeterInput): MeterLayout {
  measure = input.measure ?? ems;
  if (input.style === "tape") return tapeLayout(input);
  if (input.style === "bar") return barLayout(input);
  return ringLayout(input);
}

function ringLayout({ width: w, height: h, glass, valueText, name, history }: MeterInput): RingLayout {
  // A roomy wide card (360 px of glass or more) gives its right half to the last hours; a card wider than high stands
  // the words beside the ring.
  const roomy = history && w / glass >= 360 && w > 1.3 * h;
  const side = roomy ? w / 2 : w;
  // A long card (wider than 1.3 times its height, as meter_card.h plan_ring has it): the words beside the ring.
  const beside = side > 1.3 * h;
  const line = roomy ? { x: w / 2 + clamp(w * 0.02, 4, 12), y: 0, w: w / 2 - clamp(w * 0.02, 4, 12), h } : null;
  if (beside) {
    // The ring as high as the card (its open bottom a quarter of it), the words beside it, in the middle.
    const stroke = clamp(h / 14, 2, 14);
    // The ring gives way so the value fits in letters of 10 px, down to a fifth of the card's height.
    const need = measure(valueText) * 10 + clamp(side * 0.05, 4, 16);
    const rr = Math.max(4, h * 0.2, Math.min((h - stroke) / 1.5, (side * 0.45 - stroke) / 2, (side - need - stroke) / 2));
    const cx = rr + stroke / 2, cy = (h - 1.5 * rr) / 2 + rr;
    const x = cx + rr + stroke / 2 + clamp(side * 0.05, 4, 16), room = side - x;
    let size = fit(valueText, room, clamp(h * 0.3, 11, 40), 9);
    const nameSize = fit(name, room, clamp(size * 0.62, 8, 16), 7);
    const both = size * LINE + nameSize * LINE <= h;
    if (!both) size = Math.min(size, h / LINE);
    const top = (h - (size * LINE + (both ? nameSize * LINE : 0))) / 2;
    return { kind: "ring", cx, cy, r: rr, stroke, circle: rr * 0.48, icon: rr * 0.42,
      value: { x, y: top, w: room, size, align: "left" }, name: both ? { x, y: top + size * LINE, w: room, size: nameSize, align: "left" } : null, line };
  }
  // Stacked: the ring at the top, its value and name under its ends; as large as the room allows.
  const sizeFor = (d: number) => clamp(d * 0.16, 10, 34);
  let r = Math.min(side / 2, h / 2);
  for (let i = 0; i < 40; i++) {
    const stroke = clamp(r / 7, 2, 16), size = sizeFor(2 * r), nameSize = clamp(size * 0.62, 8, 16);
    const needed = stroke / 2 + r + 0.42 * r + size * LINE + nameSize * LINE;
    if (needed <= h && 2 * r + stroke <= side) break;
    r *= 0.95;
  }
  const stroke = clamp(r / 7, 2, 16);
  let size = sizeFor(2 * r);
  const nameSize = fit(name, side, clamp(size * 0.62, 8, 16), 7);
  size = fit(valueText, side, size, 8);
  const cy = stroke / 2 + r;
  // The value between the ring's ends while it fits there; wider (a narrow, standing card) it stands under them.
  const under = measure(valueText) * size > 1.4 * r && cy + 0.5 * r + stroke / 2 + 2 + size * LINE <= h;
  let top = under ? cy + 0.5 * r + stroke / 2 + 2 : cy + 0.42 * r;
  // On a low card the name goes first, then the value climbs into the ring's open bottom.
  let showName = top + size * LINE + nameSize * LINE <= h;
  if (!showName) top = Math.min(top, h - size * LINE);
  if (top + size * LINE > h) { size = Math.max(6, (h - top) / LINE); showName = false; }
  const total = top + size * LINE + (showName ? nameSize * LINE : 0), drop = Math.max(0, (h - total) / 2);
  const cx = side / 2;
  return { kind: "ring", cx, cy: cy + drop, r, stroke, circle: r * 0.48, icon: r * 0.42,
    value: { x: 0, y: top + drop, w: side, size, align: "center" },
    name: showName ? { x: 0, y: top + drop + size * LINE, w: side, size: nameSize, align: "center" } : null,
    line };
}

function tapeLayout({ width: w, height: h, glass, number, unit, name, ends }: MeterInput): TapeLayout {
  const hair = Math.max(1, glass);
  // The name small and muted above the value; on a low card the two share one row.
  // In small capitals, a little apart (0.04 em a letter).
  const capsEms = measure(name.toUpperCase()) + 0.04 * name.length;
  let nameSize = clamp(Math.min(clamp(h * 0.09, 8, 14), w / Math.max(capsEms, 0.5)), 7, 14);
  let size = fit(number + (unit ? "MM" : ""), w, clamp(h * 0.34, 12, 72), 10);
  let long = clamp(h * 0.12, 6, 28);
  const endSize = clamp(nameSize, 8, 13);
  const pointerOver = Math.max(2, long * 0.25);
  const rulerRoom = pointerOver + long;
  let endsRoom = ends ? endSize * LINE + 2 : 0;
  const stacked = nameSize * LINE + size * LINE + rulerRoom + endsRoom + 6 <= h;
  if (!stacked) {
    // One row of words over the ruler; the end numbers only while there is room for them.
    size = fit(number + (unit ? "MM" : "") + name, w, clamp(h * 0.4, 10, 40), 9);
    nameSize = clamp(size * 0.55, 7, 12);
    long = clamp(h * 0.18, 4, 20);
    if (size * LINE + long * 1.25 + endsRoom + 4 > h) endsRoom = 0;
    if (size * LINE + long * 1.25 + 4 > h) { size = Math.max(7, (h - long * 1.25 - 4) / LINE); }
  }
  const showEnds = Boolean(ends) && endsRoom > 0;
  const endWidth = showEnds ? Math.max(measure(ends![0]), measure(ends![1])) * endSize : 0;
  const x0 = Math.max(hair, endWidth / 2), x1 = w - x0;
  const over = Math.max(2, long * 0.25), below = Math.min(over, 2);
  const base = h - (showEnds ? endsRoom : 0) - below - hair;
  const words = stacked ? nameSize * LINE + size * LINE : size * LINE;
  // The words stand in the middle of the room above the ruler.
  const top = Math.max(0, (base - long - over - words) / 2);
  // Stacked, the name stands in the top corner and the value in the middle of the room between it and the ruler.
  const middle = Math.max(nameSize * LINE, (nameSize * LINE + base - long - over - size * LINE) / 2);
  const nameBox: TextBox | null = stacked ? { x: 0, y: 0, w, size: nameSize, align: "left" } : { x: 0, y: top + (size - nameSize) * 0.8, w: w / 2, size: nameSize, align: "left" };
  const valueBox: TextBox = stacked ? { x: 0, y: middle, w, size, align: "center" } : { x: w / 2, y: top, w: w / 2, size, align: "left" };
  return { kind: "tape", name: nameBox, value: valueBox, unitSize: size * 0.45, x0, x1, base, long, short: long * 0.5,
    pointer: { y1: base - long - over, y2: base + below, width: Math.max(2, 3 * glass) }, ends: showEnds ? { y: base + below + 2, size: endSize } : null, hair };
}

function barLayout({ width: w, height: h, glass, valueText, name: title }: MeterInput): BarLayout {
  const cell = clamp(4 * glass, 2, 8), gap = Math.max(1, cell * 0.6);
  const standing = h > 1.1 * w;
  if (standing) {
    // Upright at the right, about a third of the card's width; the words at the top beside it.
    const barW = Math.max(cell * 3, w * 0.3), x = w - barW, room = x - clamp(w * 0.05, 4, 12);
    const size = fit(valueText, room, clamp(w * 0.16, 10, 36), 8), nameSize = fit(title, room, clamp(size * 0.62, 8, 16), 7);
    const count = Math.max(4, Math.floor((h + gap) / (cell + gap)));
    return { kind: "bar", value: { x: 0, y: 0, w: room, size, align: "left" }, name: { x: 0, y: size * LINE, w: room, size: nameSize, align: "left" },
      cells: { x, y: 0, w: barW, h, count, size: cell, gap, vertical: true } };
  }
  let size = fit(valueText, w, clamp(Math.min(h * 0.24, w * 0.14), 10, 40), 8), nameSize = fit(title, w, clamp(size * 0.62, 8, 16), 7);
  const least = Math.max(6, h * 0.22);
  let words = size * LINE + nameSize * LINE + clamp(h * 0.05, 2, 10);
  let name: TextBox | null = { x: 0, y: size * LINE, w, size: nameSize, align: "left" };
  if (h - words < least) {
    // A low card: the value and the name on one row, the cells under them.
    size = Math.min(size, Math.max(7, (h - least - 2) / LINE));
    nameSize = clamp(size * 0.7, 7, 14);
    words = size * LINE + 2;
    const valueW = Math.min(w * 0.55, measure(valueText) * size + 4);
    name = { x: valueW + 4, y: (size - nameSize) * 0.8, w: Math.max(0, w - valueW - 4), size: nameSize, align: "left" };
    if (name.w < nameSize * 2) name = null;
  }
  const count = Math.max(4, Math.floor((w + gap) / (cell + gap)));
  return { kind: "bar", value: { x: 0, y: 0, w: name && name.x ? name.x - 4 : w, size, align: "left" }, name,
    cells: { x: 0, y: words, w, h: Math.max(2, h - words), count, size: cell, gap, vertical: false } };
}

/** A tape's still ruler: at most five long ticks on round steps of the range (its ends among them), short ones between
 * where they have room (at least `room` pixels apart). `x0` and `x1` are where the ends stand. */
export function tapeTicks(low: number, high: number, x0: number, x1: number, room = 5) {
  const span = high - low, width = x1 - x0;
  if (!(span > 0) || !(width > 0)) return [] as { x: number; long: boolean }[];
  const power = 10 ** Math.floor(Math.log10(span));
  // The ends, and round steps between them that keep half a step clear of either end.
  const between = (step: number) => {
    const out: number[] = [];
    for (let v = Math.ceil(low / step - 1e-9) * step; v < high - step / 2; v += step) if (v > low + step / 2) out.push(Number(v.toPrecision(12)));
    return out;
  };
  const step = [0.1, 0.2, 0.25, 0.5, 1, 2, 2.5, 5, 10].map((m) => m * power).find((s) => between(s).length <= 3) ?? span;
  const at = (value: number) => x0 + ((value - low) / span) * width;
  const ticks: { x: number; long: boolean }[] = [];
  const longs = [low, ...between(step), high];
  for (const v of longs) ticks.push({ x: at(v), long: true });
  // Short ticks: each long step cut in five, or in two, where they stand far enough apart.
  for (const parts of [5, 2]) {
    const gap = (step / parts / span) * width;
    if (gap < room) continue;
    for (let i = 0; i < longs.length - 1; i++)
      for (let v = longs[i] + step / parts; v < longs[i + 1] - step / parts / 2; v += step / parts) ticks.push({ x: at(v), long: false });
    break;
  }
  return ticks.sort((a, b) => a.x - b.x);
}

/** A colour of the theme mixed over another: `weight` of the first, from 0 to 1 (a dimmed cell, a tinted circle). */
export function tint(color: string, over: string, weight: number) {
  const a = parseInt(color.slice(1), 16), b = parseInt(over.slice(1), 16);
  const mixed = [16, 8, 0].reduce((out, shift) => out | (Math.round(((a >> shift) & 255) * weight + ((b >> shift) & 255) * (1 - weight)) << shift), 0);
  return `#${mixed.toString(16).padStart(6, "0")}`;
}

/** The arc of a ring that opens at the bottom (240°, from 150° to 390°, clockwise), from one share of it to another. */
export function arcPath(cx: number, cy: number, r: number, from: number, to: number) {
  const angle = (s: number) => ((150 + 240 * s) * Math.PI) / 180;
  const point = (s: number) => `${(cx + r * Math.cos(angle(s))).toFixed(2)} ${(cy + r * Math.sin(angle(s))).toFixed(2)}`;
  return `M${point(from)} A${r.toFixed(2)} ${r.toFixed(2)} 0 ${(to - from) * 240 > 180 ? 1 : 0} 1 ${point(to)}`;
}
