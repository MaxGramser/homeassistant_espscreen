// New screen's rules (model/installer.ts, install-progress.ts's words, useArrival): the boards a search leaves and their
// families, which way a board hangs and the grids it takes, a name another screen carries, the ways in and what is sent.
import { describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import { arrivalOf, ARRIVE_MS, bestGrid, boardFamilies, boardOrientations, boardsMatching, canStep, familyLines, familyOf, familyStatus,
  gridRange, installWays, nameClash, portLabel, profileRequest, sizeCount, sizeOfInch, wayHint, wayTarget, type BoardRow, type InstallForm } from "../src/model/installer";
import { elapsedText, followDetail, followTitle, stepLabel, type Follow } from "../src/model/install-progress";
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
    expect(familyLines(families[0])[1]).toBe("2 models");
    expect(familyLines(families[1])).toEqual(["M-b", "320 × 240 · GT911"]);
    expect(familyOf(ROWS, ROWS[1]).map((b) => b.key)).toEqual(["a", "a2"]);
    expect([sizeCount(ROWS, ""), sizeCount(ROWS, "medium")]).toEqual([3, 1]);
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
    expect(nameClash(taken, "Living room", "living-room")).toEqual({ name: true, node: false });
    expect(nameClash(taken, "Hall", "Hall ")).toEqual({ name: false, node: true });
    expect(nameClash(taken, "  ", "")).toEqual({ name: false, node: false });
  });
});

describe("how the firmware gets onto it", () => {
  it("lists USB on the Home Assistant machine first, a port found by its own name", () => {
    expect(portLabel("/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_AA-if00")).toBe("USB · Espressif USB JTAG serial debug unit AA");
    expect(portLabel("/dev/ttyUSB0")).toBe("USB · ttyUSB0");
    expect(installWays([]).map((way) => [way.value, way.live])).toEqual([["usb", false], ["browser", false], ["download", false], ["", false]]);
    expect(installWays(["/dev/ttyUSB0", "/dev/ttyUSB1"]).map((way) => way.value).slice(0, 2)).toEqual(["/dev/ttyUSB0", "/dev/ttyUSB1"]);
  });

  it("follows the ports until another way is picked", () => {
    expect(wayTarget("", false, ["/dev/ttyUSB0"])).toBe("/dev/ttyUSB0");
    expect(wayTarget("", true, ["/dev/ttyUSB0"])).toBe("");
    expect(wayTarget("/dev/ttyUSB9", true, ["/dev/ttyUSB0"])).toBe("/dev/ttyUSB0");
    expect(wayTarget("download", false, [])).toBe("usb");
    expect(wayTarget("download", true, [])).toBe("download");
    expect(wayHint("browser", "insecure", [])).toContain("https");
    expect(wayHint("/dev/a", "ok", ["/dev/a", "/dev/b"])).not.toBe(wayHint("/dev/a", "ok", ["/dev/a"]));
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
    expect(followTitle(follow({ saved: true }))).toContain("hall.yaml");
    expect(followTitle(follow({ running: true, writing: true }))).toContain("Hall");
    expect(followTitle(follow({ ok: true, download: true }))).toContain("Hall");
    expect(followDetail(follow({}), "ERROR no space")).toBe("ERROR no space");
    expect(followDetail(follow({}))).not.toBe("");
    expect(followDetail(follow({ stopped: true }), "ERROR")).toBe("");
    expect(followDetail(follow({ browser: true, built: true }))).toBe("");
    expect(followDetail(follow({ ok: true, calibrate: true }))).not.toBe(followDetail(follow({ ok: true })));
    expect([elapsedText(0, null, 5000), elapsedText(1000, null, 188000), elapsedText(1000, 62000, 999999)]).toEqual(["", "3:07", "1:01"]);
    expect(stepLabel("done", true)).not.toBe(stepLabel("done", false));
  });

  it("waits for the screen on the network, says Home Assistant saw it, and after three minutes what to fix", () => {
    const inventory = { screens: [], pending: [{ friendly: "Hall", file: "hall.yaml", seen: false }] } as unknown as Inventory;
    expect(arrivalOf(inventory, "hall.yaml", 1000)).toBe("waiting");
    expect(arrivalOf(inventory, "hall.yaml", ARRIVE_MS + 1)).toBe("missing");
    expect(arrivalOf({ ...inventory, pending: [{ friendly: "Hall", file: "hall.yaml", seen: true }] }, "hall.yaml", 0)).toBe("seen");
    expect(arrivalOf({ ...inventory, pending: [{ friendly: "Hall", file: "hall.yaml", seen: true, pairing: "failed" }] }, "hall.yaml", 0)).toBe("failed");
    expect(arrivalOf({ ...inventory, screens: [{ node: "hall" }] } as unknown as Inventory, "hall.yaml", 0)).toBe("paired");
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
