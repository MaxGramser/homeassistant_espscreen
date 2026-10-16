// The screensaver clock's faces as the firmware draws them (components/smart_display/module_clock_faces.h), for the
// editor's small picture of the glass: Glass's ring of ticks along the glass, Classic's round dial, and Bauhaus's grid of
// shapes with its composition of this ten minutes. The same rules in the same numbers, drawn as SVG; the letters are the
// browser's, so only the places and the proportions are the screen's.
import theme from "virtual:esp-screens-theme";

export type SaverFaceKind = "digital" | "glass" | "classic" | "bauhaus";
export type SaverLook = "dark" | "light" | "auto";
export const SAVER_FACES: SaverFaceKind[] = ["digital", "glass", "classic", "bauhaus"];
export const SAVER_LOOKS: SaverLook[] = ["dark", "light", "auto"];

const hex = (color: number) => `#${color.toString(16).padStart(6, "0")}`;
const mix = (a: number, b: number, weight: number) => [16, 8, 0].reduce((out, shift) =>
  out | Math.floor((((a >> shift) & 255) * weight + ((b >> shift) & 255) * (255 - weight)) / 255) << shift, 0);
const role = (name: string, dark: boolean) => theme.roles[name]?.[dark ? "dark" : "light"] ?? 0;

/** The face's colours by its look, as clock_faces::ink. */
export function faceInk(dark: boolean) {
  const face = dark ? role("CAMERA_PAGE", true) : role("PAGE", false), ink = role("INK", dark);
  return {
    face: hex(face), ink: hex(ink), soft: hex(mix(ink, face, 150)), tick: hex(mix(ink, face, dark ? 225 : 235)),
    minor: hex(mix(ink, face, dark ? 120 : 110)), hand: hex(role("CLOCK_HAND", dark)), edge: hex(dark ? face : mix(ink, face, 200)),
    accent: hex(theme.ha.ORANGE), raised: hex(role("CARD", dark)),
  };
}

/** How far from the middle a ray at `theta` (clockwise from 12) leaves a rectangle of half sizes hx, hy (clock_faces::ring_edge). */
export function ringEdge(theta: number, hx: number, hy: number) {
  const dx = Math.sin(theta), dy = -Math.cos(theta);
  return Math.min(dx ? hx / Math.abs(dx) : Infinity, dy ? hy / Math.abs(dy) : Infinity);
}

/** Glass offers twelve numerals only on glass about as wide as it is tall: on long glass they bunch at 12 and 6. */
export const twelveFits = (width: number, height: number) => Math.max(width, height) / Math.min(width, height) <= 1.25;

/** The firmware's hash (clock_faces::mix32), so the editor's Bauhaus is the composition the screen shows. */
export function mix32(value: number) {
  let x = value >>> 0;
  x ^= x >>> 16; x = Math.imul(x, 0x7feb352d) >>> 0; x ^= x >>> 15; x = Math.imul(x, 0x846ca68b) >>> 0; x ^= x >>> 16;
  return x >>> 0;
}
export type BauhausShape = { x: number; y: number; w: number; h: number; ground: string; fig: string; shape: number; extra: number };
/** Bauhaus at a moment: its squares with their shapes, and where its clock stands (clock_faces::bauhaus). */
export function bauhaus(width: number, height: number, at: Date, dark: boolean) {
  const colours = ["BAUHAUS_RED", "BAUHAUS_YELLOW", "BAUHAUS_BLUE", "BAUHAUS_BLACK", "BAUHAUS_CREAM"].map((name) => hex(role(name, dark)));
  const cream = colours[4], black = colours[3];
  const S = Math.min(width, height), cell = Math.max(1, Math.floor(S / 3));
  const half = Math.floor(cell / 2), rows = Math.max(3, Math.floor((height + half) / cell)), cols = Math.max(3, Math.floor((width + half) / cell)), cells = rows * cols;
  // ESPTime's day_of_year counts from 1 on the first of January.
  const start = new Date(at.getFullYear(), 0, 0), day = Math.floor((at.getTime() - start.getTime()) / 86400000);
  const minute = at.getMinutes(), period = (day * 144 + at.getHours() * 6 + Math.floor(minute / 10)) >>> 0;
  const turns = new Array(cells).fill(0);
  for (let m = 1; m <= minute % 10; m++) turns[mix32(Math.imul(period, 977) + m) % cells]++;
  const squares: BauhausShape[] = [];
  for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
    let seed = mix32(Math.imul(period, 7919) + (r * cols + c) * 131 + Math.imul(turns[r * cols + c], 31337));
    const next = () => { seed = mix32(seed + 0x9e3779b9); return seed & 0x7fff; };
    const x = Math.floor((c * width) / cols), y = Math.floor((r * height) / rows);
    const w = Math.floor(((c + 1) * width) / cols) - x, h = Math.floor(((r + 1) * height) / rows) - y;
    const ground = colours[next() % 5];
    let fig = colours[next() % 5];
    if (fig === ground) fig = ground === cream ? black : cream;
    const shape = next() % 5;
    const extra = shape === 1 ? next() % 4 : shape === 2 ? next() & 1 : 0;
    squares.push({ x, y, w, h, ground, fig, shape, extra });
  }
  const turn = period * 2.39996, reach = S * 0.05;
  return { squares, cx: width / 2 + Math.cos(turn) * reach, cy: height / 2 + Math.sin(turn) * reach, r: S * 0.36,
    red: colours[0], dial: dark ? black : cream, hand: hex(role(dark ? "BAUHAUS_CREAM" : "BAUHAUS_BLACK", false)) };
}
