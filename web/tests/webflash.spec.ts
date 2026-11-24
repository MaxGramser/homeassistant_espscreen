// Installing a screen from this browser (Web Serial): when the page may offer it, how it reads a factory image and the
// chip on the cable, and the order of one installation (ESPHome's install-web dialog). No serial port here: the
// flasher module (esptool-js) is replaced by a stand-in, the port picker by a stub.
import { flushPromises, mount } from "@vue/test-utils";
import { readFileSync } from "node:fs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import FirmwareView from "../src/components/FirmwareView.vue";
import { t } from "../src/i18n";
import { useInventoryStore } from "../src/stores/inventory";
import InstallerView from "../src/components/InstallerView.vue";
import { chipMatches, connectProblem, flashSupport, imageChip, imageRevisions, pickProblem, revisionFits, revisionOf, revisionText, writtenPercent } from "../src/flasher/logic";
import { setFlasherLoader, useBrowserFlash } from "../src/flasher/session";

// A factory image as ESPHome writes it: erased flash (0xFF) up to the bootloader, whose header starts with 0xE9 and
// carries the chip id at byte 12 and the range of chip revisions it runs on at bytes 15 and 17 (ESP-IDF's
// esp_image_header_t), here every revision unless a test says otherwise.
function factoryImage(chipId: number, offset: number, revisions = { min: 0, max: 0xffff }) {
  const data = new Uint8Array(offset + 64).fill(0xff);
  data[offset] = 0xe9;
  data[offset + 12] = chipId & 0xff;
  data[offset + 13] = chipId >> 8;
  data[offset + 15] = revisions.min & 0xff;
  data[offset + 16] = revisions.min >> 8;
  data[offset + 17] = revisions.max & 0xff;
  data[offset + 18] = revisions.max >> 8;
  return data;
}
// What ESP-IDF builds an ESP32-P4 for: the silicon before revision 3, or revision 3 (docs/CHIP_REVISIONS.md).
const P4_PRE_V3 = { min: 0, max: 199 };
const P4_V3 = { min: 300, max: 399 };

function fakePort() {
  return Object.assign(new EventTarget(), { getInfo: () => ({ usbVendorId: 0x1a86 }) }) as unknown as SerialPort;
}

// The flasher module's stand-in: what esptool.ts exports, recording what the session asked of it.
function fakeFlasher(chip = "ESP32", revision: number | null = null) {
  const flasher = {
    createLoader: vi.fn((port: SerialPort) => ({ port })),
    connect: vi.fn(async () => chip),
    readMac: vi.fn(async () => "aa:bb:cc:dd:ee:ff"),
    readRevision: vi.fn(async () => revision),
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
const getPorts = vi.fn(async (): Promise<SerialPort[]> => []);
function secure(on = true, serial = true) {
  Object.defineProperty(window, "isSecureContext", { value: on, configurable: true });
  if (serial) Object.defineProperty(navigator, "serial", { value: { requestPort, getPorts }, configurable: true });
  else delete (navigator as any).serial;
}
// The add-on: the factory image at its relative URL, and an empty answer to everything else.
function addon(image: Uint8Array, extra: (url: string, options: any) => any = () => null) {
  const calls: { url: string; method: string }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, options: any = {}) => {
    calls.push({ url: String(url), method: options.method || "GET" });
    const own = extra(String(url), options);
    if (own) return own;
    if (String(url).endsWith("/download")) return new Response(image as Uint8Array<ArrayBuffer>, { status: 200 });
    return new Response("", { status: 200 });
  }));
  return calls;
}

