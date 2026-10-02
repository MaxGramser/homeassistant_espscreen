import { api, send } from "../api";
import type { VoiceConnection, VoiceHooks, VoicePanel, VoicePhase } from "./voice-preview";
import { Utterance } from "./voice-utterance";
import workletUrl from "./voice-pcm-worklet.js?url&no-inline";
import { ReplyPlayback } from "./voice-output";

/** Claude uses HA speech around text turns. OpenAI's WebRTC transport stays separate. */
export class ClaudeVoiceConnection implements VoiceConnection {
  private generation = 0;
  private session = "";
  private context?: AudioContext;
  private microphone?: MediaStream;
  private node?: AudioWorkletNode;
  private input?: MediaStreamAudioSourceNode;
  private timer?: ReturnType<typeof setTimeout>;
  private progressTimer?: ReturnType<typeof setTimeout>;
  private turnTimer?: ReturnType<typeof setTimeout>;
  private tracking = false;
  private abort?: AbortController;
  private listening = false;
  private turn = 0;
  private utterance = new Utterance();
  private playback?: ReplyPlayback;

  constructor(private panel: () => VoicePanel, private hooks: VoiceHooks) {}

  async start() {
    await this.stop();
    const generation = ++this.generation;
    this.hooks.error(""); this.hooks.reply(""); this.hooks.sources?.([]); this.hooks.phase("connecting");
    this.abort = new AbortController();
    try {
      // Create/resume inside the user's click so playback is unlocked too.
      const context = new AudioContext({ sampleRate: 16000 });
      this.context = context;
      await context.resume();
      if (generation !== this.generation) return;
      if (context.sampleRate !== 16000) throw new Error("This browser cannot capture 16 kHz speech. Try Chrome.");
      const microphone = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1,
        echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
      if (generation !== this.generation) { microphone.getTracks().forEach(track => track.stop()); return; }
      this.microphone = microphone;
      microphone.getTracks().forEach(track => { track.onended = () => this.fail(generation, new Error("The microphone disconnected.")); });
      await context.audioWorklet.addModule(workletUrl);
      if (generation !== this.generation) return;
      this.input = context.createMediaStreamSource(microphone);
      this.node = new AudioWorkletNode(context, "voice-pcm");
      this.input.connect(this.node); this.node.connect(context.destination); // Worklet output is silence.
      const result = await send<{ id: string; max_seconds: number }>("voice-preview/claude/sessions", "POST",
        { context: this.panel() });
      if (generation !== this.generation) { await this.closeSession(result.id); return; }
      this.session = result.id; this.turn = 0;
      this.node.port.onmessage = event => {
        if (generation !== this.generation || !this.listening) return;
        const audio = this.utterance.push(event.data as Float32Array);
        this.hooks.userSpeech?.(this.utterance.speaking);
        if (audio) void this.speak(audio, generation);
      };
      this.timer = setTimeout(() => void this.stop(), Math.min(result.max_seconds, 600) * 1000);
      this.listen();
    } catch (error) { this.fail(generation, error); }
  }

  private listen() {
    this.utterance.reset(); this.listening = true;
    this.hooks.userSpeech?.(false); this.hooks.phase("listening");
  }

