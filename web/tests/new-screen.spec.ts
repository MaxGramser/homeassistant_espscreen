// New screen (app 0.4.103, components/InstallerView.vue and components/install/): one question a step, only the steps a
// screen needs, the cable asked before any port, and the installation followed until Home Assistant has the screen
// working. What it sends is the profile it always sent (model/installer.ts profileRequest).
import { readFileSync } from "node:fs";
import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import InstallerView from "../src/components/InstallerView.vue";
import { t } from "../src/i18n";
import { useInventoryStore } from "../src/stores/inventory";
import type { Inventory } from "../src/types";

// What New screen gets for each board (firmware.BOARD_CHOICES), made from boards.json the way the add-on makes it.
const SHAPES = JSON.parse(readFileSync("../screen_manager/app/boards.json", "utf8"));
const BOARD_CHOICES = Object.fromEntries(Object.entries(SHAPES).filter(([key, shape]: [string, any]) => shape.board === key)
  .map(([key, shape]: [string, any]) => [key, {
    square: shape.width === shape.height, orientations: shape.orientations, width: shape.width, height: shape.height, dpi: shape.dpi,
    camera: Boolean(shape.camera), dimmable: shape.dimmable ?? true, can_standby: shape.can_standby ?? true, chip: shape.chip, ...shape.catalog,
  }]));

const ESP = "/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_AA-if00";
const ZIGBEE = "/dev/serial/by-id/usb-ITead_Sonoff_Zigbee_3.0_USB_Dongle_Plus_9c2a-if00-port0";
const flush = async () => { for (let i = 0; i < 4; i++) await Promise.resolve(); await new Promise((done) => setTimeout(done, 0)); };

type Addon = { ports?: string[]; wifi?: any; job?: any; suggested?: any[]; taken?: any };
function addon({ ports = [ESP], wifi = { state: "ready", missing: [] }, job = null, suggested = [], taken = { nodes: [], prefixes: [] } }: Addon = {}) {
  const calls: { url: string; method: string; body?: any }[] = [];
  const pending = { file: "hall.yaml", friendly: "Hall", node: "hall", installed: true, seen: false };
  vi.stubGlobal("fetch", vi.fn((url: string, options: any = {}) => {
    const method = options.method || "GET", path = String(url);
    calls.push({ url: path, method, body: options.body ? JSON.parse(options.body) : undefined });
    const asked = calls.some((c) => c.url.endsWith("firmware/profiles"));
    if (path.endsWith("api/firmware")) return Promise.resolve({ ok: true, json: () => Promise.resolve({ available: true, ports, profiles: [], logs: [], wifi, boards: BOARD_CHOICES, taken, job: asked ? job : null }) });
    if (/firmware\/builds\/\d+\/log$/.test(path)) return Promise.resolve({ ok: true, json: () => Promise.resolve({ build: job, logs: [] }) });
    if (path.includes("inventory")) return Promise.resolve({ ok: true, json: () => Promise.resolve({ ...useInventoryStore().inventory, line: asked && job ? [job] : [] }) });
    if (path.endsWith("plugins/suggested")) return Promise.resolve({ ok: true, text: () => Promise.resolve(JSON.stringify({ plugins: suggested })), json: () => Promise.resolve({ plugins: suggested }) });
    const answer = path.endsWith("firmware/profiles") ? { file: "hall.yaml", api_key: "k", build: job } : path.endsWith("firmware/jobs") ? job : { state: "ready" };
    return Promise.resolve({ ok: true, text: () => Promise.resolve(JSON.stringify(answer)), json: () => Promise.resolve(answer) });
  }));
  const profile = () => calls.filter((c) => c.url.endsWith("firmware/profiles")).at(-1)?.body;
  return { calls, pending, profile };
}
async function open(options: Addon = {}) {
  const added = addon(options);
  // The steps change with a transition; jsdom runs none, so it is the plain switch here.
  const view = mount(InstallerView, { global: { stubs: { transition: true } } });
  await flush();
  return { view, ...added };
}
const at = (view: ReturnType<typeof mount>) => view.find("[data-step]").attributes("data-step");
async function next(view: ReturnType<typeof mount>) { await view.find("#setup-next").trigger("click"); await flush(); }
async function choose(view: ReturnType<typeof mount>, key: string) {
  if (!view.find(`input[name="board"][value="${key}"]`).exists()) await view.find("#board-other").trigger("click");
  await view.find(`input[name="board"][value="${key}"]`).setValue();
  await flush();
}
async function submit(view: ReturnType<typeof mount>) { await view.find("#install-form").trigger("submit"); await flush(); }

