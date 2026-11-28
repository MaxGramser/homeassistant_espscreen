// A robot vacuum's larger tile (docs/VACUUM.md, "A larger tile") in glass pixels, as the screen lays it out: a small app
// screen on a tile. A header (the icon, the name, the state, status chips with icons), a hero in a frame (the map, the
// rooms as icon tiles, the routines, or the map with the rooms) and a control dock (the cleaning mode as icons, Dock, and
// Start one size up as the focal point). A short tile gives way in a fixed order: the mode control, then the keys move
// up into the header (the battery into the state line), then a last room tile says "+N". Pure: the board's shape, the
// card's room and what the robot has come in; TileVacuum draws what this places.
import { lineOf, textWidth, touchMin, uiScale } from "./ui-scale";

type Shape = Parameters<typeof uiScale>[0] & { spacing?: { circle?: number } };
/** A text's width in glass pixels in `size`, bold or not: the page's own measure where it has one, else an estimate. */
type Measure = (text: string, size: number, bold?: boolean) => number;
let width: Measure = (text, size) => textWidth(text, size);
export const VACUUM_FACES = ["map", "rooms", "routines", "map_rooms"];
export type Box = { x: number; y: number; w: number; h: number };
export type Place = Box & { index: number };
export type StatusChip = { box: Box; icon: string; words: string; ink: "teal" | "charging" | "slate" | "red" };
export type VacuumLayout = {
  circle: number; head: number; text: { x: number; w: number }; chips: StatusChip[];
  dock: Box | null; start: Box; mode: Box | null; frame: Box; frameRadius: number; tileRadius: number;
  map: Box | null; rooms: Place[]; bigIcons: boolean; more: (Box & { count: number }) | null;
  routines: Place[]; routinesMore: (Box & { count: number }) | null;
  fonts: { label: number; small: number; mini: number; icon: number; watchIcon: number };
};
export type VacuumInput = {
  face: string; width: number; height: number; rooms: string[]; routines: string[]; map: boolean; modes: number; second: boolean;
  state: string; battery: number | null; charging: boolean; progress: number | null; radius: number; pad: number; measure?: Measure;
};

/** The cleaning mode as the tile's segments (tile_controls::vacuum_role's letters, one per option, core.VACUUM_ROLES):
 * two to four, each of its own kind, so each has its own icon; else none, and the card keeps the choice. */
export function tileModes(roles: string) {
  return roles.length >= 2 && roles.length <= 4 && new Set(roles).size === roles.length ? roles : "";
}
/** A mode's icons by its kind: the fan for vacuuming, the water for mopping, both for both, automatic its own. */
export const MODE_ICONS: Record<string, string[]> = { v: ["F0210"], m: ["F058C"], b: ["F0210", "F058C"], a: ["F18F2"] };

/** The look's sizes on this board, as the firmware takes them (ui_scale.h px, touch_min). */
export function vacuumMetrics(shape: Shape) {
  const { large, px } = uiScale(shape), touch = touchMin(shape), f = shape.fonts || {};
  const circle = shape.spacing?.circle ?? px(54);
  const fonts = { label: f.label ?? px(large ? 18 : 11), small: f.sublabel ?? px(large ? 16 : 11), mini: f.icon_mini ?? px(large ? 26 : 18),
    icon: Math.round(circle * 42 / 54), watchIcon: f.watch_icon ?? px(large ? 18 : 12) };
  return { large, px, touch, fonts, circle, gap: px(large ? 10 : 6), key: Math.max(touch, px(large ? 52 : 40)),
    row: Math.max(touch, px(large ? 46 : 34)), pad: px(large ? 8 : 6),
    mm: (n: number) => Math.floor(((shape.dpi || (large ? 170 : 143)) * n + 12) / 25) };
}
type Metrics = ReturnType<typeof vacuumMetrics>;
const inside = (m: Metrics, r: Box): Box => ({ x: r.x + m.pad, y: r.y + m.pad, w: r.w - 2 * m.pad, h: r.h - 2 * m.pad });
const startD = (m: Metrics, dock: boolean) => (dock ? Math.floor(m.key * 6 / 5) : m.key);
const pairW = (m: Metrics, dock = false, second = true) => (second ? m.key + m.gap : 0) + startD(m, dock);
const modeW = (m: Metrics, modes: number) => modes * Math.max(Math.floor(m.key * 5 / 4), 2 * width("M", m.fonts.mini) + m.px(24)) + 2 * Math.max(3, Math.floor(m.key / 12));
const chipW = (m: Metrics, words: string) => m.px(10) + width("M", m.fonts.watchIcon) + m.px(5) + width(words, m.fonts.small) + m.px(12);

