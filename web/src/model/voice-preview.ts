import type { PageLayout } from "../types";
import { OpenAIVoiceConnection } from "./voice-openai";
import { ClaudeVoiceConnection } from "./voice-claude";

export type VoicePanel = { shape: { columns: number; rows: number }; layout: PageLayout; page: number };
export type VoicePhase = "idle" | "connecting" | "listening" | "thinking" | "speaking" | "transcribing" | "searching" | "preparing_speech";
export type VoiceSource = { url: string; title: string };
export type VoiceHooks = { phase(value: VoicePhase): void; reply(value: string): void; error(value: string): void; action(): void;
  sources?(value: VoiceSource[]): void; userSpeech?(active: boolean): void };

/** Audio transport contract. Shared UI and HA tools do not depend on vendor events. */
export interface VoiceConnection {
  start(): Promise<void>;
  stop(): Promise<void>;
  refreshContext(): Promise<void>;
}

/** Shared UI contract; provider adapters retain their respective audio paths. */
export class VoicePreview implements VoiceConnection {
  private connection: VoiceConnection;
  private phase: VoicePhase = "idle";
  private userSpeaking = false;
  private idleTimer?: ReturnType<typeof setTimeout>;

  constructor(panel: () => VoicePanel, hooks: VoiceHooks, provider = "openai", private idleSeconds = 5, externalReply = false) {
    if (!Number.isInteger(idleSeconds) || idleSeconds < 1 || idleSeconds > 300) this.idleSeconds = 5;
    const activityHooks: VoiceHooks = { ...hooks,
      phase: value => {
        this.phase = value;
        if (value === "idle" || value === "connecting") this.userSpeaking = false;
        this.updateIdleTimer(); hooks.phase(value);
      },
      userSpeech: active => {
        this.userSpeaking = active; this.updateIdleTimer(); hooks.userSpeech?.(active);
      },
    };
    if (provider === "openai") this.connection = new OpenAIVoiceConnection(panel, activityHooks, externalReply);
    else if (provider === "claude") this.connection = new ClaudeVoiceConnection(panel, activityHooks);
    else throw new Error("Unknown voice provider.");
  }

  private updateIdleTimer() {
    if (this.phase !== "listening" || this.userSpeaking) {
      clearTimeout(this.idleTimer); this.idleTimer = undefined;
    } else if (this.idleTimer === undefined) {
      this.idleTimer = setTimeout(() => { this.idleTimer = undefined; void this.stop(); }, this.idleSeconds * 1000);
    }
  }

  start() { return this.connection.start(); }
  stop() {
    clearTimeout(this.idleTimer); this.idleTimer = undefined;
    return this.connection.stop();
  }
  refreshContext() { return this.connection.refreshContext(); }
}
