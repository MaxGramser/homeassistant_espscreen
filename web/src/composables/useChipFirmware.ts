// A board step of the kind chip_firmware as it goes (docs/BOARD_STEPS.md): Tessera's firmware onto a board's second
// chip, from this browser. Two clicks, because a browser gives a port and a folder only to a click: the first asks for
// the chip's port and restarts the chip as a USB drive, the second asks for that drive and writes the file to it. Then
// the chip starts with its new firmware and the screen finds it, which is what makes the step done: the add-on asks
// the screen (api/screens/<id>/steps) until it says so. The chip itself is asked over its port too, so the page can say
// "the chip has it" before the screen does.
//
// Where the browser has no serial port or no folder access (flasher/chip.ts), the step is done by hand with the same
// file, and this only waits for the screen.
import { computed, onBeforeUnmount, reactive } from "vue";
import { api, send } from "../api";
import { askChip, chipPort, driveInfo, knownChipPort, pickFolder, restartAsDrive, writeToDrive } from "../flasher/chip";
import { chipSupport, isChipDrive, isUf2, type ChipPhase, type ChipProblem } from "../model/board-steps";
import { useInventoryStore } from "../stores/inventory";
import type { BoardStep, ChipFirmwareStep, Screen } from "../types";

// How long the screen gets to find the chip after the file is on it, and how often it is asked.
const WAIT_MS = 45000, ASK_MS = 1500;

export function useChipFirmware(step: () => ChipFirmwareStep, screen: () => Screen | null) {
  const inv = useInventoryStore();
  const support = chipSupport();
  const state = reactive({
    phase: "idle" as ChipPhase, problem: null as ChipProblem | null,
    // What the chip itself answered over its port after the write, before the screen found it.
    onChip: "",
    // The drive was not the chip's: said beside the key that asks for it again.
    wrongDrive: false,
    // The browser did not open its window for the drive.
    noWindow: false,
  });
  let data: Uint8Array | null = null;
  let alive = true;
  onBeforeUnmount(() => { alive = false; });
  const busy = computed(() => ["port", "restart", "write", "wait"].includes(state.phase));

  function fail(problem: ChipProblem) { Object.assign(state, { phase: "failed", problem }); }
  async function file(): Promise<Uint8Array | null> {
    if (data) return data;
    try {
      // The step names the file as the page links to it ("api/..."); api() adds that start itself.
      const bytes = new Uint8Array(await (await api(step().file.replace(/^api\//, ""))).arrayBuffer());
      data = isUf2(bytes, step().size) ? bytes : null;
    } catch {
      data = null;
    }
    return data;
  }

  /** The first click: the chip's port, and the chip restarted as a drive. */
  async function start() {
    Object.assign(state, { phase: "port", problem: null, onChip: "", wrongDrive: false, noWindow: false });
    let port: SerialPort;
    try {
      port = await chipPort(step());
    } catch {
      return fail("no_port");
    }
    state.phase = "restart";
    if (!(await file())) return fail("file");
    try {
      await restartAsDrive(port);
    } catch {
      return fail("port");
    }
    state.phase = "drive";
  }
  /** The drive is there already (the chip was started as one by its button): on to the second click. */
  async function driveIsThere() {
    Object.assign(state, { phase: "drive", problem: null, wrongDrive: false });
    if (!(await file())) fail("file");
  }
  /** The second click: the drive, the file onto it, and the wait for the screen. */
  async function chooseDrive() {
    state.wrongDrive = false;
    let folder: FileSystemDirectoryHandle;
    state.noWindow = false;
    try {
      folder = await pickFolder();
    } catch (error) {
      // Closed without a choice (AbortError): the key is still there. Anything else is a window that did not open, as
      // when one the browser opened before still stands somewhere out of sight; the page said nothing then, and
      // someone looked for a window that was not there (2026-11-26).
      if ((error as Error)?.name !== "AbortError") state.noWindow = true;
      return;
    }
    if (!isChipDrive(await driveInfo(folder), step().drive)) {
      state.wrongDrive = true;
      return;
    }
    const bytes = await file();
    if (!bytes) return fail("file");
    state.phase = "write";
    try {
      await writeToDrive(folder, step().download, bytes);
    } catch {
      return fail("write");
    }
    await wait();
  }
  /** Asks the screen now, and takes what it says into the inventory. The step as the screen has it, or null. */
  async function askScreen(): Promise<BoardStep | null> {
    const now = screen();
    if (!now) return null;
    try {
      const answer = await send<{ steps: BoardStep[] }>(`screens/${encodeURIComponent(now.id)}/steps`, "POST");
      const steps = answer?.steps || [];
      inv.inventory = { ...inv.inventory, screens: inv.inventory.screens.map((one) => (one.id === now.id ? { ...one, steps } : one)) };
      return steps.find((one) => one.id === step().id) || null;
    } catch {
      return null;
    }
  }
  /** Until the screen says the chip answers with this firmware. By hand (no port, no folder) this is all the page does. */
  async function wait() {
    Object.assign(state, { phase: "wait", problem: null });
    const until = Date.now() + WAIT_MS;
    while (alive && Date.now() < until) {
      await new Promise((resolve) => setTimeout(resolve, ASK_MS));
      if (!state.onChip && support === "ok") {
        const port = await knownChipPort(step()).catch(() => null);
        if (port) state.onChip = (await askChip(port).catch(() => null)) || "";
      }
      const found = await askScreen();
      if (found?.state === "done") {
        state.phase = "done";
        return;
      }
      // No screen to ask (it is off, or not made yet): the chip's own word is all there is.
      if (!screen()?.online && state.onChip === step().version) {
        state.phase = "done";
        return;
      }
    }
    if (alive) fail("silent");
  }
  function reset() { Object.assign(state, { phase: "idle", problem: null, onChip: "", wrongDrive: false }); }

  return { state, support, busy, start, driveIsThere, chooseDrive, wait, reset };
}
