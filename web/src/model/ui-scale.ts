// The firmware's sizes in the editor's mockup (app 0.4.32): ui_scale.h's px() and the -/+ pill of a card's controls
// (runtime_tiles panel_metrics, stepper_keys), computed the same way from the board's density and look, so the mockup
// draws them at the size the glass does instead of sizes of its own.
type Shape = { width?: number; height?: number; dpi?: number; look?: string;
  fonts?: { watch_value?: number; sublabel_big?: number; sublabel?: number; icon_mini?: number; label?: number; headline?: number; watch_icon?: number; setpoint?: number };
  spacing?: Spacing };
// The glass's grid (boards.json "spacing"): its margin, the gaps between columns and between rows, a card's padding, where
// the tile area starts under the top bar (SCROLL_Y), the page bar's height (PAGE_BAR_H) and a card's icon circle.
type Spacing = { margin: number; gap: number; tile_pad: number; gap_y?: number; top?: number; page_bar?: number; circle?: number };

/** ui::configure and ui::px: a size of the reference look (170 dpi standard, 143 dpi compact) in this board's pixels. */
export function uiScale(shape: Shape) {
  const compact = shape.look === "compact", reference = compact ? 143 : 170;
  const dpi = Math.round(shape.dpi || reference);
  const scalePct = Math.floor((dpi * 100 + Math.floor(reference / 2)) / reference);
  const px = (n: number) => (scalePct === 100 ? n : n >= 0 ? Math.floor((n * scalePct + 50) / 100) : -Math.floor((-n * scalePct + 50) / 100));
  return { compact, large: !compact, px };
}

/** The pill of a wide card's -/+ in glass pixels: its height (panel_metrics key_h + 2), the inset of its keys and their
 * diameter (stepper_keys), and the faces its number is drawn in (watch_value first, then sublabel_big, then sublabel). */
export function pillMetrics(shape: Shape) {
  const { large, px } = uiScale(shape);
  const height = px(large ? 46 : 34) + 2, inset = Math.max(2, px(large ? 4 : 3)), key = Math.max(1, height - 2 * inset);
  const fonts = shape.fonts || {};
  return { height, inset, key, faces: [fonts.watch_value, fonts.sublabel_big, fonts.sublabel].filter((size): size is number => Boolean(size)) };
}

/** A number's width in em as the screens' Roboto draws it: a digit .56, the degree sign .37, a minus .33, a decimal mark
 * .27. Enough to pick among a board's faces as the firmware does, which measures the glyphs themselves. */
export const textEms = (text: string) => [...text].reduce((sum, ch) => sum + (/\d/.test(ch) ? 0.56 : ch === "°" ? 0.37 : ch === "-" ? 0.33 : 0.27), 0);

/** The widest temperature a thermostat's -/+ can show (tile_controls::widest_setpoint): as many 8s as its highest or
 * lowest temperature has digits, with the decimal its step shows. The face measured by it keeps its size from tap to tap. */
export function widestSetpoint(a: Record<string, any>) {
  const minimum = Number.isFinite(Number(a.min_temp)) ? Number(a.min_temp) : 7, maximum = Number.isFinite(Number(a.max_temp)) ? Number(a.max_temp) : 35;
  const reach = Math.max(Math.abs(minimum), Math.abs(maximum)), step = Number(a.target_temp_step) > 0 ? Number(a.target_temp_step) : 0.5;
  return `${minimum < 0 ? "-" : ""}${"8".repeat(String(Math.trunc(reach)).length)}${step < 1 ? ".8" : ""}°`;
}

/** A thermostat's mode bar in a card's panel (climate_tile::bar_room and bar_width, the panel's key as a finger:
 * runtime_tiles panel_metrics, the taller card's finger, panel_metrics_full): how many modes fit in `reach` glass pixels
 * and how wide the bar is. `place`: beside the name on a card of one row, over the card on a taller one or the page. */