beforeEach(() => {
  useInventoryStore().inventory = { csrf: "t", connected: true, screens: [], pending: [],
    entities: [{ id: "light.a", name: "A", area: "Kitchen" }, { id: "light.b", name: "B", area: "Kitchen" }, { id: "light.c", name: "C", area: "Hall" }] } as unknown as Inventory;
});

describe("New screen, one question a step", () => {
  it("walks a square board without versions: screen, name, cable, the way, with Back and Continue", async () => {
    const { view } = await open();
    expect(at(view)).toBe("board");
    expect(view.findAll(".ob-dots li")).toHaveLength(4);
    await next(view);
    expect(at(view)).toBe("name");
    // No name, no step on; the name shows on the drawing of the screen as it is typed.
    expect(view.find("#setup-next").attributes("disabled")).toBeDefined();
    await view.find("#friendly_name").setValue("Hall");
    expect(view.find(".ob-hero .da-name").text()).toBe("Hall");
    await next(view);
    expect(at(view)).toBe("cable");
    await view.find("#setup-back").trigger("click");
    expect(at(view)).toBe("name");
    await next(view);
    await next(view);
    expect(at(view)).toBe("connect-ha");
    expect(view.find("#install-go").exists()).toBe(true);
    expect(view.find("#setup-next").exists()).toBe(false);
  });

  it("shows the recommended boards large, and every board in a list to search behind another screen", async () => {
    const { view } = await open();
    const recommended = view.findAll('input[name="board"]').map((input) => input.attributes("value"));
    expect(recommended).toEqual(["guition", "jc8012p4a1v3", "reterminald1001", "waveshare101v3"]);
    expect(view.find(".ob-soon").text()).toBe("More to come soon.");
    expect((view.find('input[value="guition"]').element as HTMLInputElement).checked).toBe(true);
    await view.find("#board-other").trigger("click");
    expect(at(view)).toBe("board-list");
    const names = () => view.findAll(".ob-row-words b").map((b) => b.text());
    await view.find("#board-search").setValue("2432S028");
    expect(names()).toContain("CYD · 2.8 inch");
    await view.find("#board-search").setValue("nothing like it");
    expect(view.find(".pick-none").text()).toContain("nothing like it");
    await view.find("#board-search").setValue("");
    // How far a board has been tried, in plain words, on the ones not proven: whichever board the data still marks so.
    const untried = Object.keys(BOARD_CHOICES).find((key) => BOARD_CHOICES[key].status === "experimental");
    expect(untried).toBeTruthy();
    expect(view.find(`input[value="${untried}"]`).element.closest("label")!.textContent).toContain("Experimental");
    expect(view.find('input[value="cyd"]').element.closest("label")!.querySelector(".ob-tag")).toBeNull();
    // Back closes the list before it leaves the step.
    await view.find("#setup-back").trigger("click");
    expect(at(view)).toBe("board");
  });

  it("asks which version a screen of several is, and sends it", async () => {
    const { view, profile } = await open();
    await choose(view, "jc8012p4a1v3");
    await next(view);
    expect(at(view)).toBe("model");
    const models = view.findAll("#board-model .ob-row");
    expect(models.map((row) => row.find("b").text())).toEqual(["JC8012P4A1", "JC8012P4A1 V3", "JC8012P4A1 V2"]);
    expect(models[1].text()).toContain(t("editor.installer.flow.model_usual"));
    await models[0].find("input").setValue();
    await next(view);
    await view.find("#friendly_name").setValue("Hall");
    while (at(view) !== "connect-ha") await next(view);
    await submit(view);
    expect(profile().board).toBe("jc8012p4a1");
  });

  it("asks a board's own choice with the version, and sends only one that differs", async () => {
    const { view, profile } = await open();
    await choose(view, "cyd");
    await next(view);
    expect(at(view)).toBe("model");
    expect(view.find("#choice-DISPLAY_MODEL legend").text()).toBe("Display controller");
    const options = view.findAll("#choice-DISPLAY_MODEL .ob-row");
    expect(options.map((option) => option.find("b").text())).toEqual(["ILI9341", "ST7789V"]);
    await options[1].find("input").setValue();
    await next(view);
    await view.find("#friendly_name").setValue("Hall");
    // Glass that is not square asks which way it hangs, each way drawn with the tiles of its page.
    await next(view);
    expect(at(view)).toBe("hang");
    const ways = view.findAll("#orientation-fields .ob-card");
    expect(ways.map((way) => way.find("b").text())).toEqual(["Lying down", "Standing up"]);
    expect(ways[0].findAll(".da-tile")).toHaveLength(6);
    await ways[1].find("input").setValue();
    while (at(view) !== "connect-ha") await next(view);
    await submit(view);
    expect(profile()).toMatchObject({ board: "cyd", orientation: "portrait", choices: { DISPLAY_MODEL: "ST7789V" }, name: "hall" });
    expect(profile().grid).toBeUndefined();
  });

  it("offers the rooms of the home as names, and holds the step while another screen has the name", async () => {
    const { view } = await open({ taken: { nodes: ["hall"], prefixes: ["living_room"] } });
    await next(view);
    expect(view.findAll("#room-names .ob-chip").map((chip) => chip.text())).toEqual(["Kitchen", "Hall"]);
    await view.findAll("#room-names .ob-chip")[0].trigger("click");
    expect((view.find("#friendly_name").element as HTMLInputElement).value).toBe("Kitchen");
    await view.find("#friendly_name").setValue("Living room");
    expect(view.find("#name-taken").exists()).toBe(true);
    expect(view.find("#setup-next").attributes("disabled")).toBeDefined();
    await view.find("#friendly_name").setValue("Hall");
    expect(view.find("#node-taken").exists()).toBe(true);
    await view.find("#friendly_name").setValue("Kitchen");
    expect(view.find("#setup-next").attributes("disabled")).toBeUndefined();
  });

  it("keeps the device name and the grid under More options, and sends a grid that is not the board's best", async () => {
    const { view, profile } = await open();
    await next(view);
    expect(view.find("#more-box").exists()).toBe(false);
    await view.find("#more-options").trigger("click");
    expect(view.findAll("#grid-fields .grid-step b").map((b) => b.text())).toEqual(["2", "3"]);
    await view.find("#install-rows-more").trigger("click");
    expect(view.find("#install-grid-best").exists()).toBe(true);
    await view.find("#friendly_name").setValue("Hall");
    expect((view.find("#node-name").element as HTMLInputElement).value).toBe("hall");
    expect(view.findAll("#board-abilities li").length).toBeGreaterThan(0);
    while (at(view) !== "connect-ha") await next(view);
    await submit(view);
    expect(profile()).toMatchObject({ board: "guition", grid: { columns: 2, rows: 4 } });
  });

  it("asks about the plugins for the hardware, each on, and sends what was turned off as declined", async () => {
    const camera = { id: "screen_camera", name: { en: "Screen camera" }, summary: { en: "The camera of the screen." }, version: "0.7.0", why: "camera", image: null };
    const gps = { id: "gps_fix", name: { en: "GPS" }, summary: { en: "Where the screen is." }, version: "1.0.0", why: "camera", image: null };
    const { view, profile } = await open({ suggested: [camera, gps] });
    await next(view);
    await view.find("#friendly_name").setValue("Hall");
    await next(view);
    expect(at(view)).toBe("plugins");
    const rows = view.findAll("#install-plugins li");
    expect(rows.map((row) => row.classes("chosen"))).toEqual([true, true]);
    expect(rows[0].text()).toContain("Screen camera");
    await rows[1].find('[role="switch"]').trigger("click");
    await flush();
    while (at(view) !== "connect-ha") await next(view);
    await submit(view);
    expect(profile().plugins).toEqual({ add: ["screen_camera"], declined: ["gps_fix"] });
  });

  it("asks the Wi-Fi only when ESPHome has none, and sends it with the profile", async () => {
    const { view, profile } = await open({ wifi: { state: "new", missing: ["wifi_ssid", "wifi_password"] } });
    expect(view.findAll(".ob-dots li")).toHaveLength(5);
    await next(view);
    await view.find("#friendly_name").setValue("Hall");
    await next(view);
    expect(at(view)).toBe("wifi");
    expect(view.find("#setup-next").attributes("disabled")).toBeDefined();
    await view.find("#wifi_ssid").setValue("Home");
    await view.find("#wifi_password").setValue("pw");
    await next(view);
    await next(view);
    await submit(view);
    expect(profile()).toMatchObject({ wifi_ssid: "Home", wifi_password: "pw" });
  });
});

