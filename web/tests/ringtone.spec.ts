// A ringtone of one's own (model/ringtone.ts, docs/CALLS.md "Ringtone"): the bass out, the cut, the fades, the level,
// the WAV the add-on takes (ringtones.checked, tests/test_ringtones.py) and the part a hand moves on the waveform.
import { describe, expect, it } from "vitest";
import { cut, fade, firstPart, highPass, level, movePart, peaks, ringtone, rulerTicks, viewAround, wav } from "../src/model/ringtone";

const RATE = 16000;
const tone = (hz: number, seconds: number, amplitude = 0.5) =>
  Float32Array.from({ length: Math.round(seconds * RATE) }, (_, i) => amplitude * Math.sin((2 * Math.PI * hz * i) / RATE));
const loudest = (s: Float32Array, from = 0, to = s.length) => { let m = 0; for (let i = from; i < to; i++) m = Math.max(m, Math.abs(s[i])); return m; };

describe("ringtone", () => {
  it("takes the bass out and keeps what the speakers carry", () => {
    expect(loudest(highPass(tone(100, 1), RATE), 4000)).toBeLessThan(0.01);
    expect(loudest(highPass(tone(1600, 1), RATE), 4000)).toBeGreaterThan(0.48);
  });

  it("cuts, fades to silence at both ends and levels to the top", () => {
    const made = ringtone(tone(1600, 5), RATE, 1, 3);
    expect(made.length).toBe(2 * RATE);
    expect(Math.abs(made[0])).toBe(0);
    expect(Math.abs(made[made.length - 1])).toBeLessThan(0.01);
    expect(loudest(made)).toBeCloseTo(0.5, 3);
    expect(cut(tone(1600, 1), RATE, -1, 9).length).toBe(RATE);
    expect(fade(new Float32Array([1, 1]), RATE).length).toBe(2);
    expect(Array.from(level(new Float32Array(4)))).toEqual([0, 0, 0, 0]);
  });

  it("writes the WAV the add-on takes: 16 kHz, mono, 16 bits", () => {
    const bytes = wav(new Float32Array([0, 1, -1, 2]), RATE);
    const view = new DataView(bytes.buffer);
    expect(new TextDecoder().decode(bytes.slice(0, 4))).toBe("RIFF");
    expect([view.getUint16(22, true), view.getUint32(24, true), view.getUint16(34, true), view.getUint32(40, true)]).toEqual([1, RATE, 16, 8]);
    expect([view.getInt16(44, true), view.getInt16(46, true), view.getInt16(48, true), view.getInt16(50, true)]).toEqual([0, 32767, -32767, 32767]);
    expect(bytes.length).toBe(52);
  });

  it("draws the waveform as the loudest of each stretch", () => {
    expect(peaks(new Float32Array([0, 0.5, -1, 0.25]), 2)).toEqual([0.5, 1]);
    expect(peaks(new Float32Array(), 10)).toEqual([]);
  });

  it("offers the part from the first sound, as long as allowed", () => {
    const sound = new Float32Array(10 * RATE);
    sound.set(tone(1600, 4), 2 * RATE);
    const part = firstPart(sound, RATE, 3);
    expect(part.start).toBeCloseTo(1.99, 2);
    expect(part.end - part.start).toBeCloseTo(3, 5);
    // A sound shorter than allowed is taken whole.
    expect(firstPart(tone(1600, 1.5), RATE, 3)).toEqual({ start: 0, end: 1.5 });
  });

  it("keeps a moved part inside the sound and between its limits", () => {
    const part = { start: 1, end: 3 };
    expect(movePart(part, "whole", 9, 10, 0.25, 3)).toEqual({ start: 8, end: 10 });
    expect(movePart(part, "whole", -2, 10, 0.25, 3)).toEqual({ start: 0, end: 2 });
    expect(movePart(part, "start", -5, 10, 0.25, 3)).toEqual({ start: 0, end: 3 });
    expect(movePart({ start: 4, end: 6 }, "start", 1, 10, 0.25, 3)).toEqual({ start: 3, end: 6 });
    expect(movePart(part, "start", 2.9, 10, 0.25, 3)).toEqual({ start: 2.75, end: 3 });
    expect(movePart(part, "end", 9, 10, 0.25, 3)).toEqual({ start: 1, end: 4 });
    expect(movePart(part, "end", 0, 10, 0.25, 3)).toEqual({ start: 1, end: 1.25 });
  });

  it("shows a part with room around it, inside the sound", () => {
    expect(viewAround({ start: 10, end: 13 }, 60)).toEqual({ start: 8.5, end: 14.5 });
    expect(viewAround({ start: 0.2, end: 1 }, 60)).toEqual({ start: 0, end: 2.8 });
    expect(viewAround({ start: 58, end: 60 }, 60)).toEqual({ start: 56, end: 60 });
    expect(viewAround({ start: 0, end: 1.5 }, 3)).toEqual({ start: 0, end: 3 });
  });

  it("marks the ruler at a round step", () => {
    expect(rulerTicks(8.5, 14.5)).toEqual({ step: 1, ticks: [9, 10, 11, 12, 13, 14] });
    expect(rulerTicks(0, 2.8).step).toBe(0.5);
    expect(rulerTicks(0, 180).ticks.slice(0, 3)).toEqual([0, 30, 60]);
  });
});
