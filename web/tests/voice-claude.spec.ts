import { flushPromises } from "@vue/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api, send } from "../src/api";
import { ClaudeVoiceConnection } from "../src/model/voice-claude";
import { Utterance } from "../src/model/voice-utterance";
import type { VoiceHooks, VoicePanel } from "../src/model/voice-preview";
import { VoicePreview } from "../src/model/voice-preview";

vi.mock("../src/api", () => ({ api: vi.fn(), send: vi.fn() }));
let node: { port: { onmessage?: (event: { data: Float32Array }) => void } };
let source: { onended?: () => void; buffer?: unknown; start: ReturnType<typeof vi.fn>; connect: ReturnType<typeof vi.fn> };
let close: ReturnType<typeof vi.fn>, stop: ReturnType<typeof vi.fn>, hooks: VoiceHooks, voice: ClaudeVoiceConnection;
const panel = { shape: { columns: 2, rows: 3 }, page: 0, layout: {} } as VoicePanel;

beforeEach(() => {
  vi.clearAllMocks(); vi.useFakeTimers();
  close = vi.fn().mockResolvedValue(undefined); stop = vi.fn();
  source = { start: vi.fn(), connect: vi.fn() };
  vi.stubGlobal("AudioContext", class {
    sampleRate = 16000; destination = {};
    resume = vi.fn().mockResolvedValue(undefined); close = close;
    audioWorklet = { addModule: vi.fn().mockResolvedValue(undefined) };
    createMediaStreamSource = () => ({ connect: vi.fn(), disconnect: vi.fn() });
    decodeAudioData = vi.fn().mockResolvedValue({}); createBufferSource = () => source;
  });
  vi.stubGlobal("AudioWorkletNode", class {
    port = {}; connect = vi.fn(); disconnect = vi.fn();
    constructor() { node = this; }
  });
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] }) } });
  vi.mocked(send).mockImplementation(async path => path === "voice-preview/claude/sessions" ? { id: "claude-session", max_seconds: 600 } : {});
  vi.mocked(api).mockImplementation(async path => path.endsWith("/audio")
    ? { blob: async () => ({ arrayBuffer: async () => new ArrayBuffer(10) }) } as Response
    : { json: async () => ({ text: "Aan.", sources: [], action: true, audio: true }) } as Response);
  hooks = { phase: vi.fn(), reply: vi.fn(), error: vi.fn(), action: vi.fn(), sources: vi.fn() };
  voice = new ClaudeVoiceConnection(() => panel, hooks);
});
afterEach(async () => { await voice.stop(); vi.useRealTimers(); vi.unstubAllGlobals(); });

function utterance() {
  for (let i = 0; i < 8; i++) node.port.onmessage?.({ data: new Float32Array(800).fill(0.1) });
  for (let i = 0; i < 18; i++) node.port.onmessage?.({ data: new Float32Array(800) });
}

it("sends bounded PCM through HA/Claude and resumes capture only after the spoken reply", async () => {
  await voice.start();
  expect(hooks.phase).toHaveBeenLastCalledWith("listening");
  utterance(); await flushPromises();
  expect(send).toHaveBeenCalledWith("voice-preview/claude/sessions/claude-session/context", "PUT", panel, expect.any(Object));
  const upload = vi.mocked(api).mock.calls[0];
  expect(upload[0]).toBe("voice-preview/claude/sessions/claude-session/turns/1");
  expect(upload[1]?.body).toBeInstanceOf(ArrayBuffer);
  expect(source.start).toHaveBeenCalledOnce();
  expect(hooks.phase).toHaveBeenLastCalledWith("speaking");
  expect(hooks.action).toHaveBeenCalledOnce();
  utterance(); await flushPromises();
  expect(api).toHaveBeenCalledTimes(2);
  source.onended?.();
  expect(hooks.phase).toHaveBeenLastCalledWith("listening");
  expect(vi.mocked(send).mock.calls.some(([path]) => path === "voice-preview/sessions")).toBe(false);
  await voice.stop(); expect(stop).toHaveBeenCalledOnce(); expect(close).toHaveBeenCalledOnce();
});

it("discards a late answer after Stop and closes the server session", async () => {
  let finish!: (value: Response) => void;
  vi.mocked(api).mockReturnValue(new Promise(resolve => { finish = resolve; }));
  await voice.start(); utterance(); await flushPromises();
  await voice.stop();
  finish({ json: async () => ({ text: "Late.", action: true, audio: true }) } as Response);
  await flushPromises();
  expect(hooks.reply).not.toHaveBeenCalledWith("Late."); expect(hooks.action).not.toHaveBeenCalled();
  expect(send).toHaveBeenCalledWith("voice-preview/sessions/claude-session", "DELETE", undefined, { keepalive: true });
  expect(hooks.phase).toHaveBeenLastCalledWith("idle");
});

