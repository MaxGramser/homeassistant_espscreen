// What Home Assistant says of its entities (stores/entities.ts): asked once and again after a failure, the states of what
// is asked with an answer dropped once it is no longer wanted, a sensor's history kept a minute, names and icons.
import { afterEach, describe, expect, it, vi } from "vitest";
import { state } from "../../src/store";
import { useEntitiesStore } from "../../src/stores/entities";
import { failure, fakeApi } from "../helpers/fake-api";
import { useInventoryStore } from "../../src/stores/inventory";

afterEach(() => vi.useRealTimers());

const history = (value: number) => ({ history: { start: 0, end: 3600, values: [value], unit: "°C" } });

describe("capabilities, actions and second lines", () => {
  it("asks for each entity once, in batches of forty, never for the screen's own, and again after a failure", async () => {
    const api = fakeApi({ "GET capabilities": (request) => ({ capabilities: Object.fromEntries(request.query.getAll("entity").map((id) => [id, { controls: [] }])) }) });
    const entities = useEntitiesStore();
    const ids = Array.from({ length: 45 }, (_, i) => `light.l${i}`);
    await entities.loadCapabilities([...ids, "screen.clock", "light.l0"]);
    expect(api.asked("capabilities").map((r) => r.query.getAll("entity").length)).toEqual([40, 5]);
    expect(Object.keys(entities.capabilities)).toHaveLength(45);
    await entities.loadCapabilities(["light.l3"]);
    expect(api.count("capabilities")).toBe(2);
    api.on("GET capabilities", failure(502, "Bad gateway"));
    await entities.loadCapabilities(["switch.s"]);
    api.on("GET capabilities", { capabilities: { "switch.s": { controls: ["toggle"] } } });
    await entities.loadCapabilities(["switch.s"]);
    expect(api.count("capabilities")).toBe(4);
    expect(entities.capabilities["switch.s"]).toEqual({ controls: ["toggle"] });
  });

  it("asks for an entity's actions and second line once, and again after a failure", async () => {
    const api = fakeApi({ "GET entity-actions": { actions: [{ action: "light.turn_on" }] }, "GET entity-subtitle": failure(500, "Down") });
    const entities = useEntitiesStore();
    await entities.loadEntityActions("light.a");
    await entities.loadEntityActions("light.a");
    expect(api.count("entity-actions")).toBe(1);
    expect(entities.entityActions["light.a"]).toEqual([{ action: "light.turn_on" }]);
    await entities.loadSubtitleValues("sensor.t");
    expect(entities.subtitleValues["sensor.t"]).toBeUndefined();
    api.on("GET entity-subtitle", { values: [{ key: "attr:unit", name: "Unit" }] });
    await entities.loadSubtitleValues("sensor.t");
    await entities.loadSubtitleValues("sensor.t");
    expect(api.count("entity-subtitle")).toBe(2);
    expect(entities.subtitleValues["sensor.t"]).toEqual([{ key: "attr:unit", name: "Unit" }]);
  });
});

describe("live values", () => {
  it("asks for the open layout's states one request at a time, and drops an answer no longer wanted", async () => {
    const api = fakeApi({ "GET states": (request) => ({ states: Object.fromEntries(request.query.getAll("entity").map((id) => [id, { state: "on", a: {} }])) }) });
    const entities = useEntitiesStore();
    const held = api.defer("GET states");
    let wanted = true;
    const first = entities.loadStates(["light.a", "screen.clock", "light.a"], () => wanted);
    await entities.loadStates(["light.b"]);
    expect(api.count("states")).toBe(1);
    expect(api.asked("states")[0].query.getAll("entity")).toEqual(["light.a"]);
    wanted = false;
    held.resolve();
    await first;
    expect(entities.liveStates).toEqual({});
    await entities.loadStates(["light.b"]);
    expect(Object.keys(entities.liveStates)).toEqual(["light.b"]);
  });

  it("asks for the first eighty of what the library shows, and falls back on what the inventory knew", async () => {
    const api = fakeApi({ "GET states": { states: { "sensor.t": { state: "21", a: { unit_of_measurement: "°C" } } } } });
    useInventoryStore().inventory = { screens: [], entities: [{ id: "light.k", name: "Kitchen", state: "off", area: "" }] } as any;
    const entities = useEntitiesStore();
    await entities.loadLibraryStates(Array.from({ length: 100 }, (_, i) => `sensor.s${i}`));
    expect(api.asked("states").map((r) => r.query.getAll("entity").length)).toEqual([60, 20]);
    expect(entities.liveOf("sensor.t")).toEqual({ state: "21", a: { unit_of_measurement: "°C" } });
    expect(entities.liveOf("light.k")).toEqual({ state: "off", word: null, a: {} });
    expect(entities.liveOf("light.gone")).toBeNull();
  });

  it("draws the overview with the states of every home page and each bar's values, one bar at a time", async () => {
    const page = (id: string, tiles: string[], bar: string[]) => ({ id, navigation: { excludeFromPagination: false },
      topbar: { leading: [], title: { source: "screen" }, trailing: bar.map((entity, i) => ({ id: `${id}${i}`, type: "entity", entity })) },
      tiles: tiles.map((entity, i) => ({ id: `${id}t${i}`, content: { kind: "entity", entityId: entity }, appearance: { label: "" }, interaction: {},
        placement: { row: 0, column: i, columns: 1, rows: 1 } })) });
    const screen = (id: string, tiles: string[], bar: string[]) => ({ id, name: id, layout: { title: id, tiles: [], pages: 1 }, shape: { columns: 2, rows: 2, width: 480, height: 480 },
      page_document: { format: "pages-v2", revision: "r", sourceGrid: { columns: 2, rows: 2 }, layout: { title: id, homePageId: `${id}p`, pages: [page(`${id}p`, tiles, bar)] } } });
    useInventoryStore().inventory = { screens: [screen("hall", ["light.a"], ["sensor.out"]), screen("desk", ["light.b"], ["sensor.out", "sensor.in"])], entities: [] } as any;
    const api = fakeApi({
      "GET states": { states: { "light.a": { state: "on", a: {} } } },
      "POST header-preview": (request) => ({ items: request.body.header.items.map((item: any) => ({ t: item.entity })) }),
    });
    const entities = useEntitiesStore();
    await entities.loadOverview();
    expect(entities.liveStates["light.a"]).toEqual({ state: "on", a: {} });
    expect(api.asked("POST header-preview").map((r) => r.body.header.items.map((item: any) => item.entity))).toEqual([["sensor.out"], ["sensor.in"]]);
    expect(Object.values(entities.topbarPreviews).map((p) => p.t).sort()).toEqual(["sensor.in", "sensor.out"]);
  });
});

