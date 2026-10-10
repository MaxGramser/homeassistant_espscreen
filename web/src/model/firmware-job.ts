// What New screen and Firmware & USB both say of the add-on's firmware job (api/firmware), said once: the build's
// memory in the editor's words, the image a build leaves to download, the browser flasher's turn once the build it waits
// for has ended, the USB port to install over, and the line of the log that says what went wrong.
import { editorNumber, t } from "../i18n";
import { memoryNote, type BuildMemory } from "./install-progress";

// ESPHome Web is ESPHome's own browser flasher; this address opens it with its hint for a downloaded project (as ESPHome
// Device Builder does).
export const ESPHOME_WEB = "https://web.esphome.io/?dashboard_install";

/** The memory a build has (build_memory.py, app 0.4.65), in the editor's words: why it runs with fewer compilers than the
 * machine has cores, that it started again with one after the memory ran out, or why it stopped. Null when it has room. */
export function memoryText(job: { memory?: BuildMemory | null } | null | undefined) {
  const note = memoryNote(job);
  if (!note) return null;
  const params = { free: `${editorNumber(note.free)} GB`, need: `${editorNumber(note.need)} GB`, jobs: note.jobs, cores: note.cores };
  return { reason: note.reason, title: t(`editor.installer.memory.${note.reason}_title`, params), text: t(`editor.installer.memory.${note.reason}`, params) };
}

/** The factory image a build of this profile leaves to download, and the name it is saved as. */
export const firmwareImage = (file: string) => ({
  href: `api/firmware/profiles/${encodeURIComponent(file)}/download`,
  name: file.replace(/\.yaml$/, "") + ".factory.bin",
});

/** The browser flasher's turn once the build it waits for has ended: write the image when the build succeeded and the
 * port waits, let go of the port when the build failed. Nothing while the build runs. */
export function afterBrowserBuild(state: string | null | undefined, phase: string): "write" | "release" | null {
  if (!state || state === "running" || phase !== "waiting") return null;
  return state === "success" ? "write" : "release";
}

/** The USB port to install over: the one chosen while it is plugged in, else the first one there is, else "usb", which
 * waits for one. Any other way (over the network, a download) as it is. */
export function usbTarget(target: string, ports: readonly string[]) {
  return target === "usb" || (target.startsWith("/") && !ports.includes(target)) ? ports[0] || "usb" : target;
}

/** The line of a build's or a check's log that says what went wrong: the last that names an error, else the last that
 * says something failed. */
export const errorLine = (logs: readonly string[]) =>
  logs.filter((line) => /error/i.test(line)).pop() || logs.filter((line) => /failed/i.test(line)).pop();
