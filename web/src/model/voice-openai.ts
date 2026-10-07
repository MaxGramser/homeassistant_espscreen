import { send } from "../api";
import type { VoicePanel, VoiceSource, VoiceHooks } from "./voice-preview";
import { ReplyPlayback, type ReplyAudio } from "./voice-output";
import workletUrl from "./voice-pcm-worklet.js?url&no-inline";

/** Browser audio adapter. The device canvas continues to be drawn only by LVGL. */
export class OpenAIVoiceConnection {
  private peer: RTCPeerConnection | null = null;
  private channel: Pick<RTCDataChannel, "readyState" | "send" | "close"> | null = null;
  private microphone: MediaStream | null = null;
  private speaker: HTMLAudioElement | null = null;
  private session = "";
  private generation = 0;
  private contextGeneration = 0;
  private timer?: ReturnType<typeof setTimeout>;
  private connectTimeout?: ReturnType<typeof setTimeout>;
  private poll?: ReturnType<typeof setInterval>;
  private seen = new Set<string>();
  private working = Promise.resolve();
  private text = "";
  private turn = 0;
  private sources: VoiceSource[] = [];
  private userSpeaking = false;
  private playing = false;
  private responses = new Set<string>();
  private pendingTools = 0;
  private inputMuted = false;
  private endAfterReply = false;
  private finalReply: { id: string; audio: boolean } | null = null;
  private endedAudio = new Set<string>();
  private finishTimeout?: ReturnType<typeof setTimeout>;
  private context?: AudioContext;
  private input?: MediaStreamAudioSourceNode;
  private node?: AudioWorkletNode;
  private playback?: ReplyPlayback;
  private replyBusy = false;
  private allowInterruption = false;

  constructor(private panel: () => VoicePanel, private hooks: VoiceHooks, private externalReply = false) {}

  private emit(event: unknown) {
    if (this.channel?.readyState === "open") this.channel.send(JSON.stringify(event));
  }

  async start() {
    await this.stop();
    const generation = ++this.generation;
    this.sources = []; this.hooks.sources?.([]);
    this.hooks.error(""); this.hooks.reply(""); this.hooks.phase("connecting");
    try {
      if (this.externalReply) { await this.startRelay(generation); return; }
      if (!navigator.mediaDevices?.getUserMedia) throw new Error("Microphone access requires HTTPS or localhost.");
      const microphone = await navigator.mediaDevices.getUserMedia({ audio: {
        echoCancellation: true, noiseSuppression: true, autoGainControl: true,
      } });
      if (generation !== this.generation) { microphone.getTracks().forEach(track => track.stop()); return; }
      this.microphone = microphone;
      this.allowInterruption = microphone.getTracks().every(track => track.getSettings?.().echoCancellation === true);
      const peer = this.peer = new RTCPeerConnection();
      const speaker = this.speaker = new Audio();
      speaker.autoplay = true;
      peer.ontrack = event => {
        if (generation !== this.generation) return;
        speaker.srcObject = event.streams[0] ?? new MediaStream([event.track]);
        void speaker.play().catch(() => this.fail("The browser blocked spoken replies. Allow audio and restart voice.", generation));
      };
      peer.onconnectionstatechange = () => {
        if (["failed", "disconnected"].includes(peer.connectionState)) void this.fail("Voice connection lost. Start again.", generation);
      };
      microphone.getTracks().forEach(track => peer.addTrack(track, microphone));
      const channel = this.channel = peer.createDataChannel("oai-events");
      channel.onopen = () => { if (generation === this.generation) { this.hooks.phase("listening"); void this.refreshContext(); } };
      channel.onclose = () => { if (generation === this.generation) void this.fail("Voice session ended.", generation); };
      channel.onmessage = event => {
        if (generation !== this.generation) return;
        try { this.event(JSON.parse(event.data), generation); }
        catch { void this.fail("Invalid voice response. Start again.", generation); }
      };
      const offer = await peer.createOffer();
      await peer.setLocalDescription(offer);
      if (generation !== this.generation) return;
      const response = await send<{ id: string; sdp: string; max_seconds: number }>("voice-preview/sessions", "POST", {
        sdp: offer.sdp, context: this.panel(),
      });
      if (generation !== this.generation) {
        await send(`voice-preview/sessions/${encodeURIComponent(response.id)}`, "DELETE"); return;
      }
      this.session = response.id;
      this.timer = setTimeout(() => void this.stop(), response.max_seconds * 1000);
      // Also covers a stalled ICE negotiation, without leaving the microphone open.
      this.connectTimeout = setTimeout(() => {
        if (channel.readyState !== "open") void this.fail("Audio connection timed out. Start again.", generation);
      }, 20000);
      channel.addEventListener("open", () => clearTimeout(this.connectTimeout), { once: true });
      await peer.setRemoteDescription({ type: "answer", sdp: response.sdp });
      if (generation !== this.generation) return;
      this.poll = setInterval(() => void this.refreshContext(), 20000);
    } catch (error) {
      await this.fail(error instanceof Error ? error.message : "Voice could not start.", generation);
    }
  }

