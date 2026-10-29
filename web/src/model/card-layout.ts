// A card's own parts on the glass (app 0.4.90): its corner, padding and the faces of its name, its line and its icon
// (packages/looks, boards.json), where runtime_tiles puts its head (head_row: the circle at the left, the name and the
// line beside it), which icon face its circle takes (center_icon), which face its name (name_font), and the control a
// card of one row draws at its right (layout_panel, panel_metrics). In glass pixels: the mockup multiplies them by the
// glass's scale (stores/canvas.ts --glass), so a card is drawn as the glass draws it on every board, not at sizes of
// the editor's own. tests/test_editor_parity.py holds these to the firmware.
import ink from "./icon-ink.json";
import { textPx } from "./text-fit";
import { presetPanel, presetSizes } from "./light-presets";
import { cardContent, cardHeight, frameOf, lineOf, touchMin, uiScale, type Shape } from "./ui-scale";

/** The look's faces and a card's frame on this glass: the board's own sizes, or for a shape stored without them (a
 * preview screen of an older app) the look's, scaled to its density. */
export function cardLook(shape: Shape) {
  const { large, px } = uiScale(shape), fonts = shape.fonts || {}, frame = frameOf(shape);
  const face = (name: keyof NonNullable<Shape["fonts"]>, standard: number, compact: number) => fonts[name] ?? Math.max(8, px(large ? standard : compact));
  return { large, radius: frame.radius, pad: frame.tile_pad, circle: frame.circle,
    label: face("label", 18, 11), sublabel: face("sublabel", 16, 11), sublabelBig: face("sublabel_big", 21, 14), headline: face("headline", 27, 18),
    watch: face("watch_value", 38, 22), setpoint: face("setpoint", 64, 40), icon: face("icon", 42, 28), iconMini: face("icon_mini", 26, 18) };
}
export type CardLook = ReturnType<typeof cardLook>;

/** A glyph's ink at `size` pixels, as the glass rasterises it (freetype's box around the outline). */
export function inkBox(code: string, size: number) {
  const bounds = (ink as Record<string, number[] | number>)[code.toUpperCase()];
  if (!Array.isArray(bounds)) return null;
  const [x0, y0, x1, y1] = bounds, k = size / ink.upm;
  return { w: Math.ceil(x1 * k) - Math.floor(x0 * k), h: Math.ceil(y1 * k) - Math.floor(y0 * k) };
}
/** The face an icon takes in a circle of `side` (center_icon): the card's icon font, or the keys' smaller one where the
 * glyph's ink would reach past 78 % of the circle across its diagonal (a bulb steps down on a Guition, a thermometer not). */
export function iconFace(look: CardLook, code: string, side: number, face = look.icon) {
  const box = inkBox(code, face), limit = Math.floor((side * 78) / 100);
  return box && face !== look.iconMini && side > 0 && box.w * box.w + box.h * box.h > limit * limit ? look.iconMini : face;
}

/** The padding above and below every card of this grid (bind_card): 4 where the grid's first cell, as the card was
 * bound with the page bar, is 80 pixels high or less, else the board's TILE_PAD. Left and right always TILE_PAD. */
export function cardPadY(shape: Shape, down: number) {
  return cardHeight(shape, down, 1, 0, true) <= 80 ? 4 : frameOf(shape).tile_pad;
}

/** Where a card stands on its page and the room inside it, in glass pixels: `columns` x `rows` of the page's `across` x
 * `down` cells from (`column`, `row`), with the page bar under the grid when the layout has one. */
export type CardPlace = { across: number; down: number; column: number; row: number; columns: number; rows: number; paged: boolean };
export function cardRoom(shape: Shape, p: CardPlace) {
  const padY = cardPadY(shape, p.down), pad = frameOf(shape).tile_pad;
  const height = cardHeight(shape, p.down, p.rows, p.row, p.paged);
  return { pad, padY, width: cardContent(shape, p.across, p.columns, p.column), height: Math.max(0, height - 2 - 2 * padY), outer: height };
}

export type TextBox = { x: number; y: number; width: number; size: number; line: number; weight: number; center?: boolean };
export type Head = { circle: { x: number; y: number; size: number; icon: number }; title: TextBox; value: TextBox | null };

/** The head of a card of one row (runtime_tiles head_row, render): the icon circle at the left, centred on the card's
 * room; the name and its line as two lines beside it, centred together, or the name alone in the middle. `panel` is the
 * room a control at the right takes with its gap (layout_panel's panel_w), `code` the icon's glyph; `nameStep` false
 * for the head of a full card, whose name never takes the larger step. */