beforeEach(() => {
  port = fakePort();
  requestPort.mockReset();
  requestPort.mockImplementation(async () => port);
  getPorts.mockReset();
  getPorts.mockImplementation(async () => []);
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
  it("reads the range of chip revisions the image runs on from the same header", () => {
    expect(imageRevisions(factoryImage(18, 0x2000, P4_PRE_V3))).toEqual({ min: 0, max: 199 });
    expect(imageRevisions(factoryImage(18, 0x2000, P4_V3))).toEqual({ min: 300, max: 399 });
    expect(imageRevisions(new Uint8Array(0x3000).fill(0xff))).toBeNull();
  });
  it("tells whether the chip on the cable is one the image runs on, and lets the unknown through", () => {
    expect(revisionFits(302, P4_V3)).toBe(true);
    expect(revisionFits(302, P4_PRE_V3)).toBe(false);
    expect(revisionFits(103, P4_V3)).toBe(false);
    expect(revisionFits(null, P4_V3)).toBe(true);
    expect(revisionFits(302, null)).toBe(true);
  });
  it("reads a revision from esptool-js's description, and writes one as esptool does", () => {
    expect(revisionOf("ESP32-P4 (revision v3.2)")).toBe(302);
    expect(revisionOf("ESP32-D0WD-V3 (revision 3)")).toBeNull();  // the major alone says too little
    expect(revisionText(302)).toBe("v3.2");
    expect(revisionText(199)).toBe("v1.99");
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
    // The board's MAC, read while the port is open: New screen asks the add-on whether Home Assistant knows the board.
    expect(flash.state.mac).toBe("aa:bb:cc:dd:ee:ff");
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

  it("uses the one port the page was given before without the picker, and asks when there are several", async () => {
    fakeFlasher("ESP32-P4");
    addon(factoryImage(18, 0x2000));
    const flash = useBrowserFlash();
    getPorts.mockImplementation(async () => [port]);
    expect(await flash.connect("ESP32-P4")).toBe(true);
    expect(requestPort).not.toHaveBeenCalled();
    getPorts.mockImplementation(async () => [port, fakePort()]);
    expect(await flash.connect("ESP32-P4")).toBe(true);
    expect(requestPort).toHaveBeenCalledOnce();
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

  it("reads the chip's silicon revision, and refuses an image for other revisions before it writes", async () => {
    // A JC4880P443 sold with rev3 silicon and a firmware built for the earlier one: it would write, then stay black.
    const flasher = fakeFlasher("ESP32-P4", 302);
    addon(factoryImage(18, 0x2000, P4_PRE_V3));
    const flash = useBrowserFlash();
    expect(await flash.connect("ESP32-P4")).toBe(true);
    expect(flash.state.revision).toBe(302);
    expect(await flash.install("hall.yaml", true)).toBe(false);
    expect([flash.state.problem, flash.state.params]).toEqual(["wrong_revision", { found: "v3.2", from: "v0.0", to: "v1.99" }]);
    expect(flasher.writeImage).not.toHaveBeenCalled();
    expect(t("editor.webflash.errors.wrong_revision", flash.state.params)).toContain("v3.2");
  });

  it("writes an image built for the chip's revision", async () => {
    const flasher = fakeFlasher("ESP32-P4", 302);
    addon(factoryImage(18, 0x2000, P4_V3));
    const flash = useBrowserFlash();
    await flash.connect("ESP32-P4");
    expect(await flash.install("hall.yaml", true)).toBe(true);
    expect(flasher.writeImage).toHaveBeenCalledOnce();
  });

  it("goes on without a revision when the chip can't say it", async () => {
    const flasher = fakeFlasher("ESP32-P4");
    flasher.readRevision.mockRejectedValueOnce(new Error("no eFuse"));
    addon(factoryImage(18, 0x2000, P4_PRE_V3));
    const flash = useBrowserFlash();
    await flash.connect("ESP32-P4");
    expect(flash.state.revision).toBeNull();
    expect(await flash.install("hall.yaml", true)).toBe(true);
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
// The wizard's third step, where the way in is chosen (app 0.4.32): past the board and the name.
// New screen up to its last step (app 0.4.103), the cable in this computer: Continue through every question, the name
// where it is asked.
async function toInstall(view: ReturnType<typeof mount>) {
  const at = () => view.find("[data-step]").attributes("data-step");
  for (let i = 0; i < 10 && !at()!.startsWith("connect"); i++) {
    if (at() === "name") await view.find("#friendly_name").setValue("Hall");
    if (at() === "cable") await view.find('input[name="cable"][value="here"]').setValue();
    await view.find("#setup-next").trigger("click");
    await flushPromises();
  }
}
// The steps change with a transition; jsdom runs none, so it is the plain switch here.
const installer = () => mount(InstallerView, { global: { stubs: { transition: true } } });

describe("New screen from this browser", () => {
  const SHAPES = JSON.parse(readFileSync("../screen_manager/app/boards.json", "utf8"));
  const boards = { cyd: { ...SHAPES.cyd, ...SHAPES.cyd.catalog, orientations: SHAPES.cyd.orientations } };
  const flush = async () => { await flushPromises(); await new Promise((done) => setTimeout(done, 0)); await flushPromises(); };
  const build = (state: string) => ({ id: 4, by: "install", file: "hall.yaml", action: "download", state, asked: 1, started: state === "queued" ? null : 2,
    finished: state === "success" ? 3 : null, ...(state === "queued" ? { place: 1, after: "desk.yaml" } : {}) });
  function addonWithBuild(image: Uint8Array) {
    const posted: any[] = [];
    // The build in the add-on's line: it waits its turn behind another screen's first (the add-on's answer), then the line
    // says it is done.
    const calls = addon(image, (url, options) => {
      if (url.endsWith("api/firmware")) {
        return new Response(JSON.stringify({ available: true, ports: [], profiles: [], logs: [], wifi: { state: "ready" }, boards, taken: { nodes: [], prefixes: [] } }));
      }
      if (/api\/firmware\/builds\/\d+\/log$/.test(url)) return new Response(JSON.stringify({ build: build("success"), logs: ["Succeeded: download"] }));
      if (url.endsWith("api/firmware/profiles") && options.method === "POST") {
        posted.push(JSON.parse(options.body));
        return new Response(JSON.stringify({ file: "hall.yaml", api_key: "k", build: build("queued") }));
      }
      return null;
    });
    return { posted, calls };
  }

  it("explains why it can't on a page opened over plain http, and keeps Download", async () => {
    secure(false, false);
    addonWithBuild(new Uint8Array());
    const view = installer();
    await flush();
    await toInstall(view);
    // In this computer, but this browser cannot write a screen: a file to put on it, and why.
    expect(view.find("#target-hint").text()).toBe(t("editor.installer.flow.file_lead"));
    expect(view.find("#install-go").text()).toBe(t("editor.installer.flow.go_download"));
    expect(view.find("#install-go").attributes("disabled")).toBeUndefined();
  });

  it("picks the port on the click, builds with the download target, and installs erased", async () => {
    const flasher = fakeFlasher("ESP32", 301);  // an ESP32 of revision v3.1
    const { posted, calls } = addonWithBuild(factoryImage(0, 0x1000));
    const view = installer();
    await flush();
    await toInstall(view);
    expect(view.find("#here-steps").exists()).toBe(true);
    expect(view.find("#install-go").text()).toBe(t("editor.installer.flow.go_install"));
    await view.find("#install-form").trigger("submit");
    await flushPromises();
    expect(requestPort).toHaveBeenCalledOnce();
    expect(posted[0].target).toBe("download");
    // The first firmware is built for the chip's own silicon (docs/CHIP_REVISIONS.md).
    expect(posted[0].chip_revision).toBe(301);
    // Waiting its turn, the page keeps the port and writes nothing yet.
    expect(view.find("#progress-title").text()).toBe(t("editor.installer.progress.waiting"));
    expect(view.find("#progress-detail").text()).toBe(t("editor.installer.detail.waiting_browser", 1));
    expect(flasher.writeImage).not.toHaveBeenCalled();
    // The page writes the screen itself: no Close that "keeps going" while it has yet to, since closing would let go of the
    // port and nothing would be written, and no word that the window may close.
    expect(view.find("#install-close").exists()).toBe(false);
    expect(view.text()).not.toContain(t("editor.installer.flow.may_close"));
    // The add-on's next live answer: built, and the page writes it.
    useInventoryStore().applyLive({ line: [build("success") as any] });
    await flush();
    await vi.waitFor(() => expect(flasher.writeImage).toHaveBeenCalledOnce());
    expect(flasher.writeImage.mock.calls[0][2]).toBe(true);
    expect(calls.some((call) => call.url === "api/firmware/profiles/hall.yaml/flashed")).toBe(true);
    // On the screen is not the end: it starts and joins the Wi-Fi, and then Home Assistant (app 0.4.103).
    expect(view.find("#progress-title").text()).toBe(t("editor.installer.flow.now.wifi", { name: "Hall" }));
    expect(view.find('#follow-steps [data-step="write"]').classes()).toContain("done");
  });

  it("installs a board Home Assistant already has again inside the wizard, on the port it holds, without wiping", async () => {
    // The board on the cable is a screen of this app's already (its MAC, app 0.4.96): "Install it again" finishes here,
    // with that screen's own profile, built for the chip on the cable, instead of sending the person to Firmware & USB.
    const flasher = fakeFlasher("ESP32", 301);
    const jobs: any[] = [];
    const again = { id: 7, by: "install", file: "tablet.yaml", action: "download", asked: 1 };
    const { posted } = addonWithBuild(factoryImage(0, 0x1000));
    const calls = addon(factoryImage(0, 0x1000), (url, options) => {
      if (url.endsWith("api/firmware")) {
        return new Response(JSON.stringify({ available: true, ports: [], profiles: [], logs: [], wifi: { state: "ready" }, boards, taken: { nodes: [], prefixes: [] } }));
      }
      if (url.includes("api/boards/known")) {
        return new Response(JSON.stringify({ known: true, mac: "aa:bb:cc:dd:ee:ff", name: "Tablet", node: "tablet", file: "tablet.yaml",
          screen: "text.tablet_tile_settings", device_id: "d1", entries: ["E1"] }));
      }
      if (url.endsWith("api/firmware/jobs") && options.method === "POST") {
        jobs.push(JSON.parse(options.body));
        return new Response(JSON.stringify({ ...again, state: "queued", place: 0 }));
      }
      if (/api\/firmware\/builds\/\d+\/log$/.test(url)) return new Response(JSON.stringify({ build: { ...again, state: "success" }, logs: [] }));
      return null;
    });
    const view = installer();
    await flush();
    await toInstall(view);
    await view.find("#install-form").trigger("submit");
    await flush();
    expect(view.find("#known-board").exists()).toBe(true);
    await view.find("#known-keep").trigger("click");
    await flush();
    // That screen's own profile, for the chip that was read, and no new profile.
    expect(jobs).toEqual([{ file: "tablet.yaml", action: "download", chip_revision: 301 }]);
    expect(posted).toEqual([]);
    expect(calls.some((call) => call.url.endsWith("api/firmware/profiles") && call.method === "POST")).toBe(false);
    useInventoryStore().applyLive({ line: [{ ...again, state: "success", started: 2, finished: 3 } as any] });
    await flush();
    await vi.waitFor(() => expect(flasher.writeImage).toHaveBeenCalledOnce());
    expect(flasher.writeImage.mock.calls[0][2]).toBe(false);
    expect(requestPort).toHaveBeenCalledOnce();  // the port picked on Install is the one written to
  });

  it("writes nothing and makes no profile for a board of another chip", async () => {
    fakeFlasher("ESP32-S3");
    const { posted } = addonWithBuild(factoryImage(9, 0));
    const view = installer();
    await flush();
    await toInstall(view);
    await view.find("#install-form").trigger("submit");
    await flush();
    expect(posted).toEqual([]);
    expect(view.find("#webflash-line").text()).toContain("ESP32-S3");
  });
});

// Firmware & USB: reinstall or rescue a screen from this browser, keeping its settings (no erase).
// Firmware & USB fills in the address a paired screen's Update goes to (PR #143), until the person types another.
describe("Firmware & USB fills in a paired screen's address", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  function pairedProfiles() {
    const status = { available: true, ports: [], logs: [], job: null, wifi: { state: "ready" }, boards: {},
      profiles: [{ file: "hall.yaml", host: "192.0.2.10" }, { file: "office.yaml", host: "192.0.2.20" }, { file: "spare.yaml" }] as { file: string; host?: string }[] };
    const posted: any[] = [];
    addon(factoryImage(0, 0x1000), (url, options) => {
      if (url.endsWith("api/firmware")) return new Response(JSON.stringify(status));
      if (url.includes("api/inventory")) return new Response(JSON.stringify({ screens: [], line: [] }));
      if (url.endsWith("api/firmware/jobs") && options.method === "POST") {
        posted.push(JSON.parse(options.body));
        return new Response(JSON.stringify({ id: 4, by: "install", ...JSON.parse(options.body), state: "queued" }));
      }
      return null;
    });
    return { status, posted };
  }
  const hostField = (view: ReturnType<typeof mount>) => (view.get("#firmware-host").element as HTMLInputElement).value;

  it("fills in and sends the chosen profile's address, and none for a profile it has none for", async () => {
    const { posted } = pairedProfiles();
    const view = mount(FirmwareView);
    await flushPromises();
    expect(hostField(view)).toBe("192.0.2.10");
    await view.get("#firmware-file").setValue("office.yaml");
    expect(hostField(view)).toBe("192.0.2.20");
    await view.get("#firmware-install").trigger("click");
    await flushPromises();
    expect(posted).toEqual([{ file: "office.yaml", action: "install", target: "192.0.2.20" }]);
    await view.get("#firmware-file").setValue("spare.yaml");
    expect(hostField(view)).toBe("");
  });

  it("follows a new address until one is typed, which stays with its profile, an emptied field too", async () => {
    const { status } = pairedProfiles();
    const view = mount(FirmwareView);
    await flushPromises();
    status.profiles[0].host = "192.0.2.11";
    await vi.advanceTimersByTimeAsync(3000);
    await flushPromises();
    expect(hostField(view)).toBe("192.0.2.11");
    await view.get("#firmware-host").setValue("hall.example.test");
    status.profiles[0].host = "192.0.2.12";
    await vi.advanceTimersByTimeAsync(3000);
    await flushPromises();
    expect(hostField(view)).toBe("hall.example.test");
    await view.get("#firmware-file").setValue("office.yaml");
    expect(hostField(view)).toBe("192.0.2.20");
    await view.get("#firmware-file").setValue("hall.yaml");
    expect(hostField(view)).toBe("hall.example.test");
    await view.get("#firmware-host").setValue("");
    await vi.advanceTimersByTimeAsync(3000);
    await flushPromises();
    expect(hostField(view)).toBe("");
  });
});

describe("Firmware & USB from this browser", () => {
  it("builds the profile, then writes it without erasing", async () => {
    const flasher = fakeFlasher("ESP32", 301);
    let job: any = null;
    addon(factoryImage(0, 0x1000), (url, options) => {
      if (url.endsWith("api/firmware")) {
        return new Response(JSON.stringify({ available: true, ports: [], logs: [], wifi: { state: "ready" }, boards: {},
          profiles: [{ file: "hall.yaml", chip: "ESP32" }], job }));
      }
      // The live inventory carries the build line.
      if (url.includes("api/inventory")) return new Response(JSON.stringify({ screens: [], line: job ? [job] : [] }));
      if (/api\/firmware\/builds\/\d+\/log$/.test(url)) return new Response(JSON.stringify({ build: job, logs: [] }));
      if (url.endsWith("api/firmware/jobs") && options.method === "POST") {
        job = { id: 9, by: "install", ...JSON.parse(options.body), state: "success", asked: 6, started: 7, finished: 8 };
        return new Response(JSON.stringify({ ...job, state: "running", finished: null }));
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
    expect(job.chip_revision).toBe(301);
    expect(flasher.writeImage).toHaveBeenCalledOnce();
    expect(flasher.writeImage.mock.calls[0][2]).toBe(false);
    expect(view.find("#webflash-line").text()).toContain("Installed");
  });
});
