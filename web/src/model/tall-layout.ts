// A card more than one row high as the glass lays it out (app 0.4.90), in glass pixels of the card's content: the
// geometry of tall_tile.h (its heading, its body and the rows of its controls, one centred stack for a key or a switch),
// of climate_tile.h (a thermostat's number between its - and +, big or on one row, and its mode bar) and the choices
// runtime_tiles render_tall makes with them (which face a body's words take, where the controls stand). Pure: the
// words and what the card controls come in, the faces' widths are measured in the screens' Roboto (text-fit.ts).
import type { CardLook } from "./card-layout";
import { iconFace } from "./card-layout";
import { textPx } from "./text-fit";
import { presetPanel, presetSizes } from "./light-presets";
import { lineOf, touchMin, uiScale, type Shape } from "./ui-scale";

export type Rect = { x: number; y: number; w: number; h: number };
const EMPTY: Rect = { x: 0, y: 0, w: 0, h: 0 };
const bottom = (r: Rect) => r.y + r.h, right = (r: Rect) => r.x + r.w;
const div = (a: number, b: number) => Math.trunc(a / b);

// ---- tall_tile.h ----
export type TallMetrics = { width: number; height: number; nameH: number; stateH: number; icon: number; gap: number; touch: number; reach: number;
  rows: number[] };
/** The heading, the body and the rows of selected controls (tall_tile::layout); null where the selection leaves no
 * room for the name. */
export function tallLayout(m: TallMetrics) {
  if (m.width <= 0 || m.height <= 0 || m.nameH <= 0 || m.touch <= 0 || m.gap < 0 || m.rows.length > 2) return null;
  let controls = 0;
  for (const row of m.rows) controls += Math.max(m.touch, row);
  if (m.rows.length) controls += m.gap * m.rows.length;
  const room = m.height - controls;
  if (room < m.nameH) return null;
  const state = room >= m.nameH + m.stateH;
  const lines = m.nameH + (state ? m.stateH : 0);
  const heading = Math.min(room, Math.max(lines, Math.min(m.icon, div(m.height, 3))));
  const bodyTop = Math.min(room, heading + m.gap);
  const rows: Rect[] = [];
  let y = m.height - controls;
  const width = m.reach > 0 ? Math.min(m.width, m.reach) : m.width;
  for (const row of m.rows) {
    y += m.gap;
    const h = Math.max(m.touch, row);
    rows.push({ x: div(m.width - width, 2), y, w: width, h });
    y += h;
  }
  return { state, header: { x: 0, y: 0, w: m.width, h: heading }, body: { x: 0, y: bodyTop, w: m.width, h: Math.max(0, room - bodyTop) }, rows };
}
/** One centred stack: icon, name, an optional state and an optional control under them (tall_tile::action). */
export function tallAction(width: number, height: number, icon: number, glyph: number, name: number, state: number, gap: number, controlW = 0, controlH = 0) {
  if (width <= 0 || height <= 0 || icon <= 0 || glyph <= 0 || name <= 0 || gap < 0 || controlW > width) return null;
  const below = controlH ? 2 * gap + controlH : 0;
  if (height < glyph + gap + name + state + below) state = 0;
  const side = Math.min(icon, width, height - gap - name - state - below);
  if (side < glyph) return null;
  const y = div(height - side - gap - name - state - below, 2), text = y + side + gap;
  return { icon: { x: div(width - side, 2), y, w: side, h: side }, title: { x: 0, y: text, w: width, h: name }, state: { x: 0, y: text + name, w: width, h: state },
    control: controlH ? { x: div(width - controlW, 2), y: text + name + state + 2 * gap, w: controlW, h: controlH } : EMPTY };
}

// ---- climate_tile.h ----
export type ClimateMetrics = { large: boolean; touch: number; gap: number; faceH: number[]; faceW: number[]; captionH: number; maxWidth: number; px: (n: number) => number };
const inset = (m: ClimateMetrics) => Math.max(2, m.px(m.large ? 4 : 3));
export function barRoom(m: ClimateMetrics, reach: number, modes: number) {
  const room = modes >= 2 ? Math.min(modes, div(reach - 2 * inset(m), m.touch)) : 0;
  return room >= 2 ? room : 0;
}
const barWidth = (m: ClimateMetrics, reach: number, room: number, stretches: boolean) => room >= 2 ? (stretches ? reach : Math.min(reach, room * m.touch + 2 * inset(m))) : 0;
export type ClimateLayout = { form: "none" | "row" | "big"; face: number; caption: boolean; stepper: Rect; minus: Rect; plus: Rect; number: Rect; captionBox: Rect; bar: Rect; room: number };
/** A thermostat's controls under its head (climate_tile::layout): the number big between its keys with the bar under
 * it, a stepper and the bar on one finger's row, or none. */
