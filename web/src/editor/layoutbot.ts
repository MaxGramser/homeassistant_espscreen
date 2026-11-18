// Layoutbot's plan placed for a screen (docs/LAYOUTBOT.md): what the screen takes, read from its inventory record as
// the open screen's is read for Auto layout (editor/auto-layout.ts openScreen), what each entity of the plan can do and
// the home's facts asked of the add-on, then model/layoutbot.ts applyPlan, which places through model/placement.ts.
// For the open screen and for one that is not open alike, so a proposal for another screen is placed exactly as it
// would be if it were open. Plain functions over the stores, as editor/auto-layout.ts is.
import { getJson } from "../api";
import type { AutoScreen, HomeFacts } from "../model/auto-layout";
import { featuresOf } from "../model/catalogue";
import { applyPlan, withoutScope, type Plan, type PlanNote } from "../model/layoutbot";
import { measuring } from "../model/memory";
import * as pages from "../model/pages";
import * as status from "../model/screen-status";
import { sizesOn } from "../model/sizes";
import { useEntitiesStore } from "../stores/entities";
import { useInventoryStore } from "../stores/inventory";
import { usePluginsStore } from "../stores/plugins";
import type { PageGrid, PageLayout, Screen } from "../types";

/** A screen's grid with the pages it takes, as the document store holds the open screen's edits to it. */
export function gridOf(screen: Screen, grid: { columns: number; rows: number }): PageGrid {
  return { columns: grid.columns, rows: grid.rows, ...(screen.page_limit ? { pages: screen.page_limit } : {}) };
}

/** What a screen still takes after `layout`: its pages and tiles left, its memory as it is (the draft that stays is
 * priced beside what is added, `existing` of the input), as Auto layout's input. */
export function screenAfter(screen: Screen, layout: PageLayout, grid: PageGrid): AutoScreen {
  const view = pages.projectLayout(layout, grid);
  const home = layout.pages.find((page) => page.id === layout.homePageId) ?? layout.pages[0];
  return {
    grid: { columns: grid.columns, rows: grid.rows },
    pages: Math.max(0, pages.pageLimit(grid) - layout.pages.length),
    tiles: Math.max(0, (screen.tile_limit ?? 64) - view.tiles.length),
    // A screen that takes other grids takes the sizes of the one it is laid out on (page_service.save_pages).
    sizes: screen.grids ? sizesOn(grid) : screen.tile_sizes,
    sections: screen.sections === true,
    features: featuresOf({ rangeless: screen.climate_range === false, vacuumTile: screen.vacuum_tile !== false, lightPresets: screen.light_presets === true }),
    pictures: Boolean(screen.pictures), liveCamera: screen.live_camera === true, todoLists: screen.todo_lists === true,
    firmware: status.firmwareVersion(screen) || "", memory: screen.memory && !measuring(screen.memory) ? screen.memory : null,
    area: screen.area || undefined, title: layout.title, topbar: home?.topbar,
  };
}

const homeBar = (layout: PageLayout) => (layout.pages.find((page) => page.id === layout.homePageId) ?? layout.pages[0])?.topbar;
/** The plan placed in `document` for `screen`: the next draft and its notes. Nothing is applied or saved here. */
export async function placePlan(screen: Screen, document: PageLayout, grid: PageGrid, plan: Plan, covers = false): Promise<{ layout: PageLayout; notes: PlanNote[] }> {
  const inv = useInventoryStore(), entities = useEntitiesStore();
  await entities.loadCapabilities([...new Set(plan.pages.flatMap((page) => [...page.tiles, ...page.sections.flatMap((s) => s.entities)]))]);
  const facts = await getJson<HomeFacts>("home-facts");
  // A restructure places the pages it takes anew: the screen's room is what stays without them.
  const stays = plan.restructure ? withoutScope(document, plan.restructure) : document;
  const view = pages.projectLayout(stays, grid);
  return applyPlan(document, plan, {
    held: grid, covers,
    // New pages take the home page's top bar, also when the whole screen is placed anew.
    input: { entities: inv.inventory.entities, facts, capabilities: entities.capabilities, screen: { ...screenAfter(screen, stays, grid), topbar: homeBar(document) },
      existing: { tiles: view.tiles, pages: stays.pages }, plugins: usePluginsStore().pluginTileOf },
  });
}
