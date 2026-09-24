import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import FirmwarePreview from "../src/components/FirmwarePreview.vue";
import createModule from "../src/wasm/firmware_preview.js";
import { send } from "../src/api";
import { state } from "../src/store";

vi.mock("../src/wasm/firmware_preview.js", () => ({ default: vi.fn() }));
vi.mock("../src/api", () => ({ send: vi.fn() }));
vi.mock("../src/store", async () => {
  const { reactive } = await import("vue");
  return { state: reactive({ document: { title: "Test panel", pages: [] }, liveStates: {} }) };
});
const bundle = () => ({ revision: "1111111111111111", configuration: [{ op: "begin" }, { op: "commit" }], values: [{ op: "state", i: 0, state: "on" }] });
function response(name: string, _result?: unknown, _types?: unknown, args?: unknown[]) {
  if (name === "preview_next_action") return "";
  if (name === "preview_receive" && JSON.parse(String(args?.[0])).op === "hello") return "Session:2222222222222222";
  return "Synced";
}

const firmware = {
  HEAPU8: new Uint8Array(800 * 800 * 4),
  _preview_init: vi.fn(() => 1), _preview_time: vi.fn(),
  _preview_render: vi.fn(), _preview_frame: vi.fn(() => 0),
  _preview_touch: vi.fn(), _preview_cancel: vi.fn(), ccall: vi.fn(response),
};
let wrapper: VueWrapper | undefined;
let putImageData: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
  vi.clearAllMocks();
  firmware.ccall.mockImplementation(response);
  state.document = { title: "Test panel", pages: [] } as any;
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

async function preview(width = 720, height = 720) {
  wrapper = mount(FirmwarePreview, { attachTo: document.body, props: { width, height, columns: 2, rows: 3, pages: 3 } });
  await flushPromises();
  return wrapper;
}

describe("Firmware preview transport", () => {
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
    state.document!.title = "Updated panel";
    await flushPromises();
    expect(vi.mocked(send).mock.lastCall?.[2]).toMatchObject({ layout: { title: "Updated panel", pages: [] } });
    expect(createModule).toHaveBeenCalledTimes(1);
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
});
