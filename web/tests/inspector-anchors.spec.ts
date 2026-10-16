// The thing itself at the head of its inspector (app 0.4.89), for the screensaver's clock and for a tile: the clock's
// row in small, its parts the way to their settings, and the tile as its page draws it. What is chosen there, the icons,
// the things to add, a tile's actions or another entity take the place under it, the head stays, and Done or Escape goes
// back one step at a time.
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SaverClock from "../src/components/SaverClock.vue";
import ScreensaverCard from "../src/components/ScreensaverCard.vue";
import TileInspector from "../src/components/TileInspector.vue";
import type { Inventory, ScreensaverView, Tile } from "../src/types";
import { appendTiles, current, loadLayout } from "./helpers/fixtures";
import { useEntitiesStore } from "../src/stores/entities";
import { useScreenStore } from "../src/stores/screen";
import { useScreensaverStore } from "../src/stores/screensaver";
import { useInventoryStore } from "../src/stores/inventory";
import { useDocumentStore } from "../src/stores/document";
import { useInspectorStore } from "../src/stores/inspector";
import { useUiStore } from "../src/stores/ui";

let insp: ReturnType<typeof useInspectorStore>;
let doc: ReturnType<typeof useDocumentStore>;
const ICONS = { groups: [{ label: "Weather", icons: [{ name: "thermometer", label: "Thermometer", cp: "F050F" }, { name: "lamp", label: "Lamp", cp: "F06B5" }] }],
  weather: {}, sun: {}, defaults: {}, fallback: "F0335", builtin: {}, controls: {} };
const saver = (patch: Partial<ScreensaverView> = {}): ScreensaverView => ({
  show: true, media: "", more: [], camera: "", order: ["media", "camera", "clock"], off: [], weather: "", ready: true, pictures: true, standby: true,
  items: [{ type: "entity", entity: "sensor.out", content: "state", icon: "auto" }, { type: "entity", entity: "lock.front", content: "icon", icon: "auto" }], ...patch,
});

beforeEach(() => {
  insp = useInspectorStore();
  doc = useDocumentStore();
  vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
  useInventoryStore().inventory = {
    csrf: "t", connected: true,
    screens: [{ id: "living", name: "Living", virtual: true, online: true, firmware: "0.56.0", shape: { width: 480, height: 480, columns: 2, rows: 3 }, screensaver: saver(),
      layout: { title: "Living", tiles: [] } }],
    entities: [{ id: "sensor.out", name: "Outside", state: "12", area: "" }, { id: "lock.front", name: "Front lock", state: "locked", area: "" },
      { id: "light.a", name: "Lamp", state: "on", area: "" }, { id: "light.b", name: "Desk lamp", state: "off", area: "" }],
    builtin: [], icons: ICONS, backgrounds: { auto: { label: "Default" } },
    header: { max_items: 6, builtin: [], contents: [{ key: "state", label: "State" }, { key: "icon", label: "Icon" }], shows: [{ key: "always", label: "Always" }] },
  } as unknown as Inventory;
  useScreenStore().selected = "living";
  doc.documentGrid = { columns: 2, rows: 3 };
  loadLayout({ title: "Living", tiles: [] });
  insp.closeInspector();
  insp.iconPickerOpen = false; insp.actionPickerOpen = false; insp.entityPickerOpen = false;
  useUiStore().tab = "settings";
});

const clock = () => mount(SaverClock, { props: { index: insp.inspector?.kind === "saver-item" ? insp.inspector.index : -1, adding: insp.inspector?.kind === "saver-add" } });