// ---- Rooms as icon tiles ----
const roomNeedW = (m: Metrics, rooms: string[]) => Math.max(0, ...rooms.map((r) => width(r, m.fonts.small))) + 2 * m.pad;
// Its icon over its name with a thin margin: a frame two rows of rooms almost fit kept them on one (the 8-inch D1001).
const roomNeedH = (m: Metrics, icon: number) => 2 * m.px(5) + lineOf(icon) + lineOf(m.fonts.small);
type Grid = { cols: number; rows: number; w: number; h: number; shown: number; big: boolean };
/** Even rows, every tile at least a name wide and an icon and a line high, no taller than 22 mm; a last "+N" for the rest. */
function roomGrid(m: Metrics, rooms: string[], r: Box, maxRows = 99): Grid | null {
  const g = m.px(6), count = rooms.length, needW = Math.max(roomNeedW(m, rooms), m.touch), needH = Math.max(roomNeedH(m, m.fonts.mini), m.touch);
  const colsFit = Math.max(0, Math.floor((r.w + g) / (needW + g))), rowsFit = Math.min(maxRows, Math.floor((r.h + g) / (needH + g)));
  if (!colsFit || !rowsFit || !count) return null;
  let best: Grid | null = null, score = Infinity;
  for (let rows = 1; rows <= rowsFit; rows++) {
    const cols = Math.ceil(count / rows);
    if (cols > colsFit || cols * (rows - 1) >= count) continue;
    const w = Math.floor((r.w - (cols - 1) * g) / cols), h = Math.min(Math.floor((r.h - (rows - 1) * g) / rows), m.mm(22));
    const a = w / h, off = a > 1.2 ? a / 1.2 : 1.2 / a;
    if (off < score) { score = off; best = { cols, rows, w, h, shown: count, big: false }; }
  }
  if (!best) {
    const cap = colsFit * rowsFit;
    if (cap < 2) return null;
    best = { cols: colsFit, rows: rowsFit, w: Math.floor((r.w - (colsFit - 1) * g) / colsFit), h: Math.min(Math.floor((r.h - (rowsFit - 1) * g) / rowsFit), m.mm(22)), shown: cap - 1, big: false };
  }
  best.big = best.h >= roomNeedH(m, m.fonts.icon) + m.px(6);
  return best;
}
function roomsIn(m: Metrics, rooms: string[], r: Box, maxRows = 99) {
  const grid = roomGrid(m, rooms, r, maxRows), g = m.px(6);
  if (!grid) return { rooms: [] as Place[], more: null, big: false };
  const used = grid.rows * grid.h + (grid.rows - 1) * g, y0 = r.y + Math.floor((r.h - used) / 2);
  const at = (i: number): Box => ({ x: r.x + (i % grid.cols) * (grid.w + g), y: y0 + Math.floor(i / grid.cols) * (grid.h + g), w: grid.w, h: grid.h });
  return { rooms: Array.from({ length: grid.shown }, (_, i) => ({ ...at(i), index: i })), big: grid.big,
    more: grid.shown < rooms.length ? { ...at(grid.shown), count: rooms.length - grid.shown } : null };
}
const roomsReach = (m: Metrics, rooms: string[], r: Box, maxRows = 99) => roomGrid(m, rooms, r, maxRows)?.shown ?? 0;

