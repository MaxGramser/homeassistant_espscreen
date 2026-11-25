// Cards the firmware draws for the editor (docs/EMULATOR_ARCHITECTURE.md, "Plugins" and "The page editor's own cards").
// The preview loads the modules of the plugins a screen runs before it starts and starts each one; a preview its owner
// draws (`manual`) takes a step and hands out a page's cards; and the faces store keeps one picture per face, keyed by
// what is drawn, asked for while something shows it.
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick } from "vue";
import FirmwarePreview from "../src/components/FirmwarePreview.vue";
import GlassFaces from "../src/components/GlassFaces.vue";
import createModule from "../src/wasm/firmware_preview.js";
import { api, getJson, send } from "../src/api";
import { useInventoryStore } from "../src/stores/inventory";
import { useDocumentStore } from "../src/stores/document";
import { faceKey, useFace, useFacesStore, type FaceAsk, type GlassCard } from "../src/stores/faces";
import { PREVIEW_NUMBER, usePluginCodeStore } from "../src/stores/plugin-code";
import { usePluginsStore } from "../src/stores/plugins";
import { useScreenStore } from "../src/stores/screen";
import type { Screen, Tile } from "../src/types";

vi.mock("../src/wasm/firmware_preview.js", () => ({ default: vi.fn() }));
vi.mock("../src/api", () => ({ api: vi.fn(), getJson: vi.fn(), send: vi.fn() }));
// The browser's keeping between visits is not this test's: nothing is kept, nothing comes back.
vi.mock("../src/model/face-cache", () => ({ keptFaces: vi.fn(() => Promise.resolve([])), keepFace: vi.fn(() => Promise.resolve()), forgetOldFaces: vi.fn(() => Promise.resolve()) }));

const CARDS: GlassCard[] = [{ i: 0, slot: 0, x: 10, y: 60, w: 200, h: 100, r: 16, plugin: true, n: 1 }, { i: 1, slot: 2, x: 220, y: 60, w: 100, h: 100, r: 16, plugin: false, n: 1 }];
const bundle = () => ({ revision: "1111111111111111", configuration: [{ op: "begin" }, { op: "commit" }], values: [{ op: "state", i: 0, state: "ok" }] });
function response(name: string, _result?: unknown, _types?: unknown, args?: unknown[]): string | number {
  if (name === "preview_next_action" || name === "preview_next_image" || name === "preview_next_setting") return "";
  if (name === "preview_receive" && JSON.parse(String(args?.[0])).op === "hello") return "Session:2222222222222222";
  if (name === "preview_cards") return JSON.stringify(CARDS);
  if (name === "preview_plugin") return 1;
  return "Synced";
}
let shown = 0;
const firmware = {
  HEAPU8: new Uint8Array(480 * 480 * 4),
  _preview_init: vi.fn(() => 1), _preview_time: vi.fn(), _preview_render: vi.fn(), _preview_frame: vi.fn(() => 0),
  _preview_image_buffer: vi.fn(() => 128), _preview_image_ready: vi.fn(() => 1), _preview_touch: vi.fn(), _preview_cancel: vi.fn(),
  _preview_dark: vi.fn(), _preview_page: vi.fn(() => shown), _preview_show: vi.fn((page: number) => { if (page > 3) return 0; shown = page; return 1; }),
  ccall: vi.fn(response), FS: { writeFile: vi.fn() }, loadDynamicLibrary: vi.fn(() => Promise.resolve(true)),
};
// A screen as the add-on lists it: its id, and the name of its ESPHome node, which is another word.
const hall = { id: "text.hall", node: "hall", name: "Hall", online: true } as unknown as Screen;
const INSTALLED = [{ id: "bus", version: "1.0.0", source: "index", state: "active" }, { id: "broken", version: "2.0.0", source: "index", state: "failed" }];
let wrapper: VueWrapper | undefined;
let doc: ReturnType<typeof useDocumentStore>;
let paint: Record<string, ReturnType<typeof vi.fn>>;

