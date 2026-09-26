// One installation from this browser, for New screen and Firmware & USB alike. The order is ESPHome's (install-web
// dialog): the port is picked while the click that asked for it still counts (a browser only opens its port picker
// from a click), then the page connects and reads the chip, the add-on builds, the page fetches the factory image and
// writes it, and the screen restarts into it.
//
// esptool-js comes with ./esptool.ts, which is imported here only when a port has been picked.
import { reactive } from "vue";
import { api, send } from "../api";
import { chipMatches, connectProblem, flashSupport, imageChip, pickProblem, type FlashProblem } from "./logic";

export type FlashPhase = "idle" | "picking" | "connecting" | "waiting" | "downloading" | "erasing" | "writing"
  | "restarting" | "done" | "failed";
type Flasher = typeof import("./esptool");
type Loader = import("./esptool").Loader;

// The flasher module, loaded once. A seam for the tests, which have no serial port.
let loadFlasher = (): Promise<Flasher> => import("./esptool");
export function setFlasherLoader(load: () => Promise<Flasher>) {
  loadFlasher = load;
}

export type FlashState = {
  phase: FlashPhase; percent: number; chip: string; problem: FlashProblem | null;
  params: Record<string, string>; detail: string;
};

export function useBrowserFlash() {
  const state = reactive<FlashState>({ phase: "idle", percent: 0, chip: "", problem: null, params: {}, detail: "" });
  let flasher: Flasher | null = null;
  let loader: Loader | null = null;
  // Set once the image is written: the restart makes a native USB chip drop off the bus and come back, which is
  // no failure (ESPHome's `installed`).
  let written = false;

  const busy = () => ["picking", "connecting", "downloading", "erasing", "writing", "restarting"].includes(state.phase);

  function fail(problem: FlashProblem, params: Record<string, string> = {}, detail = "") {
    Object.assign(state, { phase: "failed", problem, params, detail });
  }

  async function close() {
    const current = loader;
    loader = null;
    if (current && flasher) await flasher.disconnect(current);
  }

  /**
   * Pick the port and connect: call it straight from a click, before anything else waits. True when a board of the
   * expected chip answers; the port then stays open for `install`, as in ESPHome while it compiles.
   */
  async function connect(expected?: string | null): Promise<boolean> {
    await close();
    written = false;
    Object.assign(state, { phase: "picking", percent: 0, chip: "", problem: null, params: {}, detail: "" });
    if (flashSupport() !== "ok") {
      fail("failed");
      return false;
    }
    let port: SerialPort;
    try {
      port = await navigator.serial.requestPort();
    } catch (error) {
      fail(pickProblem(error), {}, (error as Error)?.message || "");
      return false;
    }
    state.phase = "connecting";
    try {
      flasher = await loadFlasher();
    } catch (error) {
      fail("failed", { error: String((error as Error)?.message || error) });
      return false;
    }
    const current = flasher.createLoader(port);
    loader = current;
    port.addEventListener("disconnect", () => {
      if (loader !== current || written) return;
      loader = null;
      if (state.phase !== "idle" && state.phase !== "done") fail("disconnected");
    });
    try {
      state.chip = await flasher.connect(current);
    } catch (error) {
      console.error(error);
      if (loader === current) {
        await close();
        fail(connectProblem(error), {}, (error as Error)?.message || String(error));
      }
      return false;
    }
    if (!chipMatches(state.chip, expected)) {
      await close();
      fail("wrong_chip", { found: state.chip, expected: expected || "" });
      return false;
    }
    state.phase = "waiting";
    return true;
  }

  /**
   * Fetch the profile's factory image from the add-on (a relative URL, for Home Assistant's ingress path) and write it.
   * `erase` wipes the flash first, which ESPHome does when it sets up a new device and not when it reinstalls one.
   */
  async function install(file: string, erase: boolean): Promise<boolean> {
    if (!loader || !flasher || state.phase !== "waiting") return false;
    const current = loader;
    state.phase = "downloading";
    let data: Uint8Array;
    try {
      const response = await api(`firmware/profiles/${encodeURIComponent(file)}/download`);
      data = new Uint8Array(await response.arrayBuffer());
    } catch (error) {
      await close();
      fail("download", { error: String((error as Error)?.message || error) });
      return false;
    }
    if (loader !== current) return false;  // unplugged while the image came in
    const built = imageChip(data);
    if (built && !chipMatches(state.chip, built)) {
      await close();
      fail("wrong_image", { found: state.chip, expected: built });
      return false;
    }
    try {
      await flasher.writeImage(current, data, erase, () => { state.phase = "erasing"; }, (percent) => {
        state.phase = "writing";
        state.percent = percent;
      });
    } catch (error) {
      console.error(error);
      if ((state.phase as FlashPhase) !== "failed") {  // an unplugged cable already said so
        await close();
        fail("failed", { error: String((error as Error)?.message || error) });
      }
      return false;
    }
    written = true;
    state.phase = "restarting";
    try {
      await flasher.restart(current);
    } catch (error) {
      // The firmware is written; a reset that throws doesn't undo that (ESPHome logs it and reports success too).
      console.error("Restart after installing failed:", error);
    }
    await close();
    // The screen list now nudges pairing as for a screen flashed from Home Assistant's own USB port.
    try {
      await send(`firmware/profiles/${encodeURIComponent(file)}/flashed`, "POST");
    } catch (error) {
      console.error(error);
    }
    state.phase = "done";
    return true;
  }

  /** Give up: the build failed, or the person left. Closes the port. */
  async function cancel() {
    await close();
    if (state.phase !== "done" && state.phase !== "failed") Object.assign(state, { phase: "idle", problem: null });
  }

  return { state, connect, install, cancel, busy };
}
