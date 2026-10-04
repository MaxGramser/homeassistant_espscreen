import { flushPromises } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { send } from "../src/api";
import { VoicePreview, type VoicePanel } from "../src/model/voice-preview";

vi.mock("../src/api", () => ({ send: vi.fn() }));
class Channel extends EventTarget {
  readyState = "connecting";
  onopen?: () => void;
  onclose?: () => void;
  onmessage?: (event: { data: string }) => void;
  send = vi.fn();
  close() { this.readyState = "closed"; this.onclose?.(); }
  open() { this.readyState = "open"; this.onopen?.(); this.dispatchEvent(new Event("open")); }
  message(data: unknown) { this.onmessage?.({ data: JSON.stringify(data) }); }
}
class Peer {
  static last: Peer;
  channel = new Channel();
  connectionState = "connected";
  addTrack = vi.fn();
  close = vi.fn();
  onconnectionstatechange?: () => void;
  createDataChannel() { return this.channel; }
  async createOffer() { return { type: "offer", sdp: "v=0\r\ntest" }; }
  async setLocalDescription() {}
  async setRemoteDescription() { this.channel.open(); }
  constructor() { Peer.last = this; }
}

let voice: VoicePreview;
let panel: VoicePanel;
let track: { enabled: boolean; stop: ReturnType<typeof vi.fn> };
let hooks: { phase: ReturnType<typeof vi.fn>; reply: ReturnType<typeof vi.fn>; error: ReturnType<typeof vi.fn>; action: ReturnType<typeof vi.fn>; sources: ReturnType<typeof vi.fn> };
beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
  vi.clearAllMocks();
  panel = { shape: { columns: 2, rows: 3 }, page: 0, layout: { title: "Panel", homePageId: "one", pages: [] } };
  track = { enabled: true, stop: vi.fn() };
  hooks = { phase: vi.fn(), reply: vi.fn(), error: vi.fn(), action: vi.fn(), sources: vi.fn() };
  vi.stubGlobal("RTCPeerConnection", Peer);
  vi.stubGlobal("Audio", class { autoplay = false; srcObject = null; play = vi.fn(async () => {}); pause = vi.fn(); });
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia: vi.fn(async () => ({ getTracks: () => [track] })) } });
  vi.mocked(send).mockImplementation(async (path) => {
    if (path === "voice-preview/sessions") return { id: "local-session", sdp: "v=0\r\nanswer", max_seconds: 600 };
    if (path === "voice-preview/context") return { instructions: "Current panel context" };
    return { status: "accepted" };
  });
  voice = new VoicePreview(() => panel, hooks);
});
afterEach(async () => { await voice.stop(); vi.unstubAllGlobals(); vi.useRealTimers(); });
const call = { type: "response.done", response: { status: "completed", output: [{ type: "function_call", call_id: "call_1", name: "control_switch",
  arguments: JSON.stringify({ name: "Desk", area: "", action: "turn_on" }) }] } };
const lookupCall = { type: "response.done", response: { status: "completed", output: [{ type: "function_call", call_id: "lookup_1", name: "lookup_current_information",
  arguments: JSON.stringify({ query: "Current weather in Amsterdam?" }) }] } };
const lookupResult = { status: "ok", answer: "Cloudy.", sources: [{ url: "https://weather.example/forecast", title: "Forecast" }] };