describe("New screen, where the cable is", () => {
  async function toCable(options: Addon = {}) {
    const opened = await open(options);
    await next(opened.view);
    await opened.view.find("#friendly_name").setValue("Hall");
    await next(opened.view);
    return opened;
  }
  it("asks in this computer or in Home Assistant before any port, Home Assistant first where this browser cannot write", async () => {
    const { view } = await toCable();
    expect(at(view)).toBe("cable");
    expect(view.findAll("#install-cable .ob-card").map((card) => card.attributes("data-cable"))).toEqual(["ha", "here"]);
    expect(view.find('[data-cable="ha"]').classes()).toContain("chosen");
    expect(view.find('[data-cable="ha"] .ca-mark').exists()).toBe(true);
    // In this computer, where this browser cannot write a screen: a file instead, said before the way.
    await view.find('input[name="cable"][value="here"]').setValue();
    expect(view.find("#cable-browser").exists()).toBe(true);
    await next(view);
    expect(at(view)).toBe("connect-here");
    expect(view.find("#install-go").text()).toBe(t("editor.installer.flow.go_download"));
  });

  it("picks the screen among the ports of Home Assistant, and keeps a Zigbee stick out of the way", async () => {
    const { view, profile } = await toCable({ ports: [ZIGBEE, ESP] });
    await next(view);
    expect(view.find("#ha-found").text()).toContain("Espressif USB JTAG serial debug unit AA");
    expect(view.find("#ha-others summary").text()).toContain("1 other device");
    await submit(view);
    expect(profile().target).toBe(ESP);
  });

  it("waits for the screen when nothing is plugged in, and asks which one when there are more", async () => {
    const none = await toCable({ ports: [ZIGBEE] });
    await next(none.view);
    expect(none.view.find("#ha-waiting").exists()).toBe(true);
    expect(none.view.find("#install-go").attributes("disabled")).toBeDefined();
    const two = "/dev/serial/by-id/usb-1a86_USB_Single_Serial_54FC-if00";
    const more = await toCable({ ports: [ESP, two] });
    await next(more.view);
    expect(more.view.find("h1").text()).toBe(t("editor.installer.flow.ha_which"));
    expect(more.view.find("#install-go").attributes("disabled")).toBeDefined();
    await more.view.findAll("#ha-ports input")[1].setValue();
    expect(more.view.find("#install-go").attributes("disabled")).toBeUndefined();
    await submit(more.view);
    expect(more.profile().target).toBe(two);
  });

  it("saves it for later, or builds a file instead, from wherever the cable is", async () => {
    const later = await toCable();
    await later.view.find("#install-later").trigger("click");
    await flush();
    expect(later.profile().target).toBe("");
    expect(later.view.find("#progress-title").text()).toBe(t("editor.installer.flow.saved_title", { name: "Hall" }));
    const file = await toCable();
    await next(file.view);
    await file.view.find("#install-download").trigger("click");
    await flush();
    expect(file.profile().target).toBe("download");
  });

  it("writes another network before it makes the profile", async () => {
    const { view, calls } = await toCable();
    await next(view);
    await view.find("#wifi-other").trigger("click");
    await view.find("#wifi_ssid").setValue("Home");
    await view.find("#wifi_password").setValue("secret");
    await submit(view);
    const writes = calls.filter((c) => c.method !== "GET");
    expect(writes.map((c) => [c.url, c.method])).toEqual([["api/firmware/wifi", "PUT"], ["api/firmware/profiles", "POST"]]);
    expect(writes[0].body).toEqual({ wifi_ssid: "Home", wifi_password: "secret" });
    expect(writes[1].body.wifi_password).toBeUndefined();
  });
});

