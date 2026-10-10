// How long the mockup takes to draw again when the add-on sends a new inventory: one page of 64 tiles (an 8 x 8 grid) of
// lights, sensors, switches, climates and covers, each card reading its name, icon, live value and the screen's facts
// through the stores. Run by hand, not by `npm test`: `npx vitest bench --run tests/perf`. The stores' lookups on this path
// are getters, not actions (stores/lookup.ts): an action costs Pinia's bookkeeping on every call.
import { mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { bench, describe } from "vitest";
import { defineComponent, h, nextTick } from "vue";
import DevicePage from "../../src/components/DevicePage.vue";
import { entriesOf } from "../../src/model/layout";
import { loadDocument, state } from "../../src/store";
import { useEntitiesStore } from "../../src/stores/entities";
import type { Inventory, Screen, Tile } from "../../src/types";
import { documentFixture } from "../page-fixtures";
import { useScreenStore } from "../../src/stores/screen";

const DOMAINS = ["light", "sensor", "switch", "climate", "cover", "binary_sensor", "fan", "media_player"];
const grid = { columns: 8, rows: 8 };
const tiles: Tile[] = Array.from({ length: 64 }, (_, slot) => ({ entity: `${DOMAINS[slot % DOMAINS.length]}.thing_${slot}`, name: "", slot }));
const entities = tiles.map((tile, i) => ({ id: tile.entity, name: `Thing ${i}`, state: i % 2 ? "on" : "21.5", area: "Living room" }));
const screen = {
  id: "bench", name: "Bench", online: true, firmware: "0.53.0", board: "guition", layout: { title: "Bench", tiles, pages: 1 },
  shape: { width: 1280, height: 800, columns: 8, rows: 8, dpi: 170, look: "standard" }, pictures: true,
  page_capability: "ready", source_grid: grid,
} as unknown as Screen;
const inventory = (): Inventory => ({
  csrf: "t", connected: true, screens: [{ ...screen, page_document: documentFixture(screen.layout, grid) }], entities: entities.map((e) => ({ ...e })),
  icons: { groups: [{ name: "all", icons: [{ name: "lamp", cp: "F06B5", label: "Lamp" }] }], weather: {}, sun: {}, defaults: { light: "F0335", sensor: "F0F2C" },
    fallback: "F0335", builtin: {}, controls: {} },
} as unknown as Inventory);

// ---- What differs between the store's shape before and after phase 2b: the inventory's place and the open screen ----
function open() {
  state.inventory = inventory();
  useScreenStore().selected = "bench";
  loadDocument(state.inventory.screens[0]);
}
const arrive = () => { state.inventory = { ...state.inventory, entities: entities.map((e) => ({ ...e })) }; };

let page: VueWrapper | null = null;
function draw() {
  page?.unmount();
  const pinia = createPinia();
  setActivePinia(pinia);
  open();
  page = mount(defineComponent({ setup: () => () => h(DevicePage, { page: 0, entries: entriesOf(state.layout!), pages: 1, moving: null }) }),
    { global: { plugins: [pinia] } });
}

describe("a page of 64 tiles", () => {
  bench("drawn again for a new inventory", async () => {
    arrive();
    await nextTick();
  }, { time: 3000, warmupTime: 500, setup: draw });

  bench("the cards' lookups, 64 of each", () => {
    const store = useEntitiesStore();
    for (const tile of tiles) {
      store.entityName(tile.entity);
      store.tileIconCp(tile);
      store.liveOf(tile.entity);
    }
  }, { time: 2000, setup: draw });
});