// ---- Routines as a list: a play mark and the name ----
function routineCols(m: Metrics, names: string[], r: Box) {
  const widest = Math.max(0, ...names.map((n) => width(n, m.fonts.small)));
  return r.w >= 2 * (widest + m.row + m.px(22)) + m.px(6) ? 2 : 1;
}
function routinesIn(m: Metrics, names: string[], r: Box) {
  const g = m.px(6), count = names.length, cols = routineCols(m, names, r), rowsFit = Math.floor((r.h + g) / (m.row + g));
  const rows = Math.min(rowsFit, Math.ceil(count / cols)), cap = rows * cols;
  if (cap < 1 || !count) return { rows: [] as Place[], more: null };
  const shown = count > cap ? Math.max(1, cap - 1) : count, cw = Math.floor((r.w - (cols - 1) * g) / cols);
  const used = rows * m.row + (rows - 1) * g, y0 = r.y + Math.floor((r.h - used) / 2);
  const at = (i: number): Box => ({ x: r.x + (i % cols) * (cw + g), y: y0 + Math.floor(i / cols) * (m.row + g), w: cw, h: m.row });
  return { rows: Array.from({ length: shown }, (_, i) => ({ ...at(i), index: i })), more: shown < count && shown < cap ? { ...at(shown), count: count - shown } : null };
}
function routinesReach(m: Metrics, names: string[], r: Box) {
  const g = m.px(6), cap = Math.floor((r.h + g) / (m.row + g)) * routineCols(m, names, r);
  // A last place says how many more; where one place is all there is, it shows the first routine instead.
  return cap >= names.length ? names.length : cap === 1 ? 1 : Math.max(0, cap - 1);
}

// ---- The map and the rooms in one frame: side by side on a frame lying down, else the map over a strip of rooms ----
function split(m: Metrics, rooms: string[], r: Box) {
  const g = m.px(8);
  if (r.w * 5 >= r.h * 8) {
    const rw = Math.max(roomNeedW(m, rooms) * 2 + m.px(6), Math.floor(r.w * 2 / 5));
    return { map: { ...r, w: r.w - rw - g }, rooms: { x: r.x + r.w - rw, y: r.y, w: rw, h: r.h }, side: true };
  }
  const needH = Math.max(roomNeedH(m, m.fonts.mini), m.touch);
  const rows = roomsReach(m, rooms, { x: 0, y: 0, w: r.w, h: needH }, 1) >= rooms.length ? 1 : 2, rh = rows * needH + (rows - 1) * m.px(6);
  return { map: { ...r, h: r.h - rh - g }, rooms: { x: r.x, y: r.y + r.h - rh, w: r.w, h: rh }, side: false };
}
function contentOk(m: Metrics, input: VacuumInput, hero: Box, mapLeast: number, places: number) {
  const inner = inside(m, hero);
  if (inner.w <= 0 || inner.h <= 0) return false;
  places = Math.min(places, input.rooms.length);
  if (input.face === "map") return inner.h >= mapLeast;
  if (input.face === "rooms") return roomsReach(m, input.rooms, inner) >= places;
  if (input.face === "routines") return routinesReach(m, input.routines, inner) >= Math.min(3, input.routines.length);
  if (input.face === "map_rooms") {
    const sp = split(m, input.rooms, inner);
    return sp.map.h >= mapLeast && sp.map.w >= m.mm(20) && roomsReach(m, input.rooms, sp.rooms, sp.side ? 99 : 2) >= places;
  }
  return false;
}