  private async startRelay(generation: number) {
    const context = this.context = new AudioContext({ sampleRate: 24000 });
    await context.resume();
    if (generation !== this.generation) return;
    if (context.sampleRate !== 24000) throw new Error("This browser cannot capture 24 kHz speech. Try Chrome.");
    const microphone = await navigator.mediaDevices.getUserMedia({ audio: {
      channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true,
    } });
    if (generation !== this.generation) { microphone.getTracks().forEach(track => track.stop()); return; }
    this.microphone = microphone;
    microphone.getTracks().forEach(track => { track.onended = () => void this.fail("The microphone disconnected.", generation); });
    await context.audioWorklet.addModule(workletUrl);
    if (generation !== this.generation) return;
    const result = await send<{ id: string; max_seconds: number }>("voice-preview/openai/sessions", "POST", { context: this.panel() });
    if (generation !== this.generation) {
      await send(`voice-preview/sessions/${encodeURIComponent(result.id)}`, "DELETE"); return;
    }
    this.session = result.id;
    this.timer = setTimeout(() => void this.stop(), Math.min(result.max_seconds, 600) * 1000);
    const url = new URL(`api/voice-preview/sessions/${encodeURIComponent(result.id)}/stream`, document.baseURI);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(url);
    this.channel = { get readyState() { return socket.readyState === WebSocket.OPEN ? "open" : "closed"; },
      send: data => socket.send(data), close: () => socket.close() };
    this.connectTimeout = setTimeout(() => void this.fail("Audio connection timed out. Start again.", generation), 20000);
    socket.onclose = () => { if (generation === this.generation) void this.fail("Voice connection ended. Start again.", generation); };
    socket.onerror = () => void this.fail("Voice connection failed. Start again.", generation);
    socket.onmessage = message => {
      if (generation !== this.generation) return;
      try {
        const event = JSON.parse(message.data);
        if (event.type === "relay.ready") {
          clearTimeout(this.connectTimeout);
          this.hooks.phase("listening"); void this.refreshContext();
          this.poll = setInterval(() => void this.refreshContext(), 20000);
        } else this.event(event, generation);
      } catch { void this.fail("Invalid voice response. Start again.", generation); }
    };
    this.input = context.createMediaStreamSource(microphone);
    this.node = new AudioWorkletNode(context, "voice-pcm");
    this.input.connect(this.node); this.node.connect(context.destination);
    this.node.port.onmessage = event => {
      if (generation !== this.generation || this.inputMuted || socket.readyState !== WebSocket.OPEN) return;
      if (socket.bufferedAmount > 96000) { void this.fail("The audio connection is too slow. Start again.", generation); return; }
      const samples = event.data as Float32Array;
      const pcm = new DataView(new ArrayBuffer(samples.length * 2));
      samples.forEach((value, index) => pcm.setInt16(index * 2, Math.round(Math.max(-1, Math.min(1, value)) * 32767), true));
      socket.send(pcm.buffer);
    };
  }

  private async playReply(reply: ReplyAudio, responseId: string, generation: number) {
    if (!this.externalReply || this.replyBusy) { void this.fail("Unexpected reply audio.", generation); return; }
    this.replyBusy = true; this.muteInput(true); this.updatePhase();
    this.playback = new ReplyPlayback();
    try {
      await this.playback.play(this.session, reply, this.context!, value => {
        if (generation === this.generation) { this.playing = value === "speaking"; this.updatePhase(); }
      });
      if (generation !== this.generation) return;
      this.replyBusy = this.playing = false;
      this.endedAudio.add(responseId);
      if (!this.endAfterReply) this.muteInput(false);
      this.updatePhase();
    } catch (error) {
      await this.fail(error instanceof Error ? error.message : "Reply playback failed.", generation);
    }
  }

