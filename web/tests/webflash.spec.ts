// Installing a screen from this browser (Web Serial): when the page may offer it, how it reads a factory image and the
// chip on the cable, and the order of one installation (ESPHome's install-web dialog). No serial port here: the
// flasher module (esptool-js) is replaced by a stand-in, the port picker by a stub.
import { flushPromises, mount } from "@vue/test-utils";
import { readFileSync } from "node:fs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import FirmwareView from "../src/components/FirmwareView.vue";
import InstallerView from "../src/components/InstallerView.vue";
import { chipMatches, connectProblem, flashSupport, imageChip, pickProblem, writtenPercent } from "../src/flasher/logic";
import { setFlasherLoader, useBrowserFlash } from "../src/flasher/session";

// A factory image as ESPHome writes it: erased flash (0xFF) up to the bootloader, whose header starts with 0xE9 and
// carries the chip id at byte 12.
function factoryImage(chipId: number, offset: number) {
  const data = new Uint8Array(offset + 64).fill(0xff);
  data[offset] = 0xe9;
  data[offset + 12] = chipId & 0xff;
  data[offset + 13] = chipId >> 8;
  return data;
}

function fakePort() {
  return Object.assign(new EventTarget(), { getInfo: () => ({ usbVendorId: 0x1a86 }) }) as unknown as SerialPort;
}

// The flasher module's stand-in: what esptool.ts exports, recording what the session asked of it.
function fakeFlasher(chip = "ESP32") {
  const flasher = {
    createLoader: vi.fn((port: SerialPort) => ({ port })),
    connect: vi.fn(async () => chip),
    writeImage: vi.fn(async (_loader: unknown, _data: Uint8Array, erase: boolean, onErase: () => void, onProgress: (p: number) => void) => {
      if (erase) onErase();
      onProgress(0);
      onProgress(42);
      onProgress(100);
    }),
    restart: vi.fn(async () => {}),
    disconnect: vi.fn(async () => {}),
  };
  setFlasherLoader(async () => flasher as any);
  return flasher;
}

let port: SerialPort;
const requestPort = vi.fn();
function secure(on = true, serial = true) {
  Object.defineProperty(window, "isSecureContext", { value: on, configurable: true });
  if (serial) Object.defineProperty(navigator, "serial", { value: { requestPort }, configurable: true });
  else delete (navigator as any).serial;
}
// The add-on: the factory image at its relative URL, and an empty answer to everything else.
function addon(image: Uint8Array, extra: (url: string, options: any) => any = () => null) {
  const calls: { url: string; method: string }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, options: any = {}) => {
    calls.push({ url: String(url), method: options.method || "GET" });
    const own = extra(String(url), options);
    if (own) return own;
    if (String(url).endsWith("/download")) return new Response(image, { status: 200 });
    return new Response("", { status: 200 });
  }));
  return calls;
}

beforeEach(() => {
  port = fakePort();
  requestPort.mockReset();
  requestPort.mockImplementation(async () => port);
  secure();
});
afterEach(() => {
  vi.unstubAllGlobals();
  delete (navigator as any).serial;
});

describe("when the page may install from the browser", () => {
  it("needs https first, then a browser with Web Serial", () => {
    expect(flashSupport({ isSecureContext: false, navigator: { serial: {} } })).toBe("insecure");
    // Chrome hides navigator.serial on plain http too: the cure there is https, not another browser.
    expect(flashSupport({ isSecureContext: false, navigator: {} })).toBe("insecure");
    expect(flashSupport({ isSecureContext: true, navigator: {} })).toBe("browser");
    expect(flashSupport({ isSecureContext: true, navigator: { serial: {} } })).toBe("ok");
  });
});

describe("reading a factory image", () => {
  it("finds the chip in the bootloader's header wherever the chip keeps it", () => {
    expect(imageChip(factoryImage(0, 0x1000))).toBe("ESP32");
    expect(imageChip(factoryImage(9, 0x0))).toBe("ESP32-S3");
    expect(imageChip(factoryImage(18, 0x2000))).toBe("ESP32-P4");
  });
  it("says nothing about a file it can't read", () => {
    expect(imageChip(new Uint8Array(0))).toBeNull();
    expect(imageChip(new Uint8Array(0x3000).fill(0xff))).toBeNull();
    expect(imageChip(factoryImage(99, 0))).toBeNull();
  });
  it("compares chips by esptool's names and lets an unknown expectation through", () => {
    expect(chipMatches("ESP32-S3", "esp32-s3")).toBe(true);
    expect(chipMatches("ESP32", "ESP32-S3")).toBe(false);
    expect(chipMatches("ESP32", null)).toBe(true);
  });
  it("sums the progress as ESPHome does, leaving the last report to the final 100", () => {
    expect(writtenPercent(0, 100)).toBe(0);
    expect(writtenPercent(505, 1000)).toBe(50);
    expect(writtenPercent(1000, 1000)).toBeNull();
    expect(writtenPercent(5, 0)).toBeNull();
  });
  it("tells a closed picker from a blocked one, and a busy port from a silent board", () => {
    expect(pickProblem(new DOMException("No port selected by the user.", "NotFoundError"))).toBe("no_port");
    expect(pickProblem(new DOMException("blocked", "SecurityError"))).toBe("blocked");
    expect(connectProblem(new DOMException("Failed to open serial port.", "NetworkError"))).toBe("busy");
    expect(connectProblem(new DOMException("The port is already open.", "InvalidStateError"))).toBe("busy");
    expect(connectProblem(new Error("Failed to connect with the device"))).toBe("connect");
  });
});

