import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import FirmwarePreview from "../src/components/FirmwarePreview.vue";
import createModule from "../src/wasm/firmware_preview.js";
import { api, send } from "../src/api";
import { useInventoryStore } from "../src/stores/inventory";
import { useDocumentStore } from "../src/stores/document";
import { setHidden } from "./helpers/browser";

vi.mock("../src/wasm/firmware_preview.js", () => ({ default: vi.fn() }));
vi.mock("../src/api", () => ({ api: vi.fn(), send: vi.fn() }));
const bundle = () => ({ revision: "1111111111111111", configuration: [{ op: "begin" }, { op: "commit" }], values: [{ op: "state", i: 0, state: "on" }] });
function response(name: string, _result?: unknown, _types?: unknown, args?: unknown[]): string {
  if (name === "preview_next_action" || name === "preview_next_image") return "";
  if (name === "preview_receive" && JSON.parse(String(args?.[0])).op === "hello") return "Session:2222222222222222";
  return "Synced";
}

const firmware = {
  HEAPU8: new Uint8Array(800 * 800 * 4),
  _preview_init: vi.fn(() => 1), _preview_time: vi.fn(),
  _preview_render: vi.fn(), _preview_frame: vi.fn(() => 0),
  _preview_image_buffer: vi.fn(() => 128), _preview_image_ready: vi.fn(() => 1),
  _preview_touch: vi.fn(), _preview_cancel: vi.fn(), _preview_dark: vi.fn(), _preview_language: vi.fn(), ccall: vi.fn(response),
};
let wrapper: VueWrapper | undefined;
let putImageData: ReturnType<typeof vi.fn>;

// The draft the preview draws (stores/document.ts).
let doc: ReturnType<typeof useDocumentStore>;
beforeEach(() => {
  doc = useDocumentStore();
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
  vi.clearAllMocks();
  firmware.ccall.mockImplementation(response);
  doc.document = { title: "Test panel", pages: [] } as any;
  useInventoryStore().inventory = { screens: [], entities: [] } as any;
  vi.mocked(createModule).mockResolvedValue(firmware as any);
  vi.mocked(send).mockResolvedValue(bundle());
  vi.spyOn(window, "requestAnimationFrame").mockReturnValue(100);
  vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => {});
  putImageData = vi.fn();
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({ putImageData } as any);
  vi.stubGlobal("ImageData", class { constructor(public data: Uint8ClampedArray, public width: number, public height: number) {} });
});

afterEach(() => {
  wrapper?.unmount(); wrapper = undefined;
  document.body.replaceChildren();
  vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers();
});

async function preview(width = 720, height = 720, extra: Record<string, unknown> = {}) {
  wrapper = mount(FirmwarePreview, { attachTo: document.body, props: { width, height, columns: 2, rows: 3, ...extra } });
  await flushPromises();
  return wrapper;
}

