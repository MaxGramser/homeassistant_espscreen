// The clock's row of entities on the screensaver (app 0.4.80): the top bar's items, kept in the screensaver's choice.
import { beforeEach, describe, expect, it, vi } from "vitest";
import { addSaverItem, removeSaverItem, SAVER_ITEMS_MAX, saverItems, state, updateSaverItem } from "../src/store";
import type { Inventory } from "../src/types";

const item = (entity: string) => ({ type: "entity", entity, content: "state", icon: "auto", show: "always" });

beforeEach(() => {
  vi.useRealTimers();
  state.inventory = { screens: [{ id: "living", name: "Living", virtual: true, screensaver: { show: true, media: "", camera: "", order: ["media", "camera", "clock"], off: [], weather: "auto", more: [], items: [], ready: true, pictures: true, standby: true } }],
    entities: [], builtin: [], header: { max_items: 6, builtin: [] } } as unknown as Inventory;
  state.selected = "living";
  state.inspector = null;
  state.toast = null;
});

describe("the clock's entities", () => {
  it("are added to the screen's choice, and the drawer opens on the new one", () => {
    addSaverItem(item("sensor.power"));
    expect(saverItems().map((i) => i.entity)).toEqual(["sensor.power"]);
    expect(state.inspector).toEqual({ kind: "saver-item", index: 0 });
  });

  it("take no entity twice and no more than the clock has room for", () => {
    addSaverItem(item("sensor.a"));
    addSaverItem(item("sensor.a"));
    expect(state.toast?.message).toBe("This is already on the clock.");
    for (let n = 0; n < SAVER_ITEMS_MAX; n++) addSaverItem(item(`sensor.n${n}`));
    expect(saverItems()).toHaveLength(SAVER_ITEMS_MAX);
    expect(state.toast?.message).toBe(`The clock has room for ${SAVER_ITEMS_MAX} entities.`);
  });

  it("change what they show, and leave when removed, back to the clock's drawer", () => {
    addSaverItem(item("sensor.power"));
    updateSaverItem(0, { content: "icon" });
    expect(saverItems()[0].content).toBe("icon");
    removeSaverItem(0);
    expect(saverItems()).toEqual([]);
    expect(state.inspector).toEqual({ kind: "saver", step: "clock" });
  });
});