describe("Direct voice browser transport", () => {
  it("returns to listening after a silent activation without creating a spoken follow-up", async () => {
    await voice.start(); await flushPromises();
    const normal = vi.mocked(send).getMockImplementation()!;
    vi.mocked(send).mockImplementation((path, ...args) => path.endsWith("/tools")
      ? Promise.resolve({ status: "ok", wait_for_user: true }) : normal(path, ...args));
    const channel = Peer.last.channel;
    channel.send.mockClear();
    channel.message({ type: "response.created", response: { id: "wake" } });
    channel.message({ type: "response.done", response: { id: "wake", status: "completed", output: [
      { type: "function_call", call_id: "wait_1", name: "wait_for_user", arguments: "{}" },
    ] } });
    await flushPromises();
    const events = channel.send.mock.calls.map(([value]) => JSON.parse(value));
    expect(events.some(event => event.type === "response.create")).toBe(false);
    expect(events.some(event => event.item?.type === "function_call_output")).toBe(true);
    expect(track.enabled).toBe(true);
    expect(hooks.phase).toHaveBeenLastCalledWith("listening");
    expect(hooks.action).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(5000);
    expect(track.stop).toHaveBeenCalledOnce();
  });
  it.each([false, true])("allows local interruption only when browser echo cancellation is enabled (%s)", async enabled => {
    Object.assign(track, { getSettings: () => ({ echoCancellation: enabled }) });
    await voice.start(); await flushPromises();
    const channel = Peer.last.channel;
    channel.message({ type: "response.created", response: { id: "answer" } });
    channel.message({ type: "output_audio_buffer.started", response_id: "answer" });
    expect(track.enabled).toBe(enabled);
    channel.message({ type: "response.done", response: { id: "answer", output: [] } });
    channel.message({ type: "output_audio_buffer.stopped", response_id: "answer" });
    expect(track.enabled).toBe(true);
    expect(hooks.phase).toHaveBeenLastCalledWith("listening");
  });
  it.each([false, true])("mutes before starting music and waits for its acknowledgement audio (buffer first: %s)", async bufferFirst => {
    voice = new VoicePreview(() => panel, hooks, "openai", 1);
    await voice.start(); await flushPromises();
    let finish!: (value: unknown) => void;
    const normal = vi.mocked(send).getMockImplementation()!;
    vi.mocked(send).mockImplementation((path, ...args) => path.endsWith("/tools")
      ? new Promise(resolve => { finish = resolve; }) : normal(path, ...args));
    const channel = Peer.last.channel;
    channel.message({ type: "response.done", response: { id: "play", status: "completed", output: [
      { type: "function_call", call_id: "play_1", name: "play_music", arguments: '{"result_id":"track-1"}' },
    ] } });
    await flushPromises();
    expect(track.enabled).toBe(false);
    expect(channel.send).toHaveBeenCalledWith(JSON.stringify({ type: "input_audio_buffer.clear" }));
    expect(channel.send).toHaveBeenCalledWith(JSON.stringify({ type: "session.update", session: {
      type: "realtime", audio: { input: { turn_detection: null } },
    } }));
    // Music detected during the action must not become a newer user turn.
    channel.message({ type: "input_audio_buffer.speech_started" });
    channel.message({ type: "input_audio_buffer.speech_stopped" });
    finish({ status: "accepted", end_voice: true }); await flushPromises();
    expect(channel.send).toHaveBeenCalledWith(JSON.stringify({ type: "response.create" }));
    expect(hooks.action).toHaveBeenCalledOnce();
    channel.message({ type: "output_audio_buffer.stopped", response_id: "play" });
    channel.message({ type: "response.created", response: { id: "ack" } });
    const ended = { type: "output_audio_buffer.stopped", response_id: "ack" };
    const done = { type: "response.done", response: { id: "ack", status: "completed", output: [
      { type: "message", content: [{ type: "audio", transcript: "Playing." }] },
    ] } };
    if (bufferFirst) channel.message(ended); else channel.message(done);
    await vi.advanceTimersByTimeAsync(1000);
    expect(track.stop).not.toHaveBeenCalled();
    if (!bufferFirst) channel.message({ type: "output_audio_buffer.started", response_id: "ack" });
    channel.message(bufferFirst ? done : ended); await flushPromises();
    expect(track.stop).toHaveBeenCalledOnce();
    expect(hooks.phase).toHaveBeenLastCalledWith("idle");
    expect(send).toHaveBeenCalledWith("voice-preview/sessions/local-session", "DELETE", undefined, { keepalive: true });
    expect(vi.getTimerCount()).toBe(0);
  });

  it.each([false, true])("ends an accepted next command with no audio (acknowledgement missing: %s)", async missing => {
    voice = new VoicePreview(() => panel, hooks, "openai", 1);
    await voice.start(); await flushPromises();
    vi.mocked(send).mockResolvedValue({ status: "accepted", end_voice: true });
    const channel = Peer.last.channel;
    channel.message({ type: "response.done", response: { output: [
      { type: "function_call", call_id: "next_1", name: "control_media", arguments: '{"name":"Music","action":"next"}' },
    ] } });
    await flushPromises();
    expect(track.enabled).toBe(false);
    if (missing) await vi.advanceTimersByTimeAsync(30000);
    else {
      channel.message({ type: "response.created", response: { id: "ack" } });
      channel.message({ type: "response.done", response: { id: "ack", status: "completed", output: [
        { type: "message", content: [{ type: "text", text: "Next." }] },
      ] } });
    }
    await flushPromises();
    expect(track.stop).toHaveBeenCalledOnce();
    expect(hooks.phase).toHaveBeenLastCalledWith("idle");
  });

  it.each([1, 7])("resumes with the configured %s-second timeout after rejected playback and its reply", async seconds => {
    voice = new VoicePreview(() => panel, hooks, "openai", seconds);
    await voice.start(); await flushPromises();
    await vi.advanceTimersByTimeAsync(seconds * 1000 - 100);
    let finish!: (value: unknown) => void;
    const normal = vi.mocked(send).getMockImplementation()!;
    vi.mocked(send).mockImplementation((path, ...args) => path.endsWith("/tools")
      ? new Promise(resolve => { finish = resolve; }) : normal(path, ...args));
    const channel = Peer.last.channel;
    channel.message({ type: "response.done", response: { output: [
      { type: "function_call", call_id: "play_1", name: "control_media", arguments: '{"name":"Music","action":"play"}' },
    ] } });
    await flushPromises();
    await vi.advanceTimersByTimeAsync(12000);
    expect(track.stop).not.toHaveBeenCalled();
    finish({ status: "unsupported" }); await flushPromises();
    expect(track.enabled).toBe(true);
    channel.message({ type: "response.created", response: { id: "reply" } });
    channel.message({ type: "output_audio_buffer.started", response_id: "reply" });
    channel.message({ type: "response.done", response: { id: "reply", output: [] } });
    await vi.advanceTimersByTimeAsync(10000);
    expect(track.stop).not.toHaveBeenCalled();
    channel.message({ type: "output_audio_buffer.stopped", response_id: "reply" });
    expect(hooks.phase).toHaveBeenLastCalledWith("listening");
    await vi.advanceTimersByTimeAsync(seconds * 1000 - 1);
    expect(track.stop).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(track.stop).toHaveBeenCalledOnce();
  });

  it("closes the microphone and session after five seconds waiting for speech", async () => {
    await voice.start(); await flushPromises();
    await vi.advanceTimersByTimeAsync(4999);
    expect(track.stop).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1); await flushPromises();
    expect(track.stop).toHaveBeenCalledOnce();
    expect(hooks.phase).toHaveBeenLastCalledWith("idle");
    expect(send).toHaveBeenCalledWith("voice-preview/sessions/local-session", "DELETE", undefined, { keepalive: true });
    expect(vi.getTimerCount()).toBe(0);
  });

  it("waits through user speech, processing and playback before restarting the silence timer", async () => {
    await voice.start(); await flushPromises();
    const channel = Peer.last.channel;
    await vi.advanceTimersByTimeAsync(4000);
    channel.message({ type: "input_audio_buffer.speech_started" });
    await vi.advanceTimersByTimeAsync(12000);
    expect(track.stop).not.toHaveBeenCalled();
    channel.message({ type: "input_audio_buffer.speech_stopped" });
    channel.message({ type: "output_audio_buffer.cleared" });
    await vi.advanceTimersByTimeAsync(6000);
    expect(track.stop).not.toHaveBeenCalled();
    channel.message({ type: "response.created", response: { id: "answer" } });
    await vi.advanceTimersByTimeAsync(12000);
    expect(track.stop).not.toHaveBeenCalled();
    channel.message({ type: "output_audio_buffer.started" });
    channel.message({ type: "response.done", response: { id: "answer", status: "completed", output: [] } });
    await vi.advanceTimersByTimeAsync(12000);
    expect(track.stop).not.toHaveBeenCalled();
    channel.message({ type: "output_audio_buffer.stopped" });
    await vi.advanceTimersByTimeAsync(4999);
    expect(track.stop).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(track.stop).toHaveBeenCalledOnce();
  });

  it("does not treat the end of a spoken preamble as idle while a tool is still running", async () => {
    let finish!: (value: unknown) => void;
    const normal = vi.mocked(send).getMockImplementation()!;
    vi.mocked(send).mockImplementation((path, ...args) => path.endsWith("/tools")
      ? new Promise(resolve => { finish = resolve; }) : normal(path, ...args));
    await voice.start(); await flushPromises();
    const channel = Peer.last.channel;
    channel.message({ type: "response.created" });
    channel.message({ type: "output_audio_buffer.started" });
    channel.message(lookupCall); await flushPromises();
    channel.message({ type: "output_audio_buffer.stopped" });
    await vi.advanceTimersByTimeAsync(10000);
    expect(track.stop).not.toHaveBeenCalled();
    expect(hooks.phase).toHaveBeenLastCalledWith("thinking");
    finish(lookupResult); await flushPromises();
    await vi.advanceTimersByTimeAsync(6000);
    expect(track.stop).not.toHaveBeenCalled();
    channel.message({ type: "response.created", response: { id: "followup" } });
    channel.message({ type: "output_audio_buffer.started" });
    channel.message({ type: "response.done", response: { id: "followup", status: "completed" } });
    channel.message({ type: "output_audio_buffer.stopped" });
    await vi.advanceTimersByTimeAsync(5000);
    expect(track.stop).toHaveBeenCalledOnce();
  });

  it.each([1, 12])("respects the configured silence timeout of %s seconds", async seconds => {
    voice = new VoicePreview(() => panel, hooks, "openai", seconds);
    await voice.start(); await flushPromises();
    await vi.advanceTimersByTimeAsync(seconds * 1000 - 1);
    expect(track.stop).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(track.stop).toHaveBeenCalledOnce();
  });

  it.each([0, -1, 301, NaN])("uses the five-second default for invalid or legacy timeout %s", async seconds => {
    voice = new VoicePreview(() => panel, hooks, "openai", seconds);
    await voice.start(); await flushPromises();
    await vi.advanceTimersByTimeAsync(4999);
    expect(track.stop).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(track.stop).toHaveBeenCalledOnce();
  });

  it("rejects unsupported providers without opening a connection", () => {
    expect(() => new VoicePreview(() => panel, hooks, "unknown")).toThrow("Unknown voice provider");
    expect(send).not.toHaveBeenCalled();
  });

  it("passes searched facts back to voice and retains sources with the answer until the next question", async () => {
    await voice.start(); await flushPromises();
    vi.mocked(send).mockResolvedValue(lookupResult);
    const channel = Peer.last.channel;
    channel.message(lookupCall); channel.message(lookupCall);
    await flushPromises();
    expect(vi.mocked(send).mock.calls.filter(([path]) => path.endsWith("/tools"))).toHaveLength(1);
    expect(hooks.sources).toHaveBeenLastCalledWith(lookupResult.sources);
    expect(channel.send).toHaveBeenCalledWith(JSON.stringify({ type: "conversation.item.create", item: {
      type: "function_call_output", call_id: "lookup_1", output: JSON.stringify(lookupResult),
    } }));
    channel.message({ type: "response.created" });
    channel.message({ type: "response.output_audio_transcript.delta", delta: "Cloudy." });
    expect(hooks.reply).toHaveBeenLastCalledWith("Cloudy.");
    expect(hooks.sources).toHaveBeenLastCalledWith(lookupResult.sources);
    expect(hooks.action).not.toHaveBeenCalled();
    channel.message({ type: "input_audio_buffer.speech_started" });
    expect(hooks.sources).toHaveBeenLastCalledWith([]);
    expect(hooks.reply).toHaveBeenLastCalledWith("");
  });

  it("does not attach an interrupted lookup to a newer question or start a late spoken reply", async () => {
    await voice.start(); await flushPromises();
    let finish!: (value: unknown) => void;
    vi.mocked(send).mockImplementation(async () => new Promise(resolve => { finish = resolve; }));
    const channel = Peer.last.channel;
    channel.message(lookupCall); await flushPromises();
    channel.message({ type: "input_audio_buffer.speech_started" });
    finish(lookupResult); await flushPromises();
    expect(hooks.sources).toHaveBeenLastCalledWith([]);
    expect(channel.send).not.toHaveBeenCalledWith(JSON.stringify({ type: "response.create" }));
    vi.mocked(send).mockResolvedValue({});
  });

  it("keeps the audio session usable when search cannot verify an answer", async () => {
    await voice.start(); await flushPromises();
    vi.mocked(send).mockResolvedValue({ status: "unavailable", sources: [] });
    Peer.last.channel.message(lookupCall); await flushPromises();
    expect(hooks.sources).toHaveBeenLastCalledWith([]);
    expect(hooks.error).toHaveBeenLastCalledWith("");
    expect(track.stop).not.toHaveBeenCalled();
    expect(Peer.last.channel.send).toHaveBeenCalledWith(JSON.stringify({ type: "response.create" }));
  });

  it("ignores a late lookup failure after Stop and a new session", async () => {
    await voice.start(); await flushPromises();
    let reject!: (reason: unknown) => void;
    const normal = vi.mocked(send).getMockImplementation()!;
    vi.mocked(send).mockImplementation((path, ...args) => path.endsWith("/tools")
      ? new Promise((_, fail) => { reject = fail; }) : normal(path, ...args));
    Peer.last.channel.message(lookupCall); await flushPromises();
    await voice.stop(); await voice.start(); await flushPromises();
    reject(new Error("Old lookup disconnected")); await flushPromises();
    expect(track.stop).toHaveBeenCalledOnce();
    expect(hooks.phase).toHaveBeenLastCalledWith("listening");
    expect(hooks.error).toHaveBeenLastCalledWith("");
  });

  it("passes microphone tracks directly to WebRTC and stops every track", async () => {
    await voice.start(); await flushPromises();
    expect(Peer.last.addTrack).toHaveBeenCalledWith(track, expect.anything());
    expect(hooks.phase).toHaveBeenLastCalledWith("listening");
    expect(send).toHaveBeenCalledWith("voice-preview/sessions", "POST", { sdp: "v=0\r\ntest", context: panel });
    await voice.stop();
    expect(track.stop).toHaveBeenCalledOnce();
    expect(Peer.last.close).toHaveBeenCalledOnce();
    expect(send).toHaveBeenCalledWith("voice-preview/sessions/local-session", "DELETE", undefined, { keepalive: true });
  });

  it("uses the current firmware page for tool calls, deduplicates events and refreshes HA state", async () => {
    await voice.start(); await flushPromises();
    panel.page = 1;
    Peer.last.channel.message(call); Peer.last.channel.message(call);
    await flushPromises();
    const requests = vi.mocked(send).mock.calls.filter(([path]) => path.endsWith("/tools"));
    expect(requests).toHaveLength(1);
    expect(requests[0][2]).toMatchObject({ context: { page: 1 }, arguments: { name: "Desk", action: "turn_on" } });
    expect(hooks.action).toHaveBeenCalledOnce();
    expect(Peer.last.channel.send).toHaveBeenCalledWith(JSON.stringify({ type: "response.create" }));
  });

  it("closes the microphone if the session request fails", async () => {
    vi.mocked(send).mockRejectedValue(new Error("API key missing"));
    await voice.start();
    expect(track.stop).toHaveBeenCalledOnce();
    expect(hooks.error).toHaveBeenLastCalledWith("API key missing");
    expect(hooks.phase).toHaveBeenLastCalledWith("idle");
  });

  it.each(["control_media", "set_light_brightness"])("refreshes the firmware feed after an accepted %s command", async name => {
    await voice.start(); await flushPromises();
    Peer.last.channel.message({ type: "response.done", response: { status: "completed", output: [
      { type: "function_call", call_id: "control_1", name, arguments: JSON.stringify({ name: "Tile", area: "", action: "pause" }) },
    ] } });
    await flushPromises();
    expect(hooks.action).toHaveBeenCalledOnce();
  });

  it("returns unsupported playback choices to the model without claiming a device change", async () => {
    await voice.start(); await flushPromises();
    vi.mocked(send).mockResolvedValue({ status: "unsupported", available_actions: ["select_source"] });
    Peer.last.channel.message({ type: "response.done", response: { status: "completed", output: [
      { type: "function_call", call_id: "media_1", name: "control_media", arguments: JSON.stringify({ name: "Music", area: "", action: "play" }) },
    ] } });
    await flushPromises();
    expect(hooks.action).not.toHaveBeenCalled();
    expect(track.enabled).toBe(true);
    expect(track.stop).not.toHaveBeenCalled();
    expect(Peer.last.channel.send).toHaveBeenCalledWith(JSON.stringify({ type: "session.update", session: {
      type: "realtime", audio: { input: { turn_detection: { type: "semantic_vad" } } },
    } }));
    const output = Peer.last.channel.send.mock.calls.map(([data]) => JSON.parse(data)).find(event => event.type === "conversation.item.create");
    expect(JSON.parse(output.item.output)).toEqual({ status: "unsupported", available_actions: ["select_source"] });
  });

  it("handles Stop while microphone permission is still pending", async () => {
    let grant!: (value: any) => void;
    vi.mocked(navigator.mediaDevices.getUserMedia).mockImplementation(() => new Promise(resolve => { grant = resolve; }));
    const starting = voice.start(); await flushPromises();
    await voice.stop();
    grant({ getTracks: () => [track] });
    await starting;
    expect(track.stop).toHaveBeenCalledOnce();
    expect(send).not.toHaveBeenCalled();
  });

  it("hangs up a late session response after Stop", async () => {
    let answer!: (value: any) => void;
    vi.mocked(send).mockImplementation(async (path) => path === "voice-preview/sessions" ? new Promise(resolve => { answer = resolve; }) : {});
    const starting = voice.start(); await flushPromises();
    await voice.stop();
    answer({ id: "late-session", sdp: "v=0", max_seconds: 600 }); await starting;
    expect(send).toHaveBeenCalledWith("voice-preview/sessions/late-session", "DELETE");
    expect(track.stop).toHaveBeenCalledOnce();
  });

  it("stops on connection loss and ignores late tool calls", async () => {
    await voice.start(); await flushPromises();
    const channel = Peer.last.channel;
    Peer.last.connectionState = "failed"; Peer.last.onconnectionstatechange?.();
    await flushPromises(); channel.message(call); await flushPromises();
    expect(track.stop).toHaveBeenCalledOnce();
    expect(vi.mocked(send).mock.calls.filter(([path]) => path.endsWith("/tools"))).toHaveLength(0);
    expect(hooks.error).toHaveBeenLastCalledWith("Voice connection lost. Start again.");
  });

  it("does not start background polling when Stop interrupts audio negotiation", async () => {
    let finish!: () => void;
    const negotiation = vi.spyOn(Peer.prototype, "setRemoteDescription").mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    try {
      const starting = voice.start(); await flushPromises();
      await voice.stop(); finish(); await starting;
      expect(vi.getTimerCount()).toBe(0);
      expect(track.stop).toHaveBeenCalledOnce();
    } finally { negotiation.mockRestore(); }
  });
});
