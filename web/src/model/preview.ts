import { boardList } from "./boards";
import type { BoardChoice, Orientation, ScreenShape } from "../types";
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
      shape: { ...shape!, dpi: board.dpi, look: board.look || "standard", catalog: board },
    }))), customPreview];
}

export function validPreviewShape(shape: ScreenShape): boolean {
  return [shape.width, shape.height].every(n => Number.isInteger(n) && n >= 160 && n <= 2560)
    && [shape.columns, shape.rows].every(n => Number.isInteger(n) && n >= 1 && n <= 8)
    && shape.columns * shape.rows <= 64
    && renderer.profiles.some(profile => profile.dpi === shape.dpi && profile.look === shape.look);
}