beforeEach(() => {
  shown = 0;
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
  vi.clearAllMocks();
  firmware.ccall.mockImplementation(response);
  firmware.loadDynamicLibrary.mockImplementation(() => Promise.resolve(true));
  doc = useDocumentStore();
  doc.document = { title: "Hall", pages: [] } as any;
  useInventoryStore().inventory = { screens: [], entities: [], features: { plugins: true } } as any;
  // The add-on's plugins are in (api/plugins answered): what is installed, by the screen's id as the add-on writes it.
  usePluginsStore().installed = { "text.hall": INSTALLED } as any;
  usePluginsStore().loaded = true;
  vi.mocked(createModule).mockImplementation(() => Promise.resolve({ ...firmware } as any));
  vi.mocked(send).mockResolvedValue(bundle());
  vi.mocked(getJson).mockResolvedValue([{ id: "bus", version: "1.0.0", url: "api/plugins/bus/module?abi=x&screen=text.hall&v=1.0.0" }]);
  vi.mocked(api).mockResolvedValue(new Response(new Uint8Array([0, 97, 115, 109])));
  vi.spyOn(window, "requestAnimationFrame").mockReturnValue(100);
  vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => {});
  paint = { putImageData: vi.fn(), clearRect: vi.fn(), save: vi.fn(), restore: vi.fn(), beginPath: vi.fn(), roundRect: vi.fn(), clip: vi.fn(), drawImage: vi.fn() };
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(paint as any);
  vi.stubGlobal("ImageData", class { constructor(public data: Uint8ClampedArray, public width: number, public height: number) {} });
});
afterEach(async () => {
  wrapper?.unmount(); wrapper = undefined;
  document.body.replaceChildren();
  await useFacesStore().drawFor("");
  vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers();
});

async function preview(extra: Record<string, unknown> = {}) {
  wrapper = mount(FirmwarePreview, { attachTo: document.body, props: { width: 480, height: 480, columns: 3, rows: 3, ...extra } });
  await flushPromises();
  return wrapper;
}

