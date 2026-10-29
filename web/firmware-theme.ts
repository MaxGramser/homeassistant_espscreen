import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import type { Plugin } from "vite";

/** Read the firmware's one color table at build time; no second palette to maintain. */
export function firmwareTheme(): Plugin {
  const id = "virtual:esp-screens-theme", path = fileURLToPath(new URL("../components/smart_display/theme.h", import.meta.url));
  return {
    name: "esp-screens-firmware-theme",
    resolveId: (source) => source === id ? `\0${id}` : null,
    load(source) {
      if (source !== `\0${id}`) return;
      this.addWatchFile(path);
      const text = readFileSync(path, "utf8"), block = text.split("namespace ha {")[1].split("}  // namespace ha")[0];
      const ha = Object.fromEntries([...block.matchAll(/\b([A-Z_]+) = 0x([0-9A-F]{6})/g)].map((m) => [m[1], parseInt(m[2], 16)]));
      const roles = Object.fromEntries([...text.matchAll(/\/\* (\w+) \*\/\s+\{0x([0-9A-F]{6}), 0x([0-9A-F]{6})\}/g)]
        .map((m) => [m[1], { light: parseInt(m[2], 16), dark: parseInt(m[3], 16) }]));
      // An alert button's key colours (KEY_SWATCHES): its name, the key and the words on it.
      const keyBlock = text.split("KEY_SWATCHES[] = {")[1]?.split("};")[0] || "";
      const keys = [...keyBlock.matchAll(/\{"(\w+)", 0x([0-9A-F]{6}), 0x([0-9A-F]{6})\}/g)].map((m) => ({ name: m[1], key: parseInt(m[2], 16), text: parseInt(m[3], 16) }));
      const icon = /inline uint32_t icon\([\s\S]*?: mix\(color, 0x([0-9A-F]{6}), (\d+)\)/.exec(text);
      if (!ha.AMBER || !roles.CARD || !icon || !keys.length) throw new Error("The firmware theme changed; update the editor theme reader");
      return `export default ${JSON.stringify({ ha, roles, keys, iconBase: parseInt(icon[1], 16), iconWeight: Number(icon[2]) })};`;
    },
  };
}