describe("the screensaver's clock with its row at the head", () => {
  it("shows the clock, every entity and a place to add, and only the chosen part under it", () => {
    insp.openSaverStep("clock");
    let view = clock();
    expect(view.find(".bar-strip").classes()).toContain("saver");
    expect(view.findAll(".bar-strip .strip-item")).toHaveLength(2);
    expect(view.find(".strip-left").attributes("data-state")).toBe("active");
    // The clock's own part: the glass and the temperature, and its place among the steps in the foot.
    expect(view.find(".bar-part .saver-glass").exists()).toBe(true);
    expect(view.find(".bar-part #saver-weather").exists()).toBe(true);
    expect(view.find('.dr-foot button[aria-label="Try later"]').exists()).toBe(true);
    // An entity that shows its icon alone stands in the row as its icon alone.
    expect(view.find(".strip-item[data-index='1'] .strip-text").exists()).toBe(false);
    insp.openSaverItem(0);
    view = clock();
    expect(view.find(".strip-item[data-index='0']").attributes("data-state")).toBe("active");
    expect(view.find(".bar-cap b").text()).toBe("Outside");
    expect(view.find(".bar-part .saver-glass").exists()).toBe(false);
    expect(view.find(".bar-part .seg").exists()).toBe(true);
    // No second head and no list of entities any more.
    expect(view.findAll(".dr-head")).toHaveLength(1);
    expect(view.find("#screensaver-items").exists()).toBe(false);
  });

  it("changes an entity's look and moves it along the row", async () => {
    insp.openSaverItem(0);
    const view = clock();
    await view.findAll(".bar-part .seg button").find((b) => b.text() === "Icon")!.trigger("click");
    expect(useScreensaverStore().saverItems[0].content).toBe("icon");
    await view.find('.dr-foot button[aria-label="Move right"]').trigger("click");
    expect(useScreensaverStore().saverItems.map((it) => it.entity)).toEqual(["lock.front", "sensor.out"]);
    expect(insp.inspector).toEqual({ kind: "saver-item", index: 1 });
  });

  it("puts an entity's icons in the place of its look, the row still above, and Done or Escape ends it", async () => {
    insp.openSaverItem(0);
    const view = clock();
    await view.find(".bar-part .choice-field").trigger("click");
    expect(insp.iconPickerOpen).toBe(true);
    expect(view.find(".bar-part > .picker").exists()).toBe(true);
    expect(view.find(".bar-part .seg").exists()).toBe(false);
    expect(view.find(".bar-strip").exists()).toBe(true);
    expect(view.find(".dr-foot").exists()).toBe(false);
    await view.find(".bar-part .icon-grid button").trigger("click");
    expect(useScreensaverStore().saverItems[0].icon).toBe("thermometer");
    expect(insp.iconPickerOpen).toBe(true);
    await view.find("#saver-done").trigger("click");
    expect(insp.iconPickerOpen).toBe(false);
    insp.iconPickerOpen = true;
    insp.escape();
    expect(insp.iconPickerOpen).toBe(false);
    expect(insp.inspector).toEqual({ kind: "saver-item", index: 0 });
  });

  it("adds under the row with no Cancel, and Escape goes back to the clock instead of closing", async () => {
    insp.openSaverStep("clock");
    let view = clock();
    await view.find(".strip-add").trigger("mousedown", { button: 0 });
    expect(insp.inspector).toEqual({ kind: "saver-add" });
    view = clock();
    expect(view.find(".strip-add").attributes("data-state")).toBe("active");
    expect(view.find(".bar-part #saver-search").exists()).toBe(true);
    expect(view.find(".dr-foot").exists()).toBe(false);
    insp.escape();
    expect(insp.inspector).toEqual({ kind: "saver", step: "clock" });
  });

  it("keeps the clock marked in the screensaver's list while one of its entities is open", () => {
    insp.openSaverItem(1);
    const card = mount(ScreensaverCard);
    expect(card.find('.saver-row[data-kind="clock"]').classes()).toContain("opened");
  });
});

