/** Bounded 16 kHz capture: short pre-roll, silence endpoint, explicit little-endian PCM. */
export class Utterance {
  private frames: Float32Array[] = [];
  private active = false;
  private voiced = 0;
  private silence = 0;
  private samples = 0;

  get speaking() { return this.active; }

  push(frame: Float32Array): ArrayBuffer | null {
    let energy = 0;
    for (const value of frame) energy += value * value;
    const speaking = Math.sqrt(energy / frame.length) >= 0.008;
    this.frames.push(frame);
    this.samples += frame.length;
    if (speaking) { this.active = true; this.voiced += frame.length; this.silence = 0; }
    else this.silence += frame.length;
    if (!this.active) {
      while (this.samples > 4800) this.samples -= this.frames.shift()!.length;
      return null;
    }
    if (this.silence < 14400 && this.samples < 480000) return null;
    let output: ArrayBuffer | null = null;
    if (this.voiced >= 3200) {
      output = new ArrayBuffer(this.samples * 2);
      const data = new DataView(output);
      let offset = 0;
      for (const chunk of this.frames) for (const value of chunk) {
        const sample = Math.max(-1, Math.min(1, value));
        data.setInt16(offset, Math.round(sample * (sample < 0 ? 32768 : 32767)), true);
        offset += 2;
      }
    }
    this.reset();
    return output;
  }

  reset() { this.frames = []; this.active = false; this.voiced = this.silence = this.samples = 0; }
}
