// A sensor's history as the add-on sends it (history-preview, asked for by the entities store, stores/entities.ts), and
// the line a card's graph draws through it. The numbers are the firmware's, kept the same by tests/test_editor_parity.py
// (Graph): render_graph in weather_tile_lvgl.h, smooth() in tile_widgets_lvgl.h, graph_side in runtime_tiles.h and
// theme::fill_opacity().
export type HistoryPreview = { start: number; end: number; values: (number | null)[]; dom?: [number, number]; hi?: [number, number]; lo?: [number, number]; unit: string };

/** The share of a wide card's content the graph takes at its right (runtime_tiles: chart_w=content_w*55/100). */
export const GRAPH_SIDE = 55;
/** The fill under the line on a light card (theme::fill_opacity(): 51 of 255). */
export const GRAPH_FILL = 51 / 255;
/** The averages a graph draws (the add-on sends 24; render_graph places each at its own 23rd of the width). */
const SLOTS = 24;
/** Catmull-Rom steps between two averages (smooth()). */
const STEPS = 4;

/** The points of the graph on a card as the screen draws them: each average at its own place across the width, scaled
 * between the lowest and the highest of them, a missing one left out and the line run past it, then Catmull-Rom through
 * them. LVGL's points are whole pixels here (lv_value_precise_t is an int32 without LV_USE_FLOAT), so every point is cut
 * to a whole number where the firmware's cast cuts it. `width` and `height` are the graph's own, `stroke` the line's. */
export function cardPoints(values: (number | null)[], width: number, height: number, stroke: number) {
  const known: [number, number][] = [];
  values.slice(0, SLOTS).forEach((v, i) => { if (v !== null && Number.isFinite(v)) known.push([i, v]); });
  if (!known.length) return [];
  // In single precision, as the firmware's floats are (f() rounds every step to one).
  const f = Math.fround;
  const minimum = Math.min(...known.map(([, v]) => f(v))), maximum = Math.max(...known.map(([, v]) => f(v)));
  const half = Math.trunc(stroke / 2), top = stroke;
  let raw = known.map(([i, v]) => {
    const level = maximum > minimum ? f(f(f(v) - minimum) / f(maximum - minimum)) : 0.5;
    return { x: half + Math.trunc(i * (width - stroke - 1) / (SLOTS - 1)), y: Math.trunc(f(height - half - 1 - f(level * (height - stroke - 1 - top)))) };
  });
  if (raw.length === 1) raw = [raw[0], { x: width - 1, y: raw[0].y }];
  const points: { x: number; y: number }[] = [];
  for (let i = 0; i + 1 < raw.length; ++i) {
    const p0 = raw[i ? i - 1 : 0], p1 = raw[i], p2 = raw[i + 1], p3 = raw[Math.min(i + 2, raw.length - 1)];
    for (let s = 0; s < STEPS; ++s) {
      const t = f(s / STEPS), t2 = f(t * t), t3 = f(t2 * t);
      // 0.5f*(2*p1+(-p0+p2)*t+(2*p0-5*p1+4*p2-p3)*t2+(-p0+3*p1-3*p2+p3)*t3): whole numbers times floats, summed left to right.
      const at = (a: number, b: number, c: number, d: number) =>
        f(0.5 * f(f(f(2 * b + f((-a + c) * t)) + f((2 * a - 5 * b + 4 * c - d) * t2)) + f((-a + 3 * b - 3 * c + d) * t3)));
      points.push({ x: Math.trunc(Math.min(Math.max(at(p0.x, p1.x, p2.x, p3.x), 0), width - 1)),
        y: Math.trunc(Math.min(Math.max(at(p0.y, p1.y, p2.y, p3.y), 0), height - 1)) });
    }
  }
  points.push(raw[raw.length - 1]);
  return points;
}

/** The graph's line and the filled area under it, as SVG paths in the graph's own pixels. */
export function cardGraph(values: (number | null)[], width: number, height: number, stroke: number) {
  if (width < 2 || height < 2) return null;
  const points = cardPoints(values, width, height, stroke);
  if (!points.length) return null;
  const line = points.map((p, i) => `${i ? "L" : "M"}${p.x},${p.y}`).join(" ");
  return { line, area: `${line} L${points[points.length - 1].x},${height} L${points[0].x},${height} Z` };
}