describe("one installation from the browser", () => {
  it("writes the image it fetched from the add-on, restarts the screen and tells the add-on", async () => {
    const flasher = fakeFlasher("ESP32-S3");
    const calls = addon(factoryImage(9, 0));
    const flash = useBrowserFlash();
    expect(await flash.connect("ESP32-S3")).toBe(true);
    expect(flash.state.phase).toBe("waiting");
    expect(flash.state.chip).toBe("ESP32-S3");
    expect(await flash.install("hall.yaml", false)).toBe(true);
    expect(flash.state.phase).toBe("done");
    expect(flasher.writeImage.mock.calls[0][2]).toBe(false);
    expect(flasher.writeImage.mock.calls[0][1]).toEqual(factoryImage(9, 0));
    expect(flasher.restart).toHaveBeenCalledOnce();
    expect(flasher.disconnect).toHaveBeenCalled();
    // Relative URLs, for Home Assistant's ingress path.
    expect(calls).toEqual([{ url: "api/firmware/profiles/hall.yaml/download", method: "GET" },
      { url: "api/firmware/profiles/hall.yaml/flashed", method: "POST" }]);
  });

  it("builds nothing when the picker is closed without a port, and says what to check", async () => {
    const flasher = fakeFlasher();
    requestPort.mockRejectedValue(new DOMException("No port selected by the user.", "NotFoundError"));
    const flash = useBrowserFlash();
    expect(await flash.connect("ESP32")).toBe(false);
    expect(flash.state.phase).toBe("failed");
    expect(flash.state.problem).toBe("no_port");
    expect(flasher.createLoader).not.toHaveBeenCalled();
  });

  it("refuses a board of another chip before anything is built", async () => {
    const flasher = fakeFlasher("ESP32");
    const flash = useBrowserFlash();
    expect(await flash.connect("ESP32-S3")).toBe(false);
    expect([flash.state.problem, flash.state.params]).toEqual(["wrong_chip", { found: "ESP32", expected: "ESP32-S3" }]);
    expect(flasher.disconnect).toHaveBeenCalled();
  });

  it("refuses an image built for another chip than the one on the cable, and writes nothing", async () => {
    const flasher = fakeFlasher("ESP32");
    addon(factoryImage(18, 0x2000));
    const flash = useBrowserFlash();
    await flash.connect(null);  // a profile of no known board: the image itself is the check
    expect(await flash.install("custom.yaml", false)).toBe(false);
    expect([flash.state.problem, flash.state.params]).toEqual(["wrong_image", { found: "ESP32", expected: "ESP32-P4" }]);
    expect(flasher.writeImage).not.toHaveBeenCalled();
  });

  it("says a port another program holds is busy, and a silent board needs its BOOT button", async () => {
    const flasher = fakeFlasher();
    flasher.connect.mockRejectedValueOnce(new DOMException("Failed to open serial port.", "NetworkError"));
    const flash = useBrowserFlash();
    expect(await flash.connect("ESP32")).toBe(false);
    expect(flash.state.problem).toBe("busy");
    flasher.connect.mockRejectedValueOnce(new Error("Failed to connect with the device"));
    expect(await flash.connect("ESP32")).toBe(false);
    expect(flash.state.problem).toBe("connect");
  });

  it("notices a cable pulled out while the add-on builds", async () => {
    fakeFlasher();
    const flash = useBrowserFlash();
    await flash.connect("ESP32");
    port.dispatchEvent(new Event("disconnect"));
    expect([flash.state.phase, flash.state.problem]).toEqual(["failed", "disconnected"]);
    expect(await flash.install("hall.yaml", true)).toBe(false);
  });

  it("reports a failed write, and doesn't take the restart's own disconnect for one", async () => {
    const flasher = fakeFlasher();
    addon(factoryImage(0, 0x1000));
    flasher.writeImage.mockRejectedValueOnce(new Error("Timeout"));
    const flash = useBrowserFlash();
    await flash.connect("ESP32");
    expect(await flash.install("hall.yaml", true)).toBe(false);
    expect([flash.state.problem, flash.state.params.error]).toEqual(["failed", "Timeout"]);
    // Again, and this time the chip drops off the bus as it restarts.
    await flash.connect("ESP32");
    flasher.restart.mockImplementationOnce(async () => { port.dispatchEvent(new Event("disconnect")); });
    expect(await flash.install("hall.yaml", true)).toBe(true);
    expect(flash.state.phase).toBe("done");
  });
});

