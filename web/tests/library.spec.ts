// The library's rules (model/library.ts): what a search, a kind and a room leave, ranked, grouped by room while browsing,
// the kinds and rooms with their counts, and how an entity is named and marked.
import { describe, expect, it } from "vitest";
import { t } from "../src/i18n";
import { entryDetail, entryTone, inDomain, kindCounts, libraryBase, libraryGroups, libraryMatches, markOf, roomCounts, shortName, tileCounts,
  type Entry, type LibraryFilter } from "../src/model/library";

const ENTRIES: Entry[] = [
  { id: "plugin:bus.departures", name: "Departures" }, { id: "screen.clock", name: "Clock", device: "Built into the screen" },
  { id: "screen.page_9", name: "Go to page 9" }, { id: "camera.door", name: "Door camera", area: "Hall" },
  { id: "light.kitchen", name: "Kitchen light", area: "Kitchen", state: "on" }, { id: "light.hall", name: "Hall light", area: "Hall", state: "unavailable" },
  { id: "input_boolean.guest", name: "Guest mode", state: "off" }, { id: "sun.sun", name: "Sun" }, { id: "sensor.hidden", name: "Hidden", tile: false },
  { id: "switch.bedroom_screen_night", name: "Bedroom screen Night mode", device: "Bedroom screen", area: "Bedroom" },
];
const filter = (more: Partial<LibraryFilter> = {}): LibraryFilter => ({ query: "", pages: 8, pictures: true, hidePlaced: false, counts: new Map(), ...more });

describe("the library", () => {
  it("leaves what a tile can show on this screen, without what is placed when asked", () => {
    expect(libraryBase(ENTRIES, filter()).map((e) => e.id)).toEqual(["plugin:bus.departures", "screen.clock", "camera.door", "light.kitchen", "light.hall",
      "input_boolean.guest", "sun.sun", "switch.bedroom_screen_night"]);
    expect(libraryBase(ENTRIES, filter({ pictures: false })).map((e) => e.id)).not.toContain("camera.door");
    expect(libraryBase(ENTRIES, filter({ pages: 9 })).map((e) => e.id)).toContain("screen.page_9");
    const counts = tileCounts([{ entity: "light.kitchen", name: "", slot: 0 }, { entity: "light.kitchen", name: "", slot: 1 }, { entity: "sun.sun", name: "", slot: 2 }]);
    expect(libraryBase(ENTRIES, filter({ hidePlaced: true, counts })).map((e) => e.id)).not.toContain("light.kitchen");
    expect([markOf("light.kitchen", counts), markOf("sun.sun", counts), markOf("light.hall", counts)]).toEqual(["×2", "✓", "+"]);
    expect(libraryBase(ENTRIES, filter({ query: "hall" })).map((e) => e.id)).toEqual(["camera.door", "light.hall"]);
  });

  it("ranks a search as Spotlight does, and takes a kind with its second domain", () => {
    expect(libraryMatches(libraryBase(ENTRIES, filter({ query: "light" })), "", "light").map((e) => e.name)).toEqual(["Kitchen light", "Hall light"]);
    expect(libraryMatches(ENTRIES, "light", "li").map((e) => e.name)).toEqual(["Kitchen light", "Hall light"]);
    expect(libraryMatches(ENTRIES, "", "k").map((e) => e.name)[0]).toBe("Kitchen light");
    expect([inDomain("input_boolean.guest", "switch"), inDomain("sun.sun", "weather"), inDomain("light.a", "switch"), inDomain("x.y", "")]).toEqual([true, true, false, true]);
  });

  it("stands the entities under their room, the screen's own cards and the plugins' tiles last", () => {
    const groups = libraryGroups(libraryBase(ENTRIES, filter()), true);
    expect(groups.map((g) => g.title)).toEqual(["Bedroom", "Hall", "Kitchen", t("editor.library.no_room"), t("editor.library.filters.screen"), t("editor.library.plugins")]);
    expect(libraryGroups(ENTRIES.slice(0, 2), false)).toEqual([{ key: "", title: "", entities: ENTRIES.slice(0, 2) }]);
  });

  it("counts the kinds and rooms the results hold, keeping the chosen one", () => {
    const base = libraryBase(ENTRIES, filter());
    const kinds = kindCounts(base, "lock");
    expect(kinds[0]).toEqual(["", base.length]);
    expect(Object.fromEntries(kinds)).toMatchObject({ light: 2, switch: 2, weather: 1, screen: 1, lock: 0 });
    expect(roomCounts(base, "Garden")).toEqual([["Bedroom", 1], ["Garden", 0], ["Hall", 2], ["Kitchen", 1]]);
  });

  it("names an entity without its device in front, and says what it is and where", () => {
    const night = ENTRIES[9];
    expect(shortName(night)).toBe("Night mode");
    expect(shortName({ id: "light.x", name: "Bedroom screen", device: "Bedroom screen" })).toBe("Bedroom screen");
    expect(entryDetail(night, true, "")).toBe("Bedroom screen");
    expect(entryDetail(ENTRIES[4], false, "")).toBe(`${t("editor.domains.light")} · Kitchen`);
    expect(entryDetail(ENTRIES[0], true, "Bus")).toBe("Bus");
    expect(entryDetail(ENTRIES[1], true, "")).toBe("");
    expect([entryTone(ENTRIES[4]), entryTone(ENTRIES[5]), entryTone(ENTRIES[6])]).toEqual(["on", "gone", ""]);
  });
});
