// A sensor's history as the add-on sends it (history-preview, asked for by the entities store, stores/entities.ts), and
// the lines its graph draws.
export type HistoryPreview = { start: number; end: number; values: (number | null)[]; dom?: [number, number]; hi?: [number, number]; lo?: [number, number]; unit: string };
/** Bucket centers retain their time positions; missing buckets break the line.
 * The recorder's extrema are drawn separately, so the average cannot hide them.
 */
export function historyGeometry(data: HistoryPreview) {
  const known = data.values.filter((value): value is number => value !== null && Number.isFinite(value));
  if (!known.length || data.end <= data.start) return null;
  const extrema = [data.hi, data.lo].filter((value): value is [number, number] => !!value && value.every(Number.isFinite));
  const [low, high] = data.dom || [Math.min(...known, ...extrema.map(([v]) => v)), Math.max(...known, ...extrema.map(([v]) => v))];
  const y = (value: number) => high === low ? 25 : 47 - (value - low) / (high - low) * 44;
  const x = (time: number) => 3 + (time - data.start) / (data.end - data.start) * 194;
  const paths: string[] = []; let segment: string[] = [];
  data.values.forEach((value, index) => {
    if (value === null || !Number.isFinite(value)) { if (segment.length) paths.push(segment.join(' ')); segment = []; return; }
    segment.push(`${segment.length ? 'L' : 'M'}${x(data.start + (index + .5) * (data.end - data.start) / data.values.length)},${y(value)}`);
  });
  if (segment.length) paths.push(segment.join(' '));
  return { paths, points: extrema.filter(([, time]) => time >= data.start && time <= data.end).map(([value, time]) => ({ x: x(time), y: y(value) })) };
}
