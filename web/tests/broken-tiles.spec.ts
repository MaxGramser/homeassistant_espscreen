// Broken tiles (model/broken-tiles.ts, stores/broken.ts, editor/tile-entity.ts and the parts that show them): a tile whose
// entity Home Assistant no longer has, or has had no word from for a while, found on every screen, said calmly on the
// overview and in the sidebar, and opened in the inspector with the entity picker ready.
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import BrokenNotice from "../src/components/BrokenNotice.vue";
import HomeView from "../src/components/HomeView.vue";
import Sidebar from "../src/components/Sidebar.vue";
import TileEntityFix from "../src/components/TileEntityFix.vue";
import { replaceTileEntity } from "../src/editor/tile-entity";
import { t } from "../src/i18n";
import { brokenSummary, brokenTiles, entityHealth, healthText, replacementCandidates, summaryText, tileEntities, UNAVAILABLE_MS, whereText,
  type HealthFacts } from "../src/model/broken-tiles";
import { emptyLayout, emptyPage } from "../src/model/pages";
import { useBrokenStore } from "../src/stores/broken";
import { useDocumentStore } from "../src/stores/document";
import { useInspectorStore } from "../src/stores/inspector";
import { useInventoryStore } from "../src/stores/inventory";
import { useScreenStore } from "../src/stores/screen";
import { useUiStore } from "../src/stores/ui";
import type { Entity, PageLayout, PageTile, Screen } from "../src/types";
import { openScreen, screenFixture } from "./helpers/fixtures";

const NOW = Date.UTC(2026, 9, 10, 10, 42);
const entity = (id: string, more: Partial<Entity> = {}): Entity => ({ id, name: id.split(".")[1].replace(/_/g, " "), state: "on", ...more });
const facts = (entities: Entity[], live: Record<string, string> = {}, ready = true): HealthFacts =>
  ({ ready, known: (id) => entities.find((e) => e.id === id), live: (id) => live[id], now: NOW });
const tile = (id: string, content: PageTile["content"], row = 0, column = 0, children?: PageTile["children"]): PageTile =>
  ({ id, content, appearance: { label: "" }, interaction: {}, placement: { row, column, columns: 1, rows: 1 }, ...(children ? { children } : {}) });

describe("an entity's health", () => {
  const away = (minutes: number) => entity("sensor.porch", { state: "unavailable", unavailable_since: (NOW - minutes * 60000) / 1000 });
  it("is gone when Home Assistant no longer has it, and unknown before its entities are known", () => {
    expect(entityHealth("sensor.gone", facts([]))).toEqual({ kind: "missing" });
    expect(entityHealth("sensor.gone", facts([], {}, false))).toBeNull();
    expect(entityHealth("sensor.here", facts([entity("sensor.here")]))).toBeNull();
  });
  it("is unavailable only after a while, by Home Assistant's own moment, and fine again once a live state says so", () => {
    expect(entityHealth("sensor.porch", facts([away(2)]))).toBeNull();
    expect(entityHealth("sensor.porch", facts([away(UNAVAILABLE_MS / 60000)]))).toEqual({ kind: "unavailable", since: NOW - UNAVAILABLE_MS });
    expect(entityHealth("sensor.porch", facts([away(90)], { "sensor.porch": "12" }))).toBeNull();
    // Without the moment it went, nobody can tell a moment from a while.
    expect(entityHealth("sensor.porch", facts([entity("sensor.porch", { state: "unavailable" })]))).toBeNull();
    expect(healthText({ kind: "unavailable", since: NOW - 7 * 60000 }, NOW)).toBe(t("editor.broken.unavailable_minutes", 7));
    expect(healthText({ kind: "unavailable", since: NOW - 3 * 3600000 }, NOW)).toBe(t("editor.broken.unavailable_hours", 3));
    expect(healthText({ kind: "unavailable", since: NOW - 3 * 86400000 }, NOW)).toBe(t("editor.broken.unavailable_days", 3));
    expect(healthText({ kind: "missing" }, NOW)).toBe(t("editor.broken.missing"));
  });
});