export function modeBar(shape: Shape, place: "row" | "tall" | "full", reach: number, modes: number) {
  const { large, compact, px } = uiScale(shape);
  const touchMin = Math.floor(((shape.dpi || (compact ? 143 : 170)) * 7 + 12) / 25);
  const finger = place === "tall" ? Math.max(touchMin, px(large ? 48 : 34)) : place === "full" ? px(large ? 84 : 44) : px(large ? 46 : 34);
  const inset = Math.max(2, px(large ? 4 : 3));
  reach = Math.min(reach, px(compact ? 620 : 740));
  const fit = modes >= 2 ? Math.min(modes, Math.floor((reach - 2 * inset) / finger)) : 0;
  const room = fit >= 2 ? fit : 0;
  const width = !room ? 0 : place === "row" ? Math.min(reach, room * finger + 2 * inset) : reach;
  return { room, width, finger, inset };
}

const spacingOf = (shape: Shape) => shape.spacing ?? (uiScale(shape).compact ? { margin: 9, gap: 6, tile_pad: 8 } : { margin: 16, gap: 12, tile_pad: 12 });

/** The glass's grid with its heights (app 0.4.74): a shape from boards.json has them all; one stored before (a preview
 * screen kept in the browser) gets the look's own, scaled to its density as the board files scale them. */
export function frameOf(shape: Shape): Required<Spacing> {
  const s = spacingOf(shape), { compact, px } = uiScale(shape), dpi = shape.dpi || (compact ? 143 : 170);
  return { ...s, gap_y: s.gap_y ?? Math.min(px(compact ? 6 : 12), compact ? 4 : 12), top: s.top ?? px(compact ? 37 : 56),
    page_bar: s.page_bar ?? Math.min(px(compact ? 36 : 60), Math.round((dpi * 7) / 25.4)), circle: s.circle ?? px(compact ? 36 : 54) };
}

/** A card's height in glass pixels, its padding and border included: `rows` of the page's `down` rows from row `start`,
 * as LVGL's grid shares the tile area between its rows (one fr each, as cardContent shares the columns), with the gaps
 * between them. The area runs from under the top bar to the page bar where the layout has one (more than one page,
 * page_protocol.h footer), else to the margin (runtime_tiles place_page). */
export function cardHeight(shape: Shape, down: number, rows: number, start = 0, paged = false) {
  const s = frameOf(shape), n = Math.max(1, down);
  let free = Math.max(0, (shape.height ?? 240) - s.top - (paged ? s.page_bar : s.margin) - (n - 1) * s.gap_y), height = 0;
  for (let i = 0, left = n; i < n; ++i, --left) {
    const track = Math.floor((free + Math.floor(left / 2)) / left);
    free -= track;
    if (i >= start && i < start + rows) height += track;
  }
  return height + (rows - 1) * s.gap_y;
}

/** The padding above and below a Big number card (runtime_tiles bind and render): 2 on the compact look; else the
 * board's TILE_PAD, or 4 on a grid whose cells are 80 pixels high or less (as the card was bound, with the page bar). */
export function watchPadding(shape: Shape, down: number) {
  if (uiScale(shape).compact) return 2;
  return cardHeight(shape, down, 1, 0, true) <= 80 ? 4 : frameOf(shape).tile_pad;
}

/** A font's line in glass pixels: Roboto's ascender and descender at that size, as LVGL measures it. */
export const lineOf = (size: number) => Math.round(size * 1.172);

/** A text's width in glass pixels in Roboto at `size`, roughly: what the firmware measures with the glyphs themselves
 * (text_width), close enough to choose between a board's faces as it does. */