describe("the plugins' own code in the preview", () => {
  it("is asked for once per screen and what it runs, never for a preview screen or a plugin whose build failed", async () => {
    const code = usePluginCodeStore();
    const first = await code.codeFor(hall), again = await code.codeFor(hall);
    expect(first.map((plugin) => plugin.id)).toEqual(["bus"]);
    expect(again).toBe(first);
    expect(vi.mocked(getJson)).toHaveBeenCalledTimes(1);
    expect(vi.mocked(getJson).mock.calls[0]![0]).toBe(`plugins/modules?abi=${PREVIEW_NUMBER}&screen=text.hall`);
    expect(vi.mocked(api)).toHaveBeenCalledWith("plugins/bus/module?abi=x&screen=text.hall&v=1.0.0");
    expect(await code.codeFor({ ...hall, id: "virtual.1", virtual: true } as Screen)).toEqual([]);
    expect(await code.codeFor({ ...hall, id: "text.attic", node: "attic" } as Screen)).toEqual([]);
    expect(await code.codeFor(undefined)).toEqual([]);
    expect(vi.mocked(getJson)).toHaveBeenCalledTimes(1);
  });

  it("reads what a screen runs by the screen's id, as the add-on lists it, never by its node's name", async () => {
    const code = usePluginCodeStore();
    expect(code.runsOn(hall)).toBe("bus@1.0.0");
    // A list under the node's name is no screen's: the editor showed placeholders at every home that way.
    usePluginsStore().installed = { hall: INSTALLED } as any;
    expect(code.runsOn(hall)).toBe("");
    expect(await code.codeFor(hall)).toEqual([]);
    expect(vi.mocked(getJson)).not.toHaveBeenCalled();
    expect(code.runsOn({ ...hall, virtual: true } as Screen)).toBe("");
    expect(code.runsOn(undefined)).toBe("");
  });

  it("waits for the add-on's plugins before it says what a screen runs, so a preview that starts with the page has its code", async () => {
    const plugins = usePluginsStore(), code = usePluginCodeStore();
    plugins.installed = {} as any;
    plugins.loaded = false;
    // The plugins store asks the add-on itself (api/plugins); its answer comes when this test says so.
    let answer: (value: Response) => void = () => {};
    const asks = vi.fn((_url: string) => new Promise<Response>((resolve) => { answer = resolve; }));
    vi.stubGlobal("fetch", asks);
    expect(code.runsOn(hall)).toBe("");
    const asked = code.codeFor(hall);
    await flushPromises();
    // Nothing is decided, and no module asked for, while the add-on has not said what is installed.
    expect(asks.mock.calls.map((call) => call[0])).toEqual(["api/plugins"]);
    expect(vi.mocked(getJson)).not.toHaveBeenCalled();
    answer(new Response(JSON.stringify({ plugins: [], installed: { "text.hall": INSTALLED } })));
    expect((await asked).map((plugin) => plugin.id)).toEqual(["bus"]);
    expect(code.runsOn(hall)).toBe("bus@1.0.0");
    expect(code.drawnBy(hall, "plugin:bus.next")).toBe(`bus@1.0.0#${PREVIEW_NUMBER}`);
    // Asked again, the plugins are not: one answer serves every preview of the page.
    await code.codeFor({ ...hall, id: "text.attic" } as Screen);
    expect(asks).toHaveBeenCalledTimes(1);
  });

  it("starts a preview without plugins' code when the add-on does not say what is installed", async () => {
    const plugins = usePluginsStore(), code = usePluginCodeStore();
    plugins.installed = {} as any;
    plugins.loaded = false;
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
    expect(await code.codeFor(hall)).toEqual([]);
    expect(vi.mocked(getJson)).not.toHaveBeenCalled();
  });

  it("says which tiles the firmware draws, and with what, once the add-on has answered", async () => {
    const code = usePluginCodeStore();
    expect(code.drawnBy(hall, "plugin:bus.next")).toBeNull();
    await code.codeFor(hall);
    // The plugin, its version and the preview's own number: a card another version drew is another card.
    expect(code.drawnBy(hall, "plugin:bus.next")).toBe(`bus@1.0.0#${PREVIEW_NUMBER}`);
    expect(code.drawnBy(hall, "plugin:tram.next")).toBeNull();
    expect(code.drawnBy(hall, "light.desk")).toBeNull();
    expect(code.drawnBy({ ...hall, id: "text.attic" } as Screen, "plugin:bus.next")).toBeNull();
    expect(code.drawnBy(undefined, "plugin:bus.next")).toBeNull();
  });

  it("is written into the firmware and started before the first frame, in the screens' language", async () => {
    useInventoryStore().inventory.language = { effective: "nl" } as any;
    await preview({ screen: hall });
    const made = await vi.mocked(createModule).mock.results[0]!.value;
    expect(made.FS.writeFile).toHaveBeenCalledWith("/plugin-bus.wasm", expect.any(Uint8Array));
    expect(firmware.loadDynamicLibrary).toHaveBeenCalledWith("/plugin-bus.wasm", { loadAsync: true, global: true, nodelete: true });
    const started = firmware.ccall.mock.calls.findIndex((call) => call[0] === "preview_plugin");
    expect(firmware.ccall.mock.calls[started]![3]).toEqual(["/plugin-bus.wasm", "bus", "nl"]);
    expect(firmware._preview_init.mock.invocationCallOrder[0]!).toBeLessThan(firmware.ccall.mock.invocationCallOrder[started]!);
    expect(firmware.ccall.mock.invocationCallOrder[started]!).toBeLessThan(firmware._preview_render.mock.invocationCallOrder[0]!);
  });

  it("makes no firmware for a preview that left while the plugins were awaited", async () => {
    // The overview's previews when the page opens on a screen: mounted for a moment, gone before the add-on answered.
    // The preview's script is loaded when the first firmware is made; here it is in already, so that what is counted
    // below is a firmware made or not, never a script still on its way.
    await import("../src/wasm/firmware_preview.js");
    const plugins = usePluginsStore();
    plugins.installed = {} as any;
    plugins.loaded = false;
    // The add-on's plugins answer when this test says so; the firmware's own binary is there at once.
    let answer: (value: Response) => void = () => {};
    vi.stubGlobal("fetch", vi.fn((url: string) => (url === "api/plugins" ? new Promise<Response>((resolve) => { answer = resolve; })
      : Promise.resolve(new Response(new ArrayBuffer(8))))));
    await preview({ screen: hall });
    wrapper!.unmount(); wrapper = undefined;
    answer(new Response(JSON.stringify({ plugins: [], installed: { "text.hall": INSTALLED } })));
    await flushPromises();
    await flushPromises();
    expect(vi.mocked(createModule)).not.toHaveBeenCalled();
    // One that stays is made as before.
    await preview({ screen: hall });
    await flushPromises();
    expect(vi.mocked(createModule)).toHaveBeenCalledTimes(1);
  });

  it("leaves a preview without the plugin when its module does not link", async () => {
    firmware.loadDynamicLibrary.mockImplementationOnce(() => Promise.reject(new Error("undefined symbol")));
    await preview({ screen: hall });
    // A firmware a module failed to link into is not used: another one is made, without that plugin.
    expect(vi.mocked(createModule)).toHaveBeenCalledTimes(2);
    expect(firmware.ccall.mock.calls.some((call) => call[0] === "preview_plugin")).toBe(false);
    expect(firmware._preview_init).toHaveBeenCalledTimes(1);
  });
});