describe("a tile with itself at the head", () => {
  const lamp = (): Tile => { appendTiles({ entity: "light.a", name: "", slot: 0 }); const tile = doc.layout!.tiles[0]; insp.openTile(tile); return tile; };
  const panel = (tile: Tile) => mount(TileInspector, { props: { tile: current(tile) } });

  it("draws the tile as its page does, and the icon pointed at shows on it before it is picked", async () => {
    const tile = lamp();
    const view = panel(tile);
    expect(view.find(".tile-anchor .tile .nm").text()).toBe("Lamp");
    // The settings stand under it as before.
    expect(view.find(".insp-sec").exists()).toBe(true);
    await view.find(".style-section .choice-field").trigger("click");
    await view.findAll(".bar-part .icon-grid button")[1].trigger("pointerenter");
    expect(insp.optionPreview).toEqual({ tileId: tile.id, key: "icon", value: "lamp" });
    expect(view.find(".tile-anchor .tile .ic").text()).toBe(String.fromCodePoint(0xF06B5));
  });

  it("puts the icons in the place of the settings, and Done or Escape goes back", async () => {
    const tile = lamp();
    const view = panel(tile);
    await view.find(".style-section .choice-field").trigger("click");
    expect(view.find("#tile-place b").text()).toBe("Icon");
    expect(view.find(".bar-part > .picker").exists()).toBe(true);
    expect(view.find(".insp-sec").exists()).toBe(false);
    expect(view.find(".tile-anchor .tile").exists()).toBe(true);
    await view.find(".bar-part .icon-grid button").trigger("click");
    expect(current(tile).options?.icon).toBe("thermometer");
    await view.find("#tile-done").trigger("click");
    expect(insp.iconPickerOpen).toBe(false);
    expect(view.find(".insp-sec").exists()).toBe(true);
    // The tile's own icon opens them too; Escape closes them and keeps the tile's settings.
    await view.find(".tile-anchor .tile .ic").trigger("click");
    expect(insp.iconPickerOpen).toBe(true);
    insp.escape();
    expect(insp.iconPickerOpen).toBe(false);
    expect(insp.inspector).toEqual({ kind: "tile" });
  });

  it("goes to the Name field from the tile's name", async () => {
    const tile = lamp();
    const view = mount(TileInspector, { props: { tile: current(tile) }, attachTo: document.body });
    await view.find(".tile-anchor .tile .nm").trigger("click");
    await nextTick(); await nextTick();
    expect(document.activeElement?.id).toBe("tile-name");
    view.unmount();
  });

  it("chooses an action in the place under the tile, and Escape leaves the tap as it was", async () => {
    useEntitiesStore().entityActions["light.a"] = [{ action: "light.turn_on", name: "Turn on", description: "", fields: [] }] as any;
    const tile = lamp();
    const view = panel(tile);
    await view.findAll("button").find((b) => b.text() === "Perform action")!.trigger("click");
    expect(view.find(".bar-part .action-choice").exists()).toBe(true);
    insp.escape();
    await nextTick();
    expect(insp.actionPickerOpen).toBe(false);
    expect(current(tile).options?.tap).toBeUndefined();
    expect(view.findAll("button").find((b) => b.text() === "Perform action")!.attributes("aria-pressed")).toBe("false");
    // Chosen, it is stored and its row stands in the settings, which opens the list again.
    await view.findAll("button").find((b) => b.text() === "Perform action")!.trigger("click");
    await view.find(".bar-part .action-choice").trigger("click");
    expect(current(tile).options?.action).toEqual({ action: "light.turn_on" });
    await view.setProps({ tile: current(tile) });
    expect(view.find(".bar-part").exists()).toBe(false);
    await view.find("#action-choose").trigger("click");
    expect(view.find(".bar-part .action-choice").exists()).toBe(true);
  });

  it("chooses another entity in the place under the tile, from its menu", async () => {
    const tile = lamp();
    const view = panel(tile);
    insp.entityPickerOpen = true;
    await nextTick();
    expect(view.find("#tile-place b").text()).toBe("Choose another entity");
    expect(view.find(".bar-part #entity-fix").exists()).toBe(true);
    expect(view.find(".bar-part .fix-close").exists()).toBe(false);
    insp.escape();
    await nextTick();
    expect(view.find("#entity-fix").exists()).toBe(false);
    expect(insp.inspector).toEqual({ kind: "tile" });
  });
});
