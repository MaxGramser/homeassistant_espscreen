// Every question the editor asks before something that can't be taken back names what its yes does, and draws it red
// when that yes throws something away (composables/useConfirm.ts, ConfirmDialog): the questions that are not followed
// elsewhere, a layout copied over unsaved changes, an older export without its grid and a fresh start for a screen saved
// before page documents. The others are followed with their flows: leaving unsaved changes (stores/session.spec.ts), an
// import and a rename (screen-view.spec.ts), the override's example and Clear (override.spec.ts), the calibration
// (components.spec.ts), a tile past the screen's memory (editor-flows.spec.ts) and a text to copy by hand (store.spec.ts).
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import ScreenView from "../src/components/ScreenView.vue";
import { setTileOption } from "../src/editor/tiles";
import { useDocumentStore } from "../src/stores/document";
import { useInventoryStore } from "../src/stores/inventory";
import { useScreenStore } from "../src/stores/screen";
import type { Inventory, Screen } from "../src/types";
import { answerDialogs } from "./helpers/dialogs";
import { fakeApi } from "./helpers/fake-api";
import { openScreen, screenFixture } from "./helpers/fixtures";

const icons = { groups: [], weather: {}, sun: {}, defaults: {}, fallback: "F0335", builtin: {}, controls: {} };
const screen = (id: string, tiles: { entity: string; name: string; slot: number }[] = []) =>
  screenFixture({ id, name: id === "hall" ? "Hall" : "Desk", firmware: "0.53.0", online: true, in_sync: true, layout: { title: id, tiles } } as unknown as Screen);
function addon(...screens: Screen[]) {
  useInventoryStore().inventory = { csrf: "t", connected: true, entities: [], icons, screens } as unknown as Inventory;
}

describe("a question before something that can't be taken back", () => {
  it("replaces an unsaved layout with another screen's only after Replace layout, in red", async () => {
    addon(screen("hall", [{ entity: "light.a", name: "A", slot: 0 }]), screen("desk", [{ entity: "light.b", name: "B", slot: 0 }]));
    fakeApi({ states: { states: {} }, capabilities: { capabilities: {} }, "POST header-preview": { items: [] } });
    await openScreen("hall");
    const doc = useDocumentStore();
    const view = mount(ScreenView, { attachTo: document.body });
    setTileOption(doc.layout!.tiles[0], "icon", "lightbulb");
    let yes = false;
    const asked = answerDialogs(() => yes);
    const copyFrom = (view.vm as unknown as { copyFrom: (id: string) => Promise<void> }).copyFrom;
    await copyFrom("desk");
    expect(asked).toEqual([{ kind: "confirm", message: "Replace the unsaved layout with a copy of the other screen's?", confirm: "Replace layout", danger: true }]);
    expect(doc.layout!.tiles.map((tile) => tile.entity)).toEqual(["light.a"]);
    yes = true;
    await copyFrom("desk");
    expect(doc.layout!.tiles.map((tile) => tile.entity)).toEqual(["light.b"]);
  });

  it("imports an older export on the screen's grid after Import, which throws nothing away", async () => {
    addon(screen("hall"));
    const api = fakeApi({ "POST screens/:id/import": () => useInventoryStore().inventory.screens[0].page_document });
    await openScreen("hall");
    const asked = answerDialogs(false);
    await useDocumentStore().importLayout(JSON.stringify({ title: "Old", tiles: [] }));
    expect(asked).toEqual([{ kind: "confirm", message: "This older export does not record its grid. Import it as 2 × 3 cells per page?", confirm: "Import" }]);
    expect(api.count("POST screens/:id/import")).toBe(0);
  });

  it("starts a screen saved before page documents afresh only after Start fresh, in red", async () => {
    const legacy = { ...screen("hall"), page_document: { format: "legacy-v1", migrationRevision: "m1", migrationError: "Could not be brought over" } } as unknown as Screen;
    addon(legacy);
    const api = fakeApi({ "POST screens/:id/migration/reset": { ok: true }, "inventory?light=1": { screens: [legacy] } });
    useScreenStore().selected = "hall";
    let yes = false;
    const asked = answerDialogs(() => yes);
    await useDocumentStore().startFreshLayout();
    expect(asked).toEqual([{ kind: "confirm", message: expect.stringMatching(/^Start with one empty page/), confirm: "Start fresh", danger: true }]);
    expect(api.count("POST screens/:id/migration/reset")).toBe(0);
    yes = true;
    await useDocumentStore().startFreshLayout();
    await flushPromises();
    expect(api.asked("POST screens/:id/migration/reset").map((call) => call.body)).toEqual([{ revision: "m1" }]);
  });
});
