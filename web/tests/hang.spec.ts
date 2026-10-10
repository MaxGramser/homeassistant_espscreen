// Standing a screen up or laying it down (app 0.4.85, glass that turns): the draft goes on the grid the screen keeps for
// that way, the mockup turns with it, undo takes both back, and the next save sends the screen the new way with its grid.
import { describe, expect, it, beforeEach } from "vitest";
import { useInventoryStore } from "../src/stores/inventory";
import { useSessionStore } from "../src/stores/session";
import type { Screen } from "../src/types";
import { fakeApi } from "./helpers/fake-api";
import { screenFixture } from "./helpers/fixtures";
import { useDocumentStore } from "../src/stores/document";

let doc: ReturnType<typeof useDocumentStore>;
beforeEach(() => { doc = useDocumentStore(); });

const grids = { upright: false, landscape: { columns: 3, rows: 2, min: [1, 1], max: [4, 3] }, portrait: { columns: 2, rows: 3, min: [1, 1], max: [3, 4] } };
function open(patch: Partial<Screen> = {}) {
  const screen = screenFixture({ id: "hall", name: "Hall", online: true, firmware: "0.53.0", board: "guition", hang: "landscape", grids,
    shape: { width: 800, height: 480, columns: 3, rows: 2, dpi: 170, look: "standard" },
    layout: { title: "Hall", tiles: Array.from({ length: 6 }, (_, slot) => ({ entity: `light.l${slot}`, name: "", slot })) }, ...patch } as unknown as Screen);
  useInventoryStore().inventory = { connected: true, screens: [screen], entities: [] } as any;
  fakeApi({ states: { states: {} }, capabilities: { capabilities: {} } });
  useSessionStore().select("hall");
  return screen;
}

describe("standing a screen up", () => {
  it("puts the draft on the grid the screen keeps standing up, turns the mockup, and undo takes both back", () => {
    open();
    expect([doc.documentUpright, doc.documentGrid, doc.screenShape.width]).toEqual([false, { columns: 3, rows: 2 }, 800]);
    doc.chooseHang(true);
    expect([doc.documentUpright, doc.documentGrid, doc.dirty]).toEqual([true, { columns: 2, rows: 3 }, true]);
    expect([doc.screenShape.width, doc.screenShape.height]).toEqual([480, 800]);
    expect(doc.layout?.tiles).toHaveLength(6);
    // The way it already hangs, or again: nothing.
    doc.chooseHang(true);
    expect(doc.undoCount).toBe(1);
    doc.undo();
    expect([doc.documentUpright, doc.documentGrid, doc.screenShape.width, doc.dirty]).toEqual([false, { columns: 3, rows: 2 }, 800, false]);
  });

  it("does nothing on glass that does not turn, or for a screen without grids", () => {
    open({ hang: null });
    doc.chooseHang(true);
    expect([doc.documentUpright, doc.documentGrid, doc.dirty]).toEqual([null, { columns: 3, rows: 2 }, false]);
    open({ grids: null });
    doc.chooseHang(true);
    expect([doc.documentUpright, doc.dirty]).toEqual([false, false]);
  });

  it("sends the screen the new way with its grid on the next save, as a reviewed adaptation", async () => {
    open();
    doc.chooseHang(true);
    const api = fakeApi({
      "PUT screens/:id": ({ body }) => ({ saved: true, document: { format: "pages-v2", revision: "r2", sourceGrid: body.adaptation.to, layout: body.layout,
        workspace: { revision: "w2", positions: {} } } }),
      "GET inventory": { connected: true, screens: [], entities: [] },
    });
    await doc.save();
    expect(api.asked("PUT screens/:id")[0].body.adaptation).toEqual({ from: { columns: 3, rows: 2 }, to: { columns: 2, rows: 3 }, upright: true });
    expect([doc.dirty, doc.documentRevision]).toEqual([false, "r2"]);
  });
});
