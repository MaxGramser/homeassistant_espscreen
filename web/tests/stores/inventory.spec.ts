// What the add-on says (stores/inventory.ts): the inventory read in full or light, the preview screens of this browser kept
// beside it, whether the add-on can be reached, who follows a new inventory, an entity by its id, and the editor's
// features. The live stream and its polls are tests/live.spec.ts.
import { describe, expect, it, vi } from "vitest";
import { useInventoryStore } from "../../src/stores/inventory";
import type { Inventory, Screen } from "../../src/types";
import { failure, fakeApi } from "../helpers/fake-api";
import { customPreview } from "../../src/model/preview";

const screen = (id: string) => ({ id, name: id, online: true, layout: { title: id, tiles: [] } }) as unknown as Screen;
const full = (patch: Partial<Inventory> = {}) => ({ csrf: "t", connected: true, screens: [screen("hall")], entities: [{ id: "light.a", name: "Lamp", state: "on" }],
  icons: { groups: [] }, ...patch }) as unknown as Inventory;

describe("the inventory", () => {
  it("reads the whole catalogue, and a light poll keeps it while the screens follow", async () => {
    const api = fakeApi({ "GET inventory": (request) => (request.query.get("light") ? { screens: [screen("hall"), screen("desk")], connected: false } : full()) });
    const inventory = useInventoryStore();
    await inventory.refresh();
    expect([inventory.inventory.entities.length, inventory.connected, inventory.reachable]).toEqual([1, true, true]);
    await inventory.refresh(false);
    expect(api.calls.map((r) => r.query.toString())).toEqual(["", "light=1"]);
    expect(inventory.inventory.screens.map((s) => s.id)).toEqual(["hall", "desk"]);
    expect([inventory.inventory.entities.length, inventory.connected]).toEqual([1, false]);
  });

  it("keeps what it had and says the add-on cannot be reached when it does not answer, and tells nobody", async () => {
    fakeApi({ "GET inventory": full() });
    const inventory = useInventoryStore(), heard = vi.fn();
    inventory.onArrival(heard);
    await inventory.refresh();
    expect(heard).toHaveBeenCalledTimes(1);
    fakeApi({ "GET inventory": failure(502, "Bad gateway") });
    await inventory.refresh(false);
    expect([inventory.reachable, inventory.inventory.screens.length, heard.mock.calls.length]).toEqual([false, 1, 1]);
  });

  it("tells whoever follows it once each inventory has arrived, from a refresh or the stream, until they stop following", async () => {
    fakeApi({ "GET inventory": full() });
    const inventory = useInventoryStore(), heard: string[] = [];
    const stop = inventory.onArrival(() => heard.push(inventory.inventory.screens.map((s) => s.id).join()));
    await inventory.refresh();
    inventory.applyLive({ screens: [screen("desk")] });
    expect(heard).toEqual(["hall", "desk"]);
    // A message from the stream carries its part: the catalogue stays.
    expect(inventory.inventory.entities).toHaveLength(1);
    stop();
    inventory.applyLive({ screens: [] });
    expect(heard).toHaveLength(2);
  });

  it("keeps this browser's preview screens beside the add-on's, through a refresh and a message from the stream", async () => {
    fakeApi({ "GET inventory": full() });
    const inventory = useInventoryStore();
    const preview = inventory.createVirtualScreen("Desk preview", customPreview);
    expect(inventory.inventory.screens.map((s) => s.id)).toEqual([preview.id]);
    await inventory.refresh();
    expect(inventory.inventory.screens.map((s) => s.id)).toEqual(["hall", preview.id]);
    inventory.applyLive({ screens: [screen("desk")] });
    expect(inventory.inventory.screens.map((s) => s.id)).toEqual(["desk", preview.id]);
    expect(() => inventory.createVirtualScreen("  ", customPreview)).toThrow();
  });

  it("finds an entity by its id, the first of that id, and follows the list as it changes", () => {
    const inventory = useInventoryStore();
    inventory.inventory = full({ entities: [{ id: "light.a", name: "Lamp", state: "on" }, { id: "light.a", name: "Twice", state: "off" }] as any });
    expect(inventory.entityOf("light.a")?.name).toBe("Lamp");
    expect(inventory.entityOf("light.b")).toBeUndefined();
    inventory.inventory.entities.push({ id: "light.b", name: "Desk", state: "on" } as any);
    expect(inventory.entityOf("light.b")?.name).toBe("Desk");
    inventory.inventory.entities[0].name = "Floor lamp";
    expect(inventory.entityOf("light.a")?.name).toBe("Floor lamp");
  });

  it("turns the editor's features on as the add-on says", () => {
    const inventory = useInventoryStore();
    expect(inventory.tallerTilesEnabled).toBe(false);
    inventory.inventory = full({ editor_features: { tall_tiles: true } } as any);
    expect(inventory.tallerTilesEnabled).toBe(true);
    // Plugins are on in the tests as in `npm run dev`.
    expect(inventory.pluginsEnabled).toBe(true);
  });
});
