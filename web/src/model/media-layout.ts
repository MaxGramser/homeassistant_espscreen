// A media player over a whole page as the glass lays it out (app 0.4.90), in glass pixels: the head as on every full
// card (runtime_tiles render_full, head_row), and under it the media card itself (media_card.h layout): the cover's
// place, the title, the artist, the progress bar with its times, the keys and the volume row. Pure arithmetic, as the
// firmware's is; tests/test_editor_parity.py holds it to media_card.h.
import { lineOf, uiScale, type Shape } from "./ui-scale";
import type { CardLook } from "./card-layout";
import type { Rect } from "./tall-layout";

const div = (a: number, b: number) => Math.trunc(a / b);
const right = (r: Rect) => r.x + r.w, bottom = (r: Rect) => r.y + r.h, cy = (r: Rect) => r.y + div(r.h, 2);
const NONE: Rect = { x: 0, y: 0, w: 0, h: 0 };

export type MediaMetrics = { large: boolean; art: boolean; clockW: number; titleH: number; artistH: number; smallH: number; px: (n: number) => number };
const sizes = (m: MediaMetrics) => {
  const px = m.px, l = m.large;
  const slider = px(l ? 20 : 12), bar = px(l ? 6 : 4);
  return { key: px(l ? 52 : 34), play: px(l ? 64 : 40), keyGap: px(l ? 28 : 14), minGap: px(l ? 12 : 8), mute: px(l ? 32 : 22), slider,
    knob: slider + 2 * px(l ? 4 : 3), bar, seekKnob: bar + px(l ? 14 : 10), gap: px(l ? 12 : 6), margin: px(l ? 24 : 10), maxArt: px(l ? 200 : 120),
    reach: px(l ? 740 : 620), time: px(l ? 48 : 34) };
};
export type MediaLayout = { wide: boolean; times: boolean; artist: boolean; art: Rect; title: Rect; artistLine: Rect; bar: Rect; elapsed: Rect; total: Rect;
  prev: Rect; play: Rect; next: Rect; minus: Rect; volume: Rect; plus: Rect; artRadius: number };

