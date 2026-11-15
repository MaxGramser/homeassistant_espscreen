// Whether the firmware preview the editor ships is older than the firmware (web/preview-age.ts), told from the commits.
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { previewAge } from "../preview-age";

const made: string[] = [];
afterEach(() => { for (const dir of made.splice(0)) rmSync(dir, { recursive: true, force: true }); });

function repository() {
  const root = mkdtempSync(join(tmpdir(), "preview-age-"));
  made.push(root);
  const git = (...args: string[]) => execFileSync("git", args, { cwd: root, stdio: "ignore",
    env: { ...process.env, GIT_AUTHOR_NAME: "t", GIT_AUTHOR_EMAIL: "t@example.org", GIT_COMMITTER_NAME: "t", GIT_COMMITTER_EMAIL: "t@example.org" } });
  const write = (path: string, text: string) => { mkdirSync(join(root, path, ".."), { recursive: true }); writeFileSync(join(root, path), text); };
  const commit = (message: string) => { git("add", "-A"); git("commit", "-q", "-m", message); };
  git("init", "-q");
  return { root, write, commit };
}

describe("the age of the firmware preview", () => {
  it("is current when the preview was built in the commit that last changed the firmware, or after it", () => {
    const { root, write, commit } = repository();
    write("components/smart_display/runtime_tiles.h", "1"); write("web/src/wasm/firmware_preview.wasm", "a");
    commit("firmware and its preview together");
    expect(previewAge(root).stale).toBe(false);
    write("components/smart_display/runtime_tiles.h", "2"); commit("the firmware changes");
    write("web/src/wasm/firmware_preview.wasm", "b"); commit("Firmware preview: rebuilt");
    expect(previewAge(root)).toMatchObject({ stale: false });
  });
  it("is stale when the firmware changed after the preview was last built", () => {
    const { root, write, commit } = repository();
    write("components/smart_display/runtime_tiles.h", "1"); write("web/src/wasm/firmware_preview.wasm", "a");
    commit("firmware and its preview together");
    write("packages/core.yaml", "x"); commit("the firmware changes, and the preview job fails");
    const age = previewAge(root);
    expect(age.stale).toBe(true);
    expect(age.preview && age.firmware).toBeTruthy();
  });
  it("does not count the preview's own generated files, or what is no firmware", () => {
    const { root, write, commit } = repository();
    write("components/a.h", "1"); write("web/src/wasm/firmware_preview.wasm", "a"); commit("together");
    write("web/wasm/generated/firmware_renderer_manifest.h", "x"); write("web/src/model/pages.ts", "y"); write("docs/PAGES.md", "z");
    commit("the editor, a document and a generated file");
    expect(previewAge(root).stale).toBe(false);
  });
  it("claims nothing where git has no answer", () => {
    const root = mkdtempSync(join(tmpdir(), "preview-age-"));
    made.push(root);
    expect(previewAge(root)).toEqual({ stale: false, firmware: null, preview: null });
  });
});
