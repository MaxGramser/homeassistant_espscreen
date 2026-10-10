// The inspector that opens beside the mockup: what it shows, its pickers, the empty cell or key place the next tile from
// the library goes to, and the choice the pointer rests on before it is picked. The draft it shows is the document
// store's (stores/document.ts); the mockup's sizes, a drag, what the add-on says, the open screen, the session, the top
// bar and the screensaver are stores of their own (stores/), and so will this be.
import { effectScope, reactive, watch } from "vue";
import type { SaverKind, Tile } from "./types";
import { onReset } from "./resets";
import { useDocumentStore } from "./stores/document";
import { useDragStore } from "./stores/drag";
import { useEntitiesStore } from "./stores/entities";
import { useUiStore } from "./stores/ui";

export type Inspector =
  | { kind: "tile" }
  | { kind: "bar"; index: number }
  | { kind: "bar-add" }
  | { kind: "saver-item"; index: number }
  | { kind: "saver-add" }
  | { kind: "saver"; step: SaverKind }
  | { kind: "page"; id: string }
  | { kind: "inspect"; entity?: string; slot?: number; key?: number };

// The inspector as it starts, before anything was chosen: the page begins with it, and every test again (resetStore).
const fresh = () => ({
  inspector: null as Inspector | null,
  iconPickerOpen: false,
  actionPickerOpen: false,
  actionSearch: "",
  insertAt: -1,
  // The key place a click marked under a bedside clock (app 0.4.12): the next tile added from the library goes there.
  insertKey: null as null | { holder: string; key: number },
  // A choice the pointer rests on in the inspector, drawn on its tile before it is picked (app 0.4.32).
  optionPreview: null as null | { tileId: string; key: string; value: unknown },
});
export const state = reactive(fresh());

// The tile as the mockup draws it: with the choice the pointer rests on in the inspector, when that is this tile's.
export function previewed(tile: Tile): Tile {
  const hover = state.optionPreview;
  // Only while that tile's own settings are open and nothing is being dragged: the drawn copy never reaches an edit.
  if (!hover || !tile.id || hover.tileId !== tile.id || useDocumentStore().selectedTileId !== tile.id || useDragStore().active) return tile;
  return { ...tile, options: { ...(tile.options || {}), [hover.key]: hover.value } } as Tile;
}

// ---- Inspector (the drawer) ----
export function openTile(tile: Tile) {
  const doc = useDocumentStore();
  if (!doc.isSelected(tile)) { state.iconPickerOpen = false; state.actionPickerOpen = false; state.actionSearch = ""; }
  doc.selectedTileId = tile.id || null;
  doc.selectedPageId = doc.document?.pages.find((page) => page.tiles.some((item) => item.id === tile.id ||
    item.children?.some((child) => child.id === tile.id)))?.id || doc.selectedPageId;
  state.inspector = { kind: "tile" };
  useEntitiesStore().loadCapabilities([tile.entity]);
}
export function openPage(id: string) {
  const doc = useDocumentStore();
  doc.selectedPageId = id; doc.selectedTileId = null;
  state.inspector = { kind: "page", id };
}
// `page` is the page whose bar was clicked (app 0.2.105): the inspector changes that page's own title there,
// which is where you look for it after clicking the bar.
export function openBar(index: number, page = useDocumentStore().barPage) {
  const doc = useDocumentStore();
  if (!(state.inspector?.kind === "bar" && state.inspector.index === index)) state.iconPickerOpen = false;
  doc.selectedTileId = null;
  doc.selectedPageId = doc.document?.pages[page]?.id || null;
  state.inspector = { kind: "bar", index };
}
export function openBarAdd() {
  useDocumentStore().selectedTileId = null;
  state.inspector = { kind: "bar-add" };
}
// The drawer of one entity of the screensaver clock's row (app 0.4.81, stores/screensaver.ts).
export function openSaverItem(index: number) {
  if (!(state.inspector?.kind === "saver-item" && state.inspector.index === index)) state.iconPickerOpen = false;
  useDocumentStore().selectedTileId = null;
  state.inspector = { kind: "saver-item", index };
}
// One step of the screensaver in the drawer: its players, its camera or its clock.
export function openSaverStep(step: SaverKind) {
  state.iconPickerOpen = false;
  useDocumentStore().selectedTileId = null;
  state.inspector = { kind: "saver", step };
}
export function openSaverAdd() {
  useDocumentStore().selectedTileId = null;
  state.inspector = { kind: "saver-add" };
}
export function closeInspector() {
  state.inspector = null;
  useDocumentStore().selectedTileId = null;
  state.optionPreview = null;
}

// ---- Started once the page is on the screen (stores/session.ts start, from boot.ts) ----
// The screensaver's drawers belong to the settings: they close when the layout comes back. The returned function stops it.
let started: (() => void) | null = null;
export function startStore() {
  if (started) return started;
  const scope = effectScope(true);
  scope.run(() => {
    const ui = useUiStore();
    watch(() => ui.tab, (tab) => { if (tab !== "settings" && state.inspector?.kind.startsWith("saver")) closeInspector(); });
  });
  started = () => { started = null; scope.stop(); };
  return started;
}
// ---- A fresh start (tests/setup.ts, between tests) ----
// Every field back to how it starts. What the stores keep (stores/) goes with each test's pinia.
onReset(() => {
  started?.();
  Object.assign(state, fresh());
});