describe("the tiles that must have their entity", () => {
  it("are tiles of an entity, a bedside clock's keys and a plugin's tile that names one; never the screen's own cards", () => {
    const layout: PageLayout = emptyLayout("Hall");
    layout.pages.push(emptyPage());
    layout.pages[1].topbar.title = { source: "text", text: "Upstairs" };
    layout.pages[0].tiles = [tile("a", { kind: "entity", entityId: "light.a" }),
      tile("clock", { kind: "builtin", name: "nightstand" }, 0, 1, [{ id: "k", content: { kind: "entity", entityId: "switch.k" }, appearance: { label: "Key" }, interaction: {} }]),
      tile("go", { kind: "navigation", target: { kind: "page", pageId: layout.pages[1].id } }, 1, 0)];
    layout.pages[1].tiles = [tile("bus", { kind: "plugin", plugin: "bus", tile: "departures" }), tile("price", { kind: "plugin", plugin: "prices", tile: "day", entityId: "sensor.price" }, 0, 1)];
    expect(tileEntities(layout).map((item) => [item.tileId, item.entity, item.page, item.pageTitle, item.holder ?? null, item.plugin ?? false])).toEqual([
      ["a", "light.a", 0, "", null, false], ["k", "switch.k", 0, "", "clock", false], ["price", "sensor.price", 1, "Upstairs", null, true]]);
  });

  it("are found on every screen and summed up in a sentence, the one screen by its name", () => {
    const layoutOf = (screen: Screen) => (screen.page_document as any).layout as PageLayout;
    const hall = screenFixture({ id: "hall", name: "Hall", online: true, layout: { title: "Hall", tiles: [{ entity: "light.a", name: "", slot: 0 }, { entity: "sensor.gone", name: "Old", slot: 1 }] } } as any);
    const desk = screenFixture({ id: "desk", name: "Desk", online: true, layout: { title: "Desk", tiles: [{ entity: "sensor.gone", name: "", slot: 7 }] } } as any);
    const health = (id: string) => entityHealth(id, facts([entity("light.a")]));
    const found = brokenTiles([hall, desk], layoutOf, health);
    expect(found.map((item) => [item.screen.name, item.label, item.page])).toEqual([["Hall", "Old", 0], ["Desk", "", 1]]);
    const summary = brokenSummary(found)!;
    expect(summary).toEqual({ tiles: 2, screens: 2, kind: "missing" });
    expect(summaryText(summary)).toBe(t("editor.broken.summary.missing", { screens: t("editor.broken.screens", 2), n: 2 }, 2));
    expect(summaryText(brokenSummary(found.slice(0, 1))!)).toBe("1 tile on Hall shows an entity that no longer exists");
    expect(whereText(found[1])).toBe("Desk · Page 2");
    expect(whereText(found[1], false)).toBe("Page 2");
    expect(brokenSummary([])).toBeNull();
    expect(brokenSummary([found[0], { ...found[1], health: { kind: "unavailable", since: 0 } }])!.kind).toBe("mixed");
  });
});

describe("another entity for a tile", () => {
  const entities = [entity("sensor.kitchen_humidity"), entity("sensor.kitchen_temperature_2"), entity("sensor.power"), entity("light.kitchen"),
    entity("device_tracker.phone", { tile: false })];
  it("offers its kind, the names closest to the old one first, and what the search finds with its kind first", () => {
    expect(replacementCandidates("sensor.kitchen_temperature", entities, "").map((e) => e.id))
      .toEqual(["sensor.kitchen_temperature_2", "sensor.kitchen_humidity", "sensor.power"]);
    expect(replacementCandidates("sensor.kitchen_temperature", entities, "kitchen").map((e) => e.id))
      .toEqual(["sensor.kitchen_humidity", "sensor.kitchen_temperature_2", "light.kitchen"]);
    expect(replacementCandidates("sensor.kitchen_temperature", entities, "phone")).toEqual([]);
  });
});

// ---- The stores and the parts ----
const living = () => screenFixture({ id: "living", name: "Living room", online: true, firmware: "0.53.0", entity_tiles_repeat: false,
  layout: { title: "Living room", tiles: [{ entity: "sensor.gone", name: "Porch", slot: 0, options: { display: "graph" } }, { entity: "light.a", name: "", slot: 1 }] } } as any);
const hall = () => screenFixture({ id: "hall", name: "Hall", online: true, firmware: "0.53.0", layout: { title: "Hall", tiles: [{ entity: "light.a", name: "", slot: 0 }] } } as any);
beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
  useInventoryStore().inventory = { connected: true, screens: [living(), hall()],
    entities: [entity("light.a"), entity("sensor.temperature", { state: "21" }), entity("sensor.temperature_2", { state: "20" }), entity("light.b")] } as any;
});