export const textWidth = (text: string, size: number) => Math.round([...text].reduce((sum, ch) =>
  sum + (/\d/.test(ch) ? 0.56 : ch === "°" ? 0.37 : ch === "-" ? 0.33 : ch === "." || ch === "," ? 0.27 : ch === " " ? 0.25
    : /[iljtf!|:;']/.test(ch) ? 0.27 : /[mwMW@]/.test(ch) ? 0.85 : /[A-Z]/.test(ch) ? 0.64 : 0.53), 0) * size);

// What the setpoint's digits carry (packages/core.yaml setpoint_digits); a word keeps the card's own faces.
const SETPOINT_GLYPHS = new Set([..."-.,°%0123456789"]);

export type WatchCard = {
  /** The icon and the name above the number; else the name small in the corner, the number under it and no icon. */
  stacked: boolean;
  circle: { x: number; y: number; size: number; icon: number };
  title: { x: number; y: number; width: number; size: number; line: number };
  value: { x: number; y: number; width: number; size: number; line: number };
  unit: { x: number; y: number; width: number; size: number; line: number } | null;
  /** The room between the number and its unit. */
  unitGap: number;
};

/** A Big number card (display "watch") in glass pixels, as runtime_tiles lays it out in a card of `width` x `height`
 * content (firmware 0.35.0+): the icon and the name in a head above the number, all three as one group in the middle of
 * the card, the number in the largest face that fits under the head (the setpoint's digits in a tall cell, the watch
 * face, then the headline); a cell too low even for that keeps the name small in the top corner and the number below it
 * in the largest face that fits, and the icon goes. The unit stands at the right in the card's small letters, or right
 * after a number standing alone. */
export function watchCard(shape: Shape, width: number, height: number, value: string, unit: string, pad = frameOf(shape).tile_pad): WatchCard {
  const { large, px } = uiScale(shape), s = frameOf(shape);
  // The board's fonts (boards.json); a shape without them (a preview screen stored before) the look's, scaled.
  const look = large ? { label: 18, sublabel: 16, sublabel_big: 21, headline: 27, watch_value: 38, watch_icon: 18, setpoint: 64 }
    : { label: 11, sublabel: 11, sublabel_big: 14, headline: 18, watch_value: 22, watch_icon: 12, setpoint: 40 };
  const f = Object.fromEntries(Object.entries(look).map(([key, size]) =>
    [key, shape.fonts?.[key as keyof typeof look] ?? Math.max(8, px(size))])) as typeof look;
  const small = f.sublabel, label = f.label;
  const mm = (n: number) => Math.floor(((shape.dpi || (large ? 170 : 143)) * n + 12) / 25);
  // name_font: on the compact look a name with 30 mm of room takes the larger step (WIDE_NAME_FONT).
  const name = !large && width >= mm(30) ? f.sublabel_big : label, nameLine = lineOf(name);
  const circle = large ? Math.floor((s.circle * 26) / 54) : Math.floor(s.circle / 2);
  const gap = px(large ? 6 : 2), header = Math.max(circle, nameLine);
  const unitWidth = unit ? Math.max(0, Math.min(textWidth(unit, small), width - 20)) : 0;
  const unitGap = unitWidth ? unitWidth + px(large ? 6 : 3) : 0;
  let numberWidth = width - unitGap;
  const digits = [...value].every((ch) => SETPOINT_GLYPHS.has(ch));
  let face = f.watch_value;
  if (digits && header + gap + lineOf(f.setpoint) <= height && textWidth(value, f.setpoint) <= numberWidth) face = f.setpoint;
  let stacked = header + gap + lineOf(face) <= height;
  if (!stacked && f.headline !== face && header + gap + lineOf(f.headline) <= height && textWidth(value, f.headline) <= numberWidth) {
    face = f.headline;
    stacked = true;
  }
  const icon = f.watch_icon;
  const unitAt = (x: number, valueY: number, line: number) =>
    unitWidth ? { x, y: valueY + line - lineOf(small), width: unitWidth, size: small, line: lineOf(small) } : null;
  if (stacked) {
    const line = lineOf(face), groupY = Math.max(0, Math.trunc((height - header - gap - line) / 2)), valueY = groupY + header + gap;
    const titleX = circle + px(large ? 6 : 4);
    return { stacked, circle: { x: 0, y: groupY + Math.trunc((header - circle) / 2), size: circle, icon },
      title: { x: titleX, y: groupY + Math.trunc((header - nameLine) / 2), width: width - titleX, size: name, line: nameLine },
      value: { x: 0, y: valueY, width: numberWidth, size: face, line }, unit: unitAt(width - unitWidth, valueY, line), unitGap: unitGap - unitWidth };
  }
  // The number under the name, never in its box: the largest face whose line ends in the padding, never past the border.
  const nameH = lineOf(small), below = nameH + px(2), floor = height + pad + 1 - 2;
  let fitted = small;
  for (const size of [face, f.headline, small])
    if (below + lineOf(size) <= floor && textWidth(value, size) <= numberWidth) { fitted = size; break; }
  const line = lineOf(fitted), valueY = Math.min(Math.max(below, Math.trunc((height - line) / 2)), floor - line);
  numberWidth = Math.max(1, Math.min(numberWidth, Math.min(textWidth(value, fitted), numberWidth) + 2));
  const numberX = Math.max(0, Math.trunc((width - numberWidth - unitGap) / 2));
  return { stacked, circle: { x: 0, y: 0, size: 0, icon },
    title: { x: 0, y: 0, width, size: small, line: nameH },
    value: { x: numberX, y: valueY, width: numberWidth, size: fitted, line }, unit: unitAt(numberX + numberWidth + (unitGap - unitWidth), valueY, line),
    unitGap: unitGap - unitWidth };
}

/** The cell a wide card's controls fill, in glass pixels (runtime_tiles cell_content_width): the page less its margins
 * shared between `across` cells with a gap between two, rounded down, less the card's padding and its border. */
export function cellContent(shape: Shape, across: number) {
  const s = spacingOf(shape);
  return Math.floor(((shape.width ?? 320) - 2 * s.margin - (across - 1) * s.gap) / Math.max(1, across)) - 2 * s.tile_pad - 2;
}

/** A card's content width in glass pixels: `columns` of the page's `across` cells from column `start`, as LVGL's grid
 * shares the page between its columns (lv_grid.c, one fr each: every column the nearest whole share of what is left, so
 * the last one ends on the margin), with the gaps between them, less the card's padding and its border. */
export function cardContent(shape: Shape, across: number, columns: number, start = 0) {
  const s = spacingOf(shape), n = Math.max(1, across);
  let free = Math.max(0, (shape.width ?? 320) - 2 * s.margin - (n - 1) * s.gap), width = 0;
  for (let i = 0, left = n; i < n; ++i, --left) {
    const track = Math.floor((free + Math.floor(left / 2)) / left);
    free -= track;
    if (i >= start && i < start + columns) width += track;
  }
  return width + (columns - 1) * s.gap - 2 * s.tile_pad - 2;
}

/** A range's chip on a wide card's -/+ pill (runtime_tiles stepper_keys and range_chip), in glass pixels: the face its
 * number is drawn in, the largest whose line fits the pill and whose widest temperature fits the chip on its own, and
 * whether its heat or cool icon fits beside that number (else the number stands alone in its end's colour). */
export function wideChip(shape: Shape, across: number, widest: string) {
  const { px } = uiScale(shape), pill = pillMetrics(shape), fonts = shape.fonts || {};
  const width = cellContent(shape, across), chip = width - 2 * (pill.inset + pill.key + pill.inset), pad = px(6);
  const line = (size: number) => Math.round(size * 1.172), ems = textEms(widest);
  let face = pill.faces[pill.faces.length - 1] ?? 14;
  for (const size of pill.faces) if (line(size) <= pill.height && ems * size + pad <= chip) { face = size; break; }
  const icon = line(fonts.icon_mini ?? (uiScale(shape).large ? 26 : 18));
  return { face, icon: icon + pad / 2 + ems * face + pad <= chip };
}

/** The least room the energy card's diagram takes, in millimetres of the card's content (energy_card.h MIN_WIDTH_MM and
 * MIN_HEIGHT_MM, firmware 0.47.0): a card lower than that on its look shows the house's use alone, so the editor does
 * not offer it. tests/test_energy_card.cpp proves the firmware draws the diagram from there up on every board. */
export const ENERGY_MIN_MM = { width: 30, compact: 25, standard: 32 };
/** Whether the energy card's diagram fits `columns` x `rows` of the glass's `across` x `down` cells, with a page bar
 * under them (the lowest the card can be), as energy_card::offered measures it with ui::mm. */
export function energyFits(shape: Shape, across: number, down: number, columns: number, rows: number) {
  const { compact } = uiScale(shape), dpi = Math.round(shape.dpi || (compact ? 143 : 170)), pad = frameOf(shape).tile_pad;
  const mm = (n: number) => Math.floor((dpi * n + 12) / 25);
  const width = cardContent(shape, across, columns), height = cardHeight(shape, down, rows, 0, true) - 2 * (pad + 1);
  return width >= mm(ENERGY_MIN_MM.width) && height >= mm(compact ? ENERGY_MIN_MM.compact : ENERGY_MIN_MM.standard);
}