  private event(event: Record<string, any>, generation: number) {
    switch (event.type) {
      case "input_audio_buffer.speech_started":
        if (this.inputMuted) break;
        ++this.turn;
        this.userSpeaking = true; this.hooks.userSpeech?.(true);
        this.sources = []; this.hooks.sources?.([]);
        this.text = ""; this.hooks.reply(""); this.hooks.phase("listening"); break;
      case "input_audio_buffer.speech_stopped":
        if (this.inputMuted) break;
        this.userSpeaking = false; this.responses.add("requested");
        this.hooks.phase("thinking"); this.hooks.userSpeech?.(false); break;
      case "output_audio_buffer.started":
        if (!this.allowInterruption) this.muteInput(true);
        this.playing = true; this.updatePhase(); break;
      case "output_audio_buffer.stopped":
      case "output_audio_buffer.cleared":
        this.endedAudio.add(event.response_id ?? "current");
        if (!this.externalReply && !this.endAfterReply && !this.allowInterruption) this.muteInput(false);
        this.playing = false; this.updatePhase(); break;
      case "response.created":
        if (this.externalReply) this.muteInput(true);
        this.responses.delete("requested"); this.responses.add(event.response?.id ?? "current");
        this.text = ""; this.hooks.reply(""); this.updatePhase(); break;
      case "response.output_audio_transcript.delta":
        this.text += event.delta ?? ""; this.hooks.reply(this.text); break;
      case "error": void this.fail("OpenAI reported a voice error. Check the connection and restart.", generation); break;
      case "reply.ready": void this.playReply(event.reply, event.response_id, generation); break;
      case "response.done": {
        this.responses.delete(event.response?.id ?? "current");
        const calls = (event.response?.output ?? []).filter((item: any) => item.type === "function_call");
        if (event.response?.status === "failed") { void this.fail("The voice response failed. Start again.", generation); break; }
        if (!calls.length) {
          if (this.endAfterReply) this.finalReply = {
            id: event.response?.id ?? "current",
            audio: (event.response?.output ?? []).some((item: any) =>
              item.content?.some((part: any) => ["audio", "output_audio"].includes(part.type))),
          };
          if (this.externalReply && !this.replyBusy && !this.endAfterReply) this.muteInput(false);
          this.updatePhase(); break;
        }
        ++this.pendingTools; this.updatePhase();
        const turn = this.turn;
        this.working = this.working.then(async () => {
          let answered = false;
          let waiting = true;
          let complete = calls.length === 1;
          for (const call of calls) {
            if (generation !== this.generation) return;
            if (this.seen.has(call.call_id)) continue;
            this.seen.add(call.call_id);
            const args = JSON.parse(call.arguments);
            // Stop transmitting before HA can start external speakers. Browser
            // echo cancellation has no reference audio for Sonos playback.
            const startsMusic = ["play_music", "play_named_track"].includes(call.name) ||
              (call.name === "control_media" && ["play", "next", "previous"].includes(args.action));
            if (startsMusic) this.muteInput(true);
            const result = await send<{ status?: string; sources?: VoiceSource[]; end_voice?: boolean; end_voice_immediately?: boolean; wait_for_user?: boolean; complete_request?: boolean }>(`voice-preview/sessions/${encodeURIComponent(this.session)}/tools`, "POST", {
              call_id: call.call_id, name: call.name, arguments: args, context: this.panel(),
            });
            if (generation !== this.generation) return;
            if (result.end_voice_immediately === true) { await this.stop(); return; }
            waiting &&= call.name === "wait_for_user" && result.wait_for_user === true;
            complete &&= result.status === "accepted" && result.complete_request === true;
            if (result.end_voice === true) {
              this.muteInput(true); this.endAfterReply = true;
              // Bound a missing acknowledgement while the idle timer is paused.
              this.finishTimeout ??= setTimeout(() => void this.stop(), 30000);
            } else if (startsMusic && !this.endAfterReply && !this.externalReply) this.muteInput(false);
            this.emit({ type: "conversation.item.create", item: { type: "function_call_output", call_id: call.call_id, output: JSON.stringify(result) } });
            if (call.name === "lookup_current_information" && result.status === "ok" && turn === this.turn) {
              this.sources = [...new Map([...this.sources, ...(result.sources ?? [])].map(source => [source.url, source])).values()];
              this.hooks.sources?.(this.sources);
            }
            if (["control_switch", "control_media", "set_light_brightness", "play_music", "play_named_track"].includes(call.name) && result.status === "accepted") this.hooks.action();
            answered = true;
          }
          if (answered && turn === this.turn) {
            if (complete && this.endAfterReply) {
              await this.stop();
            } else if ((complete || waiting) && !this.endAfterReply) {
              // Keep the tool receipt in history, but don't request an AI
              // acknowledgement of a completed command or silent activation.
              this.muteInput(false);
            } else {
              this.responses.add("requested"); this.emit({ type: "response.create" });
            }
          }
        }).catch(() => this.fail("The voice action could not be confirmed. Check Home Assistant before retrying.", generation))
          .finally(() => { if (generation === this.generation) { --this.pendingTools; this.updatePhase(); } });
        break;
      }
    }
  }

