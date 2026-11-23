// New screen's rules (model/installer.ts, install-progress.ts's words, useArrival): the boards a search leaves and their
// families, which way a board hangs and the grids it takes, a name another screen carries, the ways in and what is sent.
import { describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import { areaNames, arrivalOf, ARRIVE_MS, bestGrid, boardFamilies, boardOrientations, boardsMatching, canStep, familyLead, familyOf, familyStatus, familyTiers,
  firstCable, gridRange, installStages, nameClash, portLabel, portName, profileRequest, screenPorts, sizeOfInch, type BoardRow, type InstallForm } from "../src/model/installer";
import { elapsedText, followDetail, journey, type Follow, type Progress } from "../src/model/install-progress";
import { useArrival } from "../src/composables/useArrival";
import { useInventoryStore } from "../src/stores/inventory";
import { inScope } from "./helpers/with-setup";
import type { Inventory } from "../src/types";

const side = (width: number, height: number, columns: number, rows: number, more = {}) => ({ width, height, columns, rows, rotation: 0, ...more });
const board = (key: string, more: Partial<BoardRow> = {}): BoardRow => ({
  key, order: 1, name: "Brand", model: `M-${key}`, status: "stable", inch: 4, touch: "GT911", calibrate: false, choices: {}, square: false,
  orientations: { landscape: side(800, 480, 3, 2, { min: [2, 2], max: [4, 3] }), portrait: side(480, 800, 2, 3) }, width: 800, height: 480, dpi: 170,
  camera: true, dimmable: true, can_standby: true, chip: "ESP32-S3", ...more,
});
const ROWS = [board("a"), board("a2", { model: "M-a rev 2", status: "new" }), board("b", { inch: 2.8, chip: "ESP32", width: 320, height: 240, status: "experimental" }),
  board("c", { name: "Other", inch: 7, model: "BIG-7" })];

describe("which screen", () => {
  it("finds a board by what someone knows of it, and by its size", () => {
    expect(boardsMatching(ROWS, "", "").map((b) => b.key)).toEqual(["a", "a2", "b", "c"]);
    expect(boardsMatching(ROWS, "big", "").map((b) => b.key)).toEqual(["c"]);
    expect(boardsMatching(ROWS, "2,8 inch", "").map((b) => b.key)).toEqual(["b"]);
    expect(boardsMatching(ROWS, "", "small").map((b) => b.key)).toEqual(["b"]);
    expect([sizeOfInch(2.8), sizeOfInch(4), sizeOfInch(7)]).toEqual(["small", "medium", "large"]);
  });

  it("keeps the models of one board together, as far along as the furthest", () => {
    const families = boardFamilies(ROWS);
    expect(families.map((family) => family.map((b) => b.key))).toEqual([["a", "a2"], ["b"], ["c"]]);
    expect(families.map(familyStatus)).toEqual(["stable", "experimental", "stable"]);
    expect(familyOf(ROWS, ROWS[1]).map((b) => b.key)).toEqual(["a", "a2"]);
  });
  it("puts the recommended families first and apart, and a click on one picks its recommended model", () => {
    const rows = [...ROWS.slice(0, 3), { ...ROWS[3], recommended: true }];
    const tiers = familyTiers(boardFamilies(rows));
    expect(tiers.recommended.map((family) => family[0].key)).toEqual(["c"]);
    // A stable board that is not recommended is proven, but not promoted.
    expect(tiers.more.map((family) => family[0].key)).toEqual(["a", "b"]);
    const mixed = [{ ...ROWS[0], status: "new" as const }, { ...ROWS[1], status: "stable" as const }, board("a3", { recommended: true })];
    expect(familyLead(mixed).key).toBe("a3");
    expect(familyLead(mixed.slice(0, 2)).key).toBe("a2");
    expect(familyLead(tiers.more[1]).key).toBe("b");
  });
});

describe("what it is called and how it hangs", () => {
  it("asks which way only glass that is not square hangs both ways, with that way's grids", () => {
    expect(boardOrientations(ROWS[0]).map((way) => way.key)).toEqual(["landscape", "portrait"]);
    expect(boardOrientations(board("s", { square: true }))).toEqual([]);
    expect(boardOrientations(undefined)).toEqual([]);
    const range = gridRange(ROWS[0].orientations.landscape);
    expect(range).toEqual({ min: [2, 2], max: [4, 3] });
    expect(gridRange(ROWS[0].orientations.portrait)).toEqual({ min: [1, 1], max: [2, 3] });
    expect(bestGrid(ROWS[0].orientations.landscape)).toEqual({ columns: 3, rows: 2 });
    expect([canStep({ columns: 3, rows: 2 }, range, "columns", 1), canStep({ columns: 4, rows: 2 }, range, "columns", 1), canStep({ columns: 3, rows: 2 }, range, "rows", -1)])
      .toEqual([true, false, false]);
  });

  it("says when another screen carries the name or the device name already", () => {
    const taken = { nodes: ["hall"], prefixes: ["living_room"] };
    expect(nameClash(taken, "Living room", "living-room")).toEqual({ name: true, node: false, quote: false });
    expect(nameClash(taken, "Hall", "Hall ")).toEqual({ name: false, node: true, quote: false });
    expect(nameClash(taken, "  ", "")).toEqual({ name: false, node: false, quote: false });
    // " and \ would break the firmware's C++ strings (#453): said before anything is built.
    expect(nameClash(taken, 'Guition 4"', "guition").quote).toBe(true);
    expect(nameClash(taken, "Hall \\ kitchen", "hall").quote).toBe(true);
  });
});

describe("how the firmware gets onto it", () => {
  it("asks one thing a step, and only what this screen needs asked (app 0.4.103)", () => {
    expect(installStages({ model: false, hang: false, plugins: false, wifi: false })).toEqual(["board", "name", "cable", "connect"]);
    expect(installStages({ model: true, hang: true, plugins: true, wifi: true }))
      .toEqual(["board", "model", "name", "hang", "plugins", "wifi", "cable", "connect"]);
    // The cable is in this computer to begin with only where this browser can write a board.
    expect([firstCable("ok"), firstCable("insecure"), firstCable("unsupported")]).toEqual(["here", "ha", "ha"]);
  });

  it("names a port by itself, and keeps what is certainly not a screen out of the way", () => {
    expect(portLabel("/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_AA-if00")).toBe("USB · Espressif USB JTAG serial debug unit AA");
    expect(portName("/dev/ttyUSB0")).toBe("ttyUSB0");
    const screen = "/dev/serial/by-id/usb-1a86_USB_Single_Serial_54FC-if00", esp = "/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_AA-if00";
    const zigbee = "/dev/serial/by-id/usb-ITead_Sonoff_Zigbee_3.0_USB_Dongle_Plus_9c2a-if00-port0";
    const skyconnect = "/dev/serial/by-id/usb-Nabu_Casa_SkyConnect_v1.0_2c5e-if00-port0", zwave = "/dev/serial/by-id/usb-Zooz_800_Z-Wave_Stick_533D-if00";
    expect(screenPorts([screen, zigbee, esp, skyconnect, zwave])).toEqual({ screens: [screen, esp], others: [zigbee, skyconnect, zwave] });
    expect(screenPorts(["/dev/ttyUSB0"])).toEqual({ screens: ["/dev/ttyUSB0"], others: [] });
  });

  it("offers the rooms of the home as names, the most used first, not the ones a screen has", () => {
    const entities = [{ area: "Kitchen" }, { area: "Hall" }, { area: "Kitchen" }, {}, { area: "Living room" }, { area: "Living room" }, { area: "Living room" }];
    expect(areaNames(entities, ["Hall"])).toEqual(["Living room", "Kitchen"]);
    expect(areaNames(entities, [], 1)).toEqual(["Living room"]);
  });

  it("sends a choice and a grid only where they are not the board's own, and the Wi-Fi it is asked", () => {
    const form: InstallForm = { board: "a", orientation: "landscape", grid: { columns: 4, rows: 2 }, choices: { display: "B" }, friendly_name: "Hall",
      name: "hall", wifi_ssid: "Home", wifi_password: "pw", target: "browser" };
    const choices = [{ key: "display", options: ["A", "B"] }];
    expect(profileRequest(form, { choices, gridChosen: true, wifiMissing: ["wifi_ssid"], browser: true }))
      .toEqual({ board: "a", orientation: "landscape", friendly_name: "Hall", name: "hall", target: "download", choices: { display: "B" }, grid: { columns: 4, rows: 2 }, wifi_ssid: "Home" });
    expect(profileRequest({ ...form, choices: { display: "A" }, target: "usb" }, { choices, gridChosen: false, wifiMissing: null, browser: false }))
      .toEqual({ board: "a", orientation: "landscape", friendly_name: "Hall", name: "hall", target: "usb" });
  });
});

describe("following the installation", () => {
  const follow = (more: Partial<Follow>): Follow => ({ saved: false, running: false, ok: false, download: false, browser: false, writing: false, calibrate: false,
    built: false, stopped: false, name: "Hall", file: "hall.yaml", ...more });
  it("says where it stands, and why it stopped from the log unless a card says so", () => {
    expect(followDetail(follow({}), "ERROR no space")).toBe("ERROR no space");
    expect(followDetail(follow({}))).not.toBe("");
    expect(followDetail(follow({ stopped: true }), "ERROR")).toBe("");
    expect(followDetail(follow({ browser: true, built: true }))).toBe("");
    expect(followDetail(follow({ ok: true, calibrate: true }))).not.toBe(followDetail(follow({ ok: true })));
    expect([elapsedText(0, null, 5000), elapsedText(1000, null, 188000), elapsedText(1000, 62000, 999999)]).toEqual(["", "3:07", "1:01"]);
  });

  it("waits for the screen on the network, says Home Assistant saw it, and after three minutes what to fix", () => {
    const inventory = { screens: [], pending: [{ friendly: "Hall", file: "hall.yaml", seen: false }] } as unknown as Inventory;
    expect(arrivalOf(inventory, "hall.yaml", 1000)).toBe("waiting");
    expect(arrivalOf(inventory, "hall.yaml", ARRIVE_MS + 1)).toBe("missing");
    expect(arrivalOf({ ...inventory, pending: [{ friendly: "Hall", file: "hall.yaml", seen: true }] }, "hall.yaml", 0)).toBe("seen");
    expect(arrivalOf({ ...inventory, pending: [{ friendly: "Hall", file: "hall.yaml", seen: true, pairing: "failed" }] }, "hall.yaml", 0)).toBe("failed");
    // In Home Assistant is not the end: ready once it is online and may perform actions (app 0.4.103).
    expect(arrivalOf({ ...inventory, screens: [{ node: "hall", online: false }] } as unknown as Inventory, "hall.yaml", 0)).toBe("paired");
    expect(arrivalOf({ ...inventory, screens: [{ node: "hall", online: true, actions_blocked: true }] } as unknown as Inventory, "hall.yaml", 0)).toBe("paired");
    expect(arrivalOf({ ...inventory, screens: [{ node: "hall", online: true }] } as unknown as Inventory, "hall.yaml", 0)).toBe("ready");
    // A file someone puts on it themselves is never late.
    expect(arrivalOf(inventory, "hall.yaml", ARRIVE_MS * 10, true)).toBe("waiting");
  });

  it("counts the wait from the moment the firmware is on, and asks the inventory while it waits", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(10_000);
    const refresh = vi.spyOn(useInventoryStore(), "refresh").mockResolvedValue(undefined as any);
    useInventoryStore().inventory = { screens: [], entities: [], pending: [] } as unknown as Inventory;
    const waiting = ref(false), now = ref(10_000);
    const { result: { arrival, restart } } = inScope(() => useArrival(() => waiting.value, () => "hall.yaml", now));
    expect(arrival.value).toBeNull();
    waiting.value = true;
    await vi.advanceTimersByTimeAsync(5000);
    expect(arrival.value).toBe("waiting");
    expect(refresh).toHaveBeenCalled();
    now.value = 10_000 + ARRIVE_MS + 1;
    expect(arrival.value).toBe("missing");
    restart();
    waiting.value = false; await vi.advanceTimersByTimeAsync(0); vi.setSystemTime(now.value); waiting.value = true; await vi.advanceTimersByTimeAsync(0);
    expect(arrival.value).toBe("waiting");
  });
});

