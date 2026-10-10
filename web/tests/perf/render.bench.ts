// How long the mockup takes to draw again when the add-on sends a new inventory: one page of 64 tiles (an 8 x 8 grid) of
// lights, sensors, switches, climates and covers, each card reading its name, icon, live value and the screen's facts
// through the stores; the same page when Home Assistant reports something new for every entity; and the lookups alone.
// Run by hand, not by `npm test`: `npx vitest bench --run tests/perf`. The stores' lookups on this path are getters, not
// actions (stores/lookup.ts), and an entity is found by its id in an index (stores/inventory.ts entityOf), not by a walk
// through the list. The page is a plain app, as main.ts makes it: Vue Test Utils' mount looks at every component it
// draws for its stubs, which no page of the editor pays.
import { createPinia, setActivePinia } from "pinia";
import { bench, describe } from "vitest";
import { createApp, h, nextTick, type App } from "vue";
import { i18n } from "../../src/i18n";
import DevicePage from "../../src/components/DevicePage.vue";
import { entriesOf } from "../../src/model/layout";
import { useDocumentStore } from "../../src/stores/document";
import { useEntitiesStore } from "../../src/stores/entities";
import { useInventoryStore } from "../../src/stores/inventory";
import { useScreenStore } from "../../src/stores/screen";
import type { Inventory, Screen, Tile } from "../../src/types";
import { documentFixture } from "../helpers/fixtures";

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

// The screen open with its draft, and the add-on's next inventory: the same entities, sent again.
function open() {
  useInventoryStore().inventory = inventory();
  useScreenStore().selected = "bench";
  useDocumentStore().loadDocument(useInventoryStore().inventory.screens[0]);
}
const arrive = () => { useInventoryStore().inventory = { ...useInventoryStore().inventory, entities: entities.map((e) => ({ ...e })) }; };
// Home Assistant's next report, in which every entity says something new (on and off swap, a value moves), the way the
// live poll writes it (entities.ts loadStates): every card has something else to draw.
let turn = 0;
const report = () => {
  turn++;
  const states = Object.fromEntries(tiles.map((tile, i) => [tile.entity, { state: (i + turn) % 2 ? "on" : String(20 + turn % 10 + i / 10),
    a: { brightness: (turn * 37) % 255, unit_of_measurement: tile.entity.startsWith("sensor.") ? "°C" : undefined }, word: null }]));
  Object.assign(useEntitiesStore().liveStates, states);
};

let page: App | null = null;
function draw() {
  page?.unmount();
  const pinia = createPinia();
  setActivePinia(pinia);
  open();
  page = createApp({ render: () => h(DevicePage, { page: 0, entries: entriesOf(useDocumentStore().layout!), pages: 1, moving: null }) }).use(pinia).use(i18n);
  page.mount(document.createElement("div"));
}

describe("a page of 64 tiles", () => {
  bench("drawn again for a new inventory", async () => {
    arrive();
    await nextTick();
  }, { time: 3000, warmupTime: 500, setup: draw });

  bench("drawn again for new states", async () => {
    report();
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
