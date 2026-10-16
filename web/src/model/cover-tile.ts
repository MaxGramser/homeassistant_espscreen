// A cover card's layout and its slats (firmware 0.57.0), ported line by line from components/smart_display/cover_tile.h:
// what a cover card draws beside its heading from the room it has, and the slats of a tilt slider at their angle. The
// firmware is the truth; tests/test_editor_parity.py compares the two on a sweep of rooms and densities. Integer
// divisions are C++'s (toward zero).
export type Rect = { x: number; y: number; w: number; h: number };
export enum Tier { NONE = 0, SWAP, ROWS, COLUMNS, COLUMNS_SIDE, COLUMNS_KEYS }
export type Group = { area: Rect; control: Rect; caption: Rect; keys: number; slider: boolean; horizontal: boolean; lying: boolean };
export type Layout = { fits: boolean; tier: Tier; groups: Group[]; swap: Rect };
export type Slat = { x1: number; y1: number; x2: number; y2: number };

const div = (a: number, b: number) => Math.trunc(a / b);
const rect = (x = 0, y = 0, w = 0, h = 0): Rect => ({ x, y, w, h });
export const empty = (r: Rect) => r.w <= 0 || r.h <= 0;
const group = (): Group => ({ area: rect(), control: rect(), caption: rect(), keys: 0, slider: false, horizontal: false, lying: false });
const none = (): Layout => ({ fits: false, tier: Tier.NONE, groups: [group(), group(), group()], swap: rect() });

export const barHeight = (touch: number) => div(touch * 85, 100);

/** The angle of the slats (cover_tile::slat_angle): flat when open (100), 72 degrees when closed (0). */
export function slatAngle(tilt: number) {
  if (!Number.isFinite(tilt)) tilt = 50;
  tilt = Math.max(0, Math.min(100, tilt));
  return (1 - tilt / 100) * 72 * 3.14159265 / 180;
}
/** The slats of a slider w x h (cover_tile::slats): standing it stacks them, lying it sets them side by side. */
export function slats(w: number, h: number, tilt: number, step: number, thickness: number): Slat[] {
  if (w <= 0 || h <= 0 || step <= 0) return [];
  const lying = w > h, across = lying ? h : w, along = lying ? w : h;
  const pitch = Math.max(step, Math.min(div(across * 42, 100), div(along, 9)));
  const half = Math.max(1, Math.min(across * 0.3, pitch * 0.78, (along - thickness) / 2));
  const n = Math.max(1, Math.min(16, div(along - 2 * Math.trunc(half) - thickness, pitch) + 1));
  const a = slatAngle(tilt), c = Math.cos(a) * half, s = Math.sin(a) * half;
  const first = (along - (n - 1) * pitch) / 2, middle = across / 2;
  return Array.from({ length: n }, (_, i) => {
    const at = first + i * pitch;
    return lying ? { x1: at - s, y1: middle - c, x2: at + s, y2: middle + c } : { x1: middle - c, y1: at - s, x2: middle + c, y2: at + s };
  });
}

/** What a cover card draws beside its heading (cover_tile::layout): group 0 the primary control, 1 the slats, 2 the
 * open/stop/close a positional blind gets beside its sliders. The richest tier that fits, or no layout. */
