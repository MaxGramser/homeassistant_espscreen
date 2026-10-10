// Standing a screen up or laying it down (app 0.4.85, glass that turns): the draft goes on the grid the screen keeps for
// that way, the mockup turns with it, undo takes both back, and the next save sends the screen the new way with its grid.
import { describe, expect, it } from "vitest";
import { chooseHang, save, screenShape, state, undo } from "../src/store";
import { useInventoryStore } from "../src/stores/inventory";
import { useSessionStore } from "../src/stores/session";
import type { Screen } from "../src/types";
import { fakeApi } from "./helpers/fake-api";
import { screenFixture } from "./page-fixtures";

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
    expect([state.documentUpright, state.documentGrid, screenShape.value.width]).toEqual([false, { columns: 3, rows: 2 }, 800]);
    chooseHang(true);
    expect([state.documentUpright, state.documentGrid, state.dirty]).toEqual([true, { columns: 2, rows: 3 }, true]);
    expect([screenShape.value.width, screenShape.value.height]).toEqual([480, 800]);
    expect(state.layout?.tiles).toHaveLength(6);
    // The way it already hangs, or again: nothing.
    chooseHang(true);
    expect(state.undoCount).toBe(1);
    undo();
    expect([state.documentUpright, state.documentGrid, screenShape.value.width, state.dirty]).toEqual([false, { columns: 3, rows: 2 }, 800, false]);
  });

  it("does nothing on glass that does not turn, or for a screen without grids", () => {
    open({ hang: null });
    chooseHang(true);
    expect([state.documentUpright, state.documentGrid, state.dirty]).toEqual([null, { columns: 3, rows: 2 }, false]);
    open({ grids: null });
    chooseHang(true);
    expect([state.documentUpright, state.dirty]).toEqual([false, false]);
  });

  it("sends the screen the new way with its grid on the next save, as a reviewed adaptation", async () => {
    open();
    chooseHang(true);
    const api = fakeApi({
      "PUT screens/:id": ({ body }) => ({ saved: true, document: { format: "pages-v2", revision: "r2", sourceGrid: body.adaptation.to, layout: body.layout,
        workspace: { revision: "w2", positions: {} } } }),
      "GET inventory": { connected: true, screens: [], entities: [] },
    });
    await save();
    expect(api.asked("PUT screens/:id")[0].body.adaptation).toEqual({ from: { columns: 3, rows: 2 }, to: { columns: 2, rows: 3 }, upright: true });
    expect([state.dirty, state.documentRevision]).toEqual([false, "r2"]);
  });
});
