// A board's own steps (docs/BOARD_STEPS.md): what there is to do with a board beyond its firmware, once. The add-on
// says which steps a screen's board has and how far each is (screen.steps, board_steps.py); this is what the editor
// works out from them, and for the kind chip_firmware what it needs to talk to a board's second chip: the frames of
// chip_protocol.h, the file it writes, and the drive it writes it to. Pure: the ports and the drive are
// flasher/chip.ts.
import type { BoardStep, ChipFirmwareStep, Screen } from "../types";

/** The steps the page brings up by itself: not done, and not put off. `update` is one too, a newer one of what is done. */
export const stepsToDo = (screen: Pick<Screen, "steps"> | null | undefined): BoardStep[] =>
  (screen?.steps || []).filter((step) => step.state === "open" || step.state === "update");
/** Every step that is not done as this app has it, the ones put off too: what the screen's settings list. */
export const stepsLeft = (screen: Pick<Screen, "steps"> | null | undefined): BoardStep[] =>
  (screen?.steps || []).filter((step) => step.state !== "done");
export const isChipFirmware = (step: BoardStep): step is ChipFirmwareStep => step.kind === "chip_firmware";

// ---- The chip's words (components/chip_link/chip_protocol.h), as far as a page needs them ----
export const HELLO = 0x01, TRY = 0x14, HELLO_BACK = 0x81;

/** CRC-16/CCITT-FALSE, the check of a frame. */
export function crc16(data: Uint8Array, crc = 0xffff): number {
  for (const byte of data) {
    crc ^= byte << 8;
    for (let bit = 0; bit < 8; bit++) crc = crc & 0x8000 ? ((crc << 1) ^ 0x1021) & 0xffff : (crc << 1) & 0xffff;
  }
  return crc;
}
export function cobsEncode(data: Uint8Array): Uint8Array {
  const out: number[] = [];
  let block: number[] = [];
  const close = (code: number) => { out.push(code, ...block); block = []; };
  for (const byte of data) {
    if (byte === 0) close(block.length + 1);
    else {
      block.push(byte);
      if (block.length === 254) close(0xff);
    }
  }
  close(block.length + 1);
  return Uint8Array.from(out);
}
/** The reverse, of a frame without its closing zero; null for what is no COBS. */
export function cobsDecode(data: Uint8Array): Uint8Array | null {
  const out: number[] = [];
  let at = 0;
  while (at < data.length) {
    const code = data[at];
    if (code === 0 || at + code > data.length) return null;
    for (let i = 1; i < code; i++) out.push(data[at + i]);
    at += code;
    if (code !== 0xff && at < data.length) out.push(0);
  }
  return Uint8Array.from(out);
}
/** A whole frame for the wire, its closing zero included. */
export function frame(type: number, payload: Uint8Array = new Uint8Array()): Uint8Array {
  const plain = new Uint8Array(payload.length + 3);
  plain[0] = type;
  plain.set(payload, 1);
  const crc = crc16(plain.subarray(0, payload.length + 1));
  plain[payload.length + 1] = crc >> 8;
  plain[payload.length + 2] = crc & 0xff;
  const wire = cobsEncode(plain);
  const out = new Uint8Array(wire.length + 1);
  out.set(wire);
  return out;
}
/** The whole frames in what came off the wire so far, and the bytes of one that is not whole yet. */
export function readFrames(bytes: Uint8Array): { frames: { type: number; payload: Uint8Array }[]; rest: Uint8Array } {
  const frames: { type: number; payload: Uint8Array }[] = [];
  let start = 0;
  for (let at = 0; at < bytes.length; at++) {
    if (bytes[at] !== 0) continue;
    const plain = at > start ? cobsDecode(bytes.subarray(start, at)) : null;
    start = at + 1;
    if (!plain || plain.length < 3) continue;
    const body = plain.subarray(0, plain.length - 2);
    if (crc16(body) !== ((plain[plain.length - 2] << 8) | plain[plain.length - 1])) continue;
    frames.push({ type: body[0], payload: body.subarray(1) });
  }
  return { frames, rest: bytes.subarray(start) };
}
/** The firmware a chip says it runs in its answer to a hello ("1.0.0"), or null for what is no such answer. */
export function versionOfHello(payload: Uint8Array): string | null {
  return payload.length >= 7 ? `${payload[1]}.${payload[2]}.${payload[3]}` : null;
}

// ---- The file and the drive ----
const UF2_FIRST = 0x0a324655, UF2_SECOND = 0x9e5d5157, UF2_LAST = 0x0ab16f30;
/** Whether these bytes are a UF2 file of the size the add-on named: whole blocks of 512 bytes, each with its marks. The
 * last look before anything is written to a chip. */
export function isUf2(data: Uint8Array, size: number): boolean {
  if (!data.length || data.length !== size || data.length % 512) return false;
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
  for (let at = 0; at < data.length; at += 512) {
    if (view.getUint32(at, true) !== UF2_FIRST || view.getUint32(at + 4, true) !== UF2_SECOND || view.getUint32(at + 508, true) !== UF2_LAST) return false;
  }
  return true;
}
/** Whether a folder is the chip's drive: its INFO_UF2.TXT names the board the step expects ("Board-ID: RPI-RP2"). A
 * folder someone picked by mistake has no such file, and nothing is written to it. */
export function isChipDrive(info: string | null, drive: string): boolean {
  if (!info) return false;
  const board = /^Board-ID:\s*(\S+)/m.exec(info);
  return !!board && board[1] === drive;
}
/** Whether a serial port is the chip's own, by its USB ids. */
export function isChipPort(info: { usbVendorId?: number; usbProductId?: number } | undefined, step: Pick<ChipFirmwareStep, "usb">): boolean {
  return !!info && step.usb.some((id) => id.vendor === info.usbVendorId && id.product === info.usbProductId);
}

// ---- The step as it goes ----
/** Where writing a chip's firmware stands: nothing yet; the chip's port is asked for; the chip restarts as a drive; the
 * drive is asked for; the file is written; the chip starts and the screen looks for it; done; or it stopped. */
export type ChipPhase = "idle" | "port" | "restart" | "drive" | "write" | "wait" | "done" | "failed";
/** Why it stopped, each a text under editor.steps.kinds.chip_firmware.errors. */
export type ChipProblem = "cancelled" | "no_port" | "port" | "file" | "not_drive" | "write" | "silent" | "failed";
/** Whether this page can do the step itself: a serial port for the restart and a folder to write to, in a secure page. */
export type ChipSupport = "ok" | "insecure" | "browser";
export function chipSupport(win: { isSecureContext?: boolean; navigator?: unknown; showDirectoryPicker?: unknown } = window): ChipSupport {
  if (!win.isSecureContext) return "insecure";
  return win.navigator && "serial" in (win.navigator as object) && typeof win.showDirectoryPicker === "function" ? "ok" : "browser";
}
