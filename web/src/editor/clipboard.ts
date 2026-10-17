// Tiles copied, cut and pasted (Cmd+C, Cmd+X, Cmd+V), and removed together, with the stores (model/tile-clipboard.ts
// does the placing). The copied tiles stay while the editor is open, from one screen to the next, and this browser keeps
// them for another tab of the editor too. A paste goes to the chosen page, at the empty cell marked on it if there is
// one, and the pasted tiles are chosen afterwards, so a second paste or a drag carries on from there.
import { t } from "../i18n";
import { entriesOf } from "../model/layout";
import { memoryUse, NEARLY_FULL, noRoom } from "../model/memory";
import { suggestedPageTitle } from "../model/page-naming";
import * as pages from "../model/pages";
import { copyTiles, pasteTiles as placeCopied, type CopiedTiles } from "../model/tile-clipboard";
import pageRules from "../model/page-rules.json";
import { useDocumentStore } from "../stores/document";
import { useEntitiesStore } from "../stores/entities";
import { useInspectorStore } from "../stores/inspector";
import { useInventoryStore } from "../stores/inventory";
import { usePluginsStore } from "../stores/plugins";
import { useScreenStore } from "../stores/screen";
import { useUiStore } from "../stores/ui";
import { askConfirm } from "../composables/useConfirm";
import { tileSizeChoices } from "./tiles";
import type { Tile } from "../types";

const STORAGE_KEY = "tessera.copied-tiles";
/** The key a shortcut is held with as this computer writes it: ⌘ on a Mac, an iPad or an iPhone, Ctrl elsewhere. */
export function modifierKey() {
  return typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent) ? "⌘" : "Ctrl";
}
/** A shortcut as this computer writes it: ⌘C, or Ctrl+C. */
export const shortcut = (letter: string) => (modifierKey() === "⌘" ? `⌘${letter}` : `Ctrl+${letter}`);
let copied: CopiedTiles | null = null;

function remember(value: CopiedTiles) {
  copied = value;
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(value)); } catch { /* kept for this page only */ }
}
/** What was copied last: on this page, else in another tab of the editor in this browser. */
export function copiedTiles(): CopiedTiles | null {
  try {
    const kept = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
    if (kept && Array.isArray(kept.tiles) && kept.grid) copied = kept;
  } catch { /* what this page copied */ }
  return copied?.tiles.length ? copied : null;
}
/** Forgets what was copied (between tests). */
export function forgetCopied() {
  copied = null;
  try { localStorage.removeItem(STORAGE_KEY); } catch { /* nothing kept */ }
}

/** Copies the chosen tiles: true when there were any. */
export function copyChosen(): boolean {
  const doc = useDocumentStore(), tiles = useInspectorStore().chosenTiles.filter((tile) => tile.id && tile.in === undefined);
  if (!doc.document || !doc.documentGrid || !tiles.length) return false;
  remember(copyTiles(doc.document, doc.documentGrid, tiles.map((tile) => tile.id!)));
  useUiStore().toast(t("editor.clipboard.copied", { n: tiles.length, key: shortcut("V") }, tiles.length));
  return true;
}
/** Copies the chosen tiles and takes them off, as one step of undo. */
export function cutChosen(): boolean {
  const tiles = useInspectorStore().chosenTiles.filter((tile) => tile.id && tile.in === undefined);
  const doc = useDocumentStore();
  if (!doc.document || !doc.documentGrid || !tiles.length) return false;
  remember(copyTiles(doc.document, doc.documentGrid, tiles.map((tile) => tile.id!)));
  removeTiles(tiles, "editor.clipboard.cut");
  return true;
}
/** Takes these tiles off together, as one step of undo. `said` is the toast's words, with the number of tiles. */
export function removeTiles(tiles: readonly Tile[], said = "editor.layout.removed_several") {
  const doc = useDocumentStore(), ids = new Set(tiles.map((tile) => tile.id).filter(Boolean));
  if (!ids.size) return false;
  const done = doc.editDocument((draft) => {
    for (const page of draft.pages) {
      page.tiles = page.tiles.filter((item) => !ids.has(item.id));
      for (const item of page.tiles) if (item.children) {
        item.children = item.children.filter((child) => !ids.has(child.id));
        if (!item.children.length) delete item.children;
      }
    }
  });
  if (done) doc.undoToast(t(said, { n: ids.size }, ids.size));
  return done;
}

