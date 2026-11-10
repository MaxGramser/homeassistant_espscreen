// The to-do card in the editor (docs/TODO.md): its choices are kept only where they differ from what nothing means and
// only on a to-do list, the page document refuses a stored default, and its face is the list on a board that draws it.
import { describe, expect, it } from "vitest";
import { canonicalOptions, TODO_DEFAULTS } from "../src/model/tile-options";
import { tileFace } from "../src/model/tile-face";
import rules from "../src/model/page-rules.json";
import { libraryBase } from "../src/model/library";

describe("the to-do card", () => {
  it("keeps no default and no choice of another tile's", () => {
    expect(canonicalOptions("todo.shopping", { ...TODO_DEFAULTS })).toEqual({});
    expect(canonicalOptions("todo.shopping", { todo_order: "alpha_asc", todo_add: false, todo_completed: true }))
      .toEqual({ todo_order: "alpha_asc", todo_add: false });
    expect(canonicalOptions("light.desk", { todo_order: "alpha_asc", todo_clear: false })).toEqual({});
  });

  it("orders as Home Assistant's own card does, the first the one never stored", () => {
    expect(rules.todo.orders).toEqual(["none", "alpha_asc", "alpha_desc", "duedate_asc", "duedate_desc"]);
    expect(TODO_DEFAULTS.todo_order).toBe("none");
  });

  it("is offered in the library only for a screen whose board has the card", () => {
    const entries = [{ id: "todo.shopping", name: "Shopping" }, { id: "light.desk", name: "Desk" }];
    const base = { query: "", pages: [], pictures: true, textTiles: true, hidePlaced: false, counts: new Map<string, number>() } as any;
    expect(libraryBase(entries, { ...base, todoLists: true }).map((e) => e.id)).toContain("todo.shopping");
    expect(libraryBase(entries, { ...base, todoLists: false }).map((e) => e.id)).toEqual(["light.desk"]);
    expect(libraryBase(entries, base).map((e) => e.id)).toEqual(["light.desk"]);
  });

  it("is the list on a board that has the card", () => {
    const input = { entity: "todo.shopping", options: {}, shape: { columns: 2, rows: 2 }, full: false, wide: true, live: { state: "3", a: {} },
      chosen: null, rangeReady: true, bigKeys: true } as any;
    expect(tileFace({ ...input }).kind).toBe("todo");
    expect(tileFace({ ...input, shape: { columns: 1, rows: 1 }, wide: false }).kind).toBe("todo");
    expect(tileFace({ ...input, todoLists: false }).kind).not.toBe("todo");
  });
});