export function coverLayout(body: Rect, touch: number, gap: number, caption: number, sliderMin: number,
  position: boolean, primaryKeys: number, tilt: boolean, tiltKeys: number, extraKeys = 0, standing = true): Layout {
  if (touch <= 0 || gap < 0 || caption <= 0 || (!tilt && !tiltKeys && !position && !primaryKeys)) return none();
  const primary = position || primaryKeys > 0;
  const has = [primary, tilt || tiltKeys > 0];
  const bar = barHeight(touch);
  const n = [primaryKeys, tiltKeys, extraKeys];
  const slider = [position, tilt];
  const bottom = body.y + body.h, right = body.x + body.w;
  const count = (has[0] ? 1 : 0) + (has[1] ? 1 : 0);
  const columns = (keysUnder: number, keysBeside: boolean): Layout => {
    const l = none();
    const columnGap = 2 * gap;
    const controlH = body.h - caption - gap - (keysUnder ? bar + gap : 0);
    if (controlH < bar) return l;
    if ((position || tilt) && controlH < sliderMin) return l;
    const widths = [0, 0], horizontal = [false, false], key = [0, 0];
    const beside = keysBeside ? touch + columnGap : 0;
    const preferred = Math.min(div(body.w - beside - columnGap * (count - 1), count), 2 * touch);
    if (keysBeside && preferred < div(touch * 3, 2)) return l;
    for (let i = 0; i < 2; ++i) {
      if (!has[i]) continue;
      horizontal[i] = n[i] > 0 && div(controlH - (n[i] - 1) * gap, n[i]) < bar;
      key[i] = n[i] ? Math.min(touch, horizontal[i] ? controlH : div(controlH - (n[i] - 1) * gap, n[i])) : 0;
      widths[i] = horizontal[i] ? n[i] * key[i] + (n[i] - 1) * gap : preferred;
      if (widths[i] < touch && !(horizontal[i] && widths[i] >= n[i] * bar)) return l;
    }
    const total = widths[0] + widths[1] + (has[0] && has[1] ? columnGap : 0) + beside;
    if (total > body.w) return l;
    if (keysBeside && body.h < 3 * bar + 2 * gap) return l;
    if (keysUnder && body.w < 3 * bar + 2 * gap) return l;
    let x = body.x + div(body.w - total, 2);
    for (let i = 0; i < 2; ++i) {
      if (!has[i]) continue;
      const g = l.groups[i];
      g.slider = slider[i]; g.keys = g.slider ? 0 : n[i]; g.horizontal = horizontal[i];
      const h = g.slider ? controlH : g.horizontal ? key[i] : g.keys * key[i] + (g.keys - 1) * gap;
      g.area = rect(x, body.y, widths[i], controlH + gap + caption);
      g.control = rect(x, body.y + div(controlH - h, 2), widths[i], h);
      g.caption = rect(x, body.y + controlH + gap, widths[i], caption);
      x += widths[i] + columnGap;
    }
    if (keysBeside) {
      const g = l.groups[2]; g.keys = extraKeys;
      const k = Math.min(touch, div(body.h - 2 * gap, 3)), h = 3 * k + 2 * gap;
      g.area = rect(x, body.y + div(controlH + gap + caption - h, 2), touch, h); g.control = { ...g.area };
    }
    if (keysUnder) {
      const g = l.groups[2]; g.keys = extraKeys; g.horizontal = true;
      const w = Math.min(body.w, 3 * Math.max(bar, Math.min(div(touch * 3, 2), div(body.w - 2 * gap, 3))) + 2 * gap);
      g.area = rect(body.x + div(body.w - w, 2), bottom - bar, w, bar); g.control = { ...g.area };
    }
    l.tier = keysUnder ? Tier.COLUMNS_KEYS : keysBeside ? Tier.COLUMNS_SIDE : Tier.COLUMNS; l.fits = true; return l;
  };
  const rows = (swap: boolean): Layout => {
    const l = none();
    const shown = swap ? 1 : count, row = Math.min(touch, div(body.h - (shown - 1) * gap, shown));
    if (row < bar) return l;
    const width = body.w;
    for (let i = 0; i < 2; ++i) {
      if (!has[i]) continue;
      const keys = slider[i] ? 0 : n[i], need = keys ? keys * row + (keys - 1) * gap : 2 * touch;
      if (need + (swap ? row + gap : 0) > width) return l;
    }
    let y = body.y + div(body.h - shown * row - (shown - 1) * gap, 2);
    for (let i = 0; i < 2; ++i) {
      if (!has[i]) continue;
      const g = l.groups[i];
      g.slider = slider[i]; g.lying = g.slider; g.keys = g.slider ? 0 : n[i]; g.horizontal = true;
      const w = swap ? width - row - gap : width;
      const cw = g.slider ? w : Math.min(w, g.keys * Math.max(row, Math.min(div(touch * 3, 2), div(w - (g.keys - 1) * gap, g.keys))) + (g.keys - 1) * gap);
      g.area = rect(body.x, y, w, row);
      g.control = rect(body.x + div(w - cw, 2), y, cw, row);
      if (!swap) y += row + gap;
    }
    if (swap) l.swap = rect(right - row, y, row, row);
    l.tier = swap ? Tier.SWAP : Tier.ROWS; l.fits = true; return l;
  };
  const lyingBody = body.w >= 2 * body.h;
  const tries: (() => Layout)[] = [
    () => (standing && extraKeys && position && !lyingBody ? columns(extraKeys, false) : none()),
    () => (standing && extraKeys && position && body.w > body.h ? columns(0, true) : none()),
    () => (!standing || lyingBody ? none() : columns(0, false)),
    () => rows(false),
    () => (standing && lyingBody ? columns(0, false) : none()),
    () => (has[0] && has[1] ? rows(true) : none()),
  ];
  for (const attempt of tries) {
    const l = attempt();
    if (l.fits) return l;
  }
  return none();
}
