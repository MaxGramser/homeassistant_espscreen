import { describe, expect, it } from "vitest";
import { previewShapeOf } from "../src/model/preview";

describe("previewShapeOf", () => {
  const shape = { width: 480, height: 480, columns: 2, rows: 3, dpi: 170, look: "standard" };
  it("takes a screen's canvas and density on the grid of its layout", () => {
    expect(previewShapeOf({ shape }, { columns: 3, rows: 3 })).toEqual({ ...shape, columns: 3, rows: 3 });
    expect(previewShapeOf({ shape })).toEqual(shape);
  });
  it("leaves a density the compiled preview does not know to the mockup", () => {
    expect(previewShapeOf({ shape: { ...shape, dpi: 999 } })).toBeNull();
    expect(previewShapeOf({ shape: { ...shape, dpi: undefined } })).toBeNull();
    expect(previewShapeOf({ shape: null })).toBeNull();
  });
});