export function cardHead(shape: Shape, look: CardLook, room: { width: number; height: number; padY: number; outer?: number }, panel: number, code: string,
  withValue: boolean, wide = false, nameStep = true): Head {
  const { large, px, compact } = uiScale(shape);
  // A card of one cell at least twice the look's cell high (a tall glass with few rows) stands its icon above its name
  // and its line, centred, as a full card does (runtime_tiles render).
  if (!wide && !panel && (room.outer ?? 0) >= 2 * px(large ? 108 : 52)) {
    const circle = Math.trunc((Math.min(room.width, (room.height * (large ? 45 : 40)) / 100))), gap = px(large ? 10 : 6), between = px(large ? 2 : 1);
    const titleLine = lineOf(look.label), valueLine = lineOf(look.sublabel);
    const top = Math.max(0, Math.trunc((room.height - (circle + gap + titleLine + between + valueLine)) / 2));
    return {
      circle: { x: Math.trunc((room.width - circle) / 2), y: top, size: circle, icon: iconFace(look, code, circle) },
      title: { x: 0, y: top + circle + gap, width: room.width, size: look.label, line: titleLine, weight: 700, center: true },
      value: withValue ? { x: 0, y: top + circle + gap + titleLine + between, width: room.width, size: look.sublabel, line: valueLine, weight: 400, center: true } : null,
    };
  }
  const dpi = shape.dpi || (compact ? 143 : 170), mm = (n: number) => Math.floor((dpi * n + 12) / 25);
  // name_font: on the compact look a name with 30 mm of room takes the L step of the text set (WIDE_NAME_FONT).
  // A full card's head keeps the card's own name face (render_full sets title_font).
  const roomy = nameStep && !large && room.width - panel >= mm(30);
  const titleSize = roomy ? look.sublabelBig : look.label, titleLine = lineOf(titleSize), valueLine = lineOf(look.sublabel);
  const gap = px(large ? 6 : 1);
  const circle = Math.max(1, Math.min(look.circle, room.height + 2 * room.padY - 2 * px(large ? 6 : 3)));
  const titleY = Math.max(0, Math.trunc((room.height - (titleLine + (withValue ? gap + valueLine : 0))) / 2));
  const x = circle + px(large ? 10 : 12), width = Math.max(1, room.width - x - panel);
  return {
    circle: { x: 0, y: Math.trunc((room.height - circle) / 2), size: circle, icon: iconFace(look, code, circle) },
    title: { x, y: titleY, width, size: titleSize, line: titleLine, weight: roomy ? 400 : 700 },
    value: withValue ? { x, y: titleY + titleLine + gap, width, size: look.sublabel, line: valueLine, weight: 400 } : null,
  };
}

/** A slider's corner (slider_handle): rounded by its height, not a pill, so its white handle sits inside the fill's end. */
export const sliderCorner = (height: number) => (height > 20 ? Math.trunc((height * 12) / 42) : height / 2);

/** The controls of a card of one row (panel_metrics): keys, the -/+ pill, a slider, a switch and a run key. */
export function panelMetrics(shape: Shape) {
  const { large, px } = uiScale(shape);
  return large
    ? { keyW: px(60), keyH: px(46), radius: px(14), gap: px(8), sliderH: px(44), toggleW: px(76), toggleH: px(40), runPad: px(22), textGap: px(8) }
    : { keyW: px(40), keyH: px(34), radius: px(9), gap: px(4), sliderH: px(30), toggleW: px(48), toggleH: px(26), runPad: px(14), textGap: px(6) };
}

export type PanelKind = "toggle" | "keys" | "setpoint" | "slider" | "volume" | "run" | "mode" | "presets";
/** A control at the right of a card of one row (layout_panel), in glass pixels: its width and height, a key's size and
 * the gap between keys, standing at the right of the card's room, centred on its height. `fill` is the room a control
 * that fills it takes (rest_content_width), `keys` how many keys a row draws, `run` the run key's word width. */
export function cardPanel(shape: Shape, kind: PanelKind, fill: number, room: { width: number; height: number }, keys = 3, run = 0) {
  const m = panelMetrics(shape);
  const keyW = Math.min(m.keyW, Math.max(touchMin(shape), Math.trunc((fill - 2 * m.gap) / 3)));
  let width = 0, height = m.keyH;
  // A light's presets (`keys` of them): a row of round keys where its slider would stand, as many as its room holds,
  // the ring's room round them (runtime_tiles layout_panel).
  let presets: ReturnType<typeof presetPanel> | null = null;
  if (kind === "presets") {
    presets = presetPanel(shape, keys, fill, Math.max(m.keyH, Math.min(room.height, presetSizes(shape).tileKey)));
    width = presets.width; height = presets.height;
  }
  if (kind === "toggle") { width = m.toggleW; height = m.toggleH; }
  else if (kind === "keys") width = keys ? keys * keyW + (keys - 1) * m.gap : 0;
  else if (kind === "setpoint") { width = fill; height = m.keyH + 2; }
  else if (kind === "slider") width = fill;
  else if (kind === "volume") width = Math.max(touchMin(shape), fill - m.gap - m.keyH) + m.gap + m.keyH;
  else if (kind === "run") width = Math.max(Math.trunc((m.keyW * 3) / 2), run + 2 * m.runPad);
  return { ...m, kind, keyW, width, height, presets, x: room.width - width, y: Math.max(0, Math.trunc((room.height - height) / 2)), taken: width ? width + m.textGap : 0,
    knob: m.toggleH - 8, slider: Math.max(touchMin(shape), fill - m.gap - m.keyH) };
}

/** The face of the number between a wide card's -/+ (stepper_keys): the largest of the look's number faces (watch_value,
 * the controls' sublabel_big, sublabel) whose line fits the pill and whose text with a digit to spare fits between
 * its keys, as the glass measures it, so a tap on + never makes it smaller. */
export function pillFace(shape: Shape, look: CardLook, width: number, height: number, text: string) {
  const { large, px } = uiScale(shape), inset = Math.max(2, px(large ? 4 : 3)), key = Math.max(1, height - 2 * inset);
  const room = width - 2 * (key + inset) - px(4), widest = `${text}8`;
  const faces = [{ size: look.watch, weight: 500 }, { size: look.sublabelBig, weight: 400 }, { size: look.sublabel, weight: 400 }];
  const face = faces.find((f) => lineOf(f.size) <= height && textPx(widest, f.size, f.weight) <= room) ?? faces[1];
  return { ...face, line: lineOf(face.size) };
}
