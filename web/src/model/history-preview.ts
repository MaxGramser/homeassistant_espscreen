// A sensor's history as the add-on sends it (history-preview, asked for by the entities store, stores/entities.ts), and
// the line a card's graph draws through it.
export type HistoryPreview = { start: number; end: number; values: (number | null)[]; dom?: [number, number]; hi?: [number, number]; lo?: [number, number]; unit: string };

/** The graph on a card as the screen draws it (render_graph in weather_tile_lvgl.h): the 24 averages, each at its own
 * place across the width, scaled between the lowest and the highest of them, a missing one left out and the line run
 * past it, smoothed through Catmull-Rom (smooth() in tile_widgets_lvgl.h, four steps a part), with the area under it
 * filled. The recorder's highest and lowest moments belong to the history card the screen opens, not to the card.
 * `width` and `height` are the graph's own, `stroke` the line's width: the line keeps half of it inside each edge.
 */
export function cardGraph(values: (number | null)[], width: number, height: number, stroke: number) {
  const known = values.slice(0, 24).map((value, i) => [i, value] as const).filter((p): p is readonly [number, number] => p[1] !== null && Number.isFinite(p[1]));
  if (!known.length || width < 2 || height < 2) return null;
  const minimum = Math.min(...known.map(([, v]) => v)), maximum = Math.max(...known.map(([, v]) => v));
  const top = stroke;
  let raw = known.map(([i, v]) => {
    const level = maximum > minimum ? (v - minimum) / (maximum - minimum) : 0.5;
    return { x: Math.floor(stroke / 2) + i * (width - stroke - 1) / 23, y: height - Math.floor(stroke / 2) - 1 - level * (height - stroke - 1 - top) };
  });
  if (raw.length === 1) raw = [raw[0], { x: width - 1, y: raw[0].y }];
  const points: { x: number; y: number }[] = [];
  for (let i = 0; i + 1 < raw.length; ++i) {
    const p0 = raw[i ? i - 1 : 0], p1 = raw[i], p2 = raw[i + 1], p3 = raw[Math.min(i + 2, raw.length - 1)];
    for (let s = 0; s < 4; ++s) {
      const t = s / 4, t2 = t * t, t3 = t2 * t;
      const at = (a: number, b: number, c: number, d: number) => 0.5 * (2 * b + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t2 + (-a + 3 * b - 3 * c + d) * t3);
      points.push({ x: Math.min(Math.max(at(p0.x, p1.x, p2.x, p3.x), 0), width - 1), y: Math.min(Math.max(at(p0.y, p1.y, p2.y, p3.y), 0), height - 1) });
    }
  }
  points.push(raw[raw.length - 1]);
  const round = (n: number) => Math.round(n * 100) / 100;
  const line = points.map((p, i) => `${i ? "L" : "M"}${round(p.x)},${round(p.y)}`).join(" ");
  const area = `${line} L${round(points[points.length - 1].x)},${height} L${round(points[0].x)},${height} Z`;
  return { line, area };
}