describe("New screen, until the screen works", () => {
  const built = { id: 2, by: "install", file: "hall.yaml", action: "install", state: "success", asked: 1, started: 2, finished: 3 };
  async function installed(job: any = built) {
    const opened = await open({ job });
    await next(opened.view);
    await opened.view.find("#friendly_name").setValue("Hall");
    await next(opened.view);
    await next(opened.view);
    await submit(opened.view);
    return opened;
  }
  const steps = (view: ReturnType<typeof mount>) => view.findAll("#follow-steps li").map((li) => `${li.attributes("data-step")}:${li.classes()[0]}`);

  it("is not done when the firmware is on: it follows the screen onto the Wi-Fi and into Home Assistant, then says it is ready", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const { view, pending } = await installed();
      expect(steps(view)).toEqual(["build:done", "write:done", "wifi:running", "ha:waiting"]);
      expect(view.find("#progress-title").text()).toBe(t("editor.installer.flow.now.wifi", { name: "Hall" }));
      expect(view.find("#install-pages").exists()).toBe(false);
      useInventoryStore().inventory.pending = [{ ...pending, seen: true }];
      await flush();
      expect(steps(view)).toEqual(["build:done", "write:done", "wifi:done", "ha:running"]);
      expect(view.find("#progress-title").text()).toBe(t("editor.installer.flow.now.ha", { name: "Hall" }));
      // In Home Assistant but not online yet: still not ready.
      useInventoryStore().inventory.screens = [{ id: "hall", name: "Hall", node: "hall", online: false, layout: { tiles: [] } } as any];
      await flush();
      expect(view.find("#install-pages").exists()).toBe(false);
      useInventoryStore().inventory.screens = [{ id: "hall", name: "Hall", node: "hall", online: true, layout: { tiles: [] } } as any];
      await flush();
      expect(view.find("#progress-title").text()).toBe(t("editor.installer.flow.ready_title", { name: "Hall" }));
      expect(view.find("#install-pages").exists()).toBe(true);
      expect(view.find("#follow-steps").exists()).toBe(false);
    } finally { vi.useRealTimers(); }
  });

  it("opens the way by hand when Home Assistant asks something, and after three minutes off the Wi-Fi offers the fix", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const { view, calls, pending } = await installed();
      useInventoryStore().inventory.pending = [{ ...pending, seen: true, pairing: "failed" }];
      await flush();
      expect(view.find("#pair-steps").exists()).toBe(true);
      expect(view.find("#api-key").text()).toBe("k");
      useInventoryStore().inventory.pending = [{ ...pending, seen: false }];
      await vi.advanceTimersByTimeAsync(181000);
      await flush();
      expect(view.find("#arrive").classes()).toContain("missing");
      expect(view.find("#arrive").text()).toContain(t("editor.installer.wifi.other_note"));
      await view.find("#fix_ssid").setValue("Right");
      await view.find("#fix_password").setValue("pw");
      await view.find("#arrive-wifi").trigger("submit");
      await flush();
      expect(calls.filter((c) => c.method !== "GET").map((c) => c.url).slice(-2)).toEqual(["api/firmware/wifi", "api/firmware/jobs"]);
    } finally { vi.useRealTimers(); }
  });

  it("says why when its build was refused at its turn, and offers it again", async () => {
    const { view } = await installed({ ...built, state: "failed", reason: "Choose the USB port of the board." });
    expect(view.find("#progress-detail").text()).toBe("Choose the USB port of the board.");
    expect(view.find("#install-retry").exists()).toBe(true);
  });
});