describe("a preview its owner draws", () => {
  type View = { capture(page: number): { cards: GlassCard[]; canvas(): HTMLCanvasElement } | null };
  it("draws no frame by itself, takes one step when asked, and copies the frame only when its owner wants it", async () => {
    const mounted = await preview({ manual: true, still: true, layout: doc.document });
    expect(firmware._preview_render).not.toHaveBeenCalled();
    const view = mounted.vm as unknown as View;
    // The page on the glass: one step, the cards, and no copy of the frame.
    const still = view.capture(0)!;
    expect(firmware._preview_render).toHaveBeenCalledTimes(1);
    expect(still.cards).toEqual(CARDS);
    expect(paint.putImageData).not.toHaveBeenCalled();
    // Its owner wants the pixels (a card changed): the frame is copied once, however many cards it cuts from it.
    expect(still.canvas()).toBe(mounted.find("canvas").element);
    still.canvas();
    expect(paint.putImageData).toHaveBeenCalledTimes(1);
    // Another page: it is turned to, made in a first step and drawn in a second.
    view.capture(2);
    expect(firmware._preview_show).toHaveBeenCalledWith(2);
    expect(firmware._preview_render).toHaveBeenCalledTimes(3);
    view.capture(2);
    expect(firmware._preview_show).toHaveBeenCalledTimes(1);
    expect(view.capture(7)).toBeNull();
  });

  it("gives nothing while the firmware does not have the layout as it is now, and says when it does", async () => {
    const mounted = await preview({ manual: true, still: true, layout: doc.document });
    const view = mounted.vm as unknown as View;
    // The whole layout came in: no single tile is named.
    expect(mounted.emitted("synced")).toEqual([[null]]);
    expect(view.capture(0)).not.toBeNull();
    // The layout changes: what the firmware shows is the one before, until the new one is in.
    let arrived: (value: ReturnType<typeof bundle>) => void = () => {};
    vi.mocked(send).mockImplementationOnce(() => new Promise((resolve) => { arrived = resolve; }));
    await mounted.setProps({ layout: { title: "Hall", pages: [], homePageId: "x" } });
    expect(view.capture(0)).toBeNull();
    vi.advanceTimersByTime(250);
    await flushPromises();
    expect(view.capture(0)).toBeNull();
    arrived(bundle());
    await flushPromises();
    expect(view.capture(0)).not.toBeNull();
    expect(mounted.emitted("synced")).toHaveLength(2);
  });

  it("names the tiles whose values came in new, and none when a refresh brought nothing", async () => {
    const mounted = await preview({ manual: true, still: true, layout: doc.document });
    // The same layout again, with the first tile's state changed and a second tile as it was.
    vi.mocked(send).mockResolvedValue({ ...bundle(), values: [{ op: "state", i: 0, state: "late" }, { op: "state", i: 1, state: "ok" }] });
    vi.advanceTimersByTime(10000);
    await flushPromises();
    expect(mounted.emitted("synced")![1]).toEqual([[0, 1]]);
    vi.mocked(send).mockResolvedValue({ ...bundle(), values: [{ op: "state", i: 0, state: "later" }, { op: "state", i: 1, state: "ok" }] });
    vi.advanceTimersByTime(10000);
    await flushPromises();
    expect(mounted.emitted("synced")![2]).toEqual([[0]]);
    vi.advanceTimersByTime(10000);
    await flushPromises();
    expect(mounted.emitted("synced")![3]).toEqual([[]]);
  });

  it("goes on after a refresh the add-on refused, and says so; a firmware that did not load is the end", async () => {
    // The add-on restarted (a write is refused until the page has its new token): the first refresh fails.
    vi.mocked(send).mockRejectedValueOnce(new Error("Forbidden"));
    const mounted = await preview({ manual: true, still: true, layout: doc.document });
    const view = mounted.vm as unknown as View;
    expect(mounted.emitted("failed")).toEqual([["Forbidden", false]]);
    expect(view.capture(0)).toBeNull();
    // Ten seconds on it asks again by itself, and draws.
    vi.advanceTimersByTime(10000);
    await flushPromises();
    expect(mounted.emitted("synced")).toEqual([[null]]);
    expect(view.capture(0)).not.toBeNull();
    expect(mounted.emitted("failed")).toHaveLength(1);
    wrapper!.unmount(); wrapper = undefined;
    // A browser that cannot run the firmware: nothing comes after it.
    vi.mocked(createModule).mockImplementation(() => Promise.reject(new Error("no WebAssembly")));
    const none = await preview({ manual: true, still: true, layout: doc.document });
    expect(none.emitted("failed")).toEqual([["no WebAssembly", true]]);
    vi.advanceTimersByTime(30000);
    await flushPromises();
    expect(none.emitted("synced")).toBeUndefined();
  });

  it("asks the add-on for the example of the slots that want one", async () => {
    await preview({ manual: true, still: true, layout: doc.document, examples: [2, 5] });
    expect(vi.mocked(send).mock.calls[0]![2]).toMatchObject({ examples: [2, 5] });
    wrapper!.unmount(); wrapper = undefined;
    vi.mocked(send).mockClear();
    await preview({ manual: true, still: true, layout: doc.document });
    expect(vi.mocked(send).mock.calls[0]![2]).not.toHaveProperty("examples");
  });
});