describe("the whole way until the screen works (app 0.4.103)", () => {
  const progress = (states: Record<string, string>, percent = 0): Progress => ({ percent, failed: false, done: false,
    steps: ["prepare", "build", "write", "restart", "done"].map((key) => ({ key, state: states[key] || "waiting", percent: key === "build" ? 40 : null })) as Progress["steps"] });
  const states = (j: ReturnType<typeof journey>) => j.steps.map((step) => `${step.key}:${step.state}`);
  it("goes from the build to Home Assistant, and is done only once Home Assistant has the screen working", () => {
    expect(states(journey(progress({ prepare: "done", build: "running" }), null, false))).toEqual(["build:running", "write:waiting", "wifi:waiting", "ha:waiting"]);
    expect(journey(progress({ prepare: "done", build: "running" }), null, false).steps[0].percent).toBe(40);
    const written = progress({ prepare: "done", build: "done", write: "done", restart: "done", done: "done" }, 100);
    // The firmware is on: that is not done yet, the screen still has to come to Home Assistant.
    expect(states(journey(written, "waiting", false))).toEqual(["build:done", "write:done", "wifi:running", "ha:waiting"]);
    expect(journey(written, "waiting", false).done).toBe(false);
    expect(states(journey(written, "seen", false))).toEqual(["build:done", "write:done", "wifi:done", "ha:running"]);
    expect(states(journey(written, "paired", false)).at(-1)).toBe("ha:running");
    const ready = journey(written, "ready", false);
    expect([ready.done, ready.percent, states(ready).at(-1)]).toEqual([true, 100, "ha:done"]);
    // What stops it says where: the Wi-Fi, or a question Home Assistant asks.
    expect(states(journey(written, "missing", false))[2]).toBe("wifi:failed");
    expect(states(journey(written, "failed", false))[3]).toBe("ha:failed");
  });
  it("waits for the person to put a file on it, and counts it written once Home Assistant sees the screen", () => {
    const built = progress({ prepare: "done", build: "done", done: "done" }, 100);
    expect(states(journey(built, "waiting", true))).toEqual(["build:done", "write:running", "wifi:waiting", "ha:waiting"]);
    expect(states(journey(built, "seen", true))).toEqual(["build:done", "write:done", "wifi:done", "ha:running"]);
    expect(journey(built, "waiting", true).percent).toBeLessThan(100);
  });
});

describe("the bar while the software is made", () => {
  it("moves while ESPHome gets the build ready, before the build counts anything", () => {
    const steps = (prepare: number | null) => ({ percent: 0, failed: false, done: false, steps: [
      { key: "prepare", state: "running", percent: prepare }, { key: "build", state: "waiting", percent: null }, { key: "write", state: "waiting", percent: null },
      { key: "restart", state: "waiting", percent: null }, { key: "done", state: "waiting", percent: null }] }) as Progress;
    expect(journey(steps(null), null, false).percent).toBe(0);
    expect(journey(steps(75), null, false).percent).toBe(7);
  });
});
