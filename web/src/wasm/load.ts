import createModule, { type FirmwarePreviewModule } from "./firmware_preview.js";
import wasmUrl from "./firmware_preview.wasm?url";

// Every screen on the home page runs its own firmware; they share one download of the binary.
let binary: Promise<ArrayBuffer | undefined> | undefined;

export function loadFirmware(): Promise<FirmwarePreviewModule> {
  binary ??= fetch(wasmUrl).then((response) => (response.ok ? response.arrayBuffer() : undefined)).catch(() => undefined);
  return binary.then((wasmBinary) => createModule(wasmBinary ? { wasmBinary } : { locateFile: () => wasmUrl }));
}