describe("the broken tiles of the house", () => {
  it("counts the open screen as its draft has it: a tile given another entity is fine at once", async () => {
    const broken = useBrokenStore();
    expect(broken.tiles.map((item) => item.entity)).toEqual(["sensor.gone"]);
    expect(await broken.show(broken.tiles[0])).toBe(true);
    const doc = useDocumentStore(), insp = useInspectorStore();
    expect(useScreenStore().selected).toBe("living");
    expect([insp.inspector?.kind, doc.currentTile?.entity, insp.entityPickerOpen]).toEqual(["tile", "sensor.gone", true]);
    // Of the same kind, the tile keeps every choice made for it; Undo brings the old one back.
    expect(replaceTileEntity(doc.currentTile!, "sensor.temperature")).toBe(true);
    expect(doc.layout!.tiles[0]).toMatchObject({ entity: "sensor.temperature", name: "Porch", options: { display: "graph" } });
    expect(broken.tiles).toEqual([]);
    expect(useUiStore().notice?.message).toBe(t("editor.broken.replaced", { name: "temperature" }));
    useUiStore().notice!.action!.run();
    expect(doc.layout!.tiles[0].entity).toBe("sensor.gone");
  });

  it("gives a tile of another kind that kind's own choices and keeps its name; one on the screen already is refused", async () => {
    const broken = useBrokenStore(), doc = useDocumentStore();
    await broken.show(broken.tiles[0]);
    expect(replaceTileEntity(doc.currentTile!, "light.a")).toBe(false);
    expect(useUiStore().notice?.message).toBe(t("editor.broken.on_screen"));
    expect(replaceTileEntity(doc.currentTile!, "light.b")).toBe(true);
    expect(doc.layout!.tiles[0].entity).toBe("light.b");
    expect(doc.layout!.tiles[0].name).toBe("Porch");
    expect(doc.layout!.tiles[0].options?.display).toBeUndefined();
  });
});

describe("the parts that show them", () => {
  it("the overview: one calm line that opens the list; a row opens that tile with the picker ready", async () => {
    const notice = mount(BrokenNotice);
    expect(notice.find(".broken-text").text()).toBe("1 tile on Living room shows an entity that no longer exists");
    expect(notice.find(".broken-list").exists()).toBe(false);
    await notice.find(".broken-head").trigger("click");
    const row = notice.find(".broken-row");
    expect(row.find("strong").text()).toBe("Porch");
    expect(row.find("small").text()).toBe(`Living room · Page 1 · ${t("editor.broken.missing")}`);
    await row.trigger("click");
    await flushPromises();
    expect(useInspectorStore().entityPickerOpen).toBe(true);
    expect(useDocumentStore().currentTile?.entity).toBe("sensor.gone");
  });

  it("the overview's card and the sidebar's row say it per screen; the sidebar has one row for all of them", () => {
    useScreenStore().selected = null;
    const cards = mount(HomeView).findAll(".home-card");
    expect(cards[0].find(".home-name small.broken").text()).toBe(t("editor.broken.short", 1));
    expect(cards[1].find(".home-name small.broken").exists()).toBe(false);
    const side = mount(Sidebar);
    const rows = side.findAll("#screens .screen-item");
    expect(rows[0].find(".broken-dot").attributes("aria-label")).toBe(t("editor.broken.short", 1));
    expect(rows[1].find(".broken-dot").exists()).toBe(false);
    expect(side.find("#broken-tiles-open .txt").text()).toBe(t("editor.broken.short", 1));
  });

  it("nothing when every tile shows what it should", () => {
    useInventoryStore().inventory.entities.push(entity("sensor.gone"));
    expect(mount(BrokenNotice).find("#broken").exists()).toBe(false);
    expect(mount(Sidebar).find("#broken-tiles-open").exists()).toBe(false);
  });

  it("the tile's inspector: why, then the entities to choose, walked with the arrows and taken with Enter", async () => {
    const broken = useBrokenStore(), doc = useDocumentStore();
    await broken.show(broken.tiles[0]);
    const fix = mount(TileEntityFix, { props: { tile: doc.currentTile! }, attachTo: document.body });
    await flushPromises();
    expect(fix.find(".fix-words strong").text()).toBe(t("editor.broken.fix.missing"));
    expect(document.activeElement?.id).toBe("entity-fix-search");
    expect(fix.findAll(".fix-row").map((row) => row.attributes("data-entity"))).toEqual(["sensor.temperature", "sensor.temperature_2"]);
    const field = fix.find("#entity-fix-search");
    await field.trigger("keydown", { key: "ArrowDown" });
    expect(fix.findAll(".fix-row")[1].classes()).toContain("active");
    await field.trigger("keydown", { key: "Enter" });
    expect(doc.layout!.tiles[0].entity).toBe("sensor.temperature_2");
    expect(useInspectorStore().entityPickerOpen).toBe(false);
    fix.unmount();
  });

  it("the tile's inspector, for a tile that is fine: only when its menu asks, and it closes again", async () => {
    useInventoryStore().inventory.entities.push(entity("sensor.gone"));
    const doc = useDocumentStore();
    await openScreen("living");
    useInspectorStore().openTile(doc.layout!.tiles[0]);
    useInspectorStore().entityPickerOpen = false;
    const fix = mount(TileEntityFix, { props: { tile: doc.currentTile! } });
    expect(fix.find("#entity-fix").exists()).toBe(false);
    useInspectorStore().entityPickerOpen = true;
    await flushPromises();
    expect(fix.find(".fix-words strong").text()).toBe(t("editor.broken.fix.choose"));
    await fix.find(".fix-close").trigger("click");
    expect(fix.find("#entity-fix").exists()).toBe(false);
  });
});
