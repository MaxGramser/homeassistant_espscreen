// A board's own steps in the editor (docs/BOARD_STEPS.md): the frames a page speaks to a board's second chip, which are
// chip_protocol.h's (tests/test_chip_protocol.cpp proves the screen's and the chip's side), the checks before a file
// is written, the card above a screen, and the step of the kind chip_firmware from its first click to "the screen found
// it", with the browser's ports and folders played by flasher/chip.ts's stand-in.
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import BoardStepCard from "../src/components/BoardStepCard.vue";
import BoardStepView from "../src/components/steps/BoardStepView.vue";
import { t } from "../src/i18n";
import { chipSupport, cobsDecode, cobsEncode, crc16, frame, HELLO, HELLO_BACK, isChipDrive, isChipPort, isUf2, readFrames, stepsLeft, stepsToDo,
  versionOfHello } from "../src/model/board-steps";
import type { ChipFirmwareStep, Screen } from "../src/types";

const flasher = vi.hoisted(() => ({
  chipPort: vi.fn(), knownChipPort: vi.fn(), restartAsDrive: vi.fn(), askChip: vi.fn(), tryChip: vi.fn(), pickFolder: vi.fn(), driveInfo: vi.fn(), writeToDrive: vi.fn(),
}));
vi.mock("../src/flasher/chip", () => flasher);

const FILE = new Uint8Array(1024);
for (const at of [0, 512]) {
  const view = new DataView(FILE.buffer);
  view.setUint32(at, 0x0a324655, true); view.setUint32(at + 4, 0x9e5d5157, true); view.setUint32(at + 508, 0x0ab16f30, true);
}
const step = (changes: Partial<ChipFirmwareStep> = {}): ChipFirmwareStep => ({
  id: "buzzer", kind: "chip_firmware", state: "open", found: "", chip: "indicator-rp2040", version: "1.0.0", size: FILE.length,
  file: "api/chips/indicator-rp2040/firmware", download: "tessera-indicator-rp2040-1.0.0.uf2", usb: [{ vendor: 0x2886, product: 0x0050 }], drive: "RPI-RP2", ...changes,
});
const screen = (changes: Partial<Screen> = {}): Screen =>
  ({ id: "hall", name: "Hall", online: true, board: "sensecapd1", layout: { title: "Hall", tiles: [] }, feedback: null, plugin_ask: null, plugin_suggest: null, steps: [step()], ...changes }) as unknown as Screen;

