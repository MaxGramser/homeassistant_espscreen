import { flushPromises } from "@vue/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api, send } from "../src/api";
import { VoicePreview, type VoiceHooks, type VoicePanel } from "../src/model/voice-preview";

vi.mock("../src/api", () => ({ api: vi.fn(), send: vi.fn() }));
class Socket {
  static OPEN = 1;
  static last: Socket;
  readyState = 1; bufferedAmount = 0;
  onmessage?: (event: { data: string }) => void;
  onclose?: () => void;
  send = vi.fn();
  close = vi.fn(() => { this.readyState = 3; this.onclose?.(); });
  constructor() { Socket.last = this; }
  message(data: unknown) { this.onmessage?.({ data: JSON.stringify(data) }); }
}
let node: { port: { onmessage?: (event: { data: Float32Array }) => void }; disconnect: ReturnType<typeof vi.fn> };
let source: { onended?: () => void; connect: ReturnType<typeof vi.fn>; start: ReturnType<typeof vi.fn>; stop: ReturnType<typeof vi.fn>; disconnect: ReturnType<typeof vi.fn> };
let track: { enabled: boolean; stop: ReturnType<typeof vi.fn> };
let close: ReturnType<typeof vi.fn>, hooks: VoiceHooks, voice: VoicePreview;
let state: string;
const panel = { shape: { columns: 2, rows: 3 }, page: 0, layout: {} } as VoicePanel;
const completed = { type: "response.done", response: { id: "answer", status: "completed", output: [
  { type: "message", content: [{ type: "audio", transcript: "Answer." }] },
] } };

beforeEach(() => {
  vi.clearAllMocks(); vi.useFakeTimers();
  close = vi.fn().mockResolvedValue(undefined);
  track = { enabled: true, stop: vi.fn() };
  source = { connect: vi.fn(), start: vi.fn(), stop: vi.fn(), disconnect: vi.fn() };
  vi.stubGlobal("AudioContext", class {
    sampleRate = 24000; destination = {};
    resume = vi.fn().mockResolvedValue(undefined); close = close;
    audioWorklet = { addModule: vi.fn().mockResolvedValue(undefined) };
    createMediaStreamSource = () => ({ connect: vi.fn(), disconnect: vi.fn() });
    decodeAudioData = vi.fn().mockResolvedValue({}); createBufferSource = () => source;
  });
  vi.stubGlobal("AudioWorkletNode", class {
    port = {}; connect = vi.fn(); disconnect = vi.fn();
    constructor() { node = this; }
  });
  vi.stubGlobal("WebSocket", Socket);
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [track] }) } });
  state = "preparing_speech";
  vi.mocked(send).mockImplementation(async path => {
    if (path === "voice-preview/openai/sessions") return { id: "relay-session", max_seconds: 600 };
    if (path === "voice-preview/context") return { instructions: "Panel context" };
    if (path.endsWith("/tools")) return { status: "accepted", end_voice: true };
    return { state };
  });
  vi.mocked(api).mockImplementation(async path => path.endsWith("/audio")
    ? { arrayBuffer: async () => new ArrayBuffer(100) } as Response
    : { json: async () => ({ state, error: state === "error" ? "Speaker unavailable" : "" }) } as Response);
  hooks = { phase: vi.fn(), reply: vi.fn(), error: vi.fn(), action: vi.fn(), sources: vi.fn() };
  voice = new VoicePreview(() => panel, hooks, "openai", 1, true);
});
afterEach(async () => { await voice.stop(); vi.useRealTimers(); vi.unstubAllGlobals(); });

async function start() {
  await voice.start(); await flushPromises();
  Socket.last.message({ type: "relay.ready" }); await flushPromises();
}
function reply(output = "sonos") {
  Socket.last.message({ type: "response.created", response: { id: "answer" } });
  Socket.last.message({ type: "reply.ready", response_id: "answer", reply: { id: "reply-1", output, state: "ready" } });
  Socket.last.message(completed);
}