describe("Firmware preview transport", () => {
  it('delivers firmware image events and pixels without invoking HA actions or drawing images in Vue', async () => {
    const request = { service: 'esphome.screen_camera', event: true, data: { entity: 'media_player.test', view: '1' } };
    const packet = { op: 'camera', t: 'cover', e: 'media_player.test', view: 1,
      session: '2222222222222222', rev: '1111111111111111', u: 'http://firmware-preview.invalid/abcdefghijklmnop.bmp' };
    let queued = true, download = true;
    firmware.ccall.mockImplementation((name, result, types, args) => {
      if (name === 'preview_next_action') { if (!queued) return ''; queued = false; return JSON.stringify(request); }
      if (name === 'preview_next_image') { if (!download) return ''; download = false; return JSON.stringify({ id: 7, url: packet.u }); }
      return response(name, result, types, args);
    });
    vi.mocked(send).mockImplementation(async path => (path === 'firmware-preview/image' ? packet : bundle()) as any);
    vi.mocked(api).mockResolvedValue(new Response(new Uint8Array([66, 77, 1, 2])));
    await preview();
    expect(send).toHaveBeenCalledWith('firmware-preview/image', 'POST',
      { request, shape: { width: 720, height: 720 } }, expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(vi.mocked(send).mock.calls.some(([path]) => path === 'firmware-preview/action')).toBe(false);
    expect(firmware.ccall).toHaveBeenCalledWith('preview_receive', 'string', ['string'],
      [JSON.stringify({ ...packet, v: 2, seq: 5 })]);
    expect(api).toHaveBeenCalledWith('firmware-preview/images/abcdefghijklmnop.bmp', expect.any(Object));
    expect(firmware._preview_image_buffer).toHaveBeenCalledWith(7, 4);
    expect([...firmware.HEAPU8.subarray(128, 132)]).toEqual([66, 77, 1, 2]);
    expect(firmware._preview_image_ready).toHaveBeenCalledWith(7, 1);
    expect(putImageData).toHaveBeenCalledTimes(1);
  });

  it('rejects arbitrary image URLs and tells the firmware that loading failed', async () => {
    let queued = true;
    firmware.ccall.mockImplementation((name, result, types, args) => {
      if (name === 'preview_next_image' && queued) { queued = false; return JSON.stringify({ id: 9, url: 'https://example.com/image.bmp' }); }
      return response(name, result, types, args);
    });
    await preview();
    expect(api).not.toHaveBeenCalled();
    expect(firmware._preview_image_ready).toHaveBeenCalledWith(9, 0);
  });
  it("forwards touch coordinates and layout updates to the same firmware instance", async () => {
    const editor = await preview();
    const canvas = editor.get("canvas").element;
    canvas.setPointerCapture = vi.fn(); canvas.releasePointerCapture = vi.fn();
    vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue({ left: 0, top: 0, width: 720, height: 720 } as DOMRect);
    for (const type of ["pointerdown", "pointerup"]) {
      const event = new MouseEvent(type, { clientX: 695, clientY: 695, bubbles: true });
      Object.defineProperty(event, "pointerId", { value: 1 });
      canvas.dispatchEvent(event);
    }
    expect(firmware._preview_touch.mock.calls).toEqual([[695, 695, 1], [695, 695, 0]]);
    doc.document!.title = "Updated panel";
    await flushPromises();
    await vi.advanceTimersByTimeAsync(200);
    expect(vi.mocked(send).mock.lastCall?.[2]).toMatchObject({ layout: { title: "Updated panel", pages: [] } });
    expect(createModule).toHaveBeenCalledTimes(1);
  });

  it("sends the layout once typing pauses, not on every key", async () => {
    const sent: string[] = [], layouts = () => sent;
    vi.mocked(send).mockImplementation(async (path: string, _method: string, body: any) => {
      if (path === "firmware-preview") sent.push(body.layout.title);
      return bundle() as any;
    });
    await preview();
    expect(layouts()).toEqual(["Test panel"]);
    // A name typed into the inspector changes the draft with every key.
    for (const title of ["H", "Ha", "Hal", "Hall"]) {
      doc.document!.title = title;
      await flushPromises();
      await vi.advanceTimersByTimeAsync(80);
    }
    expect(layouts()).toEqual(["Test panel"]);
    await vi.advanceTimersByTimeAsync(200);
    expect(layouts()).toEqual(["Test panel", "Hall"]);
  });

  it("asks nothing while the tab is hidden, and what came due once it is shown again", async () => {
    const asked = () => vi.mocked(send).mock.calls.filter(([path]) => path === "firmware-preview").length;
    await preview();
    expect(asked()).toBe(1);
    setHidden(true);
    await vi.advanceTimersByTimeAsync(60000);
    expect(asked()).toBe(1);
    setHidden(false);
    await flushPromises();
    expect(asked()).toBe(2);
    await vi.advanceTimersByTimeAsync(10000);
    expect(asked()).toBe(3);
  });

  it("keeps the device session and page on value-only refreshes", async () => {
    await preview();
    await vi.advanceTimersByTimeAsync(10000);
    const packets = firmware.ccall.mock.calls.filter(([name]) => name === "preview_receive")
      .map(([, , , args]) => JSON.parse(String(args?.[0])));
    expect(packets.map(packet => packet.op)).toEqual(["hello", "begin", "commit", "state", "ping", "ping"]);
    expect(packets.slice(1).map(packet => packet.seq)).toEqual([1, 2, 3, 4, 5]);
    expect(packets.slice(1).every(packet => packet.v === 2 && packet.session === "2222222222222222")).toBe(true);
  });

  it('receives delayed track metadata from HA events without waiting for the poll or resetting the page', async () => {
    const streams: { url: string; onmessage: (() => void) | null; close: ReturnType<typeof vi.fn> }[] = [];
    vi.stubGlobal('EventSource', class {
      onmessage = null;
      close = vi.fn();
      constructor(public url: string) { streams.push(this); }
    });
    doc.document = { title: 'Music', pages: [{ tiles: [{ content: { kind: 'entity', entityId: 'media_player.test' } }],
      topbar: { trailing: [{ type: 'entity', entity: 'sensor.temperature' }] } }] } as any;
    let track = 'First track';
    vi.mocked(send).mockImplementation(async () => ({ ...bundle(), values: [
      { op: 'state', i: 0, state: 'playing', a: { media_title: track }, x: { pic: track } },
    ] }) as any);
    await preview();
    expect(streams[0].url).toBe('api/firmware-preview/events?entity=media_player.test&entity=sensor.temperature');
    // The command has returned while HA still has the old metadata. Its later
    // state_changed event must reach the native decoder with title and picture.
    track = 'Next track';
    streams[0].onmessage!(); streams[0].onmessage!();
    await vi.advanceTimersByTimeAsync(100);
    const packets = firmware.ccall.mock.calls.filter(([name]) => name === 'preview_receive')
      .map(([, , , args]) => JSON.parse(String(args?.[0])));
    expect(packets.filter(packet => packet.op === 'state').at(-1)).toMatchObject({
      a: { media_title: 'Next track' }, x: { pic: 'Next track' }, session: '2222222222222222',
    });
    expect(packets.filter(packet => packet.op === 'hello')).toHaveLength(1);
    expect(vi.mocked(send).mock.calls.filter(([path]) => path === 'firmware-preview')).toHaveLength(2);
    doc.document!.pages[0].tiles[0].content = { kind: 'entity', entityId: 'media_player.other' };
    await flushPromises();
    expect(streams[0].close).toHaveBeenCalledOnce();
    expect(streams[1].url).toContain('entity=media_player.other');
    wrapper!.unmount(); wrapper = undefined;
    expect(streams[1].close).toHaveBeenCalledOnce();
  });

  it.each([true, false])("relays firmware commands and returns Home Assistant's result (success=%s)", async (success) => {
    const request = { service: "light.turn_on", call_id: 123, event: false, data: { entity_id: "light.test" }, templates: {} };
    let queued = true;
    firmware.ccall.mockImplementation((name, result, types, args) => {
      if (name !== "preview_next_action") return response(name, result, types, args);
      if (!queued) return "";
      queued = false; return JSON.stringify(request);
    });
    vi.mocked(send).mockImplementation(async (path: string) => {
      if (path !== "firmware-preview/action") return bundle() as any;
      if (!success) throw new Error("Device unavailable");
      return { success: true } as any;
    });
    const editor = await preview();
    expect(send).toHaveBeenCalledWith("firmware-preview/action", "POST", request);
    expect(firmware.ccall).toHaveBeenCalledWith("preview_action_response", null,
      ["number", "number", "string"], [123, success ? 1 : 0, success ? "" : "Device unavailable"]);
    expect(vi.mocked(send).mock.calls.filter(([path]) => path === "firmware-preview")).toHaveLength(2);
    if (!success) expect(editor.get('[role="alert"]').text()).toContain("Device unavailable");
    expect(firmware._preview_init).toHaveBeenCalledTimes(1);
  });

  it.each([{ still: true }, { controls: false }])("keeps a tap away from Home Assistant when %o", async (mode) => {
    const request = { service: "light.turn_on", call_id: 55, event: false, data: { entity_id: "light.test" }, templates: {} };
    let queued = true;
    firmware.ccall.mockImplementation((name, result, types, args) => {
      if (name !== "preview_next_action") return response(name, result, types, args);
      if (!queued) return "";
      queued = false; return JSON.stringify(request);
    });
    await preview(720, 720, mode);
    expect(vi.mocked(send).mock.calls.some(([path]) => path === "firmware-preview/action")).toBe(false);
    expect(firmware.ccall).toHaveBeenCalledWith("preview_action_response", null, ["number", "number", "string"], [55, 1, ""]);
    // The states go out again, so the tile lets go of what it expected.
    const states = firmware.ccall.mock.calls.filter(([name, , , args]) => name === "preview_receive" && JSON.parse(String(args?.[0])).op === "state");
    expect(states).toHaveLength(2);
  });

  it("draws a layout it is given, without touch, and says when its first frame is up", async () => {
    const layout = { title: "Kitchen", pages: [] };
    const editor = await preview(480, 480, { still: true, layout });
    expect(vi.mocked(send).mock.calls[0][2]).toMatchObject({ layout: { title: "Kitchen" } });
    expect(editor.emitted("ready")).toHaveLength(1);
    expect(editor.find(".firmware-preview.still").exists()).toBe(true);
    const canvas = editor.get("canvas").element;
    const event = new MouseEvent("pointerdown", { clientX: 10, clientY: 10, bubbles: true });
    Object.defineProperty(event, "pointerId", { value: 1 });
    canvas.dispatchEvent(event);
    expect(firmware._preview_touch).not.toHaveBeenCalled();
  });

  it("draws the screen in the screens' language and its Dark mode, before the first layout and when they change", async () => {
    useInventoryStore().inventory = { screens: [], entities: [], language: { setting: "auto", effective: "nl", ha: "nl", languages: [] } } as any;
    const editor = await preview(480, 480, { dark: true });
    const calls = firmware.ccall.mock.calls.map(([name, , , args]) => name === "preview_language" ? `language ${args?.[0]}` : name);
    expect(calls.indexOf("language nl")).toBeGreaterThanOrEqual(0);
    expect(calls.indexOf("language nl")).toBeLessThan(calls.indexOf("preview_receive"));
    expect(firmware._preview_dark).toHaveBeenLastCalledWith(1);
    await editor.setProps({ dark: false });
    expect(firmware._preview_dark).toHaveBeenLastCalledWith(0);
    useInventoryStore().inventory = { ...useInventoryStore().inventory, language: { setting: "de", effective: "de", ha: "nl", languages: [] } } as any;
    await flushPromises();
    expect(firmware.ccall).toHaveBeenLastCalledWith("preview_language", "number", ["string"], ["de"]);
    // A new inventory in the same language (every few seconds) draws nothing again.
    const spoken = () => firmware.ccall.mock.calls.filter(([name]) => name === "preview_language").length;
    const before = spoken();
    useInventoryStore().inventory = { ...useInventoryStore().inventory, screens: [] } as any;
    await flushPromises();
    expect(spoken()).toBe(before);
  });

  it("shows a screen without a chosen language in English and in its light look", async () => {
    await preview();
    expect(firmware.ccall).toHaveBeenCalledWith("preview_language", "number", ["string"], ["en"]);
    expect(firmware._preview_dark).toHaveBeenLastCalledWith(0);
  });
});