/** Puts what was copied on the chosen page. True when any tile went on. */
export async function pasteCopied(): Promise<boolean> {
  const doc = useDocumentStore(), insp = useInspectorStore(), scr = useScreenStore(), ui = useUiStore();
  const source = copiedTiles();
  if (!source || !doc.document || !doc.documentGrid || !doc.layout) return false;
  const grid = doc.screenGridOf(doc.documentGrid);
  const target = Math.max(0, doc.document.pages.findIndex((page) => page.id === doc.selectedPageId));
  // A cell marked on that page is where the group's top left corner goes.
  const cells = grid.columns * grid.rows, marked = insp.insertAt;
  const anchor = marked >= 0 && Math.floor(marked / cells) === target ? { row: Math.floor((marked % cells) / grid.columns), column: marked % grid.columns } : undefined;
  const entities = useEntitiesStore(), inventory = useInventoryStore();
  const result = placeCopied(doc.document, grid, source, target, {
    // An entity the screen takes once (a bedside clock, or every tile on older firmware) is left out where it stands.
    allowed: (tile, entity, layout) => {
      if (tile.content.kind === "plugin" && !usePluginsStore().pluginTileOf(entity)) return false;
      const here = layout.pages.some((page) => page.tiles.some((item) => item !== tile && pages.entityOf(layout, item) === entity));
      return !here || (scr.repeatable(entity) && !(entity in pageRules.keyHolders));
    },
    sizes: (tile, entity) => tileSizeChoices({ entity, name: "", slot: 0, options: { display: tile.appearance.display } } as Tile),
    entityOf: pages.entityOf,
    room: doc.tileLimit - doc.layout.tiles.length,
    pages: grid.pages ?? pages.pageLimit(grid),
  }, anchor);
  if (!result.added.length) {
    ui.toast(t(source.tiles.length ? "editor.clipboard.none_fit" : "editor.clipboard.empty"));
    return false;
  }
  // Past nine tenths of the screen's memory, or past all of it, the editor asks first, as for a tile from the library.
  const memory = scr.screenMemory;
  if (memory && !scr.memoryMeasuring) {
    const plugins = usePluginsStore().pluginTileOf;
    const before = memoryUse(doc.layout.tiles, memory, doc.document.pages, plugins);
    const after = memoryUse(pages.projectLayout(result.layout, doc.documentGrid).tiles, memory, result.layout.pages, plugins);
    const line = after.level === "over" && before.level !== "over" ? (noRoom(after) ? "none" : "over")
      : after.share >= NEARLY_FULL && before.share < NEARLY_FULL ? "close" : null;
    if (line && !(await askConfirm(t(`editor.memory.confirm_${line}`, { n: Math.min(999, Math.round(after.share * 100)) }), { confirm: t("editor.confirm.add_anyway") })))
      return false;
  }
  // A page the paste started is named after what is on it, as a page a drag starts.
  const existing = new Set(doc.document.pages.map((page) => page.id));
  for (const page of result.layout.pages) if (!existing.has(page.id)) {
    const title = suggestedPageTitle(page, inventory.inventory.entities);
    page.topbar.title = title ? { source: "text", text: title } : { source: "screen" };
  }
  let done: boolean;
  try { done = doc.applyEdit(result.layout); }
  catch (error: any) { ui.toast(error.message); return false; }
  if (!done) return false;
  entities.loadCapabilities(doc.layout!.tiles.filter((tile) => tile.id && result.added.includes(tile.id)).map((tile) => tile.entity));
  doc.loadStates();
  insp.insert = null;
  insp.selectTiles(result.added);
  const n = result.added.length;
  ui.toast(result.skipped ? t("editor.clipboard.pasted_some", { n, total: n + result.skipped })
    : result.newPages ? t("editor.clipboard.pasted_pages", { n, pages: result.newPages }, result.newPages)
    : t("editor.clipboard.pasted", { n }, n), { label: t("editor.common.undo"), run: doc.undo });
  return true;
}

/** Every tile of the chosen page chosen together (Cmd+A). */
export function selectPage() {
  const doc = useDocumentStore();
  if (!doc.layout || !doc.document) return false;
  const page = Math.max(0, doc.document.pages.findIndex((item) => item.id === doc.selectedPageId));
  const { pageOf } = doc.editorLayout;
  const ids = entriesOf(doc.layout).filter(({ slot }) => pageOf(slot) === page).map(({ tile }) => tile.id!).filter(Boolean);
  useInspectorStore().selectTiles(ids);
  return ids.length > 0;
}
