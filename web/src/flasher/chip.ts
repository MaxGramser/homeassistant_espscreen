// A board's second chip from the browser (docs/BOARD_STEPS.md, the kind chip_firmware): the three things a page does
// with it. Its serial port, to restart the chip as a USB drive (opening the port at 1200 baud does that, the way an
// Arduino or a Pico takes a new program) and to ask which firmware it runs; and the drive, to write the firmware to.
// Chrome and Edge on a computer have both (Web Serial and the File System Access API), on a page served over https.
//
// What it does not know: the step, its words or its order (composables/useChipFirmware.ts). The frames are
// model/board-steps.ts, where they are tested without a port.
import { frame, HELLO, HELLO_BACK, isChipPort, readFrames, TRY, versionOfHello } from "../model/board-steps";
import type { ChipFirmwareStep } from "../types";

type Folder = FileSystemDirectoryHandle;

/** The chip's port: one this page was given before and that is plugged in now, else the browser's picker, which lists
 * only ports with the chip's USB ids. Call it straight from a click. */
export async function chipPort(step: Pick<ChipFirmwareStep, "usb">): Promise<SerialPort> {
  const known = ((await navigator.serial.getPorts?.()) || []).filter((port) => isChipPort(port.getInfo?.(), step));
  if (known.length === 1) return known[0];
  return navigator.serial.requestPort({ filters: step.usb.map((id) => ({ usbVendorId: id.vendor, usbProductId: id.product })) });
}
/** The chip's port without asking, when this page has it and it is plugged in. */
export async function knownChipPort(step: Pick<ChipFirmwareStep, "usb">): Promise<SerialPort | null> {
  const known = ((await navigator.serial.getPorts?.()) || []).filter((port) => isChipPort(port.getInfo?.(), step));
  return known.length === 1 ? known[0] : null;
}

/** Restarts the chip as a drive: its port opened at 1200 baud and let go. The chip leaves the bus as it restarts, so a
 * close that fails on the way out is how it goes. */
export async function restartAsDrive(port: SerialPort): Promise<void> {
  await port.open({ baudRate: 1200 });
  try {
    await port.setSignals?.({ dataTerminalReady: false });
  } catch { /* gone already */ }
  await new Promise((resolve) => setTimeout(resolve, 150));
  try {
    await port.close();
  } catch { /* gone already */ }
}

/** The firmware the chip on this port says it runs ("1.0.0"), or null when nothing that speaks Tessera's frames answers
 * within `ms` (another firmware, or none). */
export async function askChip(port: SerialPort, ms = 1500): Promise<string | null> {
  await port.open({ baudRate: 115200 });
  let reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const writer = port.writable!.getWriter();
    await writer.write(frame(HELLO));
    writer.releaseLock();
    reader = port.readable!.getReader();
    const stop = new Promise<null>((resolve) => { timer = setTimeout(() => resolve(null), ms); });
    let held: Uint8Array = new Uint8Array();
    for (;;) {
      const got = await Promise.race([reader.read(), stop]);
      if (!got || got.done || !got.value) return null;
      const all = new Uint8Array(held.length + got.value.length);
      all.set(held);
      all.set(got.value, held.length);
      const { frames, rest } = readFrames(all);
      held = rest;
      const answer = frames.find((one) => one.type === HELLO_BACK);
      if (answer) return versionOfHello(answer.payload);
    }
  } finally {
    clearTimeout(timer);
    try {
      await reader?.cancel();
      reader?.releaseLock();
    } catch { /* closing anyway */ }
    try {
      await port.close();
    } catch { /* gone */ }
  }
}

/** The chip plays its own short sound (two notes), so someone hears that it works. */
export async function tryChip(port: SerialPort): Promise<void> {
  await port.open({ baudRate: 115200 });
  try {
    const writer = port.writable!.getWriter();
    await writer.write(frame(TRY));
    writer.releaseLock();
    // The frame is on its way before the port closes.
    await new Promise((resolve) => setTimeout(resolve, 200));
  } finally {
    try {
      await port.close();
    } catch { /* gone */ }
  }
}

/** The folder someone picks for the chip's drive. Call it straight from a click. */
export const pickFolder = (): Promise<Folder> =>
  (window as unknown as { showDirectoryPicker: (options: object) => Promise<Folder> }).showDirectoryPicker({ id: "tessera-chip", mode: "readwrite" });
/** What the drive says of itself (its INFO_UF2.TXT), or null for a folder that is no such drive. */
export async function driveInfo(folder: Folder): Promise<string | null> {
  try {
    return await (await (await folder.getFileHandle("INFO_UF2.TXT")).getFile()).text();
  } catch {
    return null;
  }
}
/** Writes the firmware to the drive. The chip takes the last block and restarts at once, so the drive is gone before
 * the browser is done closing the file: once every byte was handed over, an error of the close is how it goes. */
export async function writeToDrive(folder: Folder, name: string, data: Uint8Array): Promise<void> {
  const file = await folder.getFileHandle(name, { create: true });
  const out = await file.createWritable();
  await out.write(data as unknown as BufferSource);
  try {
    await out.close();
  } catch { /* the drive left with the last block */ }
}
