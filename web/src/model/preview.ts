import { boardList } from "./boards";
import { validatePages } from "./pages";
import type { BoardChoice, GridWay, Orientation, PageGrid, Screen, ScreenGrids, ScreenShape } from "../types";
import renderer from "../wasm/renderer.json";

export type PreviewProfile = { key: string; board: string; name: string; orientation: Orientation; shape: ScreenShape };

// This display is available for design before a physical firmware profile exists.
export const customPreview: PreviewProfile = {
  key: "virtual720", board: "virtual720", name: "Waveshare ESP32-P4-WIFI6-Touch-LCD-4B", orientation: "landscape",
  shape: { width: 720, height: 720, columns: 2, rows: 3, dpi: 254, look: "standard" },
};

export function previewProfiles(boards: Record<string, BoardChoice>): PreviewProfile[] {
  return [...boardList(boards).flatMap(board => Object.entries(board.orientations)
    .filter(([orientation]) => !board.square || orientation === "landscape")
    .map(([orientation, shape]) => ({
      key: `${board.key}-${orientation}`, board: board.key, name: `${board.name} ${board.model}`,
      orientation: orientation as Orientation,
      shape: { ...shape!, dpi: board.dpi, look: board.look || "standard", ...(board.fonts ? { fonts: board.fonts } : {}),
        ...(board.spacing?.margin !== undefined ? { spacing: board.spacing } : {}), catalog: board },
    }))), customPreview];
}

export function validPreviewShape(shape: ScreenShape): boolean {
  return [shape.width, shape.height].every(n => Number.isInteger(n) && n >= 160 && n <= 2560)
    && [shape.columns, shape.rows].every(n => Number.isInteger(n) && n >= 1 && n <= 8)
    && shape.columns * shape.rows <= 64
    && renderer.profiles.some(profile => profile.dpi === shape.dpi && profile.look === shape.look);
}

// A screen the renderer can draw: its canvas and density, on the grid its layout was made for. Null for a board whose
// density or look the compiled preview does not know yet; the page then keeps its drawn mockup.
export function previewShapeOf(screen: Pick<Screen, "shape">, grid?: PageGrid | null): ScreenShape | null {
  const shape = screen.shape;
  if (!shape?.dpi) return null;
  const found: ScreenShape = { width: shape.width, height: shape.height, columns: grid?.columns ?? shape.columns,
    rows: grid?.rows ?? shape.rows, dpi: shape.dpi, look: shape.look || "standard" };
  return validPreviewShape(found) ? found : null;
}

// Preview screens live in this browser's storage, written by an older app too. Each one is checked on its own (app
// 0.4.32): one that no longer reads, or whose pages this app refuses, is left out, and never keeps the editor or the
// other preview screens from loading.
export function usablePreview(s: any): boolean {
  try {
    if (!(s?.virtual && typeof s.id === "string" && s.id.startsWith("virtual.") && s.shape && validPreviewShape(s.shape) && Array.isArray(s.layout?.tiles))) return false;
    const document = s.page_document;
    if (document?.format === "pages-v2") validatePages(document.layout, document.sourceGrid);
    return true;
  } catch { return false; }
}
// A preview screen takes the grids its board takes (boards.json, firmware 0.53.0+), the way it was made; null for one
// without its board's catalogue (the custom glass, or made by an app before 0.4.85).
export function previewGrids(shape: ScreenShape, orientation?: Orientation): ScreenGrids | null {
  const way = (side: Orientation): GridWay | null => {
    const o = (shape.catalog as Partial<BoardChoice> | undefined)?.orientations?.[side];
    return o?.min && o.max ? { columns: o.columns, rows: o.rows, min: o.min, max: o.max } : null;
  };
  const landscape = way("landscape"), portrait = way("portrait");
  return landscape && portrait ? { upright: orientation === "portrait", landscape, portrait } : null;
}