it.each([false, true])("closes after starting music without capturing lyrics (spoken acknowledgement: %s)", async audio => {
  const normal = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation((path, ...args) => path.endsWith("/audio") ? normal(path, ...args)
    : Promise.resolve({ json: async () => ({ text: "Playing.", action: true, audio, end_voice: true }) } as Response));
  await voice.start(); utterance(); await flushPromises();
  if (audio) {
    expect(stop).not.toHaveBeenCalled();
    expect(hooks.phase).toHaveBeenLastCalledWith("speaking");
    utterance(); await flushPromises();
    source.onended?.();
  }
  await flushPromises();
  const calls = vi.mocked(api).mock.calls.length;
  utterance(); await flushPromises();
  expect(api).toHaveBeenCalledTimes(calls);
  expect(vi.mocked(api).mock.calls.filter(([path]) => path.endsWith("/turns/1"))).toHaveLength(1);
  expect(stop).toHaveBeenCalledOnce();
  expect(hooks.phase).toHaveBeenLastCalledWith("idle");
  expect(send).toHaveBeenCalledWith("voice-preview/sessions/claude-session", "DELETE", undefined, { keepalive: true });
});

it("pauses Claude input through external playback, then applies a fresh silence timeout", async () => {
  const shared = new VoicePreview(() => panel, hooks, "claude", 1);
  let state = "preparing_speech";
  const normal = vi.mocked(send).getMockImplementation()!;
  vi.mocked(send).mockImplementation((path, ...args) => path.endsWith('/replies/reply-1')
    ? Promise.resolve({ state }) : normal(path, ...args));
  vi.mocked(api).mockImplementation(async path => ({ json: async () => path.includes('/replies/') ? { state }
    : { text: 'Answer.', audio: true, reply: { id: 'reply-1', output: 'sonos', state: 'ready' } } }) as Response);
  try {
    await shared.start(); utterance(); await flushPromises();
    await vi.advanceTimersByTimeAsync(3200);
    expect(stop).not.toHaveBeenCalled();
    state = "speaking"; await vi.advanceTimersByTimeAsync(400);
    expect(hooks.phase).toHaveBeenLastCalledWith('speaking');
    utterance(); await flushPromises();
    expect(vi.mocked(api).mock.calls.filter(([path]) => path.includes('/turns/'))).toHaveLength(1);
    state = "done"; await vi.advanceTimersByTimeAsync(400);
    expect(hooks.phase).toHaveBeenLastCalledWith('listening');
    expect(source.start).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(999);
    expect(stop).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(stop).toHaveBeenCalledOnce();
  } finally { await shared.stop(); }
});

it("closes the microphone if session setup fails", async () => {
  vi.mocked(send).mockRejectedValue(new Error("STT unavailable"));
  await voice.start(); await flushPromises();
  expect(stop).toHaveBeenCalledOnce(); expect(close).toHaveBeenCalledOnce();
  expect(hooks.error).toHaveBeenCalledWith("STT unavailable");
});

it("shows server stages and ignores a late progress response after the answer", async () => {
  let finish!: (value: Response) => void, progress!: (value: Response) => void;
  vi.mocked(api).mockImplementation(path => path.endsWith('/status')
    ? new Promise(resolve => { progress = resolve; }) : new Promise(resolve => { finish = resolve; }));
  await voice.start(); utterance(); await flushPromises();
  expect(hooks.phase).toHaveBeenLastCalledWith('transcribing');
  await vi.advanceTimersByTimeAsync(1000);
  progress({ json: async () => ({ phase: 'searching' }) } as Response); await flushPromises();
  expect(hooks.phase).toHaveBeenLastCalledWith('searching');
  await vi.advanceTimersByTimeAsync(1000);
  finish({ json: async () => ({ text: 'Cloudy.', sources: [], action: false, audio: false }) } as Response);
  await flushPromises();
  expect(hooks.phase).toHaveBeenLastCalledWith('listening');
  progress({ json: async () => ({ phase: 'searching' }) } as Response); await flushPromises();
  expect(hooks.phase).toHaveBeenLastCalledWith('listening');
  expect(api).toHaveBeenCalledTimes(3);
});

