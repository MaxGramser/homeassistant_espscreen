import { describe, expect, it } from "vitest";
import { emptyLayout } from "../src/model/pages";
import { customPreview, previewGrids, previewShapeOf, usablePreview } from "../src/model/preview";

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

describe("a preview screen kept in this browser", () => {
  const way = { width: 480, height: 480, columns: 2, rows: 3, rotation: 0, min: [1, 1] as [number, number], max: [3, 5] as [number, number] };
  const stored = (more: object = {}) => ({ id: "virtual.hall-1", name: "Hall", virtual: true, shape: customPreview.shape,
    layout: { title: "Hall", tiles: [] }, page_document: { format: "pages-v2", layout: emptyLayout("Hall"), sourceGrid: { columns: 2, rows: 3 } }, ...more });
  it("takes the grids of its board, the way it was made, and none without its board's catalogue", () => {
    const shape = { ...customPreview.shape, catalog: { orientations: { landscape: way, portrait: { ...way, columns: 3, rows: 2 } } } as any };
    expect(previewGrids(shape, "portrait")).toEqual({ upright: true, landscape: { columns: 2, rows: 3, min: [1, 1], max: [3, 5] },
      portrait: { columns: 3, rows: 2, min: [1, 1], max: [3, 5] } });
    expect(previewGrids(shape, "landscape")?.upright).toBe(false);
    expect(previewGrids(customPreview.shape, "landscape")).toBeNull();
  });
  it("reads one that still reads, and leaves out one that does not, without throwing", () => {
    expect(usablePreview(stored())).toBe(true);
    expect(usablePreview(stored({ id: "hall" }))).toBe(false);
    expect(usablePreview(stored({ shape: { ...customPreview.shape, dpi: 999 } }))).toBe(false);
    expect(usablePreview(stored({ layout: {} }))).toBe(false);
    const broken = stored();
    broken.page_document.layout.homePageId = "missing";
    expect(usablePreview(broken)).toBe(false);
    expect(usablePreview(null)).toBe(false);
  });
});