  private updatePhase() {
    // response.done ends generation, not playback. Wait for the final reply's
    // own WebRTC audio buffer, not a previous spoken preamble, to finish.
    if (this.finalReply && !this.responses.size && !this.pendingTools && !this.playing && !this.replyBusy &&
        (!this.finalReply.audio || this.endedAudio.has(this.finalReply.id))) {
      void this.stop(); return;
    }
    this.hooks.phase(this.userSpeaking ? "listening" : this.playing ? "speaking" : this.replyBusy ? "preparing_speech"
      : this.responses.size || this.pendingTools || this.endAfterReply ? "thinking" : "listening");
  }

  private muteInput(muted: boolean) {
    if (this.inputMuted === muted) return;
    this.inputMuted = muted;
    this.microphone?.getTracks().forEach(track => { track.enabled = !muted; });
    // Disable automatic turns as well, so already buffered music cannot
    // interrupt the acknowledgement while the muted stream reaches the server.
    this.emit({ type: "session.update", session: { type: "realtime", audio: { input: {
      turn_detection: muted ? null : { type: "semantic_vad" },
    } } } });
    this.emit({ type: "input_audio_buffer.clear" });
    this.userSpeaking = false; this.hooks.userSpeech?.(false);
  }

  async refreshContext() {
    if (!this.session || this.channel?.readyState !== "open") return;
    const generation = this.generation, revision = ++this.contextGeneration;
    try {
      const result = await send<{ instructions: string }>("voice-preview/context", "POST", this.panel());
      if (generation === this.generation && revision === this.contextGeneration)
        this.emit({ type: "session.update", session: { type: "realtime", instructions: result.instructions } });
    } catch {
      await this.fail("Panel context is unavailable. Restart voice once Home Assistant reconnects.", generation);
    }
  }

  private async fail(message: string, generation: number) {
    if (generation !== this.generation) return;
    const stopping = this.stop(), stoppedGeneration = this.generation;
    await stopping;
    if (this.generation === stoppedGeneration) this.hooks.error(message);
  }

  async stop() {
    ++this.generation; ++this.contextGeneration;
    clearTimeout(this.timer); clearTimeout(this.connectTimeout); clearTimeout(this.finishTimeout); clearInterval(this.poll);
    this.finishTimeout = undefined;
    this.channel?.close(); this.channel = null;
    this.peer?.close(); this.peer = null;
    this.microphone?.getTracks().forEach(track => { track.onended = null; track.stop(); }); this.microphone = null;
    this.playback?.stop(); this.playback = undefined;
    this.node?.disconnect(); this.input?.disconnect(); this.node = undefined; this.input = undefined;
    const context = this.context; this.context = undefined;
    if (context) void context.close().catch(() => {});
    if (this.speaker) { this.speaker.pause(); this.speaker.srcObject = null; this.speaker = null; }
    const session = this.session; this.session = "";
    this.seen.clear(); this.working = Promise.resolve();
    this.responses.clear(); this.pendingTools = 0; this.playing = this.userSpeaking = false;
    this.inputMuted = this.endAfterReply = false; this.finalReply = null; this.endedAudio.clear();
    this.replyBusy = false;
    this.allowInterruption = false;
    this.hooks.phase("idle");
    if (session) {
      try { await send(`voice-preview/sessions/${encodeURIComponent(session)}`, "DELETE", undefined, { keepalive: true }); }
      catch { /* The media tracks are closed; the server's lifetime limit also expires the call. */ }
    }
  }
}
