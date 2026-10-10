// A tile shown from elsewhere (the broken tiles, ⌘K), and another entity for a tile: one whose entity Home Assistant no
// longer has (stores/broken.ts), or any tile of an entity whose menu asks for another. The tile keeps its place, its size, its name, its icon and its colour; another entity
// of the same kind keeps every choice made for it as well, one of another kind starts with that kind's own choices,
// as a new tile of it would. A plain function over the stores, as editing the tiles is (editor/tiles.ts).
import { t } from "../i18n";
import { dimensions, effectiveControls, newTile, sizeOf } from "../model/layout";
import * as pages from "../model/pages";
import { canonicalOptions } from "../model/tile-options";
import { revealTile } from "../composables/revealTile";
import { useDocumentStore } from "../stores/document";
import { useEntitiesStore } from "../stores/entities";
import { useInspectorStore } from "../stores/inspector";
import { useScreenStore } from "../stores/screen";
import { useSessionStore } from "../stores/session";
import { useUiStore } from "../stores/ui";
import type { Screen, Tile, TileOptions } from "../types";
import { commitArrangement, setTileOption } from "./tiles";

/** A tile in the inspector, on its screen and page, brought into sight. The screen is opened first (which asks about
 * unsaved changes on another one); a person who keeps those stays where they are. True when it is shown. */
export async function showTile(screen: Screen, tileId: string) {
  const scr = useScreenStore(), doc = useDocumentStore(), ui = useUiStore();
  if (scr.selected !== screen.id || !doc.document) await useSessionStore().select(screen.id);
  if (scr.selected !== screen.id || !doc.layout) return false;
  ui.go("");
  ui.tab = "layout";
  const found = doc.layout.tiles.find((item) => item.id === tileId);
  if (!found) return false;
  useInspectorStore().openTile(found);
  void revealTile(tileId);
  return true;
}

// What a tile keeps of its own whatever it shows.
const KEPT = ["size", "icon", "background", "overlay"] as const;

/** The tile shows `entity` from now on; true when it changed. Undo brings the one it showed back. */
export function replaceTileEntity(tile: Tile, entity: string): boolean {
  const doc = useDocumentStore(), scr = useScreenStore(), entities = useEntitiesStore(), ui = useUiStore();
  if (!doc.layout || !tile.id) return false;
  // A plugin's tile keeps its entity beside its options (its manifest's `entity`).
  if (tile.entity.startsWith("plugin:")) {
    setTileOption(tile, "plugin_entity", entity);
    return true;
  }
  if (!scr.repeatable(entity) && doc.layout.tiles.some((item) => item.entity === entity && item.id !== tile.id)) {
    ui.toast(t("editor.broken.on_screen"));
    return false;
  }
  const layout = pages.clone(doc.layout);
  const current = layout.tiles.find((item) => item.id === tile.id);
  if (!current || current.entity === entity) return false;
  if (current.entity.split(".")[0] !== entity.split(".")[0]) {
    const kept: Record<string, unknown> = {};
    for (const key of KEPT) if (current.options?.[key] !== undefined) kept[key] = current.options[key];
    current.options = { ...(newTile(entity, scr.coversByDefault).options || {}), ...kept } as TileOptions;
    // A card more than a row high has its controls chosen, as one that grows does.
    if (current.in === undefined && dimensions(sizeOf(current), doc.editorLayout.grid).rows > 1 && !("controls" in current.options))
      current.options.controls = effectiveControls({ ...current, entity }) || "none";
  }
  current.entity = entity;
  current.options = canonicalOptions(entity, current.options, current.in !== undefined);
  if (!Object.keys(current.options).length) delete current.options;
  if (!commitArrangement(layout.tiles.map((item) => ({ tile: item, slot: item.slot })))) return false;
  entities.loadCapabilities([entity]);
  doc.loadStates();
  doc.undoToast(t("editor.broken.replaced", { name: entities.entityName(entity) }));
  return true;
}