// New screen: This computer builds as Download does, then writes the image from the page, erased first.
describe("New screen from this browser", () => {
  const SHAPES = JSON.parse(readFileSync("../screen_manager/app/boards.json", "utf8"));
  const boards = { cyd: { ...SHAPES.cyd, ...SHAPES.cyd.catalog, orientations: SHAPES.cyd.orientations } };
  const flush = async () => { await flushPromises(); await new Promise((done) => setTimeout(done, 0)); await flushPromises(); };
  function addonWithBuild(image: Uint8Array) {
    const posted: any[] = [];
    const calls = addon(image, (url, options) => {
      if (url.endsWith("api/firmware")) {
        return new Response(JSON.stringify({ available: true, ports: [], profiles: [], logs: [], wifi: { state: "ready" }, boards, taken: { nodes: [], prefixes: [] } }));
      }
      if (url.endsWith("api/firmware/profiles") && options.method === "POST") {
        posted.push(JSON.parse(options.body));
        // The build is quick here: the job comes back done, as the next poll would report it.
        return new Response(JSON.stringify({ file: "hall.yaml", api_key: "k", job: { file: "hall.yaml", action: "download", state: "success" } }));
      }
      return null;
    });
    return { posted, calls };
  }

  it("explains why it can't on a page opened over plain http, and keeps Download", async () => {
    secure(false, false);
    addonWithBuild(new Uint8Array());
    const view = mount(InstallerView);
    await flush();
    await view.find("#install-target").setValue("browser");
    expect(view.find("#target-hint").text()).toContain("https");
    expect(view.find("#install-go").attributes("disabled")).toBeDefined();
    expect(view.find('#install-target option[value="download"]').exists()).toBe(true);
  });

  it("picks the port on the click, builds with the download target, and installs erased", async () => {
    const flasher = fakeFlasher("ESP32");
    const { posted, calls } = addonWithBuild(factoryImage(0, 0x1000));
    const view = mount(InstallerView);
    await flush();
    await view.find("#install-target").setValue("browser");
    expect(view.find("#install-go").text()).toBe("Connect & install");
    await view.find("#friendly_name").setValue("Hall");
    await view.find("#install-form").trigger("submit");
    await flush();
    expect(requestPort).toHaveBeenCalledOnce();
    expect(posted[0].target).toBe("download");
    expect(flasher.writeImage.mock.calls[0][2]).toBe(true);
    expect(calls.some((call) => call.url === "api/firmware/profiles/hall.yaml/flashed")).toBe(true);
    expect(view.find("#progress-title").text()).toContain("Firmware is on Hall");
    expect(view.find("#install-steps").exists()).toBe(true);
  });

  it("writes nothing and makes no profile for a board of another chip", async () => {
    fakeFlasher("ESP32-S3");
    const { posted } = addonWithBuild(factoryImage(9, 0));
    const view = mount(InstallerView);
    await flush();
    await view.find("#install-target").setValue("browser");
    await view.find("#friendly_name").setValue("Hall");
    await view.find("#install-form").trigger("submit");
    await flush();
    expect(posted).toEqual([]);
    expect(view.find("#webflash-line").text()).toContain("ESP32-S3");
  });
});

// Firmware & USB: reinstall or rescue a screen from this browser, keeping its settings (no erase).
describe("Firmware & USB from this browser", () => {
  it("builds the profile, then writes it without erasing", async () => {
    const flasher = fakeFlasher("ESP32");
    let job: any = null;
    addon(factoryImage(0, 0x1000), (url, options) => {
      if (url.endsWith("api/firmware")) {
        return new Response(JSON.stringify({ available: true, ports: [], logs: [], wifi: { state: "ready" }, boards: {},
          profiles: [{ file: "hall.yaml", chip: "ESP32" }], job }));
      }
      if (url.endsWith("api/firmware/jobs") && options.method === "POST") {
        job = { ...JSON.parse(options.body), state: "success", started: 7 };
        return new Response(JSON.stringify({ ...job, state: "running" }));
      }
      return null;
    });
    const view = mount(FirmwareView);
    await flushPromises();
    await view.find("#firmware-port").setValue("browser");
    expect(view.find("#firmware-browser-hint").text()).toContain("keeps its settings");
    await view.find("#firmware-install").trigger("click");
    for (let i = 0; i < 5; i++) await flushPromises();
    expect(job.action).toBe("download");
    expect(flasher.writeImage).toHaveBeenCalledOnce();
    expect(flasher.writeImage.mock.calls[0][2]).toBe(false);
    expect(view.find("#webflash-line").text()).toContain("Installed");
  });
});
