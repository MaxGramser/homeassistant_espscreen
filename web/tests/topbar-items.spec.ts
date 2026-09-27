import { seedLayout } from "./page-fixtures";
// An item of the top bar is the same item on every page, whatever id each page gave it (app 0.4.1). Since app 0.3.1 each
// item carries an id of its own, and the editor's item key had that id in it: "already in the bar" never matched, Add
// never marked a clock that was there, and the live preview asked the add-on for one entity twice and got nothing back.
import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TopbarAdd from "../src/components/TopbarAdd.vue";
import { itemKey } from "../src/model/topbar";
import { addTopbarItem, loadTopbarPreview, state, topbarView } from "../src/store";
import type { Inventory } from "../src/types";

beforeEach(() => {
  vi.useRealTimers();
  state.inventory = { screens: [], entities: [{ id: "sensor.out", name: "Outside", state: "12", area: "" }], builtin: [],
    icons: { groups: [], weather: {}, sun: {}, defaults: {}, fallback: "F0335", builtin: {}, controls: {} },
    header: { max_items: 6, builtin: [{ type: "clock", label: "Clock" }, { type: "date", label: "Date" }] } } as unknown as Inventory;
  state.documentGrid = { columns: 2, rows: 3 };
  state.selected = "living";
  seedLayout({ title: "Home", pages: 2, tiles: [], header: { items: [{ type: "entity", entity: "sensor.out", content: "last_changed" }, { type: "clock" }] } });
  state.topbarPreviews = {};
  state.toast = null;
});

describe("the items of the top bar", () => {
  it("are the same item whatever their id", () => {
    expect(itemKey({ id: "a", type: "clock" })).toBe(itemKey({ type: "clock" }));
    expect(itemKey({ id: "a", type: "entity", entity: "sensor.out" })).toBe(itemKey({ type: "entity", entity: "sensor.out", content: "state", icon: "auto", show: "always" }));
    expect(itemKey({ type: "entity", entity: "sensor.out", content: "last_changed" })).not.toBe(itemKey({ type: "entity", entity: "sensor.out" }));
  });

  it("refuses an item the bar already has, and Add marks it as added", () => {
    addTopbarItem({ type: "clock" });
    expect(state.toast?.message).toBe("This is already in the top bar.");
    expect(state.document!.pages[0].topbar.trailing).toHaveLength(2);
    const add = mount(TopbarAdd);
    const clock = add.findAll("button.option").find((b) => b.text().includes("Clock"))!;
    expect(clock.attributes("disabled")).toBeDefined();
  });

  it("asks the add-on once for an item that stands on several pages, and every page shows the answer", async () => {
    vi.useFakeTimers();
    const bodies: any[] = [];
    vi.stubGlobal("fetch", vi.fn((_: string, options: RequestInit) => {
      const body = JSON.parse(String(options.body));
      bodies.push(body);
      // The add-on refuses the same item twice in one request (core.validate_header).
      const keys = body.header.items.map((item: any) => JSON.stringify(item));
      if (new Set(keys).size !== keys.length) return Promise.resolve(new Response(JSON.stringify({ error: "twice" }), { status: 400 }));
      return Promise.resolve(new Response(JSON.stringify({ items: body.header.items.map(() => ({ t: "2 min", shown: true })) }), { status: 200 }));
    }));
    loadTopbarPreview(0);
    await vi.runAllTimersAsync();
    expect(bodies).toHaveLength(1);
    expect(bodies[0].header.items).toHaveLength(1);
    for (const page of state.document!.pages) expect(topbarView(page.topbar.trailing[0]).text).toBe("2 min");
  });
});
