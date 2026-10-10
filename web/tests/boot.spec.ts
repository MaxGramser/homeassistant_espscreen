// What the editor starts, and when (boot.ts): importing a module starts nothing (no request, no listener, no timer), the
// page's boot starts what it always did, and its stop takes all of it away again.
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import { FakeEventSource, lastStream, mediaListeners, setMedia } from "./helpers/browser";

const PHONE = "(max-width: 640px)";
const answer = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });

// The listeners the editor's own code adds and removes, by target and event: what a library does from its start
// (floating-vue listens for a click outside its popper) is its own business. One the editor adds through VueUse or Vue
// (useEventListener, a watch) is the editor's: the first caller that is neither of them decides.
// The whole stack: through VueUse and Vue it is deeper than the ten frames an Error keeps by default.
function deepStack() {
  const limit = Error.stackTraceLimit;
  Error.stackTraceLimit = 100;
  try { return new Error().stack!; } finally { Error.stackTraceLimit = limit; }
}
function listeners() {
  const count = new Map<string, number>();
  const src = `${join(__dirname, "..", "src")}/`;
  const fromSrc = () => deepStack().split("\n")
    .find((line) => (line.includes(src) || line.includes("/node_modules/")) && !/node_modules\/(@vitest|tinyspy|vitest|@vueuse|@vue|vue)\//.test(line))?.includes(src);
  for (const [target, label] of [[window, "window"], [document, "document"]] as const) {
    const add = target.addEventListener.bind(target), remove = target.removeEventListener.bind(target);
    const step = (name: string, by: number) => { if (fromSrc()) count.set(`${label}:${name}`, (count.get(`${label}:${name}`) || 0) + by); };
    vi.spyOn(target, "addEventListener").mockImplementation((name: string, ...rest: any[]) => { step(name, 1); return add(name, ...(rest as [any])); });
    vi.spyOn(target, "removeEventListener").mockImplementation((name: string, ...rest: any[]) => { step(name, -1); return remove(name, ...(rest as [any])); });
  }
  return { added: () => [...count.entries()].filter(([, n]) => n > 0).map(([name]) => name).sort(), touched: () => count.size };
}

afterEach(() => vi.resetModules());

describe("boot", () => {
  it("starts nothing when a module is imported: no request, no listener, no timer, no stream", async () => {
    vi.resetModules();
    const fetch = vi.fn(async () => answer({}));
    vi.stubGlobal("fetch", fetch);
    vi.useFakeTimers();
    const ours = listeners();
    // Every module of the editor, the components with them; main.ts is the page itself, which mounts and boots.
    const modules = import.meta.glob(["../src/**/*.ts", "../src/**/*.vue", "!../src/main.ts", "!../src/**/*.d.ts"]);
    for (const load of Object.values(modules)) await load();
    await vi.advanceTimersByTimeAsync(60000);
    expect(fetch).not.toHaveBeenCalled();
    expect(FakeEventSource.streams).toHaveLength(0);
    expect(mediaListeners(PHONE)).toBe(0);
    expect(ours.touched()).toBe(0);
    expect(vi.getTimerCount()).toBe(0);
  }, 30000);

  it("starts the store, the plugins and the drag, as the page always did, and stops all of it", async () => {
    vi.resetModules();
    vi.useFakeTimers();
    vi.stubGlobal("scrollTo", vi.fn());
    const fetch = vi.fn(async (url: string) => answer(String(url).startsWith("api/inventory")
      ? { csrf: "t", connected: true, screens: [], entities: [] } : { plugins: [], installed: {} }));
    vi.stubGlobal("fetch", fetch);
    const ours = listeners();
    const { boot } = await import("../src/boot");
    const store = await import("../src/store");
    const ui = (await import("../src/stores/ui")).useUiStore();
    const inventory = (await import("../src/stores/inventory")).useInventoryStore();
    const stop = boot();
    expect(boot()).toBe(stop);
    await vi.advanceTimersByTimeAsync(0);
    // The inventory, and the stream that keeps it current, in the editor's language.
    expect(fetch.mock.calls.filter(([url]) => String(url).startsWith("api/inventory")).map(([url]) => url)).toEqual(["api/inventory"]);
    expect(lastStream()?.url).toBe("api/events?language=en");
    expect(inventory.connected).toBe(true);
    // The plugins load where they are on (import.meta.env.DEV in the tests, editor_features.plugins in the app).
    expect(fetch.mock.calls.some(([url]) => url === "api/plugins")).toBe(true);
    // The address and the width of the window are followed.
    history.replaceState(null, "", "#settings");
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    expect(ui.route).toBe("#settings");
    setMedia(PHONE, true);
    expect(ui.narrowPhone).toBe(true);
    // The screensaver's drawers close when the layout comes back.
    store.state.tab = "settings";
    await nextTick();
    store.openSaverStep("clock");
    store.state.tab = "layout";
    await nextTick();
    expect(store.state.inspector).toBeNull();
    expect(ours.added()).toEqual(["document:visibilitychange", "window:beforeunload", "window:click", "window:hashchange", "window:pagehide"]);

    stop();
    expect(ours.added()).toEqual([]);
    expect(mediaListeners(PHONE)).toBe(0);
    expect(lastStream()?.readyState).toBe(FakeEventSource.CLOSED);
    expect(vi.getTimerCount()).toBe(0);
    const asked = fetch.mock.calls.length;
    await vi.advanceTimersByTimeAsync(600000);
    expect(fetch).toHaveBeenCalledTimes(asked);
    // Started again, it starts again.
    const again = boot();
    expect(again).not.toBe(stop);
    again();
  });
});
