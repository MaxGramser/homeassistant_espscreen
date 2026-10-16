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
  // Several tiles chosen at once (Cmd or Shift and a click, or a band dragged over them): stores/inspector.ts selection.
  | { kind: "tiles" }
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
  // A tile's entity picker (TileEntityFix): open for a tile whose entity is gone, or when its menu asks for another.
  const entityPickerOpen = ref(false);
  const insert = ref<InsertTarget>(null);
  // The marked cell (-1 for none) and the marked key place, as the mockup and the library read them.
  const insertAt = computed(() => insert.value?.kind === "cell" ? insert.value.slot : -1);
  const insertKey = computed(() => insert.value?.kind === "key" ? { holder: insert.value.holder, key: insert.value.key } : null);
  const optionPreview = ref<OptionPreview | null>(null);
  // Where the way back in the inspector's head leads (app 0.4.89): the page whose settings opened its top bar. Anything
  // opened another way has none.
  const back = ref<Inspector | null>(null);
  // Which part of a page its settings show (app 0.4.89): the page itself or its place in the Dock, chosen in the small
  // page at their head. Kept while its top bar is open, so the way back finds the part it left.
  const pagePart = ref<"page" | "dock">("page");
  // A name asked to be changed (app 0.4.x): the drawer of that tile or page puts the focus in its name field. Counted, so
  // asking again for the same one focuses it again.
  const naming = ref<{ kind: "tile" | "page"; id: string; asked: number } | null>(null);
  let asked = 0;
  // The tiles chosen together, by id, in the order they were chosen: two or more while the drawer shows them
  // (SelectionInspector), none otherwise. One tile chosen is the tile's own drawer.
  const selection = ref<string[]>([]);
  const selectedTiles = computed(() => {
    const tiles = doc.layout?.tiles || [];
    return selection.value.map((id) => tiles.find((tile) => tile.id === id)).filter((tile): tile is Tile => Boolean(tile));
  });
  // Every tile chosen: the several, or the one whose drawer is open.
  const chosenTiles = computed<Tile[]>(() => inspector.value?.kind === "tiles" ? selectedTiles.value
    : inspector.value?.kind === "tile" && doc.currentTile ? [doc.currentTile] : []);
  // The tiles under a band being drawn (composables/useBandSelect.ts), chosen once it is let go.
  const band = ref<string[] | null>(null);
  const isPicked = (tile: Tile) => Boolean(tile.id) && ((inspector.value?.kind === "tiles" && selection.value.includes(tile.id!)) || Boolean(band.value?.includes(tile.id!)));
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
  /** These tiles chosen: none closes the drawer, one opens its own, more show what they have in common. Only tiles on the
   * grid, not keys under a bedside clock. */
  function selectTiles(ids: readonly string[]) {
    const tiles = doc.layout?.tiles || [];
    const found = [...new Set(ids)].map((id) => tiles.find((tile) => tile.id === id && tile.in === undefined)).filter((tile): tile is Tile => Boolean(tile));
    if (!found.length) { if (inspector.value?.kind === "tiles" || inspector.value?.kind === "tile") closeInspector(); return; }
    if (found.length === 1) { openTile(found[0]); return; }
    iconPickerOpen.value = false; actionPickerOpen.value = false; entityPickerOpen.value = false; optionPreview.value = null; back.value = null;
    // The drawer first: a tile's drawer closes itself (and lets go of every choice) once its tile is no longer chosen.
    inspector.value = { kind: "tiles" };
    selection.value = found.map((tile) => tile.id!);
    doc.selectedTileId = null;
    doc.selectedPageId = doc.document?.pages.find((page) => page.tiles.some((item) => item.id === found[0].id))?.id || doc.selectedPageId;
  }
  /** A tile taken into the choice, or out of it (Cmd, Ctrl or Shift and a click): the tile already open counts along. */
  function toggleTile(tile: Tile) {
    if (!tile.id || tile.in !== undefined) return;
    const now = chosenTiles.value.map((item) => item.id!);
    selectTiles(now.includes(tile.id) ? now.filter((id) => id !== tile.id) : [...now, tile.id]);
  }
  function openTile(tile: Tile) {
    selection.value = []; back.value = null;
    if (!doc.isSelected(tile)) { iconPickerOpen.value = false; actionPickerOpen.value = false; actionSearch.value = ""; entityPickerOpen.value = false; }
    doc.selectedTileId = tile.id || null;
    doc.selectedPageId = doc.document?.pages.find((page) => page.tiles.some((item) => item.id === tile.id ||
      item.children?.some((child) => child.id === tile.id)))?.id || doc.selectedPageId;
    inspector.value = { kind: "tile" };
    entities.loadCapabilities([tile.entity]);
  }
  function openPage(id: string) {
    if (!(inspector.value?.kind === "page" && inspector.value.id === id)) iconPickerOpen.value = false;
    if (doc.selectedPageId !== id) pagePart.value = "page";
    selection.value = []; back.value = null;
    doc.selectedPageId = id; doc.selectedTileId = null;
    inspector.value = { kind: "page", id };
  }
  // `page` is the page whose bar was clicked (app 0.2.105): the inspector changes that page's own title there, which is
  // where you look for it after clicking the bar.
  function openBar(index: number, page = doc.barPage) {
    const was = inspector.value;
    if (!(was?.kind === "bar" && was.index === index)) iconPickerOpen.value = false;
    // From a page's settings the way back leads there; from the bar itself it stays where it led.
    back.value = was?.kind === "page" ? was : was?.kind === "bar" || was?.kind === "bar-add" ? back.value : null;
    doc.selectedTileId = null;
    doc.selectedPageId = doc.document?.pages[page]?.id || null;
    inspector.value = { kind: "bar", index };
  }
  function openBarAdd() {
    iconPickerOpen.value = false;
    doc.selectedTileId = null;
    inspector.value = { kind: "bar-add" };
  }
  // The drawer of one entity of the screensaver clock's row (app 0.4.81, stores/screensaver.ts).
  function openSaverItem(index: number) {
    back.value = null;
    if (!(inspector.value?.kind === "saver-item" && inspector.value.index === index)) iconPickerOpen.value = false;
    doc.selectedTileId = null;
    inspector.value = { kind: "saver-item", index };
  }
  // One step of the screensaver in the drawer: its players, its camera or its clock.
  function openSaverStep(step: SaverKind) {
    iconPickerOpen.value = false; back.value = null;
    doc.selectedTileId = null;
    inspector.value = { kind: "saver", step };
  }
  function openSaverAdd() {
    iconPickerOpen.value = false; back.value = null;
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
  /** The way back in the head: to the page whose settings opened this top bar. */
  function goBack() {
    const to = back.value;
    back.value = null;
    if (to?.kind === "page") openPage(to.id);
  }
  /** Escape goes one step out (app 0.4.89): an open icon choice, a tile's actions or another entity closes, Add goes back to its bar or its clock, a top bar
   * opened from its page goes back to that page, and only then the inspector closes. */
  function escape() {
    if (iconPickerOpen.value) { iconPickerOpen.value = false; optionPreview.value = null; return; }
    // A tile's actions or another entity in the place under it (app 0.4.89).
    if (actionPickerOpen.value) { actionPickerOpen.value = false; actionSearch.value = ""; return; }
    if (entityPickerOpen.value) { entityPickerOpen.value = false; return; }
    if (inspector.value?.kind === "bar-add") { openBar(-1); return; }
    if (inspector.value?.kind === "saver-add") { openSaverStep("clock"); return; }
    if (back.value) { goBack(); return; }
    closeInspector();
  }
  function closeInspector() {
    back.value = null;
    inspector.value = null;
    selection.value = [];
    doc.selectedTileId = null;
    optionPreview.value = null;
  }

  // ---- Closing by itself ----
  // A tile's drawer goes with its tile (removed, its page removed, undone), at once, so nothing draws a tile that is gone.
  watch(() => doc.currentTile, (tile) => { if (!tile && inspector.value?.kind === "tile") closeInspector(); }, { flush: "sync" });
  // Tiles chosen together that go (removed, undone) leave the choice; one left is that tile's own drawer.
  watch(() => inspector.value?.kind === "tiles" ? selectedTiles.value : null, (left) => {
    if (left && left.length !== selection.value.length) selectTiles(left.map((tile) => tile.id!));
  });
  // Anything else opened in the drawer lets go of the tiles chosen together.
  watch(inspector, (open) => { if (open?.kind !== "tiles") selection.value = []; }, { flush: "sync" });
  // The screensaver's drawers belong to the settings: they close when the layout comes back.
  watch(() => ui.tab, (tab) => { if (tab !== "settings" && inspector.value?.kind.startsWith("saver")) closeInspector(); });
  // Another screen, none, or another draft of this one (copied, imported, the saved one read again): every drawer closes,
  // and a cell or key place marked on another screen is forgotten.
  onScopeDispose(doc.onReplaced((opened) => {
    closeInspector();
    if (opened) insert.value = null;
  }));

  return {
    inspector, selection, band, selectedTiles, chosenTiles, isPicked, selectTiles, toggleTile, iconPickerOpen, actionPickerOpen, actionSearch, entityPickerOpen, insert, insertAt, insertKey, optionPreview, naming, renameTile, renamePage,
    // What the mockup reads as it draws (stores/lookup.ts).
    ...lookups({ previewed }),
    back, pagePart, goBack, escape,
    forgetCell, openTile, openPage, openBar, openBarAdd, openSaverItem, openSaverStep, openSaverAdd, closeInspector,
  };
});
