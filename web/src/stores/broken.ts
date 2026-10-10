// Broken tiles: the tiles of every screen that show an entity Home Assistant no longer has, or one it has had no word from
// for a while (model/broken-tiles.ts). The overview and the sidebar say how many and where; a click opens that tile in
// the inspector with the entity picker ready to choose another. The open screen counts as its draft has it, so a tile
// given another entity is fine at once, before it is saved; every other screen as its saved document has it.
import { defineStore } from "pinia";
import { computed } from "vue";
import * as broken from "../model/broken-tiles";
import type { Screen } from "../types";
import { useDocumentStore } from "./document";
import { useEntitiesStore } from "./entities";
import { useInspectorStore } from "./inspector";
import { useInventoryStore } from "./inventory";
import { lookups } from "./lookup";
import { useScreenStore } from "./screen";
import { useSessionStore } from "./session";
import { useUiStore } from "./ui";

export const useBrokenStore = defineStore("broken", () => {
  const inv = useInventoryStore();
  const entities = useEntitiesStore();
  const doc = useDocumentStore();
  const scr = useScreenStore();
  const ui = useUiStore();
  const session = useSessionStore();
  const insp = useInspectorStore();

  // What the inventory knows besides Home Assistant's entities: the screen's own cards and the map's trackers.
  const others = computed(() => new Map([...(inv.inventory.builtin || []), ...(inv.inventory.trackers || [])].map((entity) => [entity.id, entity])));
  function health(id: string) {
    // The editor's clock ticks while a screen is edited; a new inventory brings the time along too.
    void ui.now;
    return broken.entityHealth(id, {
      ready: inv.connected && inv.inventory.entities.length > 0,
      known: (entity) => inv.entityOf(entity) || others.value.get(entity),
      live: (entity) => entities.liveStates[entity]?.state,
      now: Date.now(),
    });
  }
  const layoutOf = (screen: Screen) => screen.id === scr.selected && doc.document ? doc.document
    : screen.page_document?.format === "pages-v2" ? screen.page_document.layout : null;
  const tiles = computed(() => broken.brokenTiles(inv.inventory.screens, layoutOf, health));
  const summary = computed(() => broken.brokenSummary(tiles.value));
  const onScreen = (screen: Screen) => tiles.value.filter((tile) => tile.screen.id === screen.id);
  /** The health of the entity a tile of the open draft shows, for its inspector. */
  const tileHealth = (entity: string) => health(entity);

  /** The tile in the inspector, on its screen and page, with the entity picker ready. The screen is opened first (which
   * asks about unsaved changes on another one); a person who keeps those stays where they are. True when it is shown. */
  async function show(tile: broken.BrokenTile) {
    const screen = tile.screen;
    if (scr.selected !== screen.id || !doc.document) await session.select(screen.id);
    if (scr.selected !== screen.id || !doc.layout) return false;
    ui.go("");
    ui.tab = "layout";
    const found = doc.layout.tiles.find((item) => item.id === tile.tileId);
    if (!found) return false;
    insp.openTile(found);
    insp.entityPickerOpen = true;
    return true;
  }

  return { tiles, summary, ...lookups({ onScreen, tileHealth }), show };
});