it("ends a stalled HTTP turn and stops capture instead of thinking indefinitely", async () => {
  vi.mocked(api).mockImplementation(path => path.endsWith('/status')
    ? Promise.resolve({ json: async () => ({ phase: 'transcribing' }) } as Response) : new Promise(() => {}));
  await voice.start(); utterance(); await flushPromises();
  await vi.advanceTimersByTimeAsync(140000); await flushPromises();
  expect(hooks.error).toHaveBeenCalledWith(expect.stringContaining('timed out'));
  expect(hooks.phase).toHaveBeenLastCalledWith('idle');
  expect(stop).toHaveBeenCalledOnce();
  expect(send).toHaveBeenCalledWith('voice-preview/sessions/claude-session', 'DELETE', undefined, { keepalive: true });
  const calls = vi.mocked(api).mock.calls.length;
  await vi.advanceTimersByTimeAsync(5000);
  expect(api).toHaveBeenCalledTimes(calls);
  expect(vi.mocked(api).mock.calls.filter(([path]) => !path.endsWith('/status'))).toHaveLength(1);
});

it("releases microphone permission granted after Stop", async () => {
  let grant!: (value: MediaStream) => void;
  vi.mocked(navigator.mediaDevices.getUserMedia).mockReturnValue(new Promise(resolve => { grant = resolve; }));
  const pending = voice.start(); await flushPromises(); await voice.stop();
  grant({ getTracks: () => [{ stop }] } as unknown as MediaStream); await pending;
  expect(stop).toHaveBeenCalledOnce(); expect(send).not.toHaveBeenCalled();
});

it("closes a session returned after Stop rather than leaking a server slot", async () => {
  let finish!: (value: unknown) => void;
  vi.mocked(send).mockImplementation(async path => path === "voice-preview/claude/sessions"
    ? new Promise(resolve => { finish = resolve; }) : {});
  const pending = voice.start(); await flushPromises(); await voice.stop();
  finish({ id: "late", max_seconds: 600 }); await pending;
  expect(send).toHaveBeenCalledWith("voice-preview/sessions/late", "DELETE", undefined, { keepalive: true });
});

it("bounds silence and utterances and encodes little-endian samples", () => {
  const capture = new Utterance();
  for (let i = 0; i < 1000; i++) expect(capture.push(new Float32Array(800))).toBeNull();
  let output: ArrayBuffer | null = null;
  for (let i = 0; i < 600 && !output; i++) output = capture.push(new Float32Array(800).fill(0.5));
  expect(output!.byteLength).toBeLessThanOrEqual(960000);
  const data = new DataView(output!);
  expect(data.getInt16(data.byteLength - 2, true)).toBe(16384);
  capture.reset();
  for (let i = 0; i < 2; i++) expect(capture.push(new Float32Array(800).fill(0.1))).toBeNull();
  for (let i = 0; i < 20; i++) expect(capture.push(new Float32Array(800))).toBeNull(); // brief clicks are not turns
});

it.each([1, 5, 12])("resumes with the configured %s-second timeout after Claude capture, processing and playback", async seconds => {
  const shared = new VoicePreview(() => panel, hooks, "claude", seconds);
  try {
    await shared.start();
    await vi.advanceTimersByTimeAsync(Math.min(4000, seconds * 1000 - 100));
    node.port.onmessage?.({ data: new Float32Array(800).fill(0.1) });
    await vi.advanceTimersByTimeAsync(6000);
    expect(stop).not.toHaveBeenCalled();
    let finish!: (value: Response) => void;
    const normal = vi.mocked(api).getMockImplementation()!;
    vi.mocked(api).mockImplementation((path, ...args) => path.endsWith('/audio') ? normal(path, ...args)
      : path.endsWith('/status') ? Promise.resolve({ json: async () => ({ phase: 'searching' }) } as Response)
      : new Promise(resolve => { finish = resolve; }));
    utterance(); await flushPromises();
    await vi.advanceTimersByTimeAsync(15000);
    expect(stop).not.toHaveBeenCalled();
    expect(hooks.phase).toHaveBeenLastCalledWith('searching');
    finish({ json: async () => ({ text: 'Cloudy.', action: false, audio: true }) } as Response);
    await flushPromises();
    await vi.advanceTimersByTimeAsync(10000);
    expect(stop).not.toHaveBeenCalled();
    source.onended?.();
    await vi.advanceTimersByTimeAsync(seconds * 1000 - 1);
    expect(stop).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(stop).toHaveBeenCalledOnce();
    expect(hooks.phase).toHaveBeenLastCalledWith('idle');
    expect(send).toHaveBeenCalledWith('voice-preview/sessions/claude-session', 'DELETE', undefined, { keepalive: true });
  } finally { await shared.stop(); }
});