export function climateLayout(m: ClimateMetrics, width: number, top: number, end: number, modes: number): ClimateLayout {
  const l: ClimateLayout = { form: "none", face: -1, caption: false, stepper: EMPTY, minus: EMPTY, plus: EMPTY, number: EMPTY, captionBox: EMPTY, bar: EMPTY, room: 0 };
  const body = end - top, t = m.touch, g = m.gap, inn = inset(m);
  if (body < t || width < 2 * t + g) return l;
  const reach = Math.min(width, m.maxWidth), x0 = div(width - reach, 2);
  const room0 = barRoom(m, reach, modes);
  const zone = body - (room0 >= 2 ? t + 2 * g : 0);
  const key = Math.min(Math.max(Math.min(zone, div(t * 115, 100)), t), t * 2);
  if (zone >= t) {
    for (const [f, withLine] of [[0, 1], [0, 0], [1, 1], [2, 1], [1, 0], [2, 0]]) {
      if (m.faceW[f] <= 0 || m.faceW[f] > reach - 2 * key - 2 * g) continue;
      if (m.faceH[f] + (withLine ? m.captionH : 0) > zone) continue;
      l.face = f; l.caption = withLine === 1; break;
    }
    if (l.face >= 0 && m.faceH[l.face] + (l.caption ? m.captionH : 0) >= t + g) {
      l.form = "big";
      const block = m.faceH[l.face] + (l.caption ? m.captionH : 0), lead = Math.max(block, key);
      const group = lead + (room0 >= 2 ? 2 * g + t : 0), first = top + Math.max(0, div(body - group, 2));
      l.minus = { x: x0, y: first + div(lead - key, 2), w: key, h: key };
      l.plus = { x: x0 + reach - key, y: l.minus.y, w: key, h: key };
      l.number = { x: right(l.minus) + g, y: first + div(lead - block, 2), w: reach - 2 * key - 2 * g, h: m.faceH[l.face] };
      if (l.caption) l.captionBox = { x: l.number.x, y: bottom(l.number), w: l.number.w, h: m.captionH };
      if (room0 >= 2) { l.bar = { x: x0, y: Math.min(end - t, first + lead + 2 * g), w: reach, h: t }; l.room = room0; }
      return l;
    }
    l.face = -1; l.caption = false;
  }
  let face = -1;
  for (let f = 0; f < 3; ++f) if (m.faceW[f] > 0 && m.faceH[f] <= t + m.px(m.large ? 6 : 4)) { face = f; break; }
  if (face < 0) return l;
  const keyIn = t - 2 * inn, extra = m.px(m.large ? 12 : 6);
  if (2 * keyIn + 2 * inn + m.faceW[face] + extra > reach)
    for (let f = face + 1; f < 3; ++f) if (m.faceW[f] > 0 && 2 * keyIn + 2 * inn + m.faceW[f] + extra <= reach) { face = f; break; }
  const need = 2 * keyIn + 2 * inn + m.faceW[face] + extra;
  if (need > reach) return l;
  let room = barRoom(m, reach - need - g, modes);
  const twoLines = room < 2 && body >= 2 * t + g && barRoom(m, reach, modes) >= 2;
  if (twoLines) room = barRoom(m, reach, modes);
  const barW = barWidth(m, reach, room, twoLines);
  const stepW = twoLines ? reach : Math.min(barW ? reach - barW - g : reach, Math.max(need, m.px(m.large ? 250 : 170)));
  const y = top + div(body - (twoLines ? 2 * t + g : t), 2);
  l.form = "row"; l.face = face;
  l.stepper = { x: x0, y, w: Math.max(need, stepW), h: t };
  l.minus = { x: x0 + inn, y: y + inn, w: keyIn, h: keyIn };
  l.plus = { x: right(l.stepper) - inn - keyIn, y: y + inn, w: keyIn, h: keyIn };
  l.number = { x: right(l.minus), y: y + div(t - m.faceH[face], 2), w: l.plus.x - right(l.minus), h: m.faceH[face] };
  if (room >= 2) { l.bar = twoLines ? { x: x0, y: y + t + g, w: barW, h: t } : { x: x0 + reach - barW, y, w: barW, h: t }; l.room = room; }
  return l;
}

// ---- render_tall ----
type Face = { size: number; weight: number };
export type TallText = { x: number; y: number; w: number; size: number; weight: number; line: number; align: "left" | "center"; text: string; muted?: boolean;
  /** Rolls by on the glass (a player's title, marquee), so it is cut at the edge, never dotted. */
  marquee?: boolean };
