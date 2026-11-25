// An editor older than its app reloads itself once nothing is in progress (stores/editor-version.ts).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import { ownBundle, stale, startEditorVersion } from "../src/stores/editor-version";
import { useInventoryStore } from "../src/stores/inventory";
import { useDocumentStore } from "../src/stores/document";
import { useUiStore } from "../src/stores/ui";

function page(src: string) {
  const script = document.createElement("script");
  script.type = "module";
  script.setAttribute("src", src);
  document.head.appendChild(script);
  return script;
}

describe("the editor this page runs", () => {
  let script: HTMLScriptElement | null = null;
  afterEach(() => { script?.remove(); script = null; });

  it("is the script its index.html named, and none on the development server", () => {
    expect(ownBundle()).toBeNull();
    script = page("./assets/index-AbC_12-x.js");
    expect(ownBundle()).toBe("index-AbC_12-x.js");
    expect(stale("index-a.js", "index-b.js")).toBe(true);
    expect(stale("index-a.js", "index-a.js")).toBe(false);
    expect(stale(null, "index-b.js")).toBe(false);
    expect(stale("index-a.js", null)).toBe(false);
  });
});

describe("an app that serves a newer editor", () => {
  let script: HTMLScriptElement;
  beforeEach(() => { script = page("./assets/index-old.js"); sessionStorage.clear(); });
  afterEach(() => script.remove());

  it("reloads the page at once when nothing is in progress", async () => {
    const reload = vi.fn();
    const stop = startEditorVersion(reload);
    useInventoryStore().inventory.editor = "index-old.js";
    await nextTick();
    expect(reload).not.toHaveBeenCalled();
    useInventoryStore().inventory.editor = "index-new.js";
    await nextTick();
    expect(reload).toHaveBeenCalledTimes(1);
    stop();
  });

  it("waits for New screen or Firmware & USB to be left, saying so once with a key to reload now", async () => {
    const reload = vi.fn();
    const ui = useUiStore();
    await ui.go("#new-screen");
    const stop = startEditorVersion(reload);
    useInventoryStore().inventory.editor = "index-new.js";
    await nextTick();
    expect(reload).not.toHaveBeenCalled();
    expect(ui.notice?.message).toContain("new version of the editor");
    await ui.go("");
    await nextTick();
    expect(reload).toHaveBeenCalledTimes(1);   // left New screen: it reloads once
    ui.notice?.action?.run();
    expect(reload).toHaveBeenCalledTimes(2);   // the key reloads now, whatever
    stop();
  });

  it("waits for plugins set aside in the tray, and reloads at most once for one editor", async () => {
    const reload = vi.fn();
    const plugins = (await import("../src/stores/plugins")).usePluginsStore();
    plugins.tray.items = [{ screen: "text.hall", plugin: "rain" }];
    const stop = startEditorVersion(reload);
    useInventoryStore().inventory.editor = "index-new.js";
    await nextTick();
    expect(reload).not.toHaveBeenCalled();
    plugins.tray.items = [];
    await nextTick();
    expect(reload).toHaveBeenCalledTimes(1);
    stop();
    // The page came back with the same old editor (the app named one it cannot serve): no second reload, no loop.
    const again = startEditorVersion(reload);
    await nextTick();
    expect(reload).toHaveBeenCalledTimes(1);
    again();
  });

  it("waits for unsaved changes", async () => {
    const reload = vi.fn();
    const doc = useDocumentStore();
    const dirty = vi.spyOn(doc, "dirty", "get").mockReturnValue(true);
    const stop = startEditorVersion(reload);
    useInventoryStore().inventory.editor = "index-new.js";
    await nextTick();
    expect(reload).not.toHaveBeenCalled();
    dirty.mockRestore();
    stop();
  });
});
