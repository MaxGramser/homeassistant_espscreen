// ---- The boards as the add-on describes them ----
// Everything New screen and the screen list say about a board comes from the add-on's catalog (boards.yaml and the
// board's own files, through boards.json, app 0.2.129), so a new board needs nothing here: no name, no translation.
import { editorNumber, t } from "../i18n";
import type { BoardCatalog, BoardChoice } from "../types";

/** "Guition · 4 inch": the board's name and the size of its glass, the number written the way the language writes it. */
export const boardTitle = (board: Pick<BoardCatalog, "name" | "inch">) =>
  t("editor.installer.board_title", { name: board.name, inch: editorNumber(board.inch) });

/** ["ESP32-S3-4848S040", "480 × 480 · GT911"]: what is printed on it, then its pixels lying down and its touch controller. */
export const boardDetail = (board: BoardChoice) =>
  [board.model, [`${board.width} × ${board.height}`, board.touch].filter(Boolean).join(" · ")];

/** The boards in the catalog's order. */
export const boardList = (boards: Record<string, BoardChoice>) =>
  Object.entries(boards).map(([key, board]) => ({ key, ...board })).sort((a, b) => a.order - b.order);

/** What a board can do and cannot, in the words of the translations: each ability once, said either way. */
export const boardAbilities = (board: BoardChoice) => [
  { key: "camera", on: board.camera, text: t(board.camera ? "editor.installer.abilities.camera" : "editor.installer.abilities.no_camera") },
  { key: "dimming", on: board.dimmable, text: t(board.dimmable ? "editor.installer.abilities.dimming" : "editor.installer.abilities.no_dimming") },
  { key: "standby", on: board.can_standby, text: t(board.can_standby ? "editor.installer.abilities.standby" : "editor.installer.abilities.no_standby") },
  ...(board.calibrate ? [{ key: "calibration", on: true, text: t("editor.installer.abilities.calibration") }] : []),
  // How many tiles it holds (firmware 0.34.0+): more on a board with PSRAM; the screen's memory says how many of them a
  // layout really takes, which the editor shows beside its tiles.
  ...(board.max_tiles ? [{ key: "tiles", on: true, text: t("editor.installer.abilities.tiles", { n: board.max_tiles, pages: board.max_pages ?? 8 }) }] : []),
];