it("sends native PCM, pauses input through external delivery and resumes with a fresh timeout", async () => {
  await start();
  node.port.onmessage?.({ data: new Float32Array([.5, -.5]) });
  const pcm = Socket.last.send.mock.calls.find(([data]) => data instanceof ArrayBuffer)![0];
  expect(new DataView(pcm).getInt16(0, true)).toBe(16384);
  expect(send).toHaveBeenCalledWith("voice-preview/openai/sessions", "POST", { context: panel });
  expect(vi.mocked(send).mock.calls.some(([path]) => path.includes("claude"))).toBe(false);
  await vi.advanceTimersByTimeAsync(900);
  reply(); await flushPromises();
  expect(track.enabled).toBe(false);
  const calls = Socket.last.send.mock.calls.length;
  node.port.onmessage?.({ data: new Float32Array([.5]) });
  expect(Socket.last.send).toHaveBeenCalledTimes(calls);
  await vi.advanceTimersByTimeAsync(5000);
  expect(track.stop).not.toHaveBeenCalled();
  expect(hooks.phase).toHaveBeenLastCalledWith("preparing_speech");
  state = "speaking"; await vi.advanceTimersByTimeAsync(400);
  expect(hooks.phase).toHaveBeenLastCalledWith("speaking");
  Socket.last.message({ type: "input_audio_buffer.speech_started" }); // playback must not start a new turn
  await vi.advanceTimersByTimeAsync(3000);
  expect(track.stop).not.toHaveBeenCalled();
  state = "done"; await vi.advanceTimersByTimeAsync(400);
  expect(track.enabled).toBe(true);
  expect(hooks.phase).toHaveBeenLastCalledWith("listening");
  await vi.advanceTimersByTimeAsync(999);
  expect(track.stop).not.toHaveBeenCalled();
  await vi.advanceTimersByTimeAsync(1);
  expect(track.stop).toHaveBeenCalledOnce();
  expect(hooks.phase).toHaveBeenLastCalledWith("idle");
  expect(source.start).not.toHaveBeenCalled(); // no double playback on the browser
});

it("keeps a music confirmation local and closes voice after its actual audio ends", async () => {
  await start();
  Socket.last.message({ type: "response.created", response: { id: "command" } });
  Socket.last.message({ type: "response.done", response: { id: "command", status: "completed", output: [
    { type: "function_call", call_id: "play-1", name: "control_media", arguments: '{"name":"Music","action":"play"}' },
  ] } });
  await flushPromises();
  reply("local"); await flushPromises();
  expect(source.start).toHaveBeenCalledOnce();
  expect(hooks.phase).toHaveBeenLastCalledWith("speaking");
  await vi.advanceTimersByTimeAsync(2000);
  expect(track.stop).not.toHaveBeenCalled();
  source.onended?.(); await flushPromises();
  expect(track.stop).toHaveBeenCalledOnce();
  expect(hooks.phase).toHaveBeenLastCalledWith("idle");
  expect(vi.mocked(send).mock.calls.filter(([path]) => path.includes("/replies/"))).toHaveLength(0);
});

it("ends voice on speaker failure without resuming the mic or falling back to local playback", async () => {
  await start(); reply(); await flushPromises();
  state = "error"; await vi.advanceTimersByTimeAsync(400);
  expect(track.stop).toHaveBeenCalledOnce();
  expect(hooks.phase).toHaveBeenLastCalledWith("idle");
  expect(hooks.error).toHaveBeenLastCalledWith("Speaker unavailable");
  expect(source.start).not.toHaveBeenCalled();
});

it("Stop cancels polling and ignores a late delivery result", async () => {
  await start(); reply(); await flushPromises();
  let finish!: (response: Response) => void;
  vi.mocked(api).mockReturnValue(new Promise(resolve => { finish = resolve; }));
  await vi.advanceTimersByTimeAsync(400);
  await voice.stop();
  finish({ json: async () => ({ state: "done" }) } as Response); await flushPromises();
  expect(hooks.phase).toHaveBeenLastCalledWith("idle");
  expect(track.stop).toHaveBeenCalledOnce();
  expect(close).toHaveBeenCalledOnce();
  expect(vi.getTimerCount()).toBe(0);
});

it("ends a stuck external delivery even though the silence timer is paused", async () => {
  await start(); reply(); await flushPromises();
  await vi.advanceTimersByTimeAsync(105000); await flushPromises();
  expect(track.stop).toHaveBeenCalledOnce();
  expect(hooks.phase).toHaveBeenLastCalledWith("idle");
  expect(hooks.error).toHaveBeenLastCalledWith(expect.stringContaining("did not finish"));
});