export type TallInput = {
  domain: string; name: string; line: string; code: string;
  /** What the card controls under its head (tile-face tallControls) and whether it has the room and the entity for it
   * (runtime_tiles with_panel and panel_available). */
  controls: string; panel: boolean;
  keys: number; modes: number; bigKey: boolean; action: boolean; full: boolean;
  /** A player's volume over its keys (volume_playback, a player that sets its volume). */
  volume: boolean;
  /** The words of its body: a player's track and artist, a thermostat's reading, or the value it stands large. */
  title?: string; artist?: string; reading?: string; value?: string;
  /** The number between a thermostat's -/+, the widest it can be (a range's chip). */
  setpoint?: string; widest?: string; runWidth?: number;
  /** "Now 23°" under a thermostat's big number. */
  now?: string;
  /** A light's presets: how many the tile has, and whether the card is one cell with its heading over them (preset_cell). */
  presets?: number; presetCell?: boolean;
};
export type TallCard = {
  circle: { x: number; y: number; size: number; icon: number } | null;
  title: TallText | null; value: TallText | null; body: TallText[];
  panel: { kind: string; x: number; y: number; w: number; h: number; keyW: number; keyH: number; gap: number; knob: number; slider: Rect | null; keys: Rect | null;
    standing: Rect | null; dots?: { x: number; y: number; size: number }[] } | null;
  climate: (ClimateLayout & { faceSize: number; faceWeight: number; now: string }) | null;
};

/** What runtime_tiles render_tall draws in a card's content `width` x `height`; null where it draws something else (a
 * cover's slats and keys, which cover-tile.ts lays out). */
