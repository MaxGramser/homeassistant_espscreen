// The drawer beside the mockup (the inspector): what it shows (a tile, a page, the top bar or one of its items, a step of the
// screensaver or its clock's row, what Home Assistant says of an entity), its pickers, the empty cell or key place the next
// tile from the library goes to, and the choice the pointer rests on before it is picked. It follows the draft
// (stores/document.ts) and nothing of the draft follows it: the drawer of a tile closes itself when its tile goes, the
// screensaver's drawers when the layout comes back, and every drawer when the draft is replaced as a whole.
import { defineStore } from "pinia";
import { computed, onScopeDispose, ref, watch } from "vue";
import type { SaverKind, Tile } from "../types";
import { useDocumentStore } from "./document";
import { useDragStore } from "./drag";
import { useEntitiesStore } from "./entities";
import { lookups } from "./lookup";
import { useUiStore } from "./ui";

export type Inspector =
  | { kind: "tile" }
  | { kind: "bar"; index: number }
  | { kind: "bar-add" }
  | { kind: "saver-item"; index: number }
  | { kind: "saver-add" }
  | { kind: "saver"; step: SaverKind }
  | { kind: "page"; id: string }
  | { kind: "inspect"; entity?: string; slot?: number; key?: number };
// Where the next tile from the library goes: an empty cell a click marked, or a key place under a bedside clock (app
// 0.4.12). One at a time: marking one forgets the other.
export type InsertTarget = { kind: "cell"; slot: number } | { kind: "key"; holder: string; key: number } | null;
// A choice the pointer rests on in the inspector, drawn on its tile before it is picked (app 0.4.32).
export type OptionPreview = { tileId: string; key: string; value: unknown };

export const useInspectorStore = defineStore("inspector", () => {
  const doc = useDocumentStore();
  const entities = useEntitiesStore();
  const dragging = useDragStore();
  const ui = useUiStore();

  const inspector = ref<Inspector | null>(null);
  const iconPickerOpen = ref(false);
  const actionPickerOpen = ref(false);
  const actionSearch = ref("");
  const insert = ref<InsertTarget>(null);
  // The marked cell (-1 for none) and the marked key place, as the mockup and the library read them.
  const insertAt = computed(() => insert.value?.kind === "cell" ? insert.value.slot : -1);
  const insertKey = computed(() => insert.value?.kind === "key" ? { holder: insert.value.holder, key: insert.value.key } : null);
  const optionPreview = ref<OptionPreview | null>(null);
  // A name asked to be changed (app 0.4.x): the drawer of that tile or page puts the focus in its name field. Counted, so
  // asking again for the same one focuses it again.
  const naming = ref<{ kind: "tile" | "page"; id: string; asked: number } | null>(null);
  let asked = 0;
  // A marked cell forgotten (another page, the library closed), a marked key place kept.
  function forgetCell() { if (insert.value?.kind === "cell") insert.value = null; }

  // The tile as the mockup draws it: with the choice the pointer rests on in the inspector, when that is this tile's.
  function previewed(tile: Tile): Tile {
    const hover = optionPreview.value;
    // Only while that tile's own settings are open and nothing is being dragged: the drawn copy never reaches an edit.
    if (!hover || !tile.id || hover.tileId !== tile.id || doc.selectedTileId !== tile.id || dragging.active) return tile;
    return { ...tile, options: { ...(tile.options || {}), [hover.key]: hover.value } } as Tile;
  }

  // ---- What the drawer shows ----
  function openTile(tile: Tile) {
    if (!doc.isSelected(tile)) { iconPickerOpen.value = false; actionPickerOpen.value = false; actionSearch.value = ""; }
    doc.selectedTileId = tile.id || null;
    doc.selectedPageId = doc.document?.pages.find((page) => page.tiles.some((item) => item.id === tile.id ||
      item.children?.some((child) => child.id === tile.id)))?.id || doc.selectedPageId;
    inspector.value = { kind: "tile" };
    entities.loadCapabilities([tile.entity]);
  }
  function openPage(id: string) {
    doc.selectedPageId = id; doc.selectedTileId = null;
    inspector.value = { kind: "page", id };
  }
  // `page` is the page whose bar was clicked (app 0.2.105): the inspector changes that page's own title there, which is
  // where you look for it after clicking the bar.
  function openBar(index: number, page = doc.barPage) {
    if (!(inspector.value?.kind === "bar" && inspector.value.index === index)) iconPickerOpen.value = false;
    doc.selectedTileId = null;
    doc.selectedPageId = doc.document?.pages[page]?.id || null;
    inspector.value = { kind: "bar", index };
  }
  function openBarAdd() {
    doc.selectedTileId = null;
    inspector.value = { kind: "bar-add" };
  }
  // The drawer of one entity of the screensaver clock's row (app 0.4.81, stores/screensaver.ts).
  function openSaverItem(index: number) {
    if (!(inspector.value?.kind === "saver-item" && inspector.value.index === index)) iconPickerOpen.value = false;
    doc.selectedTileId = null;
    inspector.value = { kind: "saver-item", index };
  }
  // One step of the screensaver in the drawer: its players, its camera or its clock.
  function openSaverStep(step: SaverKind) {
    iconPickerOpen.value = false;
    doc.selectedTileId = null;
    inspector.value = { kind: "saver", step };
  }
  function openSaverAdd() {
    doc.selectedTileId = null;
    inspector.value = { kind: "saver-add" };
  }
  /** Opens a tile's drawer with its name ready to be typed. */
  function renameTile(tile: Tile) {
    if (!tile.id) return;
    openTile(tile);
    naming.value = { kind: "tile", id: tile.id, asked: ++asked };
  }
  /** Opens a page's settings with its title ready to be typed. */
  function renamePage(id: string) {
    openPage(id);
    naming.value = { kind: "page", id, asked: ++asked };
  }
  function closeInspector() {
    inspector.value = null;
    doc.selectedTileId = null;
    optionPreview.value = null;
  }

  // ---- Closing by itself ----
  // A tile's drawer goes with its tile (removed, its page removed, undone), at once, so nothing draws a tile that is gone.
  watch(() => doc.currentTile, (tile) => { if (!tile && inspector.value?.kind === "tile") closeInspector(); }, { flush: "sync" });
  // The screensaver's drawers belong to the settings: they close when the layout comes back.
  watch(() => ui.tab, (tab) => { if (tab !== "settings" && inspector.value?.kind.startsWith("saver")) closeInspector(); });
  // Another screen, none, or another draft of this one (copied, imported, the saved one read again): every drawer closes,
  // and a cell or key place marked on another screen is forgotten.
  onScopeDispose(doc.onReplaced((opened) => {
    closeInspector();
    if (opened) insert.value = null;
  }));

  return {
    inspector, iconPickerOpen, actionPickerOpen, actionSearch, insert, insertAt, insertKey, optionPreview, naming, renameTile, renamePage,
    // What the mockup reads as it draws (stores/lookup.ts).
    ...lookups({ previewed }),
    forgetCell, openTile, openPage, openBar, openBarAdd, openSaverItem, openSaverStep, openSaverAdd, closeInspector,
  };
});
