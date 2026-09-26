// The browser flasher: esptool-js (Espressif, Apache-2.0) over Web Serial. Loaded with a dynamic import only when
// someone installs a screen from this browser, so the editor's own load doesn't carry it.
//
// Adapted from ESPHome's dashboard (github.com/esphome/dashboard, src/web-serial/create-esploader.ts, flash.ts and
// hard-reset.ts, at commit 72b9b1b; Copyright (c) 2019 Nabu Casa, MIT licence per the repository's LICENSE file; see
// NOTICE). Changed: the image arrives as bytes (esptool-js
// 0.6 takes a Uint8Array instead of a binary string), and the progress sum lives in ./logic.ts, where it is tested.
import { ESPLoader, Transport, UsbJtagSerialReset } from "esptool-js";
import { writtenPercent } from "./logic";

export type Loader = ESPLoader;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** ESPHome's createESPLoader: 115200 baud to the ROM and the stub alike (esptool-js 0.6 talks to the ROM at 115200),
 * so the port is never reopened at another speed. */
export function createLoader(port: SerialPort): ESPLoader {
  const transport = new Transport(port);
  return new ESPLoader({ transport, baudrate: 115200, enableTracing: false });
}

/** Connect, load the stub and check the flash chip: what ESPHome runs before it builds. Returns esptool's chip name. */
export async function connect(loader: ESPLoader): Promise<string> {
  await loader.main();
  await loader.flashId();
  return loader.chip.CHIP_NAME;
}

/** ESPHome's flashFiles for one factory image at address 0: optionally erase, then write compressed and keep the
 * flash settings the image has. */
export async function writeImage(loader: ESPLoader, data: Uint8Array, erase: boolean, onErase: () => void,
                                 onProgress: (percent: number) => void): Promise<void> {
  if (erase) {
    onErase();
    await loader.eraseFlash();
  }
  onProgress(0);
  await loader.writeFlash({
    fileArray: [{ data, address: 0 }],
    flashSize: "keep",
    flashMode: "keep",
    flashFreq: "keep",
    eraseAll: false,
    compress: true,
    reportProgress: (_file: number, written: number, total: number) => {
      const percent = writtenPercent(written, total);
      if (percent !== null) onProgress(percent);
    },
  });
  onProgress(100);
}

const ESPRESSIF_USB_VID = 0x303a;
// RTC watchdog registers per chip (base + offsets), from esptool python, as ESPHome's hard-reset.ts has them.
const WDT_RESET_CHIPS: Record<string, { wdtConfig0: number; wdtConfig1: number; wdtWProtect: number }> = {
  "ESP32-S2": { wdtConfig0: 0x3f408094, wdtConfig1: 0x3f408098, wdtWProtect: 0x3f4080ac },
  "ESP32-S3": { wdtConfig0: 0x60008098, wdtConfig1: 0x6000809c, wdtWProtect: 0x600080b0 },
  "ESP32-C2": { wdtConfig0: 0x60008084, wdtConfig1: 0x60008088, wdtWProtect: 0x6000809c },
  "ESP32-C3": { wdtConfig0: 0x60008090, wdtConfig1: 0x60008094, wdtWProtect: 0x600080a8 },
};
const RTC_CNTL_WDT_WKEY = 0x50d83aa1;

// A full chip reset through the RTC watchdog, which reaches a chip that a DTR/RTS reset doesn't (native
// USB-Serial-JTAG, CH9102F bridges). False for a chip without a safe watchdog reset (the classic ESP32, the P4).
async function watchdogReset(loader: ESPLoader, transport: Transport): Promise<boolean> {
  const regs = loader.chip?.CHIP_NAME ? WDT_RESET_CHIPS[loader.chip.CHIP_NAME] : undefined;
  if (!regs) return false;
  try {
    await transport.setDTR(false);
    await transport.setRTS(false);
  } catch {
    // The watchdog can still reset the chip.
  }
  try {
    await loader.writeReg(regs.wdtWProtect, RTC_CNTL_WDT_WKEY);
    await loader.writeReg(regs.wdtConfig1, 2000);
    await loader.writeReg(regs.wdtConfig0, ((1 << 31) | (5 << 28) | (1 << 8) | 2) >>> 0);
  } catch (error) {
    console.error("Watchdog reset failed to arm:", error);
    return false;
  }
  try {
    await loader.writeReg(regs.wdtWProtect, 0);
  } catch {
    // Raced by the reset itself.
  }
  await sleep(200);
  return true;
}

// A classic ESP32 behind a USB-UART bridge (the CYD's CH340): EN low, then high, with GPIO0 released, so it runs the app.
async function classicHardReset(transport: Transport): Promise<void> {
  await transport.setDTR(false);
  await transport.setRTS(true);
  await sleep(100);
  await transport.setRTS(false);
}

/** ESPHome's hardResetChip: boot the new firmware. esptool-js's own after() leaves a native USB chip in download mode. */
export async function restart(loader: ESPLoader): Promise<void> {
  const transport = loader.transport;
  if (await watchdogReset(loader, transport)) return;
  if (transport.device.getInfo().usbVendorId === ESPRESSIF_USB_VID) await new UsbJtagSerialReset(transport).reset();
  else await classicHardReset(transport);
}

/** Close the port; a port that is already gone is fine. */
export async function disconnect(loader: ESPLoader): Promise<void> {
  try {
    await loader.transport.disconnect();
  } catch {
    // Already closed by an unplugged cable.
  }
}
