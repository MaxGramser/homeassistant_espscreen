import { api, send } from "../api";
import type { VoicePhase } from "./voice-preview";

export type ReplyAudio = { id: string; output: "local" | "sonos"; state: string; error?: string };

/** Both providers use the same delivery lifecycle for prepared replies. */
export class ReplyPlayback {
  private abort = new AbortController();
  private source?: AudioBufferSourceNode;
  private wake?: () => void;
  private timer?: ReturnType<typeof setTimeout>;

  async play(session: string, reply: ReplyAudio, context: AudioContext, phase: (value: VoicePhase) => void) {
    this.timer = setTimeout(() => this.stop(new Error("The reply speaker did not finish in time. Voice has stopped.")), 105000);
    try { await this.deliver(session, reply, context, phase); }
    finally { clearTimeout(this.timer); this.timer = undefined; }
  }

  private async deliver(session: string, reply: ReplyAudio, context: AudioContext, phase: (value: VoicePhase) => void) {
    const root = `voice-preview/sessions/${encodeURIComponent(session)}/replies/${encodeURIComponent(reply.id)}`;
    const signal = this.abort.signal;
    phase("preparing_speech");
    if (reply.output === "local") {
      const audio = await (await api(root + "/audio", { signal })).arrayBuffer();
      const buffer = await context.decodeAudioData(audio);
      signal.throwIfAborted();
      const source = this.source = context.createBufferSource();
      source.buffer = buffer; source.connect(context.destination);
      phase("speaking");
      await new Promise<void>(resolve => { this.wake = resolve; source.onended = () => resolve(); source.start(); });
      signal.throwIfAborted();
      source.onended = null; source.disconnect();
      this.wake = undefined; this.source = undefined;
      return;
    }
    if (reply.output !== "sonos") throw new Error("Unknown reply output.");
    // POST is idempotent on the server. A lost response is not retried here.
    let status = await send<ReplyAudio>(root, "POST", undefined, { signal });
    const deadline = Date.now() + 105000;
    while (status.state !== "done") {
      signal.throwIfAborted();
      if (["error", "cancelled"].includes(status.state)) throw new Error(status.error || "Reply playback ended.");
      if (Date.now() >= deadline) throw new Error("The reply speaker did not finish in time. Voice has stopped.");
      phase(status.state === "speaking" ? "speaking" : "preparing_speech");
      await new Promise<void>(resolve => {
        const timer = setTimeout(() => { this.wake = undefined; resolve(); }, 400);
        this.wake = () => { clearTimeout(timer); resolve(); };
      });
      signal.throwIfAborted();
      status = await (await api(root, { signal })).json();
    }
  }

  stop(error?: Error) {
    clearTimeout(this.timer); this.timer = undefined;
    this.abort.abort(error);
    this.wake?.(); this.wake = undefined;
    if (this.source) { this.source.onended = null; this.source.stop(); this.source.disconnect(); this.source = undefined; }
  }
}
