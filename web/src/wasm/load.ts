import type { FirmwarePreviewModule } from "./firmware_preview.js";
import wasmUrl from "./firmware_preview.wasm?url";

// A plugin's own code for the preview (docs/EMULATOR_ARCHITECTURE.md, "Plugins"): a module the add-on checked and
// handed over (stores/plugin-code.ts), built for this preview (web/wasm/build_plugin.py).
export type PluginCode = { id: string; bytes: Uint8Array };

// Every screen on the home page runs its own firmware; they share one download of the binary.
let binary: Promise<ArrayBuffer | undefined> | undefined;

// The firmware, with the plugins' own code loaded into it: each plugin's module is written into the preview's own
// file system and linked from there. A module that does not link leaves a preview that cannot be trusted, so the
// firmware is made anew without that plugin, whose tiles then show as on a screen that lacks it.
export async function loadFirmware(plugins: PluginCode[] = []): Promise<FirmwarePreviewModule> {
  binary ??= fetch(wasmUrl).then((response) => (response.ok ? response.arrayBuffer() : undefined)).catch(() => undefined);
  // The preview's own script comes with the first preview, not with the editor: a main module that plugins link
  // against brings all of Emscripten's runtime, which a page without a preview never needs.
  const [wasmBinary, { default: createModule }] = await Promise.all([binary, import("./firmware_preview.js")]);
  const module = await createModule(wasmBinary ? { wasmBinary } : { locateFile: () => wasmUrl });
  module.plugins = [];
  if (!module.FS || !module.loadDynamicLibrary) return module;
  for (const plugin of plugins) {
    const path = `/plugin-${plugin.id}.wasm`;
    try {
      module.FS.writeFile(path, plugin.bytes);
      await module.loadDynamicLibrary(path, { loadAsync: true, global: true, nodelete: true });
      module.plugins.push({ id: plugin.id, path });
    } catch {
      return loadFirmware(plugins.filter((other) => other !== plugin));
    }
  }
  return module;
}

// Each plugin's setup(), as the screen's boot runs it: after _preview_init and before the first frame, so the plugins
// hear on_ready together. `language`: the screens' language, which picks the plugin's own texts.
export function startPlugins(module: FirmwarePreviewModule, language: string) {
  for (const plugin of module.plugins ?? []) module.ccall("preview_plugin", "number", ["string", "string", "string"], [plugin.path, plugin.id, language]);
}
