// A sound of one's own (docs/SOUNDS.md): the part of a sound file someone picks on the waveform, made into what the
// screens play. The browser decodes the file and brings it to 16 kHz mono (stores/sounds.ts, Web Audio's resampler);
// everything after that is here and pure, so tests/ringtone.spec.ts checks it: the bass out, the cut, short fades so the
// loop does not click, and the level as loud as it goes. The add-on checks the finished WAV again (sounds.checked)
// and holds the limits this reads from api/sounds (rate, max_seconds, min_seconds).
//
// Why each step: the screens' small speakers carry 1.4 to 1.9 kHz best and nothing much under 400 Hz, so the bass only
// takes level that the rest could use; a ringtone plays back to back, so a jump at its ends is a click every turn; and a
// ring must be heard across a room, so it is levelled to one height for every sound instead of kept as the file came.

export const HIGH_PASS_HZ = 400;
export const FADE_SECONDS = 0.008;
// Half of full scale (-6 dB), as the app's own sounds (sounds.LEVEL): at 97 % the speakers distorted at a ring's volume.
export const PEAK = 0.5;

/** A second-order high-pass (RBJ's cookbook, Butterworth Q), run twice: 24 dB an octave under `cutoff`. */
export function highPass(input: Float32Array, rate: number, cutoff = HIGH_PASS_HZ): Float32Array {
  const w = (2 * Math.PI * cutoff) / rate;
  const alpha = Math.sin(w) / (2 * Math.SQRT1_2);
  const cos = Math.cos(w);
  const a0 = 1 + alpha;
  const b0 = (1 + cos) / 2 / a0, b1 = -(1 + cos) / a0, b2 = (1 + cos) / 2 / a0;
  const a1 = (-2 * cos) / a0, a2 = (1 - alpha) / a0;
  let out = input;
  for (let pass = 0; pass < 2; pass++) {
    const next = new Float32Array(out.length);
    let x1 = 0, x2 = 0, y1 = 0, y2 = 0;
    for (let i = 0; i < out.length; i++) {
      const x = out[i];
      const y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
      next[i] = y;
      x2 = x1; x1 = x; y2 = y1; y1 = y;
    }
    out = next;
  }
  return out;
}

/** The part from `start` to `end` seconds. */
export function cut(input: Float32Array, rate: number, start: number, end: number): Float32Array {
  const from = Math.max(0, Math.min(input.length, Math.round(start * rate)));
  const to = Math.max(from, Math.min(input.length, Math.round(end * rate)));
  return input.slice(from, to);
}

/** Short fades in and out, so the sound starts and ends at silence. */
export function fade(input: Float32Array, rate: number, seconds = FADE_SECONDS): Float32Array {
  const out = input.slice();
  const n = Math.min(Math.round(seconds * rate), Math.floor(out.length / 2));
  for (let i = 0; i < n; i++) {
    const gain = i / n;
    out[i] *= gain;
    out[out.length - 1 - i] *= gain;
  }
  return out;
}

/** As loud as it goes: the loudest sample at `peak` of full scale. Silence stays silence. */
export function level(input: Float32Array, peak = PEAK): Float32Array {
  let most = 0;
  for (const s of input) most = Math.max(most, Math.abs(s));
  if (most < 1e-6) return input.slice();
  const gain = peak / most;
  return input.map((s) => s * gain);
}

/** The whole way from the picked part of a 16 kHz mono sound to what the screens play. The filter runs over the whole
 *  sound first, so its start-up lies before the cut instead of in it. */
export function ringtone(sound: Float32Array, rate: number, start: number, end: number): Float32Array {
  return level(fade(cut(highPass(sound, rate), rate, start, end), rate));
}

/** A 16-bit mono WAV of `samples` (-1..1). */
export function wav(samples: Float32Array, rate: number): Uint8Array {
  const bytes = new Uint8Array(44 + samples.length * 2);
  const view = new DataView(bytes.buffer);
  const text = (at: number, word: string) => { for (let i = 0; i < 4; i++) bytes[at + i] = word.charCodeAt(i); };
  text(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  text(8, "WAVE");
  text(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, rate, true);
  view.setUint32(28, rate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  text(36, "data");
  view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) view.setInt16(44 + i * 2, Math.round(Math.max(-1, Math.min(1, samples[i])) * 32767), true);
  return bytes;
}

/** The waveform as `columns` bars: the loudest sample of each stretch, 0..1. */
export function peaks(samples: Float32Array, columns: number): number[] {
  const out: number[] = [];
  if (!samples.length || columns <= 0) return out;
  const step = samples.length / columns;
  for (let c = 0; c < columns; c++) {
    let most = 0;
    for (let i = Math.floor(c * step); i < Math.min(samples.length, Math.floor((c + 1) * step)); i++) most = Math.max(most, Math.abs(samples[i]));
    out.push(most);
  }
  return out;
}

/** The part first offered: from the first sound (a file that opens with silence starts at its sound), as long as
 *  allowed or as the file runs. */
export function firstPart(samples: Float32Array, rate: number, most: number): { start: number; end: number } {
  let first = 0;
  let loudest = 0;
  for (const s of samples) loudest = Math.max(loudest, Math.abs(s));
  const floor = loudest * 0.05;
  while (first < samples.length && Math.abs(samples[first]) < floor) first++;
  const start = Math.max(0, first / rate - 0.01);
  const length = samples.length / rate;
  if (length - start < most) return { start: Math.max(0, length - most), end: length };
  return { start, end: start + most };
}

/** A part moved or stretched by a hand: kept inside the sound, at least `least` and at most `most` long. `edge` says what
 *  moved: the start, the end, or the whole part (its length stays). */
export function movePart(part: { start: number; end: number }, edge: "start" | "end" | "whole", to: number, length: number,
  least: number, most: number): { start: number; end: number } {
  if (edge === "whole") {
    const span = part.end - part.start;
    const start = Math.max(0, Math.min(length - span, to));
    return { start, end: start + span };
  }
  if (edge === "start") {
    const start = Math.max(0, Math.max(part.end - most, Math.min(part.end - least, to)));
    return { start, end: part.end };
  }
  const end = Math.min(length, Math.min(part.start + most, Math.max(part.start + least, to)));
  return { start: part.start, end };
}

/** What the editor's large waveform shows around a part: the part with room on both sides (half its length, at least a
 *  second), kept inside the sound; the whole sound when it is short. */
export function viewAround(part: { start: number; end: number }, length: number): { start: number; end: number } {
  const span = part.end - part.start;
  const room = Math.max(1, span * 0.5);
  if (span + 2 * room >= length) return { start: 0, end: length };
  let start = part.start - room, end = part.end + room;
  if (start < 0) { end -= start; start = 0; }
  if (end > length) { start -= end - length; end = length; }
  return { start: Math.max(0, start), end: Math.min(length, end) };
}

/** The ruler under a waveform from `start` to `end` seconds: a round step that gives at most `most` marks, and the marks. */
export function rulerTicks(start: number, end: number, most = 10): { step: number; ticks: number[] } {
  const steps = [0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300];
  const span = Math.max(1e-6, end - start);
  const step = steps.find((s) => span / s <= most) ?? steps[steps.length - 1];
  const ticks: number[] = [];
  for (let t = Math.ceil(start / step - 1e-9) * step; t <= end + 1e-9; t += step) ticks.push(Math.round(t * 1000) / 1000 + 0);
  return { step, ticks };
}