type Call = { url: string; method: string; body: any };
let calls: Call[] = [];
// What the add-on says of the step when the screen is asked: open until the test says the screen found the chip.
let found = "";
beforeEach(() => {
  setActivePinia(createPinia());
  calls = [];
  found = "";
  Object.values(flasher).forEach((fn) => fn.mockReset());
  vi.stubGlobal("isSecureContext", true);
  vi.stubGlobal("showDirectoryPicker", () => undefined);
  Object.defineProperty(navigator, "serial", { value: {}, configurable: true });
  vi.stubGlobal("fetch", vi.fn((url: string, init: RequestInit = {}) => {
    calls.push({ url: String(url), method: init.method || "GET", body: init.body ? JSON.parse(String(init.body)) : null });
    if (String(url) === "api/chips/indicator-rp2040/firmware") return Promise.resolve(new Response(FILE, { status: 200 }));
    if (String(url).endsWith("/steps")) return Promise.resolve(new Response(JSON.stringify({ steps: [step(found ? { state: "done", found } : {})] }), { status: 200 }));
    return Promise.resolve(new Response(JSON.stringify({ screens: [], entities: [] }), { status: 200 }));
  }));
});
const posts = () => calls.filter((c) => c.method === "POST").map((c) => [c.url.replace(/^.*api\//, ""), c.body]);

describe("the frames a page speaks to the chip", () => {
  it("are chip_protocol.h's, byte for byte", () => {
    expect(crc16(new TextEncoder().encode("123456789"))).toBe(0x29b1);
    // The same frames tools/chip.py makes: a hello, and a chip's answer.
    expect([...frame(HELLO)]).toEqual([4, 1, 241, 209, 0]);
    expect([...frame(HELLO_BACK, Uint8Array.from([1, 1, 0, 0, 1, 0, 0x80, 0x34, 0x12]))]).toEqual([4, 129, 1, 1, 1, 2, 1, 6, 128, 52, 18, 172, 145, 0]);
    const hello = frame(HELLO);
    expect(hello[hello.length - 1]).toBe(0);
    expect([...hello.subarray(0, -1)]).not.toContain(0);
    const answer = frame(HELLO_BACK, Uint8Array.from([1, 1, 0, 0, 1, 0, 0x80, 0x34, 0x12]));
    const { frames, rest } = readFrames(Uint8Array.from([...hello, ...answer, 7, 7]));
    expect(frames.map((one) => one.type)).toEqual([HELLO, HELLO_BACK]);
    expect([...rest]).toEqual([7, 7]);
    expect(versionOfHello(frames[1].payload)).toBe("1.0.0");
    expect(versionOfHello(Uint8Array.from([1, 2]))).toBeNull();
  });
  it("come back whatever they hold, and a damaged one is dropped", () => {
    for (const length of [0, 1, 253, 254, 255, 600]) {
      const data = Uint8Array.from({ length }, (_, i) => (i % 5 ? i * 7 + 1 : 0));
      expect([...cobsDecode(cobsEncode(data))!]).toEqual([...data]);
      expect([...cobsEncode(data)]).not.toContain(0);
    }
    const bad = frame(HELLO_BACK, Uint8Array.from([1, 1, 0, 0, 1, 0, 0x80]));
    bad[2] ^= 0x10;
    expect(readFrames(bad).frames).toEqual([]);
    expect(cobsDecode(Uint8Array.from([5, 1]))).toBeNull();
  });
});

describe("the checks before anything is written", () => {
  it("takes only a whole UF2 file of the size the add-on named", () => {
    expect(isUf2(FILE, FILE.length)).toBe(true);
    expect(isUf2(FILE, 2048)).toBe(false);
    expect(isUf2(FILE.subarray(0, 700), 700)).toBe(false);
    expect(isUf2(new Uint8Array(512), 512)).toBe(false);
    expect(isUf2(new Uint8Array(), 0)).toBe(false);
  });
  it("takes only the chip's own drive and port", () => {
    expect(isChipDrive("UF2 Bootloader v3.0\nModel: Raspberry Pi RP2\nBoard-ID: RPI-RP2\n", "RPI-RP2")).toBe(true);
    expect(isChipDrive("Board-ID: OTHER\n", "RPI-RP2")).toBe(false);
    expect(isChipDrive(null, "RPI-RP2")).toBe(false);
    expect(isChipPort({ usbVendorId: 0x2886, usbProductId: 0x0050 }, step())).toBe(true);
    expect(isChipPort({ usbVendorId: 0x1a86, usbProductId: 0x7523 }, step())).toBe(false);
    expect(isChipPort(undefined, step())).toBe(false);
  });
  it("knows whether this page can do it: a secure page with a serial port and a folder picker", () => {
    expect(chipSupport({ isSecureContext: true, navigator: { serial: {} }, showDirectoryPicker: () => 0 })).toBe("ok");
    expect(chipSupport({ isSecureContext: false, navigator: { serial: {} }, showDirectoryPicker: () => 0 })).toBe("insecure");
    expect(chipSupport({ isSecureContext: true, navigator: {}, showDirectoryPicker: () => 0 })).toBe("browser");
    expect(chipSupport({ isSecureContext: true, navigator: { serial: {} } })).toBe("browser");
  });
  it("brings up what is open or newer, and lists what is put off too", () => {
    const steps = [step(), step({ id: "b", state: "later" }), step({ id: "c", state: "done" }), step({ id: "d", state: "update" })];
    expect(stepsToDo({ steps }).map((one) => one.id)).toEqual(["buzzer", "d"]);
    expect(stepsLeft({ steps }).map((one) => one.id)).toEqual(["buzzer", "b", "d"]);
    expect(stepsToDo(null)).toEqual([]);
  });
});

describe("the card above a screen", () => {
  it("offers the step in its own words, and waits for the other cards and an offline screen", () => {
    const card = mount(BoardStepCard, { props: { screen: screen() } });
    expect(card.find("#board-step-card-title").text()).toBe(t("editor.steps.buzzer.title"));
    expect(card.find("#board-step-set-up").text()).toBe(t("editor.steps.set_up"));
    for (const changes of [{ online: false }, { feedback: { ask: true } as any }, { plugin_ask: { plugin: "x" } as any }, { plugin_suggest: { plugins: [] } as any },
      { steps: [step({ state: "done" })] }, { steps: [step({ state: "later" })] }, { steps: [step({ kind: "unheard_of" } as any)] }, { steps: undefined }])
      expect(mount(BoardStepCard, { props: { screen: screen(changes) } }).find("#board-step-card").exists()).toBe(false);
  });
  it("offers a newer one of what is done, without a way to put it off for good", () => {
    const card = mount(BoardStepCard, { props: { screen: screen({ steps: [step({ state: "update", found: "0.9.0" })] }) } });
    expect(card.find("#board-step-card-title").text()).toBe(t("editor.steps.buzzer.update_title"));
    expect(card.find("#board-step-set-up").text()).toBe(t("editor.steps.update"));
    expect(card.find("#board-step-not-now").exists()).toBe(false);
  });
  it("asks the page to open the step, and tells the add-on a not now", async () => {
    const card = mount(BoardStepCard, { props: { screen: screen() } });
    await card.find("#board-step-set-up").trigger("click");
    expect(card.emitted("open")).toEqual([["buzzer"]]);
    expect(posts()).toEqual([]);
    await card.find("#board-step-not-now").trigger("click");
    await flushPromises();
    expect(posts()).toEqual([["screens/hall/steps/buzzer", { answer: "later" }]]);
  });
});

describe("writing a chip's firmware from the page", () => {
  const page = (changes: Partial<Screen> = {}) => mount(BoardStepView, { props: { step: step(), screen: screen(changes) } });
  const words = (key: string, more = {}) => t(`editor.steps.kinds.chip_firmware.${key}`, { drive: "RPI-RP2", version: "1.0.0", name: step().download, ...more });

  it("goes from the first click to the screen that found the chip", async () => {
    vi.useFakeTimers();
    const port = {}, folder = {};
    flasher.chipPort.mockResolvedValue(port);
    flasher.restartAsDrive.mockResolvedValue(undefined);
    flasher.pickFolder.mockResolvedValue(folder);
    flasher.driveInfo.mockResolvedValue("Board-ID: RPI-RP2\n");
    flasher.writeToDrive.mockResolvedValue(undefined);
    flasher.knownChipPort.mockResolvedValue(port);
    flasher.askChip.mockResolvedValue("1.0.0");
    const view = page();
    expect(view.find("h1").text()).toBe(t("editor.steps.buzzer.title"));
    expect(view.find("#step-go").text()).toBe(words("go"));
    // The first click: the chip's port, and the chip restarted as a drive. Nothing is written yet.
    await view.find("#step-go").trigger("click");
    await flushPromises();
    expect(flasher.restartAsDrive).toHaveBeenCalledWith(port);
    expect(view.find("#step-now").text()).toBe(words("phase.drive"));
    expect(flasher.writeToDrive).not.toHaveBeenCalled();
    // The second: the drive, and the file the add-on has, under its own name.
    await view.find("#step-drive").trigger("click");
    await flushPromises();
    expect(flasher.writeToDrive).toHaveBeenCalledWith(folder, step().download, expect.any(Uint8Array));
    expect((flasher.writeToDrive.mock.calls[0][2] as Uint8Array).length).toBe(FILE.length);
    // The chip answers over its port before the screen has found it.
    await vi.advanceTimersByTimeAsync(1600);
    await flushPromises();
    expect(view.find("#step-now").text()).toBe(words("phase.wait_chip"));
    expect(view.find("#step-done").exists()).toBe(false);
    // The screen found it: done, with the way on and the chip's own sound to hear.
    found = "1.0.0";
    await vi.advanceTimersByTimeAsync(1600);
    await flushPromises();
    expect(view.find("#step-done").text()).toContain(words("done"));
    expect(view.find("h1").text()).toBe(t("editor.steps.buzzer.done_title"));
    await view.find("#step-try").trigger("click");
    await flushPromises();
    expect(flasher.tryChip).toHaveBeenCalledWith(port);
    await view.find("#board-step-next").trigger("click");
    expect(view.emitted("next")).toHaveLength(1);
    vi.useRealTimers();
  });

  it("writes nothing to a folder that is not the chip's drive, and asks again", async () => {
    flasher.chipPort.mockResolvedValue({});
    flasher.restartAsDrive.mockResolvedValue(undefined);
    flasher.pickFolder.mockResolvedValue({});
    flasher.driveInfo.mockResolvedValue(null);
    const view = page();
    await view.find("#step-go").trigger("click");
    await flushPromises();
    await view.find("#step-drive").trigger("click");
    await flushPromises();
    expect(view.find("#step-wrong-drive").text()).toContain(words("wrong_drive"));
    expect(flasher.writeToDrive).not.toHaveBeenCalled();
    expect(view.find("#step-drive").exists()).toBe(true);
  });

  it("says why when no port was chosen, and takes a drive that is there already", async () => {
    flasher.chipPort.mockRejectedValue(new Error("No port selected by the user."));
    const view = page();
    await view.find("#step-go").trigger("click");
    await flushPromises();
    expect(view.find("#step-problem").text()).toContain(words("errors.no_port"));
    expect(flasher.restartAsDrive).not.toHaveBeenCalled();
    await view.find("#step-drive-there").trigger("click");
    await flushPromises();
    expect(view.find("#step-drive").exists()).toBe(true);
  });

  it("says so when the screen never finds the chip", async () => {
    vi.useFakeTimers();
    flasher.chipPort.mockResolvedValue({});
    flasher.restartAsDrive.mockResolvedValue(undefined);
    flasher.pickFolder.mockResolvedValue({});
    flasher.driveInfo.mockResolvedValue("Board-ID: RPI-RP2\n");
    flasher.writeToDrive.mockResolvedValue(undefined);
    flasher.knownChipPort.mockResolvedValue(null);
    const view = page();
    await view.find("#step-go").trigger("click");
    await flushPromises();
    await view.find("#step-drive").trigger("click");
    await flushPromises();
    await vi.advanceTimersByTimeAsync(50000);
    await flushPromises();
    expect(view.find("#step-problem").text()).toContain(words("errors.silent"));
    expect(view.find("#step-again").exists()).toBe(true);
    vi.useRealTimers();
  });

  it("is put off with Later, which the page that holds it keeps", async () => {
    const view = page();
    await view.find("#board-step-later").trigger("click");
    expect(view.emitted("later")).toHaveLength(1);
    expect(posts()).toEqual([]);
  });

  it("goes by hand where the browser has no USB port: the file, the steps, and the wait for the screen", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("showDirectoryPicker", undefined);
    const view = page();
    expect(view.find("#step-go").exists()).toBe(false);
    expect(view.find("#step-by-hand").text()).toContain(words("hand.browser"));
    expect(view.find("#step-download").attributes("href")).toBe(step().file);
    expect(view.find("#step-download").attributes("download")).toBe(step().download);
    expect(view.find("#step-hand-steps").text()).toContain(t("editor.steps.buzzer.button"));
    await view.find("#step-did").trigger("click");
    found = "1.0.0";
    await vi.advanceTimersByTimeAsync(1600);
    await flushPromises();
    expect(view.find("#step-done").exists()).toBe(true);
    expect(view.find("#step-try").exists()).toBe(false);
    vi.useRealTimers();
  });
});