  private async speak(pcm: ArrayBuffer, generation: number) {
    this.listening = false; this.hooks.phase("transcribing"); this.hooks.error(""); this.hooks.reply(""); this.hooks.sources?.([]);
    const turn = ++this.turn;
    // Bound the browser wait as well as server work, including a lost proxy
    // connection. Stop closes the server session; a timeout never retries audio.
    this.turnTimer = setTimeout(() => this.fail(generation, new Error("The voice request timed out. Start voice to try again.")), 140000);
    try {
      await this.refreshContext();
      if (generation !== this.generation) return;
      const root = `voice-preview/claude/sessions/${this.session}/turns/${turn}`;
      this.tracking = true;
      this.trackProgress(root, generation, turn);
      const response = await api(root, { method: "POST", headers: { "Content-Type": "application/octet-stream" },
        body: pcm, signal: this.abort?.signal });
      const result = await response.json();
      if (generation !== this.generation) return;
      this.stopTracking();
      if (result.error) throw new Error(result.error);
      clearTimeout(this.turnTimer); this.turnTimer = undefined;
      this.hooks.reply(result.text); this.hooks.sources?.(result.sources || []);
      if (result.action) this.hooks.action();
      if (result.audio_error) this.hooks.error(result.audio_error);
      // Capture is already suspended during a turn. After starting music, do
      // not reopen it for the lyrics when the acknowledgement finishes.
      const finished = () => {
        if (generation !== this.generation) return;
        if (result.end_voice) void this.stop(); else this.listen();
      };
      if (result.reply) {
        this.playback = new ReplyPlayback();
        await this.playback.play(this.session, result.reply, this.context!, value => {
          if (generation === this.generation) this.hooks.phase(value);
        });
        finished();
      } else if (result.audio) {
        this.hooks.phase("preparing_speech");
        const audio = await (await api(root + "/audio", { signal: this.abort?.signal })).blob();
        if (generation !== this.generation) return;
        // Play through the already unlocked AudioContext, including on browsers
        // that refuse a new HTMLAudioElement after an asynchronous network turn.
        const buffer = await this.context!.decodeAudioData(await audio.arrayBuffer());
        if (generation !== this.generation) return;
        const source = this.context!.createBufferSource();
        source.buffer = buffer; source.connect(this.context!.destination);
        this.hooks.phase("speaking");
        source.onended = finished;
        source.start();
      } else finished();
    } catch (error) { this.fail(generation, error); }
    finally {
      if (generation === this.generation) { this.stopTracking(); clearTimeout(this.turnTimer); this.turnTimer = undefined; }
    }
  }

  private trackProgress(root: string, generation: number, turn: number) {
    this.progressTimer = setTimeout(async () => {
      if (!this.tracking || generation !== this.generation || turn !== this.turn) return;
      try {
        const response = await api(root + "/status", { signal: this.abort?.signal });
        const { phase } = await response.json();
        if (this.tracking && generation === this.generation && turn === this.turn &&
            ["transcribing", "thinking", "searching", "preparing_speech"].includes(phase)) {
          this.hooks.phase(phase as VoicePhase);
        }
      } catch { /* The main request reports failures; this is just progress. */ }
      if (this.tracking && generation === this.generation && turn === this.turn) this.trackProgress(root, generation, turn);
    }, 1000);
  }

  private stopTracking() { this.tracking = false; clearTimeout(this.progressTimer); this.progressTimer = undefined; }

  async refreshContext() {
    if (this.session) await send(`voice-preview/claude/sessions/${this.session}/context`, "PUT", this.panel(), { signal: this.abort?.signal });
  }

  private fail(generation: number, error: unknown) {
    if (generation !== this.generation) return;
    this.hooks.error(error instanceof Error ? error.message : String(error));
    void this.stop();
  }

  private async closeSession(id: string) {
    try { await send(`voice-preview/sessions/${id}`, "DELETE", undefined, { keepalive: true }); } catch { /* Server also expires sessions. */ }
  }

  async stop() {
    ++this.generation; this.listening = false; this.utterance.reset();
    clearTimeout(this.timer); this.timer = undefined;
    this.stopTracking(); clearTimeout(this.turnTimer); this.turnTimer = undefined;
    this.abort?.abort(); this.abort = undefined;
    this.playback?.stop(); this.playback = undefined;
    const session = this.session; this.session = "";
    this.node?.disconnect(); this.input?.disconnect(); this.node = undefined; this.input = undefined;
    this.microphone?.getTracks().forEach(track => { track.onended = null; track.stop(); }); this.microphone = undefined;
    const context = this.context; this.context = undefined;
    this.hooks.phase("idle");
    await Promise.all([context?.close().catch(() => {}), session ? this.closeSession(session) : undefined]);
  }
}