describe("a sensor's history", () => {
  it("is asked once a minute per entity and span, shared by whoever asks, and asked again after a failure", async () => {
    vi.useFakeTimers({ now: new Date(2026, 9, 10, 12, 0) });
    let value = 1;
    const api = fakeApi({ "GET history-preview": () => history(value++) });
    const entities = useEntitiesStore();
    const [first, second] = await Promise.all([entities.loadHistory("sensor.t", 24), entities.loadHistory("sensor.t", 24)]);
    expect(first).toBe(second);
    expect(first?.values).toEqual([1]);
    expect((await entities.loadHistory("sensor.t", 6))?.values).toEqual([2]);
    vi.advanceTimersByTime(59000);
    expect((await entities.loadHistory("sensor.t", 24))?.values).toEqual([1]);
    vi.advanceTimersByTime(1000);
    expect((await entities.loadHistory("sensor.t", 24))?.values).toEqual([3]);
    expect(api.asked("history-preview").map((r) => [r.query.get("entity"), r.query.get("hours")])).toEqual([["sensor.t", "24"], ["sensor.t", "6"], ["sensor.t", "24"]]);
    api.on("GET history-preview", failure(500, "No recorder"));
    await expect(entities.loadHistory("sensor.x", 24)).rejects.toThrow("No recorder");
    api.on("GET history-preview", () => history(9));
    expect((await entities.loadHistory("sensor.x", 24))?.values).toEqual([9]);
  });

  it("keeps the newest sixty-four", async () => {
    const api = fakeApi({ "GET history-preview": () => history(0) });
    const entities = useEntitiesStore();
    for (let i = 0; i < 65; i++) await entities.loadHistory(`sensor.s${i}`, 24);
    await entities.loadHistory("sensor.s64", 24);
    expect(api.count("history-preview")).toBe(65);
    await entities.loadHistory("sensor.s0", 24);
    expect(api.count("history-preview")).toBe(66);
  });
});

describe("names and icons", () => {
  it("names an entity as Home Assistant does, and draws Home Assistant's icon, else its domain's", () => {
    useInventoryStore().inventory = {
      screens: [], entities: [{ id: "light.k", name: "Kitchen", icon: "F0335", area: "" }, { id: "weather.home", name: "Home", state: "rainy", area: "" }, { id: "fan.f", name: "Fan", area: "" }],
      builtin: [{ id: "screen.clock", name: "Clock" }],
      icons: { groups: [{ name: "Home", icons: [{ name: "mdi:sofa", cp: "F04B9", label: "Sofa" }] }], weather: { rainy: "F0597", partlycloudy: "F0595" }, sun: {},
        defaults: { fan: "F0210" }, fallback: "F0B49", builtin: {}, controls: {} },
    } as any;
    const entities = useEntitiesStore();
    expect([entities.entityName("light.k"), entities.entityName("screen.clock"), entities.entityName("light.gone")]).toEqual(["Kitchen", "Clock", "light.gone"]);
    expect(entities.iconNamed("mdi:sofa")?.cp).toBe("F04B9");
    expect([entities.automaticIcon("light.k"), entities.automaticIcon("weather.home"), entities.automaticIcon("fan.f"), entities.automaticIcon("lock.x")])
      .toEqual(["F0335", "F0597", "F0210", "F0B49"]);
    expect(entities.tileIconCp({ entity: "fan.f", name: "", slot: 0, options: { icon: "mdi:sofa" } })).toBe("F04B9");
    // Another list of icons from the add-on is read again.
    useInventoryStore().inventory.icons = { ...useInventoryStore().inventory.icons!, groups: [{ name: "Home", icons: [{ name: "mdi:sofa", cp: "F0001", label: "Sofa" }] }] } as any;
    expect(entities.iconNamed("mdi:sofa")?.cp).toBe("F0001");
  });
});
