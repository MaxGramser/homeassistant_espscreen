// The first layout in the editor (docs/AUTO_LAYOUT.md): what the open screen takes, read from the stores; the home's
// facts and the candidates' capabilities asked of the add-on; the layout made by model/auto-layout.ts; and applying it
// as one edit the person can undo. Plain functions over the stores, as the draft's pages are (editor/pages.ts).
import { getJson } from "../api";
import { t } from "../i18n";
import { appendPages, autoLayout, candidates, type AutoInput, type AutoResult, type AutoScreen, type HomeFacts } from "../model/auto-layout";
import { featuresOf } from "../model/catalogue";
import { label } from "../model/change-label";
import * as pages from "../model/pages";
import { sizesOn } from "../model/sizes";
import { useDocumentStore } from "../stores/document";
import { useEntitiesStore } from "../stores/entities";
import { useInventoryStore } from "../stores/inventory";
import { usePluginsStore } from "../stores/plugins";
import { useScreenStore } from "../stores/screen";
import { useUiStore } from "../stores/ui";

export type AutoMode = "replace" | "append";

/** Whether the open draft holds no tile at all: a new screen, where the first layout is offered at once. */
export function draftEmpty() {
  const document = useDocumentStore().document;
  return Boolean(document) && document!.pages.every((page) => !pages.allTiles(page).length);
}

/** What the open screen takes, for a layout that replaces its pages or comes after them (`append`): then only the pages,
 * tiles and memory the draft leaves. */
export function openScreen(mode: AutoMode): AutoScreen | null {
  const doc = useDocumentStore(), scr = useScreenStore(), screen = scr.currentScreen, document = doc.document, grid = doc.documentGrid;
  if (!screen || !document || !grid) return null;
  const append = mode === "append";
  const tilesNow = append ? doc.layout?.tiles.length ?? 0 : 0, pagesNow = append ? document.pages.length : 0;
  // The screen's memory as it is: the draft that stays is priced beside the new pages (proposeLayout's `existing`).
  const memory = scr.memoryMeasuring ? null : scr.screenMemory;
  const home = document.pages.find((page) => page.id === document.homePageId) ?? document.pages[0];
  return {
    grid: { columns: grid.columns, rows: grid.rows },
    pages: doc.editorLayout.grid.pages - pagesNow, tiles: doc.tileLimit - tilesNow,
    // A screen that takes other grids takes the sizes of the one it is laid out on (page_service.save_pages).
    sizes: screen.grids ? sizesOn(grid) : screen.tile_sizes,
    sections: screen.sections === true,
    features: featuresOf({ rangeless: screen.climate_range === false, vacuumTile: screen.vacuum_tile !== false, lightPresets: screen.light_presets === true }),
    pictures: scr.pictures, liveCamera: screen.live_camera === true, todoLists: screen.todo_lists === true,
    firmware: scr.firmwareOf || "", memory, area: screen.area || undefined, title: document.title,
    topbar: home.topbar,
  };
}

/** The layout for the open screen: the home's facts from the add-on, what each candidate can do, then the model. */
export async function proposeLayout(mode: AutoMode): Promise<AutoResult> {
  const inv = useInventoryStore(), entities = useEntitiesStore(), doc = useDocumentStore();
  const screen = openScreen(mode);
  if (!screen) throw new Error(t("editor.pages.wait_grid"));
  const facts = await getJson<HomeFacts>("home-facts");
  const exclude = mode === "append" ? new Set((doc.layout?.tiles ?? []).map((tile) => tile.entity)) : undefined;
  // What stays of the draft, priced with the new pages as Library prices an add: all of it beside pages that go after it.
  const existing = mode === "append" && doc.layout && doc.document ? { tiles: doc.layout.tiles, pages: doc.document.pages } : undefined;
  const input: AutoInput = { entities: inv.inventory.entities, facts, capabilities: {}, screen, exclude, existing, plugins: usePluginsStore().pluginTileOf };
  await entities.loadCapabilities(candidates(input).map((c) => c.id));
  return autoLayout({ ...input, capabilities: entities.capabilities });
}

/** The layout in the draft as one edit: the pages it has replaced, or the new ones after them. The first new page opens,
 * and a toast offers to take it back. */
export function applyLayout(result: AutoResult, mode: AutoMode) {
  const doc = useDocumentStore(), document = doc.document, grid = doc.documentGrid;
  if (!document || !grid) return false;
  const next = mode === "append" ? appendPages(document, result.layout) : { ...result.layout, title: document.title };
  try {
    if (!doc.applyDocument(next, true, grid, label("auto_layout"))) return false;
  } catch (error: any) { useUiStore().toast(error.message); return false; }
  const first = mode === "append" ? next.pages[document.pages.length] : next.pages[0];
  if (first) doc.selectedPageId = first.id;
  const added = mode === "append" ? next.pages.length - document.pages.length : next.pages.length;
  doc.undoToast(t("editor.auto.made", { pages: added }, added));
  return true;
}