const tile = (changes: Partial<Tile> = {}): Tile => ({ id: "a1", entity: "plugin:bus.next", name: "Station", slot: 3, options: { size: "wide", plugin: { stop: "30009581", walk: 3 } }, ...changes });
const ask = (changes: Partial<FaceAsk> = {}): FaceAsk => ({ tile: tile(), columns: 2, rows: 1, example: false, by: "bus@1.0.0#abc", ...changes });
const GLASS = "text.hall:480x480:3x3:170:light:en";

describe("a face's key", () => {
  it("is the same for a tile that moved, a copy of it, and the same tile shown where it is on no page", () => {
    const key = faceKey(GLASS, ask());
    expect(faceKey(GLASS, ask({ tile: tile({ slot: 11 }) }))).toBe(key);
    expect(faceKey(GLASS, ask({ tile: tile({ id: "b2", slot: 0 }) }))).toBe(key);
    expect(faceKey(GLASS, ask({ tile: tile({ id: undefined, slot: 0 }) }))).toBe(key);
    // The options as they are written, in whatever order.
    expect(faceKey(GLASS, ask({ tile: tile({ options: { plugin: { walk: 3, stop: "30009581" }, size: "wide" } }) }))).toBe(key);
  });

  it("is another one for whatever changes the picture", () => {
    const key = faceKey(GLASS, ask());
    const others = [
      ask({ tile: tile({ options: { size: "wide", plugin: { stop: "30009581", walk: 4 } } }) }),
      ask({ tile: tile({ name: "Home" }) }),
      ask({ tile: tile({ entity: "plugin:bus.lines" }) }),
      ask({ columns: 2, rows: 2 }),
      ask({ example: true }),
      // Another version of the plugin, or another preview, drew another card.
      ask({ by: "bus@1.1.0#abc" }), ask({ by: "bus@1.0.0#def" }),
    ].map((other) => faceKey(GLASS, other));
    for (const other of others) expect(other).not.toBe(key);
    expect(new Set(others).size).toBe(others.length);
    // The look, the language, the grid and the screen are the glass.
    for (const glass of ["text.hall:480x480:3x3:170:dark:en", "text.hall:480x480:3x3:170:light:nl", "text.hall:480x480:2x4:170:light:en", "text.attic:480x480:3x3:170:light:en"])
      expect(faceKey(glass, ask())).not.toBe(key);
  });

  it("is its own full text, with every part readable in it", () => {
    expect(JSON.parse(faceKey(GLASS, ask()))).toEqual([GLASS, "bus@1.0.0#abc", "plugin:bus.next", 2, 1, false, "Station", { plugin: { stop: "30009581", walk: 3 }, size: "wide" }]);
  });
});

