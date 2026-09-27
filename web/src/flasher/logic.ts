// Installing a screen from the browser (Web Serial): the rules that need no serial port, so the page can ask them
// before it loads the flasher, and the tests can ask them without one. The flasher itself is ./esptool.ts, loaded only
// when someone installs this way.
//
// The route follows ESPHome's own dashboard ("Install → Plug into this computer", github.com/esphome/dashboard,
// see NOTICE): the same requirements (Web Serial in a secure context), the same library (esptool-js by Espressif) and
// the same order: pick the port, connect and read the chip, build, fetch the factory image, write it from address 0.

/** Whether this page can reach a USB port, and if not, why not. */
export type FlashSupport = "ok" | "insecure" | "browser";

/**
 * Web Serial exists only in Chrome and Edge on a computer, and only on a page served over https (or from localhost).
 * Chrome hides `navigator.serial` on a plain http page as well, so an insecure page is named first: there the cure is
 * https, not another browser. ESPHome's dashboard asks the same two questions (supportsWebSerial, allowsWebSerial).
 */
export function flashSupport(win: { isSecureContext?: boolean; navigator?: unknown } = window): FlashSupport {
  if (!win.isSecureContext) return "insecure";
  return win.navigator && "serial" in (win.navigator as object) ? "ok" : "browser";
}

// ESP-IDF's esp_chip_id_t, as an image header carries it, by the name esptool gives the chip (its CHIP_NAME).
export const IMAGE_CHIP_IDS: Record<number, string> = {
  0: "ESP32", 2: "ESP32-S2", 5: "ESP32-C3", 9: "ESP32-S3", 12: "ESP32-C2", 13: "ESP32-C6", 16: "ESP32-H2",
  18: "ESP32-P4", 20: "ESP32-C61", 23: "ESP32-C5",
};
// Where the bootloader sits in a factory image, which starts at flash address 0: 0x1000 on the ESP32 and S2, 0x2000
// on the P4 and C5, 0 on the others. What comes before it is erased flash (0xFF).
const BOOTLOADER_OFFSETS = [0x0, 0x1000, 0x2000];
const IMAGE_MAGIC = 0xe9;

/**
 * The chip a factory image was built for, from its bootloader's header (magic 0xE9, chip id at byte 12, little
 * endian), or null when the file doesn't say. The last check before anything is written: the board on the cable
 * was compared with the screen's board before the build, and this compares it with what the build really made.
 */
export function imageChip(data: Uint8Array): string | null {
  for (const offset of BOOTLOADER_OFFSETS) {
    if (data.length < offset + 16) break;
    if (data[offset] !== IMAGE_MAGIC) continue;
    return IMAGE_CHIP_IDS[data[offset + 12] | (data[offset + 13] << 8)] ?? null;
  }
  return null;
}

/** Whether a chip esptool found fits the chip a screen is built for; an unknown expectation lets any chip through. */
export const chipMatches = (found: string, expected?: string | null) => !expected || found.toUpperCase() === expected.toUpperCase();

/**
 * The percentage written, from esptool-js's report of compressed blocks: the same sum as ESPHome's flashFiles, for
 * one file from address 0. The report at the very end (written === total) is left to the caller's final 100.
 */
export function writtenPercent(written: number, total: number): number | null {
  if (!total || written >= total) return null;
  return Math.max(0, Math.min(99, Math.floor((written / total) * 100)));
}

/** What went wrong, as a key under editor.webflash.errors; the texts say what to do about it. */
export type FlashProblem = "no_port" | "blocked" | "busy" | "connect" | "wrong_chip" | "wrong_image" | "disconnected"
  | "download" | "failed";

/** Why the browser's port picker gave no port. */
export function pickProblem(error: unknown): FlashProblem {
  const name = (error as { name?: string } | null)?.name;
  // NotFoundError: the picker was closed without a port, which is also what an empty list (a cable that only
  // charges, a missing driver) ends in. SecurityError: a policy or the site's permissions keep USB ports away.
  if (name === "NotFoundError" || name === "AbortError") return "no_port";
  if (name === "SecurityError") return "blocked";
  return "failed";
}

/** Why connecting to the chosen port failed: the port is someone else's, or the chip didn't answer. */
export function connectProblem(error: unknown): FlashProblem {
  const name = (error as { name?: string } | null)?.name || "";
  const message = String((error as { message?: string } | null)?.message ?? error ?? "");
  // Chrome refuses to open a port another program or tab holds: NetworkError "Failed to open serial port", or
  // InvalidStateError when this page itself still has it open.
  if (name === "NetworkError" || name === "InvalidStateError" || /failed to open serial port|already open/i.test(message)) return "busy";
  return "connect";
}
