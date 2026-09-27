// ---- The top bar as the screen draws it ----
// One rule set with header_bar.h in the firmware, in screen pixels of the board: every value (the
// time too) in the same 400 Roboto on the name's baseline; icons and the dial centred on the
// height of the digits; the gaps measured between what you see (glyph ink), not between boxes, so
// an icon with side bearings sits exactly as close to its value as one without.
import { t } from "../i18n";
import type { HeaderItem } from "../types";

// The words are the screens' own (app 0.2.90): screen.date and screen.time of the translations, in the language the
// screens have, which `locale` names; English where none is given.
export const BUILTIN_ICONS: Record<string, string> = { clock: "clock-outline", analog: "clock-outline", date: "calendar" };
// What makes an item that item, as the add-on compares them (core.validate_header): its kind, and for an entity what it
// shows with the defaults filled in. Never its id: since app 0.3.1 every item on every page has an id of its own, and a
// key with the id in it matched no other item, so "already in the bar", the preview of an entity on several pages and
// the flash of a new item all stopped working (fixed in app 0.4.1).
export const itemKey = (item: HeaderItem) => item.type === "entity"
  ? JSON.stringify(["entity", item.entity, item.content ?? "state", item.icon ?? "auto", item.show ?? "always"])
  : JSON.stringify([item.type]);
export const glyph = (cp: string) => String.fromCodePoint(parseInt(cp, 16));

// The time as the screens write it (screen_text::clock_text): "07:12" on 24 hours; on 12 "7:12 PM" in the top bar, with
// the language's day periods, and "7:12" in the clock card's big digits, which have no letters.
export function clockText(clock24: boolean, now = new Date(), locale?: string) {
  const minutes = String(now.getMinutes()).padStart(2, "0");
  if (clock24) return `${String(now.getHours()).padStart(2, "0")}:${minutes}`;
  const time = `${now.getHours() % 12 || 12}:${minutes}`;
  return locale ? `${time} ${t(`screen.time.${now.getHours() < 12 ? "am" : "pm"}`, {}, { locale })}` : time;
}
// "Sa 19 Sep", "za 19 sep", "sam. 19 sept.": the language's pattern with its abbreviation or its two letters.
export const dateText = (now = new Date(), locale = "en") => t("screen.date.top_bar", {
  weekday: t(`screen.date.weekdays_short.${now.getDay()}`, {}, { locale }),
  weekday_min: t(`screen.date.weekdays_min.${now.getDay()}`, {}, { locale }),
  day: now.getDate(),
  month: t(`screen.date.months_short.${now.getMonth()}`, {}, { locale }),
}, { locale });
// Same thresholds as header_bar::ago_text() in the firmware, and the same words.
export function agoText(then: number, now = Math.floor(Date.now() / 1000), locale = "en") {
  const seconds = now - then, span = Math.abs(seconds), per = (unit: number) => Math.floor(span / unit);
  const say = (key: string, n?: number) => (n === undefined ? t(`screen.time.${key}`, {}, { locale }) : t(`screen.time.${key}`, n, { locale }));
  if (seconds < 0) {
    if (span < 3600) return say("in_minutes", Math.max(1, per(60)));
    if (span < 86400) return say("in_hours", per(3600));
    if (span < 172800) return say("tomorrow");
    return say("in_days", per(86400));
  }
  if (span < 60) return say("just_now");
  if (span < 3600) return say("minutes_ago", per(60));
  if (span < 86400) return say("hours_ago", per(3600));
  if (span < 172800) return say("yesterday");
  if (span < 604800) return say("days_ago", per(86400));
  if (span < 2592000) return say("weeks_ago", per(604800));
  if (span < 31536000) return say("months_ago", per(2592000));
  return say("years_ago", per(31536000));
}