/** Where every part of the tile stands in a content box of `width` x `height` glass pixels. */
export function vacuumLayout(shape: Shape, input: VacuumInput): VacuumLayout {
  width = input.measure ?? ((text, size) => textWidth(text, size));
  const m = vacuumMetrics(shape), { width: w, height: h, face } = input;
  const head = Math.max(m.circle, lineOf(m.fonts.label) + lineOf(m.fonts.small) + m.px(2)), top = head + m.gap;
  const tx = m.circle + m.px(m.large ? 12 : 8), dockH = startD(m, true);
  const withDock: Box = { x: 0, y: top, w, h: h - top - dockH - m.gap };
  const docked = contentOk(m, input, withDock, m.mm(16), 4);
  const frame = docked ? withDock : { x: 0, y: top, w, h: h - top };
  let dock: Box | null = null, start: Box, mode: Box | null = null;
  if (docked) {
    const cy = h - Math.floor(dockH / 2), sd = startD(m, true), pw = pairW(m, true, input.second);
    const withMode = input.modes >= 2 && face !== "routines" && w >= modeW(m, input.modes) + 2 * m.gap + pw;
    const x = withMode ? w - pw : Math.trunc((w - pw) / 2);
    if (input.second) dock = { x, y: cy - Math.floor(m.key / 2), w: m.key, h: m.key };
    start = { x: x + pw - sd, y: cy - Math.floor(sd / 2), w: sd, h: sd };
    if (withMode) mode = { x: 0, y: cy - Math.floor(m.key / 2), w: modeW(m, input.modes), h: m.key };
  } else {
    const x = w - pairW(m, false, input.second), y = Math.floor((head - m.key) / 2);
    if (input.second) dock = { x, y, w: m.key, h: m.key };
    start = { x: w - m.key, y, w: m.key, h: m.key };
  }
  // Status chips at the header's right where it has room for them beside the name, the battery else in the state line.
  const chips: StatusChip[] = [];
  if (docked) {
    const wanted: Omit<StatusChip, "box">[] = [];
    if (input.state === "cleaning" && input.progress !== null) wanted.push({ icon: "F0996", words: `${input.progress} %`, ink: "teal" });
    if (input.battery !== null) {
      const level = input.battery, icon = input.charging ? "F0084" : level >= 85 ? "F12A3" : level >= 60 ? "F0080" : level >= 40 ? "F007E" : "F0079";
      wanted.push({ icon, words: `${level} %`, ink: input.charging ? "charging" : level <= 20 ? "red" : "slate" });
    }
    const all = wanted.reduce((sum, c) => sum + chipW(m, c.words) + m.px(6), 0) - m.px(6);
    const nameLeast = Math.max(width("Vacuum", m.fonts.label, true), m.px(80));
    if (wanted.length && w - tx - all - m.gap >= nameLeast) {
      const ch = lineOf(m.fonts.small) + m.px(10);
      let x = w - all;
      for (const c of wanted) { chips.push({ ...c, box: { x, y: Math.floor((head - ch) / 2), w: chipW(m, c.words), h: ch } }); x += chipW(m, c.words) + m.px(6); }
    }
  }
  const right = docked ? (chips.length ? w - chips[0].box.x + m.gap : 0) : pairW(m, false, input.second) + m.gap;
  const inner = inside(m, frame);
  let map: Box | null = null, rooms = { rooms: [] as Place[], more: null as (Box & { count: number }) | null, big: false };
  let routines: Place[] = [], routinesMore = null;
  if (face === "map") { if (input.map) map = inner; }
  else if (face === "rooms") rooms = roomsIn(m, input.rooms, inner);
  else if (face === "routines") ({ rows: routines, more: routinesMore } = routinesIn(m, input.routines, inner));
  else if (face === "map_rooms") {
    const sp = split(m, input.rooms, inner);
    if (input.map) map = sp.map;
    rooms = roomsIn(m, input.rooms, sp.rooms, sp.side ? 99 : 2);
  }
  const frameRadius = Math.max(m.px(8), input.radius - input.pad);
  return { circle: m.circle, head, text: { x: tx, w: w - tx - right }, chips, dock, start, mode, frame, frameRadius,
    tileRadius: Math.max(m.px(6), frameRadius - m.pad), map, rooms: rooms.rooms, bigIcons: rooms.big, more: rooms.more,
    routines, routinesMore, fonts: m.fonts };
}