export function tallCard(shape: Shape, look: CardLook, width: number, height: number, input: TallInput): TallCard | null {
  const { large, px } = uiScale(shape), gap = px(large ? 8 : 4), touchKey = Math.max(touchMin(shape), px(large ? 48 : 34));
  const nameH = lineOf(look.label), stateH = lineOf(look.sublabel), label: Face = { size: look.label, weight: 700 }, small: Face = { size: look.sublabel, weight: 400 };
  const mediaKey = input.domain === "media_player" ? Math.min(Math.max(div(height, 6), touchKey), div(touchKey * 3, 2)) : touchKey;
  const reach = px(large ? 740 : 620);
  let selected = input.panel;
  let m: TallMetrics = { width, height, nameH, stateH, icon: look.circle, gap, touch: touchMin(shape), reach, rows: selected ? [mediaKey + 2] : [] };
  const wholeW = width;
  let standing = 0;
  if (selected && !input.full && input.volume) {
    const inner = width - mediaKey - gap, beside = { ...m, width: inner };
    if (width * 4 >= height * 5 && inner >= 3 * mediaKey + 2 * gap && tallLayout(beside)) { m = beside; standing = height; width = inner; }
    else {
      const both = { ...m, rows: [mediaKey + 2, mediaKey + 2] };
      if (tallLayout(both)) m = both; else standing = -1;
    }
  }
  // A light's slider with its presets under it: two rows, the second as high as the keys; its keys alone, on a card of one
  // cell or a taller one, a row as high as them (runtime_tiles render_tall).
  const z = presetSizes(shape), presetRow = z.tileKey + 2 * z.ring;
  if (selected && input.controls === "brightness_presets" && (input.presets ?? 0) > 0) {
    const both = { ...m, rows: [touchKey + 2, presetRow] };
    if (tallLayout(both)) m = both;
  }
  if (selected && (input.presetCell || input.controls === "presets")) m = { ...m, rows: [presetRow] };
  let l = tallLayout(m);
  if (!l) { selected = false; m = { ...m, rows: [] }; l = tallLayout(m); }
  if (!l) return { circle: null, title: null, value: null, body: [], panel: null, climate: null };
  const text = (t: string, f: Face, x: number, y: number, w: number, align: "left" | "center", muted = false): TallText =>
    ({ x, y, w, size: f.size, weight: f.weight, line: lineOf(f.size), align, text: t, muted });
  const out: TallCard = { circle: null, title: null, value: null, body: [], panel: null, climate: null };
  const stack = (a: NonNullable<ReturnType<typeof tallAction>>, name: Face) => {
    out.circle = { x: a.icon.x, y: a.icon.y, size: a.icon.w, icon: iconFace(look, input.code, a.icon.w, a.icon.w >= look.circle ? look.icon : look.iconMini) };
    out.title = text(input.name, name, a.title.x, a.title.y, a.title.w, "center");
    out.value = a.state.h > 0 && input.line ? text(input.line, small, a.state.x, a.state.y, a.state.w, "center", true) : null;
  };
  // A page's or the settings' card: one centred stack.
  if (input.action) {
    const a = tallAction(width, height, look.circle, lineOf(look.icon), nameH, input.line ? stateH : 0, gap);
    if (a) { stack(a, label); return out; }
  }
  // An on/off or run card is one big key: the name in the page's headline where it fits whole.
  if (input.bigKey && !input.full) {
    let name: Face = { size: look.headline, weight: 500 };
    if (textPx(input.name, name.size, name.weight) > width) name = label;
    const a = tallAction(width, height, div(Math.min(width, height) * 44, 100), lineOf(look.icon), lineOf(name.size), l.state && input.line ? stateH : 0, gap);
    if (a) stack(a, name);
    return out;
  }
  // The heading: the circle at the left of the header row, the name and its line beside it.
  let circle = Math.min(look.circle, l.header.h, div(width, 3));
  let iconSize = look.icon;
  if (circle < look.circle) { circle = Math.min(look.circle, l.header.h, div(width, 2)); iconSize = circle >= look.circle ? look.icon : look.iconMini; }
  const tx = circle + gap, tw = Math.max(1, width - tx), lines = nameH + (l.state ? stateH : 0), ty = div(l.header.h - lines, 2);
  out.circle = { x: 0, y: div(l.header.h - circle, 2), size: circle, icon: iconFace(look, input.code, circle, iconSize) };
  out.title = text(input.name, label, tx, ty, tw, "left");
  out.value = l.state && input.line ? text(input.line, small, tx, ty + nameH, tw, "left", true) : null;
  const dropRepeat = (headline: string) => {
    if (!headline || !out.value) return;
    const state = out.value.text;
    if (state !== headline && !state.startsWith(`${headline} `)) return;
    out.value = null; out.title!.y = div(l!.header.h - nameH, 2);
  };
  // The control rows (layout_panel on a taller card): their size, centred in the rows' room.
  const kind = input.controls;
  if (selected && kind) {
    const keyH = input.domain === "media_player" ? mediaKey : touchKey, pill = Math.min(width, reach), panelGap = px(large ? 8 : 4);
    const keyW = Math.min(keyH, Math.max(touchMin(shape), div(pill - 2 * panelGap, 3)));
    let pw: number, ph = keyH, slider: Rect | null = null, keys: Rect | null = null, dots: { x: number; y: number; size: number }[] | undefined;
    const isKeys = ["buttons", "playback", "volume_playback"].includes(kind) || (kind === "stepper" && input.domain.endsWith("select"));
    if (kind === "toggle") { pw = Math.min(width, 2 * keyH); }
    else if (kind === "setpoint" || kind === "setpoint_mode" || (kind === "stepper" && !isKeys)) { pw = pill; ph = keyH + 2; }
    else if (kind === "mode") { pw = Math.min(pill, reach); }
    else if (kind === "run") pw = Math.max(div(keyW * 3, 2), (input.runWidth ?? 0) + 2 * px(large ? 22 : 14));
    else if (kind === "presets" || kind === "brightness_presets") {
      // A row of round keys, the ring's room round them, under the slider of the pair.
      const pair = kind === "brightness_presets", p = presetPanel(shape, input.presets ?? 0, pill, z.tileKey);
      pw = Math.max(p.width, pair ? pill : 0);
      const rowY = pair ? keyH + (p.row.count ? panelGap : 0) : 0;
      ph = pair && !p.row.count ? keyH : rowY + p.height;
      if (pair) slider = { x: div(pw - pill, 2), y: 0, w: pill, h: keyH };
      dots = p.keys.map((k) => ({ x: div(pw - p.width, 2) + k.x, y: rowY + k.y, size: k.size }));
    }
    else if (kind === "volume") pw = Math.max(touchMin(shape), pill - keyH - panelGap) + panelGap + keyH;
    else if (isKeys) {
      const count = Math.max(0, Math.min(3, input.keys)), row = count ? count * keyW + (count - 1) * panelGap : 0;
      const pair = kind === "volume_playback" && input.volume && standing === 0;
      if (pair) {
        const pairW = Math.max(3 * keyW + 2 * panelGap, pill);
        slider = { x: 0, y: 0, w: pairW, h: keyH };
        keys = { x: div(pairW - row, 2), y: keyH + panelGap, w: row, h: keyH };
        pw = pairW; ph = keyH + panelGap + keyH;
      } else { keys = { x: 0, y: 0, w: row, h: keyH }; pw = row; }
    } else { pw = pill; slider = { x: 0, y: 0, w: pill, h: keyH }; }
    const top = l.rows[0]?.y ?? 0, room = (l.rows.length > 1 ? bottom(l.rows[1]) : bottom(l.rows[0] ?? EMPTY)) - top;
    if (pw && pw <= width && ph <= room) {
      out.panel = { kind, x: standing > 0 ? 0 : div(width - pw, 2), y: top + div(room - ph, 2), w: pw, h: ph, keyW, keyH, gap: panelGap,
        knob: keyH - 2 * px(large ? 4 : 3), slider, keys, dots,
        standing: standing > 0 ? { x: width + gap, y: 0, w: wholeW - width - gap, h: standing } : null };
    }
  }
  // A thermostat's -/+ and modes (climate_tile.h).
  if ((input.domain === "climate" || input.domain === "humidifier") && out.panel && (kind === "setpoint" || kind === "setpoint_mode")) {
    const target = input.widest ? `${input.widest}88` : input.setpoint || "";
    const faces: Face[] = [{ size: look.setpoint, weight: 400 }, { size: look.watch, weight: 500 }, { size: look.sublabelBig, weight: 400 }];
    const cm: ClimateMetrics = { large, touch: touchKey, gap, faceH: faces.map((f) => lineOf(f.size)), faceW: faces.map((f) => Math.ceil(textPx(target, f.size, f.weight)) + 2),
      captionH: stateH, maxWidth: reach, px };
    const cl = climateLayout(cm, width, l.body.y, height, kind === "setpoint_mode" ? input.modes : 0);
    if (cl.form !== "none") {
      out.panel = null;
      out.climate = { ...cl, faceSize: faces[cl.face].size, faceWeight: faces[cl.face].weight, now: cl.caption ? input.now ?? "" : "" };
      return out;
    }
    out.panel = null;
  }
  // An on/off card: icon, name, state and the switch as one centred stack.
  if (out.panel && kind === "toggle") {
    const a = tallAction(width, height, look.circle, lineOf(look.icon), nameH, l.state && input.line ? stateH : 0, gap, out.panel.w, out.panel.h);
    if (a) { stack(a, label); out.panel.x = a.control.x; out.panel.y = a.control.y; }
    return out;
  }
  const body = l.body;
  if (input.domain === "media_player") {
    const title = input.title || "", artist = input.artist || "";
    const steps: { title: Face; artist: Face; whole: boolean }[] = [
      { title: { size: look.watch, weight: 500 }, artist: { size: look.sublabelBig, weight: 400 }, whole: true },
      { title: { size: look.headline, weight: 500 }, artist: small, whole: false }, { title: label, artist: small, whole: false }];
    let font = label, sub = small, secondary = false;
    for (const step of steps) {
      const th = lineOf(step.title.size), ah = lineOf(step.artist.size);
      if (th > body.h || (step.whole && (!title || textPx(title, step.title.size, step.title.weight) > width))) continue;
      const both = Boolean(artist) && body.h >= th + ah + div(gap, 2);
      if (step.whole && artist && !both) continue;
      font = step.title; sub = step.artist; secondary = both; break;
    }
    const fh = lineOf(font.size), ah = lineOf(sub.size), y = body.y + Math.max(0, div(body.h - fh - (secondary ? ah + div(gap, 2) : 0), 2));
    if (title && body.h >= fh) { out.body.push({ ...text(title, font, 0, y, width, "left"), marquee: true }); dropRepeat(title); }
    if (secondary) out.body.push(text(artist, sub, 0, y + fh + div(gap, 2), width, "left", true));
  } else if ((input.domain === "climate" || input.domain === "humidifier") && input.reading) {
    const font = lineOf(look.watch) <= body.h ? { size: look.watch, weight: 500 } : small;
    if (body.h >= lineOf(font.size)) out.body.push(text(input.reading, font, 0, body.y + Math.max(0, div(body.h - lineOf(font.size), 2)), width, "center"));
  } else if (input.value) {
    let font = small;
    // A light's percentage that cannot take the large face steps down to the controls' regular face, never the bold name's.
    const second: Face = input.domain === "light" ? { size: look.sublabelBig, weight: 400 } : label;
    for (const f of [{ size: look.watch, weight: 500 }, second, small])
      if (textPx(input.value, f.size, f.weight) <= body.w && lineOf(f.size) <= body.h) { font = f; break; }
    if (body.h >= lineOf(font.size)) { out.body.push(text(input.value, font, 0, body.y + Math.max(0, div(body.h - lineOf(font.size), 2)), width, "center")); dropRepeat(input.value); }
  }
  return out;
}