// `inset` is the margin the board keeps from the edge of the glass: the bar starts there, and the home key keeps
// the same distance to the page title (firmware 0.2.100+).
export type BarMetrics = { width: number; top: number; name: number; text: number; icon: number; inset: number };
// The bar of each look at the look's own density, across the canvas it was drawn on (480 and 320 wide): the fonts of
// the page title, the values and the icons (FONT_HEADLINE_SIZE, FONT_SUBLABEL_BIG_SIZE, FONT_ICON_MINI_SIZE) and the
// margin from the glass (HEADER_INSET) of packages/looks/, which tests/test_header_bar.py keeps equal. `top` is where
// the mockup puts the page title's baseline.
export type Look = "standard" | "compact";
export const LOOK_BARS: Record<Look, BarMetrics & { dpi: number }> = {
  standard: { width: 448, top: 36, name: 27, text: 21, icon: 26, inset: 16, dpi: 170 },
  compact: { width: 298, top: 24, name: 18, text: 14, icon: 18, inset: 11, dpi: 143 },
};
export type ShapeLike = { width: number; look?: string; dpi?: number };
// The bar for a screen of this shape: the look's sizes scaled to the screen's density, the way the firmware scales
// every size (ui::px), across the screen's own width. The two first boards come out exactly as they are.
export function barMetricsFor(shape: ShapeLike): BarMetrics {
  const base = LOOK_BARS[shape.look === "compact" || (!shape.look && shape.width < 400) ? "compact" : "standard"];
  const f = (shape.dpi && shape.dpi > 0 ? shape.dpi : base.dpi) / base.dpi;
  const px = (n: number) => Math.round(n * f);
  return { width: shape.width - 2 * px(base.inset), top: px(base.top), name: px(base.name), text: px(base.text),
           icon: px(base.icon), inset: px(base.inset) };
}
export type ItemView = { icon?: string | null; text?: string; color?: string | null; shown: boolean; analog?: boolean; loading?: boolean };
type Ink = { left: number; right: number; top: number; bottom: number; advance: number };