function layoutWith(m: MediaMetrics, width: number, height: number, volumeH: number): MediaLayout {
  const s = sizes(m), g = s.gap, margin = s.margin, timesW = Math.max(s.time, m.clockW);
  const l: MediaLayout = { wide: false, times: false, artist: true, art: NONE, title: NONE, artistLine: NONE, bar: NONE, elapsed: NONE, total: NONE,
    prev: NONE, play: NONE, next: NONE, minus: NONE, volume: NONE, plus: NONE, artRadius: 0 };
  const rowW = Math.min(width - 2 * margin, s.reach), rowX = div(width - rowW, 2), rowY = height - volumeH;
  l.minus = { x: rowX, y: rowY, w: volumeH, h: volumeH };
  l.plus = { x: rowX + rowW - volumeH, y: rowY, w: volumeH, h: volumeH };
  const knobReach = g + div(s.knob, 2), sliderX = right(l.minus) + knobReach;
  l.volume = { x: sliderX, y: rowY + div(volumeH - s.slider, 2), w: Math.max(1, l.plus.x - knobReach - sliderX), h: s.slider };
  const above = height - volumeH - g;
  const stackMin = s.maxArt + m.titleH + m.artistH + 3 * g + m.smallH + s.play;
  l.wide = width * 4 > height * 5 && !(width > s.reach && above >= stackMin);
  const rowMin = 2 * s.key + s.play + 2 * s.minGap;
  const barRow = (x: number, w: number, y: number, withTimes: boolean) => {
    const tw = withTimes && w >= 4 * timesW ? timesW : 0;
    l.times = tw > 0;
    const rowH = l.times ? m.smallH : s.bar;
    l.elapsed = { x, y, w: tw, h: m.smallH };
    l.total = { x: x + w - tw, y, w: tw, h: m.smallH };
    const side = tw ? tw + div(g, 2) + div(s.seekKnob, 2) : 0;
    l.bar = { x: x + side, y: y + div(rowH - s.bar, 2), w: Math.max(1, w - 2 * side), h: s.bar };
    return rowH;
  };
  const keys = (x: number, w: number, y: number) => {
    const gap = Math.min(Math.max(div(w - 2 * s.key - s.play, 2), s.minGap), s.keyGap);
    const rowWidth = 2 * s.key + s.play + 2 * gap, at = x + div(w - rowWidth, 2);
    l.prev = { x: at, y: y + div(s.play - s.key, 2), w: s.key, h: s.key };
    l.play = { x: at + s.key + gap, y, w: s.play, h: s.play };
    l.next = { x: right(l.play) + gap, y: l.prev.y, w: s.key, h: s.key };
  };
  if (!m.art) {
    l.wide = false;
    const textW = Math.min(width - 2 * margin, s.reach), textX = div(width - textW, 2);
    let stack = m.titleH + m.artistH + g + m.smallH + g + s.play;
    l.artist = stack <= above;
    if (!l.artist) stack -= m.artistH;
    const withTimes = stack <= above;
    if (!withTimes) stack -= m.smallH - s.bar;
    let y = Math.max(0, div(above - stack, 2));
    l.title = { x: textX, y, w: textW, h: m.titleH }; y += m.titleH;
    if (l.artist) { l.artistLine = { x: textX, y, w: textW, h: m.artistH }; y += m.artistH; }
    y += g;
    y += barRow(textX, textW, y, withTimes);
    keys(0, width, y + g);
  } else if (!l.wide) {
    const keysY = above - s.play, stack = m.titleH + m.artistH + g + m.smallH + g;
    const cap = Math.min(320, Math.max(s.maxArt, Math.min(div(width, 3), div(above, 2))));
    const art = Math.max(32, Math.min(cap, keysY - g - stack - g));
    const textW = Math.min(width - 2 * margin, s.reach), textX = div(width - textW, 2), stackY = keysY - g - stack;
    l.art = { x: div(width - art, 2), y: Math.max(0, div(stackY - g - art, 2)), w: art, h: art };
    l.title = { x: textX, y: stackY, w: textW, h: m.titleH };
    l.artistLine = { x: textX, y: bottom(l.title), w: textW, h: m.artistH };
    barRow(textX, textW, bottom(l.artistLine) + g, true);
    keys(0, width, keysY);
  } else {
    const cap = Math.min(320, Math.max(s.maxArt, Math.min(div(width, 3), div(above, 2))));
    const art = Math.max(32, Math.min(cap, above, width - 2 * margin - 2 * g - rowMin));
    const h = div(g, 2);
    let column = m.titleH + m.artistH + h + m.smallH + h + s.play;
    l.artist = column <= above;
    if (!l.artist) column -= m.artistH;
    const withTimes = column <= above;
    if (!withTimes) column -= m.smallH - s.bar;
    const w = Math.max(1, Math.min(width - 2 * margin - 2 * g - art, s.reach));
    l.art = { x: Math.max(margin, div(width - art - 2 * g - w, 2)), y: Math.max(0, div(above - art, 2)), w: art, h: art };
    const x = right(l.art) + 2 * g;
    let y = Math.min(Math.max(l.art.y + div(art - column, 2), 0), Math.max(0, above - column));
    l.title = { x, y, w, h: m.titleH }; y += m.titleH;
    if (l.artist) { l.artistLine = { x, y, w, h: m.artistH }; y += m.artistH; }
    y += h;
    y += barRow(x, w, y, withTimes);
    keys(x, w, y + h);
  }
  l.artRadius = Math.max(4, div(l.art.w, 12));
  return l;
}
/** The media card in `width` x `height` (media_card::layout): the volume row a key high, or a mute key's where a wide
 * card's artist line would not fit. */
export function mediaLayout(m: MediaMetrics, width: number, height: number) {
  const s = sizes(m), l = layoutWith(m, width, height, s.key);
  if (!m.art) return l.artist ? l : layoutWith(m, width, height, s.mute);
  if (!l.wide || l.artist) return l;
  return layoutWith(m, width, height, s.mute);
}

/** A whole-page media card's metrics on this glass (media_metrics): the title in the headline, the artist in the controls'
 * face, the times in the small one; `clockW` the widest time its length writes. */
export function mediaMetrics(shape: Shape, look: CardLook, art: boolean, clockW = 0): MediaMetrics {
  const { large, px } = uiScale(shape);
  return { large, art, clockW, titleH: lineOf(look.headline), artistH: lineOf(look.sublabelBig), smallH: lineOf(look.sublabel), px };
}
/** Where the media card starts under a full card's head (render_full, render_media_full). */
export function mediaTop(shape: Shape, headH: number) {
  const { large, px } = uiScale(shape);
  return { top: headH + px(large ? 8 : 4), below: px(large ? 4 : 2) };
}
/** A track's length as the card writes it beside the bar. */
export const clockText = (seconds: number) => {
  const s = Math.max(0, Math.floor(seconds));
  return s >= 3600 ? `${div(s, 3600)}:${String(div(s, 60) % 60).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}` : `${div(s, 60)}:${String(s % 60).padStart(2, "0")}`;
};
export { cy };
