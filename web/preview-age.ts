import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import type { Plugin } from "vite";

// Whether the firmware preview the editor ships (web/src/wasm/firmware_preview.wasm) is older than the firmware it is
// made from, said when the editor is built. The preview is rebuilt by CI after every firmware change on dev
// (.github/workflows/preview.yml), which builds the editor again too, so an editor built by CI always says "current".
// When that job fails, nothing says so where people look: in November 2026 the preview stood still for five days. The
// editor built last is then the one a developer built, and it says "stale" here, which the preview pane shows.
//
// By the commits, without a tool of its own: the last commit that changed what the preview is made from (the paths
// preview.yml watches, less its own output) against the last commit that changed the preview. The same commit, or a
// later one for the preview, is current. Where git cannot say (no history, no git), nothing is claimed.
const SOURCES = ["packages", "components", "fonts", "checkout", "tools/profiles.py", "screen_manager/Dockerfile",
  "web/wasm", ":!web/wasm/generated"];
const PREVIEW = ["web/src/wasm/firmware_preview.wasm"];

export type PreviewAge = { stale: boolean; firmware: string | null; preview: string | null };

/** The last commit that changed `paths`: its hash and its date, or null where git has no answer. */
function last(root: string, paths: string[]): { hash: string; at: string } | null {
  try {
    const out = execFileSync("git", ["log", "-1", "--format=%H %cI", "--", ...paths], { cwd: root, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
    const [hash, at] = out.split(" ");
    return hash && at ? { hash, at } : null;
  } catch { return null; }
}
/** Whether `ancestor` came before `commit` in the history. */
function before(root: string, ancestor: string, commit: string) {
  try { execFileSync("git", ["merge-base", "--is-ancestor", ancestor, commit], { cwd: root, stdio: "ignore" }); return true; } catch { return false; }
}
export function previewAge(root = fileURLToPath(new URL("..", import.meta.url))): PreviewAge {
  const firmware = last(root, SOURCES), preview = last(root, PREVIEW);
  if (!firmware || !preview) return { stale: false, firmware: null, preview: null };
  // Stale: the firmware changed in a commit that came after the preview's last one.
  const stale = firmware.hash !== preview.hash && before(root, preview.hash, firmware.hash);
  // The dates are said only when the preview is stale: that is the one time the editor shows them. A current preview's
  // dates would only make the built editor differ from one commit to the next (the preview's own commit has a date of
  // its own), and then the bundle in Git could never equal a build of the same sources ("bundle in Git is fresh").
  return stale ? { stale, firmware: firmware.at, preview: preview.at } : { stale: false, firmware: null, preview: null };
}

/** `virtual:esp-screens-preview-age`: what previewAge says while the editor is built. */
export function previewAgePlugin(): Plugin {
  const id = "virtual:esp-screens-preview-age";
  return {
    name: "esp-screens-preview-age",
    resolveId: (source) => (source === id ? `\0${id}` : null),
    load: (source) => (source === `\0${id}` ? `export default ${JSON.stringify(previewAge())};` : undefined),
  };
}
