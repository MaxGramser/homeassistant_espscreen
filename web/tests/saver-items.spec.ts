// The clock's row of entities on the screensaver (app 0.4.80): the top bar's items, kept in the screensaver's choice.
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Inventory } from "../src/types";
import { useUiStore } from "../src/stores/ui";
import { useScreenStore } from "../src/stores/screen";
import { SAVER_ITEMS_MAX, useScreensaverStore } from "../src/stores/screensaver";
import { useInventoryStore } from "../src/stores/inventory";
import { useInspectorStore } from "../src/stores/inspector";

let insp: ReturnType<typeof useInspectorStore>;
beforeEach(() => { insp = useInspectorStore(); });

const item = (entity: string) => ({ type: "entity", entity, content: "state", icon: "auto", show: "always" });

beforeEach(() => {
  vi.useRealTimers();
  useInventoryStore().inventory = { screens: [{ id: "living", name: "Living", virtual: true, screensaver: { show: true, media: "", camera: "", order: ["media", "camera", "clock"], off: [], weather: "auto", more: [], items: [], ready: true, pictures: true, standby: true } }],
    entities: [], builtin: [], header: { max_items: 6, builtin: [] } } as unknown as Inventory;
  useScreenStore().selected = "living";
  insp.inspector = null;
});

describe("the clock's entities", () => {
  it("are added to the screen's choice, and the drawer opens on the new one", () => {
    useScreensaverStore().addSaverItem(item("sensor.power"));
    expect(useScreensaverStore().saverItems.map((i) => i.entity)).toEqual(["sensor.power"]);
    expect(insp.inspector).toEqual({ kind: "saver-item", index: 0 });
  });

  it("take no entity twice and no more than the clock has room for", () => {
    useScreensaverStore().addSaverItem(item("sensor.a"));
    useScreensaverStore().addSaverItem(item("sensor.a"));
    expect(useUiStore().notice?.message).toBe("This is already on the clock.");
    for (let n = 0; n < SAVER_ITEMS_MAX; n++) useScreensaverStore().addSaverItem(item(`sensor.n${n}`));
    expect(useScreensaverStore().saverItems).toHaveLength(SAVER_ITEMS_MAX);
    expect(useUiStore().notice?.message).toBe(`The clock has room for ${SAVER_ITEMS_MAX} entities.`);
  });

  it("change what they show, and leave when removed, back to the clock's drawer", () => {
    useScreensaverStore().addSaverItem(item("sensor.power"));
    useScreensaverStore().updateSaverItem(0, { content: "icon" });
    expect(useScreensaverStore().saverItems[0].content).toBe("icon");
    useScreensaverStore().removeSaverItem(0);
    expect(useScreensaverStore().saverItems).toEqual([]);
    expect(insp.inspector).toEqual({ kind: "saver", step: "clock" });
  });
});