describe("asking for a face", () => {
  const Card = defineComponent({
    props: { wanted: { type: Object as () => FaceAsk | null, default: null } },
    setup(props) { const face = useFace(() => props.wanted); return () => h("i", face.value ? `${face.value.stamp}:${face.value.width}` : "none"); },
  });
  const frame = () => document.createElement("canvas");

  it("is asked while something shows it and given back after, however many show the same one", async () => {
    const faces = useFacesStore();
    await faces.drawFor(GLASS);
    const key = faces.keyOf(ask());
    const first = mount(Card, { props: { wanted: ask() } });
    expect(faces.asks.get(key)?.count).toBe(1);
    // A copy of the tile, elsewhere on the page: the same face, asked twice.
    const second = mount(Card, { props: { wanted: ask({ tile: tile({ id: "b2", slot: 9 }) }) } });
    expect(faces.asks.size).toBe(1);
    expect(faces.asks.get(key)?.count).toBe(2);
    first.unmount();
    expect(faces.asks.get(key)?.count).toBe(1);
    second.unmount();
    expect(faces.asks.size).toBe(0);
  });

  it("asks nothing for a card the editor draws itself, nor while there is no glass to draw for", async () => {
    const faces = useFacesStore();
    const none = mount(Card, { props: { wanted: ask() } });
    expect(faces.asks.size).toBe(0);
    await faces.drawFor(GLASS);
    await nextTick();
    expect(faces.asks.size).toBe(1);
    await none.setProps({ wanted: null });
    expect(faces.asks.size).toBe(0);
    none.unmount();
  });

  it("gets the picture when the firmware has drawn it, and keeps the last one while a new question has none yet", async () => {
    const faces = useFacesStore();
    await faces.drawFor(GLASS);
    const card = mount(Card, { props: { wanted: ask() } });
    expect(card.text()).toBe("none");
    faces.take(faces.keyOf(ask()), frame(), CARDS[0]!);
    await nextTick();
    expect(card.text()).toBe("1:200");
    // The frame is cut with the card's corners left clear, from where the card stands in it.
    expect(paint.roundRect).toHaveBeenCalledWith(0, 0, 200, 100, 16);
    expect(paint.drawImage).toHaveBeenCalledWith(expect.any(HTMLCanvasElement), 10, 60, 200, 100, 0, 0, 200, 100);
    faces.take(faces.keyOf(ask()), frame(), CARDS[0]!);
    await nextTick();
    expect(card.text()).toBe("2:200");
    // An option is typed: another face, not drawn yet. The card keeps what it showed, at the same size.
    const next = ask({ tile: tile({ options: { size: "wide", plugin: { stop: "3000", walk: 3 } } }) });
    await card.setProps({ wanted: next });
    expect(faces.asks.size).toBe(1);
    expect(card.text()).toBe("2:200");
    faces.take(faces.keyOf(next), frame(), CARDS[0]!);
    await nextTick();
    expect(card.text()).toBe("1:200");
    // Another size is another card: the picture of the old size does not stand in.
    await card.setProps({ wanted: ask({ columns: 1, rows: 1 }) });
    expect(card.text()).toBe("none");
    card.unmount();
  });

  it("takes no picture for a face nobody asks for, and lets go of the faces of another glass", async () => {
    const faces = useFacesStore();
    await faces.drawFor(GLASS);
    faces.take(faces.keyOf(ask()), frame(), CARDS[0]!);
    expect(faces.faces.size).toBe(0);
    const held = faces.ask(ask());
    faces.take(held.key, frame(), CARDS[0]!);
    expect(faces.of(held.key)?.kept).toBe(false);
    await faces.drawFor("text.hall:480x480:3x3:170:dark:en");
    expect(faces.of(held.key)).toBeUndefined();
    held.release(); held.release();
    expect(faces.asks.size).toBe(0);
  });
});

