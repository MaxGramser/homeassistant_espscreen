// The top bar (stores/topbar.ts): its items added, moved and taken off with undo, a page's bar copied onto others, and the
// entity items' previews, which follow the items once the store has started: at once for another screen or the
// screensaver clock's row, after a short pause for a page's bar, every half minute while a screen is open, and never
// after its stop.
import { describe, expect, it, beforeEach } from "vitest";
import { i18n } from "../../src/i18n";
import { state } from "../../src/store";
import { useScreenStore } from "../../src/stores/screen";
import { useSessionStore } from "../../src/stores/session";
import { useTopbarStore } from "../../src/stores/topbar";
import { useUiStore } from "../../src/stores/ui";
import type { HeaderItem, Inventory, Screen } from "../../src/types";
import { useFakeClock } from "../helpers/clock";
import { fakeApi } from "../helpers/fake-api";
import { screenFixture } from "../helpers/fixtures";
import { useInventoryStore } from "../../src/stores/inventory";
import { addPage } from "../../src/editor/pages";
import { setTileOption } from "../../src/editor/tiles";
import { useDocumentStore } from "../../src/stores/document";

let doc: ReturnType<typeof useDocumentStore>;
beforeEach(() => { doc = useDocumentStore(); });

const t = (key: string, named: Record<string, unknown> = {}) => i18n.global.t(key, named);
const entity = (id: string): HeaderItem => ({ type: "entity", entity: id, content: "state", icon: "auto", show: "always" });
const screen = (id: string, items: HeaderItem[] = []) => screenFixture({ id, name: id, online: true, firmware: "0.53.0",
  layout: { title: id, tiles: [{ entity: "light.a", name: "", slot: 0 }], header: { items } },
  screensaver: { show: true, media: "", camera: "", order: ["clock"], off: [], weather: "auto", more: [], items: [], ready: true } } as unknown as Screen);
const inventory = (...screens: Screen[]) => ({ connected: true, screens, entities: [{ id: "sensor.out", name: "Outside", state: "12" }],
  header: { max_items: 3, builtin: [{ type: "clock", label: "Clock" }, { type: "date", label: "Date" }] } }) as unknown as Inventory;
function addOn() {
  return fakeApi({ states: { states: {} }, capabilities: { capabilities: {} },
    "POST header-preview": ({ body }) => ({ items: body.header.items.map((item: HeaderItem) => ({ t: `${item.entity} now`, shown: true })) }) });
}

describe("the entity items' previews", () => {
  it("follow the items once started, and stop with the store's stop", async () => {
    const clock = useFakeClock();
    const api = addOn();
    useInventoryStore().inventory = inventory(screen("hall", [entity("sensor.out")]), screen("desk"));
    const topbar = useTopbarStore(), session = useSessionStore();
    const stop = topbar.start();
    expect(topbar.start()).toBe(stop);
    const asked = () => api.asked("POST header-preview").map((r) => r.body.header.items.map((item: HeaderItem) => item.entity).join());
    // Another screen: at once.
    session.select("hall");
    await clock.tick(0);
    expect(asked()).toEqual(["sensor.out"]);
    expect(topbar.topbarView(doc.document!.pages[0].topbar.trailing[0]).text).toBe("sensor.out now");
    // A page's bar while it is typed in: once after a short pause.
    topbar.addTopbarItem(entity("sensor.in"));
    topbar.setTopbarItems([entity("sensor.in"), entity("sensor.out"), entity("sensor.rain")]);
    await clock.tick(100);
    expect(asked()).toHaveLength(1);
    await clock.tick(50);
    expect(asked().at(-1)).toBe("sensor.in,sensor.out,sensor.rain");
    // A change that is not the bar's asks nothing.
    setTileOption(doc.layout!.tiles[0], "icon", "lightbulb");
    await clock.tick(1000);
    expect(asked()).toHaveLength(2);
    // The screensaver clock's row: at once.
    useScreenStore().currentScreen!.screensaver!.items = [entity("sensor.wind")];
    await clock.tick(0);
    expect(asked()).toHaveLength(3);
    expect(asked().at(-1)).toBe("sensor.in,sensor.out,sensor.rain,sensor.wind");
    // Every half minute while the screen is open.
    const before = asked().length;
    await clock.tick(30000);
    expect(asked().length).toBe(before + 1);
    stop();
    await clock.tick(120000);
    expect(asked().length).toBe(before + 1);
    expect(clock.timers()).toBe(0);
  });

  it("drops an answer for a screen no longer open", async () => {
    const clock = useFakeClock();
    const api = addOn();
    const answer = api.defer("POST header-preview");
    useInventoryStore().inventory = inventory(screen("hall", [entity("sensor.out")]), screen("desk"));
    useSessionStore().select("hall");
    useTopbarStore().loadTopbarPreview(0);
    await clock.tick(0);
    useSessionStore().select("desk");
    answer.resolve();
    await clock.tick(0);
    expect(useTopbarStore().topbarView(entity("sensor.out"))).toMatchObject({ text: "…", loading: true });
  });
});

describe("a page's top bar", () => {
  it("adds an item once and as many as the screen holds, and takes one off with undo", () => {
    addOn();
    useInventoryStore().inventory = inventory(screen("hall", [{ type: "clock" }]));
    useSessionStore().select("hall");
    const topbar = useTopbarStore(), ui = useUiStore();
    topbar.addTopbarItem({ type: "clock" });
    expect(ui.notice?.message).toBe(t("editor.topbar.already"));
    topbar.addTopbarItem({ type: "date" });
    expect(topbar.topbarAdded?.key).toBe(JSON.stringify(["date"]));
    expect(state.inspector).toEqual({ kind: "bar", index: 1 });
    topbar.addTopbarItem(entity("sensor.out"));
    topbar.addTopbarItem(entity("sensor.in"));
    expect(ui.notice?.message).toBe(t("editor.topbar.full", 3));
    expect(topbar.moveTopbarItem(2, 0)).toBe(true);
    expect(topbar.topbarItems().map((item) => item.type)).toEqual(["entity", "clock", "date"]);
    topbar.removeTopbarItem(0);
    expect(ui.notice?.message).toBe(t("editor.topbar.removed", { name: "Outside" }));
    expect(state.inspector).toBeNull();
    ui.notice!.action!.run();
    expect(topbar.topbarItems().map((item) => item.type)).toEqual(["entity", "clock", "date"]);
  });

  it("copies a page's bar onto others on a screen whose pages are ready, and shows its home key as the screen does", () => {
    addOn();
    useInventoryStore().inventory = inventory(screen("hall", [entity("sensor.out")]));
    useSessionStore().select("hall");
    addPage();
    const topbar = useTopbarStore(), [first, second] = doc.document!.pages;
    topbar.setTopbarItems([], 1);
    expect(topbar.topbarItems(1)).toEqual([]);
    expect(topbar.copyPageBars(first.id, [second.id], false)).toBe(true);
    expect(topbar.topbarItems(1).map((item) => item.entity)).toEqual(["sensor.out"]);
    expect(topbar.homeKeyShown(0)).toBe(Boolean(first.topbar.leading.length));
    useScreenStore().currentScreen!.page_capability = "update_screen";
    expect(topbar.copyPageBars(first.id, [second.id], true)).toBe(false);
  });
});