let measure: CanvasRenderingContext2D | null | undefined;
const inkCache = new Map<string, Ink>();
export const clearInkCache = () => inkCache.clear();
// Ink box of a string relative to its origin on the baseline: left/right, and top (negative, up)/bottom.
// Without a canvas (a test runner) the box is estimated from the font size, so the layout rules still run.
export function inkOf(text: string, font: string): Ink {
  const key = `${font}|${text}`;
  let ink = inkCache.get(key);
  if (!ink) {
    if (measure === undefined) measure = document.createElement("canvas").getContext("2d");
    if (measure) {
      measure.font = font;
      const m = measure.measureText(text);
      ink = { left: -m.actualBoundingBoxLeft, right: m.actualBoundingBoxRight, top: -m.actualBoundingBoxAscent, bottom: m.actualBoundingBoxDescent, advance: m.width };
    } else {
      const px = Number(/(\d+(?:\.\d+)?)px/.exec(font)?.[1] || 14);
      const width = [...text].length * px * 0.55;
      ink = { left: 0, right: width, top: -px * 0.72, bottom: px * 0.02, advance: width };
    }
    inkCache.set(key, ink);
  }
  return ink;
}
export const barFonts = (m: BarMetrics) => ({ name: `500 ${m.name}px "Bar Roboto"`, text: `400 ${m.text}px "Bar Roboto"`, icon: `${m.icon}px "Tile Icons"` });
// Same integer arithmetic as header_bar::gaps() in the firmware, from the digit height in pixels.
export function barGaps(cap: number) {
  return { icon: Math.max(2, Math.floor((cap * 4 + 5) / 10)), item: Math.max(6, Math.floor((cap * 125 + 50) / 100)), name: Math.max(8, Math.floor((cap * 16 + 5) / 10)) };
}
export type BarPart = {
  index: number; item: HeaderItem; view: ItemView; shown: boolean; width: number; x?: number;
  dial?: number; icon?: { glyph: string; ink: Ink }; text?: { value: string; ink: Ink };
};
export type BarLayout = ReturnType<typeof barLayout>;
// The parts per item with their ink widths, the placement, and which items fall off.
// mdi:home, the key at the far left of the bar (firmware 0.2.100+). The screens draw it as tall as the capitals of
// the page title, on the same baseline, with the same air between it and the name as between it and the edge.
export const HOME_GLYPH = "F02DC";
export function barLayout(items: HeaderItem[], metrics: BarMetrics, nameText: string, viewOf: (item: HeaderItem) => ItemView,
                          home = false, back = false) {
  const fonts = barFonts(metrics);
  // The firmware reads the digit height as a whole number of pixels (the glyph box of "0").
  const zero = inkOf("0", fonts.text), cap = Math.round(zero.bottom - zero.top), gaps = barGaps(cap);
  const dialInk = inkOf(String.fromCodePoint(0xf0150), fonts.icon), dial = Math.round(dialInk.bottom - dialInk.top);
  const parts: BarPart[] = items.map((item, index) => {
    const view = viewOf(item);
    const part: BarPart = { index, item, view, shown: view.shown, width: 0 };
    if (view.analog) { part.dial = dial; part.width = dial; return part; }
    if (view.icon) { part.icon = { glyph: glyph(view.icon), ink: inkOf(glyph(view.icon), fonts.icon) }; part.width += part.icon.ink.right - part.icon.ink.left; }
    if (view.text) {
      part.text = { value: view.text, ink: inkOf(view.text, fonts.text) };
      part.width += (part.icon ? gaps.icon : 0) + part.text.ink.right - part.text.ink.left;
    }
    return part;
  });
  const shown = parts.filter((p) => p.shown);
  // The home key takes the name's place and the name moves behind it; the items on the right keep every pixel.
  const leading = back ? 'F0141' : HOME_GLYPH;
  const key = home || back ? { glyph: glyph(leading), ink: inkOf(glyph(leading), fonts.icon) } : null;
  const homeShift = key ? Math.round(key.ink.right - key.ink.left) + metrics.inset : 0;
  const width = Math.max(0, metrics.width - homeShift);
  const natural = inkOf(nameText, fonts.name).advance;
  const minName = Math.min(natural, Math.floor((width * 35) / 100));
  const total = (list: BarPart[]) => list.reduce((sum, p) => sum + p.width, 0) + Math.max(0, list.length - 1) * gaps.item;
  let first = 0;
  while (first < shown.length && total(shown.slice(first)) + gaps.name + minName > width) first++;
  const placed = shown.slice(first), dropped = new Set(shown.slice(0, first).map((p) => p.index));
  let x = metrics.width - total(placed);
  for (const p of placed) { p.x = x; x += p.width + gaps.item; }
  const nameRoom = (placed.length ? placed[0].x! - gaps.name : metrics.width) - homeShift;
  return { metrics, fonts, cap, zero, gaps, parts, placed, dropped, nameText, natural, nameRoom, key, homeShift };
}
// LVGL's LV_LABEL_LONG_DOT: the longest start that fits with "..." after it.
export function dotted(text: string, font: string, room: number) {
  if (inkOf(text, font).advance <= room) return text;
  const chars = [...text];
  while (chars.length && inkOf(chars.join("") + "...", font).advance > room) chars.pop();
  return chars.join("") + "...";
}
// The fonts load on first use; measurements before that are wrong, so draw again once they are in.
export function whenBarFontsLoad(then: () => void) {
  if (!("fonts" in document)) return;
  Promise.all([
    document.fonts.load('500 27px "Bar Roboto"', "Studio 0"),
    document.fonts.load('400 21px "Bar Roboto"', "Away 0"),
    document.fonts.load('26px "Tile Icons"', String.fromCodePoint(0xf0150)),
  ]).then(() => { clearInkCache(); then(); }).catch(() => {});
}