describe("the firmware behind the editor", () => {
  // A plugin's tile as its card asks (components/tile/TilePlugin.vue): a face, once the store says what draws it.
  const page = () => {
    const scr = useScreenStore(), code = usePluginCodeStore();
    const face = useFace(() => {
      const by = code.drawnBy(scr.currentScreen, "plugin:bus.next");
      return by ? { tile: tile(), columns: 2, rows: 1, example: false, by } : null;
    });
    return () => h("div", [h(GlassFaces), h("i", face.value ? `drawn ${face.value.width}x${face.value.height}` : "placeholder")]);
  };
  // The screen as a home has it: chosen in the editor, on a board the preview draws, with a node name of its own.
  function open() {
    const home = { ...hall, shape: { width: 480, height: 480, columns: 3, rows: 3, dpi: 133, look: "standard" } };
    useInventoryStore().inventory = { screens: [home], entities: [], features: { plugins: true } } as any;
    useScreenStore().selected = home.id;
    doc.documentGrid = { columns: 3, rows: 3 };
    return mount({ setup: page }, { attachTo: document.body });
  }
  const settle = async (ms: number) => { vi.advanceTimersByTime(ms); await flushPromises(); };

  it("draws a plugin's tile of the open screen, found by the screen's id", async () => {
    wrapper = open();
    await flushPromises();
    // The add-on was asked for this screen's modules, and the firmware runs a layout of the asked tile alone.
    expect(vi.mocked(getJson).mock.calls[0]![0]).toBe(`plugins/modules?abi=${PREVIEW_NUMBER}&screen=text.hall`);
    await settle(1000);
    expect(vi.mocked(send).mock.calls[0]![0]).toBe("firmware-preview");
    expect(wrapper.find("i").text()).toBe("drawn 200x100");
  });

  it("starts when the add-on's plugins come in after the screen was opened", async () => {
    const plugins = usePluginsStore();
    plugins.installed = {} as any;
    wrapper = open();
    await settle(1000);
    expect(wrapper.find("i").text()).toBe("placeholder");
    expect(vi.mocked(createModule)).not.toHaveBeenCalled();
    // The plugin is installed, or the list only now arrives: the code is asked for and the card drawn.
    plugins.installed = { "text.hall": INSTALLED } as any;
    await flushPromises();
    await settle(1000);
    expect(wrapper.find("i").text()).toBe("drawn 200x100");
  });

  it("ends at once on another screen that asks for no face, and comes back with its own screen", async () => {
    wrapper = open();
    await flushPromises();
    await settle(1000);
    expect(wrapper.find("i").text()).toBe("drawn 200x100");
    // The attic runs no plugin: its page asks for nothing.
    const inv = useInventoryStore();
    inv.inventory = { ...inv.inventory, screens: [...inv.inventory.screens, { ...inv.inventory.screens[0], id: "text.attic", node: "attic", name: "Attic" }] } as any;
    const made = vi.mocked(createModule).mock.calls.length;
    vi.mocked(send).mockClear();
    useScreenStore().selected = "text.attic";
    await flushPromises();
    expect(wrapper.find("i").text()).toBe("placeholder");
    expect(wrapper.find(".glass-faces").exists()).toBe(false);
    // No firmware for the attic, and nothing asked of the add-on for it, for as long as its page is open.
    await settle(30000);
    expect(vi.mocked(createModule)).toHaveBeenCalledTimes(made);
    expect(vi.mocked(send)).not.toHaveBeenCalled();
    // Back on the hall the firmware is made for it again and the card drawn.
    useScreenStore().selected = "text.hall";
    await flushPromises();
    await settle(1000);
    expect(wrapper.find("i").text()).toBe("drawn 200x100");
    expect(wrapper.find(".glass-faces").exists()).toBe(true);
  });

  it("does not give up when the add-on refuses one refresh", async () => {
    // The app restarted under an open page: a write is refused until the page has the app's new token.
    vi.mocked(send).mockRejectedValueOnce(new Error("Forbidden"));
    wrapper = open();
    await settle(1000);
    expect(wrapper.find("i").text()).toBe("placeholder");
    // The preview asks again ten seconds on; the card comes with it.
    await settle(10000);
    await settle(1000);
    expect(wrapper.find("i").text()).toBe("drawn 200x100");
  });

  it("leaves the editor's own drawing when the firmware cannot run, and does not try again and again", async () => {
    // A browser that cannot run the firmware.
    vi.mocked(createModule).mockImplementation(() => Promise.reject(new Error("no WebAssembly")));
    wrapper = open();
    await settle(1000);
    const made = vi.mocked(createModule).mock.calls.length;
    expect(made).toBeGreaterThan(0);
    await settle(30000);
    expect(wrapper.find("i").text()).toBe("placeholder");
    expect(vi.mocked(createModule)).toHaveBeenCalledTimes(made);
  });
});
