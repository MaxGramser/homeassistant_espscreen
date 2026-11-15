// A first layout for a screen (docs/AUTO_LAYOUT.md): a whole pages-v2 document made from the home's own entities, for
// the person to undo or tweak in the editor. Pure: the inventory's entities, the facts of Home Assistant's registries
// (api/home-facts, screen_manager/app/home_facts.py), what Home Assistant says each candidate can do (api/capabilities)
// and what the screen takes go in; a layout and what it holds come out. tests: web/tests/auto-layout.spec.ts.
//
// It follows Home Assistant's own generated dashboards (the frontend's areas and home strategies): an entity with a
// category or hidden is left out, an area is a room in Home Assistant's order, a room's entities stand in its groups
// (lights, covers, climate, media, security, actions, others) in that order, and the house's own things (weather, the
// alarm, people, energy, cameras, the vacuum, lists, the calendar) stand together. A home without areas is grouped by the
// words its names share, then by device, then by kind. What a tile can show comes from the catalogue and the capabilities,
// never from a rule of this file: a richer control or display is only chosen where both say it is drawn.
import { t } from "../i18n";
import type { Capability, Entity, Page, PageGrid, PageLayout, PageTile, ScreenMemory, Section } from "../types";
import { controlOption, displayOption, drawable, fits, growOrder, ofType } from "./catalogue";
import { versionAtLeast } from "./layout";
import { pageCost, tileCost } from "./memory";
import { instanceId, SECTION_TITLE_BYTES, SECTIONS_MAX, copyBar, emptyPage } from "./pages";
import rules from "./page-rules.json";
import { sizeFor, sizesOn } from "./sizes";

// ---- What goes in ----

/** One entity as Home Assistant's registries know it (home_facts.facts). */
export type HomeFact = {
  id: string; area?: string; device?: string; category?: string; hidden?: boolean; platform?: string; class?: string;
  stateClass?: string; unit?: string; members?: string[]; screen?: boolean; features?: number;
};
export type HomeArea = { id: string; name: string; floor?: string; icon?: string; temperature?: string; humidity?: string };
export type HomeFacts = {
  entities: HomeFact[]; areas: HomeArea[]; floors: { id: string; name: string; level?: number | null }[];
  devices: Record<string, { name: string; area?: string; model?: string; maker?: string; service?: boolean }>;
};
/** What the screen takes, as the editor knows it (stores/screen.ts, the screen's hello). */
export type AutoScreen = {
  grid: { columns: number; rows: number };
  /** The pages and tiles it holds at most. */
  pages: number; tiles: number;
  /** The sizes its hello names (tile_sizes); left out, what its grid takes. */
  sizes?: string[];
  /** Its board draws sections (the full tier). */
  sections: boolean;
  /** The catalogue features it draws (catalogue.featuresOf): null for all. */
  features: Set<string> | null;
  pictures: boolean; liveCamera: boolean; todoLists: boolean;
  /** How many live camera tiles it streams at once (caps.live_tiles); left out, one. */
  liveTiles?: number;
  /** Its firmware's X.Y.Z, empty when not known yet (a new screen): nothing is held against it then. */
  firmware: string;
  memory?: ScreenMemory | null;
  /** The screen's own area by name: its room comes first and is Home. */
  area?: string;
  title: string;
  /** The top bar new pages take (the open document's first page's), else a Home key and the clock. */
  topbar?: Page["topbar"];
};
export type AutoInput = {
  entities: readonly Entity[]; facts: HomeFacts;
  capabilities: Record<string, Capability | null | undefined>;
  screen: AutoScreen;
  /** Entities left out: those already on the screen, when the pages go after its own. */
  exclude?: ReadonlySet<string>;
};
export type AutoResult = {
  layout: PageLayout;
  /** Tiles placed, sections made, the rooms they came from, and the candidates that found no room. */
  tiles: number; sections: number; rooms: number; leftOut: number;
};

// ---- Which entities, and how they group ----

/** The icons a section (and here a page) may take: the fixed set every screen carries (tile_icons.ICONS). */
export const ICONS: ReadonlySet<string> = new Set(rules.icons);

/** The groups of a room, in the order Home Assistant's area view shows them (areas/area-view-strategy.ts). */
export const ROOM_GROUPS = ["lights", "covers", "climate", "media", "security", "actions", "others"] as const;
/** The house's own groups, in the order its home page shows them. */
export const HOUSE_GROUPS = ["weather", "alarm", "people", "energy", "cameras", "vacuum", "todo", "calendar"] as const;
type Group = (typeof ROOM_GROUPS)[number] | (typeof HOUSE_GROUPS)[number];
/** Each group's icon, from the fixed set a section's icon is (tile_icons.ICONS; tests check every one is there). */
export const GROUP_ICONS: Record<Group, string> = {
  lights: "lightbulb-group", covers: "blinds", climate: "thermostat", media: "music", security: "shield-home", actions: "palette",
  others: "power-plug", weather: "weather-partly-cloudy", alarm: "shield-home", people: "home-account", energy: "flash",
  cameras: "cctv", vacuum: "robot-vacuum", todo: "script-text", calendar: "calendar",
};
const COVER_SENSORS = new Set(["door", "window", "garage_door", "opening"]);
const SAFETY_SENSORS = new Set(["smoke", "moisture", "gas", "carbon_monoxide", "safety"]);
const ROOM_SENSORS = new Set(["temperature", "humidity", "carbon_dioxide", "pm25"]);
// Meters of a whole house: the integrations of a smart meter, a home battery or solar panels.
const METER_PLATFORMS = new Set(["dsmr", "dsmr_reader", "p1_monitor", "homewizard", "tibber", "enphase_envoy", "solaredge", "growatt_server",
  "fronius", "sma", "powerwall", "youless", "slimmelezer", "energyzero", "easyenergy"]);

type Candidate = {
  id: string; domain: string; name: string; area: string; device: string; deviceName: string; maker: string; fact: HomeFact; entity: Entity;
  group: Group; house: boolean;
};

const domainOf = (id: string) => id.split(".")[0];
/** Whether the screen's firmware draws this type at all (the catalogue's `firmware`); an unknown firmware is not held against it. */
const typeDrawn = (domain: string, firmware: string) => {
  const type = ofType(domain);
  if (!type) return false;
  return !type.firmware || !firmware || versionAtLeast(firmware, type.firmware);
};

/** The group an entity stands in, or null when it is left out (Home Assistant's own filters, and what a wall wants). */
function groupOf(domain: string, fact: HomeFact, screen: AutoScreen): Group | null {
  const kind = fact.class ?? "";
  switch (domain) {
    case "light": return "lights";
    case "cover": return "covers";
    case "climate": case "humidifier": case "fan": return "climate";
    case "media_player": return "media";
    case "lock": return "security";
    case "scene": return "actions";
    case "switch": case "vacuum": return domain === "vacuum" ? "vacuum" : "others";
    case "alarm_control_panel": return "alarm";
    case "weather": return "weather";
    case "person": return "people";
    case "camera": return screen.pictures ? "cameras" : null;
    case "todo": return screen.todoLists ? "todo" : null;
    case "calendar": return "calendar";
    case "binary_sensor": return COVER_SENSORS.has(kind) ? "covers" : SAFETY_SENSORS.has(kind) ? "security" : null;
    case "sensor":
      if (ROOM_SENSORS.has(kind)) return "climate";
      return (kind === "power" || kind === "energy") ? "energy" : null;
    default: return null;
  }
}
// The groups that are the house's whatever room they are in.
const HOUSE_WIDE = new Set<Group>(["weather", "alarm", "people", "energy", "cameras", "vacuum", "todo", "calendar"]);
// What of a home of rooms may stand on the house's page without a room of its own.
const ROOMLESS = new Set(["light", "climate", "humidifier", "fan", "cover", "media_player", "lock", "scene"]);

/** Every entity worth a tile, with its group and its room: no category, not hidden, not a screen's own, not unavailable, a
 * type the screen draws. An entity without an area takes the area most of its group's members are in (a light group of a
 * room), else the area whose name its own name or its device's holds as a word ("LG Oled Living room"). */
export function candidates(input: AutoInput): Candidate[] {
  const facts = new Map(input.facts.entities.map((fact) => [fact.id, fact]));
  const areaWords = input.facts.areas.map((area) => ({ id: area.id, words: words(area.name).map(fold) })).filter((area) => area.words.length)
    .sort((a, b) => b.words.length - a.words.length);
  const named = (text: string) => {
    const own = words(text).map(fold);
    return areaWords.find((area) => own.some((_, i) => area.words.every((word, j) => own[i + j] === word)))?.id ?? "";
  };
  // Pictures of a weather integration (a rain radar) are the weather's, not a camera that watches the house.
  const weather = new Set(input.facts.entities.filter((fact) => fact.id.startsWith("weather.") && fact.platform).map((fact) => fact.platform));
  const out: Candidate[] = [];
  for (const entity of input.entities) {
    const fact = facts.get(entity.id), domain = domainOf(entity.id);
    if (!fact || input.exclude?.has(entity.id) || entity.tile === false || fact.category || fact.hidden || fact.screen || entity.id.startsWith("screen.")) continue;
    if (entity.state === "unavailable" || !typeDrawn(domain, input.screen.firmware)) continue;
    // A screen's own camera (screen_video.py's integration) is the screen itself.
    if (domain === "camera" && (fact.platform === "tessera_video" || weather.has(fact.platform))) continue;
    const group = groupOf(domain, fact, input.screen);
    if (!group) continue;
    const device = fact.device ?? "", known = input.facts.devices[device], deviceName = known?.name ?? entity.device ?? "";
    let area = fact.area ?? "";
    if (!area && fact.members?.length) {
      const counts = new Map<string, number>();
      for (const member of fact.members) { const where = facts.get(member)?.area; if (where) counts.set(where, (counts.get(where) ?? 0) + 1); }
      const [best, count] = [...counts.entries()].sort((a, b) => b[1] - a[1])[0] ?? ["", 0];
      if (count * 2 > fact.members.length) area = best;
    }
    // A room named in the name only places what stands on its own in a room (a lamp, a player, a camera), not a device's
    // switches ("Camera Living room Privacy").
    if (!area && (ROOMLESS.has(domain) || domain === "camera")) area = named(entity.name || "") || named(deviceName);
    out.push({ id: entity.id, domain, name: entity.name || entity.id, area, device, deviceName, maker: known?.maker ?? "", fact, entity, group, house: HOUSE_WIDE.has(group) });
  }
  return out;
}

// ---- Names ----

const fold = (text: string) => text.normalize("NFD").replace(/\p{M}/gu, "").toLocaleLowerCase();
const words = (text: string) => text.split(/[\s_\-:·,]+/).filter(Boolean);
const capital = (text: string) => text.charAt(0).toLocaleUpperCase() + text.slice(1);
/** A name without the words of `prefix` before it, or after it unless `front` ("Living room Lamp" in the living room is
 * "Lamp"), its first letter upper case; the name as it was where nothing would be left. */
export function strip(name: string, prefix: string, front = false): string {
  const own = words(name), cut = words(prefix);
  if (!cut.length || own.length <= cut.length) return name.trim();
  const same = (offset: number) => cut.every((word, i) => fold(own[offset + i]) === fold(word));
  let rest: string[] | null = null;
  if (same(0)) rest = own.slice(cut.length);
  else if (!front && same(own.length - cut.length)) rest = own.slice(0, own.length - cut.length);
  if (!rest?.length) return name.trim();
  return capital(rest.join(" "));
}
/** Text cut to a number of UTF-8 bytes, on a whole character. */
export function cutBytes(text: string, most: number) {
  const encoder = new TextEncoder();
  let out = text.trim();
  while (encoder.encode(out).length > most) out = [...out].slice(0, -1).join("");
  return out.trim();
}
const startsWith = (name: string, prefix: string) => {
  const own = words(name).map(fold), cut = words(prefix).map(fold);
  return cut.length > 0 && cut.length <= own.length && cut.every((word, i) => own[i] === word);
};
/** The label of a tile in its room or group (`context`), short and without the room's name, as Home Assistant names an
 * entity under its device: the device's name where the entity is the one of its device here and its name is the device's
 * with a word added ("Spot 1 Light" is "Spot 1"), else the entity's own part ("Bathroom Mirror" is "Mirror"). A name that
 * would say only a number or only the room keeps more: "Bathroom 1" stays, a player named after its room is its maker's
 * ("Sonos"), a room's light group "All lights". `alone`: no other entity of its device stands in the same group. */
export function labelOf(c: Pick<Candidate, "name" | "deviceName" | "maker" | "domain" | "fact">, context: string, alone = true) {
  const room = context ? fold(context) : "";
  const tidy = (text: string, whole: string) => {
    const short = context ? strip(text, context) : capital(text.trim());
    return /^\d+$/.test(short) || short.length < 2 ? capital(whole.trim()) : short;
  };
  let label = tidy(c.name, c.name);
  const part = c.deviceName && startsWith(c.name, c.deviceName) ? strip(c.name, c.deviceName, true) : c.name;
  if (c.deviceName && fold(c.deviceName) !== fold(c.name) && startsWith(c.name, c.deviceName))
    label = alone ? tidy(c.deviceName, c.deviceName) : tidy(part, c.name);
  if (room && fold(label) === room) {
    if (c.fact.members?.length && c.domain === "light") label = t("editor.auto.all_lights");
    else if (fold(part) !== fold(c.name) && fold(part) !== room) label = capital(part);
    else if (c.maker && c.maker.length <= 20) label = c.maker;
  }
  return cutBytes(capital(label), 80);
}

// ---- A tile's size and what it shows ----

type Planned = { candidate: Candidate; columns: number; rows: number; tile: Omit<PageTile, "id" | "placement">; rank: number };

/** How much a kind matters on a wall (Home Assistant's order of what an area shows first): a smaller rank stays when room
 * runs short. */
const RANKS: Record<string, number> = {
  alarm_control_panel: 0, climate: 0, light: 1, media_player: 1, weather: 1, cover: 2, lock: 2, vacuum: 2, humidifier: 2, fan: 2, camera: 2,
  todo: 2, calendar: 3, person: 3, switch: 3, sensor: 4, scene: 4, binary_sensor: 5,
};

type Room = { sizes: Set<string>; grid: { columns: number; rows: number }; level: "rich" | "roomy" | "plain" };
/** Whether the screen takes a rectangle: the grid has it and its hello names it. */
const takes = (room: Room, columns: number, rows: number) => {
  const size = sizeFor(columns, rows, room.grid as PageGrid);
  return size !== null && size !== "full" && room.sizes.has(size);
};
/** The first of the sizes wanted that the screen takes. */
const firstSize = (room: Room, wanted: [number, number][]) => wanted.find(([c, r]) => takes(room, c, r)) ?? [1, 1];

/** The richest control set the entity has, the screen draws and a card of this size fits: the catalogue's order of what a
 * growing tile gets first, then the type's other sets. */
function bestControls(c: Candidate, caps: Capability | null | undefined, columns: number, rows: number, screen: AutoScreen, room: Room, wanted: string[] = []) {
  if (!caps) return undefined;
  const size = sizeFor(columns, rows, room.grid as PageGrid) ?? "single";
  const attributes = c.fact.features !== undefined ? { supported_features: c.fact.features } : {};
  for (const key of [...wanted, ...growOrder(c.domain)]) {
    const item = controlOption(c.domain, key);
    if (!item || !caps.controls.includes(key) || !fits(item, size, room.grid.columns)) continue;
    if (item.screen?.firmware && screen.firmware && !versionAtLeast(screen.firmware, item.screen.firmware)) continue;
    if (drawable(c.domain, key, attributes, screen.features) !== key) continue;
    return key;
  }
  return undefined;
}
/** Whether a display is offered for the entity and drawn by the screen (firmware, pictures). */
function displayDrawn(c: Candidate, caps: Capability | null | undefined, key: string, screen: AutoScreen) {
  const item = displayOption(c.domain, key);
  if (!item || !caps?.displays.includes(key) || !(rules.displays as Record<string, string[]>)[c.domain]?.includes(key)) return false;
  if (item.screen?.pictures && !screen.pictures) return false;
  return !(item.screen?.firmware && screen.firmware && !versionAtLeast(screen.firmware, item.screen.firmware));
}

/** The sizes a kind's card may take, the first the screen takes winning: on a screen of four by four cells and more
 * (rich), on one of three by three (roomy). Only the first of its kind in a room or group gets a larger card, but a list
 * or a camera, which need the room whatever. */
const SIZES: Record<string, { rich: [number, number][]; roomy: [number, number][]; every?: boolean }> = {
  light: { rich: [[2, 2]], roomy: [[2, 1]] },
  climate: { rich: [[2, 2]], roomy: [[1, 2]] },
  humidifier: { rich: [[1, 2]], roomy: [[1, 2]] },
  media_player: { rich: [[2, 2]], roomy: [[2, 1]] },
  weather: { rich: [[2, 2], [2, 1]], roomy: [[2, 1]] },
  vacuum: { rich: [[3, 2], [2, 2]], roomy: [[2, 1]] },
  todo: { rich: [[2, 3], [2, 4], [1, 2]], roomy: [[1, 2]], every: true },
  calendar: { rich: [[2, 2], [2, 1]], roomy: [[2, 1]] },
  camera: { rich: [[2, 2]], roomy: [[2, 1]], every: true },
  alarm_control_panel: { rich: [[2, 2]], roomy: [] },
  sensor: { rich: [[2, 1]], roomy: [[2, 1]] },
};
/** The control sets a larger card of a kind asks for first; then the catalogue's order of what a growing tile gets. */
const CONTROLS: Record<string, string[]> = {
  light: ["brightness_presets"], climate: ["setpoint_mode"], humidifier: ["setpoint_mode"], media_player: ["playback"], vacuum: ["map_rooms", "map", "rooms"],
};

/** The tile an entity gets: on a screen with room, a larger card with more controls where that pays off (the light group
 * of a room, a thermostat, the first player, the weather, the vacuum, a list, a camera), else one cell. */
function plan(c: Candidate, label: string, input: AutoInput, room: Room, role: { first: boolean; others?: string[]; live?: boolean }): Planned {
  const caps = input.capabilities[c.id], screen = input.screen;
  const appearance: PageTile["appearance"] = { label }, interaction: PageTile["interaction"] = {};
  let [columns, rows] = [1, 1];
  const sizes = SIZES[c.domain], wanted = room.level === "plain" || !sizes ? [] : sizes[room.level];
  // Which entities of a kind get a larger card: a light group, the first thermostat or player, the house's meter.
  const larger = sizes && (sizes.every || role.first) && (c.domain !== "light" || Boolean(c.fact.members?.length))
    && (c.domain !== "sensor" || (c.group === "energy" && displayDrawn(c, caps, "graph", screen)));
  if (larger) [columns, rows] = firstSize(room, wanted);
  // The other players of a room keep their keys on a wide card where the screen is large.
  else if (c.domain === "media_player" && room.level === "rich") [columns, rows] = firstSize(room, [[2, 1]]);
  switch (c.domain) {
    case "media_player":
      // The album cover behind the first player where the screen draws pictures, its keys on the others.
      if (role.first && screen.pictures && displayDrawn(c, caps, "cover", screen)) appearance.display = "cover";
      else if (columns > 1) { const set = bestControls(c, caps, columns, rows, screen, room, CONTROLS.media_player); if (set) interaction.controls = set; }
      break;
    case "weather":
      // Its forecast takes two columns: a wide card where the screen has one (the editor's own start, layout.defaultOptions).
      if (room.level === "plain" && takes(room, 2, 1)) [columns, rows] = [2, 1];
      if (columns > 1 && displayDrawn(c, caps, "forecast", screen)) appearance.display = "forecast";
      else [columns, rows] = [1, 1];
      break;
    case "calendar":
      // The house's other calendars in the same card (firmware 0.56.0): one card, its events together.
      if (role.others?.length) appearance.calendarEntities = role.others.slice(0, rules.calendar.calendars);
      break;
    case "camera":
      // Live where the screen streams it, as many as it streams at once (its caps' live_tiles); a picture on the others.
      if (screen.liveCamera && role.live && displayDrawn(c, caps, "live", screen)) appearance.display = "live";
      break;
    case "sensor":
      if (columns > 1) { appearance.display = "graph"; appearance.historyHours = 24; }
      break;
    default:
      if (columns * rows > 1) { const set = bestControls(c, caps, columns, rows, screen, room, CONTROLS[c.domain] ?? []); if (set) interaction.controls = set; }
  }
  // The house's meter counts as much as a list; a room's other sensors less.
  const rank = c.group === "energy" ? 3 : RANKS[c.domain] ?? 5;
  return { candidate: c, columns, rows, tile: { content: { kind: "entity", entityId: c.id }, appearance, interaction }, rank };
}

// ---- Units: what becomes one section (or one page on a screen without sections) ----

/** `kind`: what shares a page. The house's own groups (and the screen's own room when it is small) stand together; a room
 * that fills most of a page stands on pages of its own, a section for each of its groups (`own`); the other rooms share
 * pages, a section each. `floor`: the room's floor, which names a page of several rooms of one floor. */
type Unit = { key: string; title: string; icon?: string; summary?: string; tiles: Planned[]; page: string; pageIcon?: string;
  kind: "house" | "own" | "room"; room: string; floor?: string };

const groupTitle = (group: Group) => t(`editor.auto.groups.${group}`);
const byName = (a: Candidate, b: Candidate) => a.name.localeCompare(b.name);
const areaIcon = (icon: string | undefined, allowed: ReadonlySet<string> = ICONS) => {
  const name = icon?.startsWith("mdi:") ? icon.slice(4) : undefined;
  if (!name) return undefined;
  if (allowed.has(name)) return name;
  // A close one of the fixed set: "bed-king" is a bed, "sofa-outline" a sofa.
  const base = name.replace(/-(outline|variant|king|double|single|empty|off)$/, "");
  return allowed.has(base) ? base : undefined;
};

/** A home without areas, or the entities left without one: clusters of what their names share (a word in front or at the
 * end that two or more names have, and not most of them), then of their device, then of their kind. */
export function clusters(list: Candidate[]): { title: string; members: Candidate[] }[] {
  const out: { title: string; members: Candidate[] }[] = [];
  let left = [...list];
  const count = new Map<string, { title: string; ids: Set<string>; domains: Set<string> }>();
  for (const c of left) {
    const own = words(c.name);
    if (own.length < 2) continue;
    for (const word of new Set([own[0], own.at(-1)!])) {
      const key = fold(word);
      if (key.length < 3 || /\d/.test(key)) continue;
      const found = count.get(key) ?? { title: word.charAt(0).toLocaleUpperCase() + word.slice(1), ids: new Set(), domains: new Set() };
      found.ids.add(c.id); found.domains.add(c.domain); count.set(key, found);
    }
  }
  const ranked = [...count.values()].filter((k) => k.ids.size >= 2 && k.ids.size <= Math.max(2, list.length * 0.4) && (k.domains.size >= 2 || k.ids.size <= 6))
    .sort((a, b) => b.domains.size - a.domains.size || b.ids.size - a.ids.size);
  for (const k of ranked) {
    const members = left.filter((c) => k.ids.has(c.id));
    if (members.length < 2) continue;
    out.push({ title: k.title, members });
    left = left.filter((c) => !k.ids.has(c.id));
  }
  const byDevice = new Map<string, Candidate[]>();
  for (const c of left) if (c.device && c.deviceName) byDevice.set(c.device, [...(byDevice.get(c.device) ?? []), c]);
  for (const members of byDevice.values()) {
    if (members.length < 2) continue;
    out.push({ title: members[0].deviceName, members });
    left = left.filter((c) => !members.includes(c));
  }
  for (const group of ROOM_GROUPS) {
    const members = left.filter((c) => c.group === group);
    if (members.length) out.push({ title: groupTitle(group), members });
  }
  return out;
}

/** The room's summary: the temperature Home Assistant shows for the area, else its first temperature sensor, else its
 * humidity. */
function summaryOf(area: HomeArea | undefined, members: Candidate[]) {
  const sensors = members.filter((c) => c.domain === "sensor");
  const known = new Set(sensors.map((c) => c.id));
  if (area?.temperature && known.has(area.temperature)) return area.temperature;
  return sensors.find((c) => c.fact.class === "temperature")?.id ?? (area?.humidity && known.has(area.humidity) ? area.humidity : undefined)
    ?? sensors.find((c) => c.fact.class === "humidity")?.id;
}

/** A room's tiles in Home Assistant's order of its groups, the big ones first; its climate sensors only where it has no
 * thermostat and nothing shows its temperature (a section's summary does). */
function roomTiles(members: Candidate[], context: string, input: AutoInput, room: Room, summary?: string) {
  // A group first (a room's light group), a speaker before a television (its album cover is the card's), then by name.
  const ordered = ROOM_GROUPS.flatMap((group) => members.filter((c) => c.group === group).sort((a, b) =>
    Number(Boolean(b.fact.members?.length)) - Number(Boolean(a.fact.members?.length))
    || Number(b.fact.class === "speaker") - Number(a.fact.class === "speaker") || byName(a, b)));
  // A thermostat shows the room's temperature, and so does a section's summary.
  const thermostat = members.some((c) => c.domain === "climate");
  const kept = ordered.filter((c) => c.domain !== "sensor" || (!thermostat && c.id !== summary));
  // A room's sensors as tiles: one of each kind at most.
  const seen = new Set<string>();
  const tiles = kept.filter((c) => {
    if (c.domain !== "sensor") return true;
    const kind = c.fact.class ?? "";
    if (seen.has(kind)) return false;
    seen.add(kind);
    return true;
  });
  const firsts = new Set<string>(), perDevice = new Map<string, number>();
  for (const c of tiles) if (c.device) perDevice.set(`${c.device}:${c.group}`, (perDevice.get(`${c.device}:${c.group}`) ?? 0) + 1);
  return tiles.map((c) => {
    const kind = c.domain === "light" && c.fact.members?.length ? "group" : c.domain;
    const first = !firsts.has(kind);
    firsts.add(kind);
    return plan(c, labelOf(c, context, (perDevice.get(`${c.device}:${c.group}`) ?? 0) <= 1), input, room, { first });
  }).sort((a, b) => b.columns * b.rows - a.columns * a.rows);
}

/** The house's own tiles, each group in its order: one weather, the alarm, the people, one power meter, the cameras, the
 * vacuum, the lists and one calendar card with the others in it. */
function houseUnits(list: Candidate[], input: AutoInput, room: Room, areaNames: Map<string, string>): Unit[] {
  const units: Unit[] = [];
  const home = t("editor.auto.home");
  for (const group of HOUSE_GROUPS) {
    let members = list.filter((c) => c.group === group).sort(byName);
    if (group === "weather") members = members.sort((a, b) => a.id.localeCompare(b.id)).slice(0, 1);
    if (group === "people") members = members.slice(0, 8);
    // A room's camera and a camera with a stream before a picture alone; two on a large screen, one elsewhere.
    if (group === "cameras") members = members.sort((a, b) => Number(Boolean(b.area)) - Number(Boolean(a.area)) || byName(a, b)).slice(0, room.level === "rich" ? 2 : 1);
    if (group === "energy") {
      // The house's meter: power before energy, one that belongs to no room (a meter, not a plug), a meter's integration first.
      // What the house takes, not what it gives back: an integration names it so in the entity's id.
      const score = (c: Candidate) => (c.fact.class === "power" ? 0 : 2) + (c.area ? 1 : 0) - (METER_PLATFORMS.has(c.fact.platform ?? "") ? 4 : 0)
        + (/produc|return|export|deliver/.test(c.id) ? 3 : 0) - (/consum|import|usage/.test(c.id) ? 1 : 0);
      members = members.filter((c) => !c.area || METER_PLATFORMS.has(c.fact.platform ?? "")).sort((a, b) => score(a) - score(b)).slice(0, 1);
    }
    if (group === "todo") members = members.slice(0, 2);
    if (!members.length) continue;
    let others: string[] = [];
    if (group === "calendar") { others = members.slice(1).map((c) => c.id); members = members.slice(0, 1); }
    const firsts = new Set<string>();
    // A person by the first name, where no one else of the house has it.
    const given = (c: Candidate) => fold(words(c.name)[0] ?? c.name);
    const firstNames = new Map<string, number>();
    for (const c of members) if (c.domain === "person") firstNames.set(given(c), (firstNames.get(given(c)) ?? 0) + 1);
    const tiles = members.map((c, index) => {
      const first = !firsts.has(c.domain);
      firsts.add(c.domain);
      // A camera or a vacuum keeps its room's name, which says where it looks or cleans.
      const where = c.area ? areaNames.get(c.area) ?? "" : "";
      // One calendar card with the others in it is the house's calendar.
      const label = group === "cameras" && where ? (members.filter((m) => m.area === c.area).length === 1 ? cutBytes(where, 80) : labelOf(c, where)) : group === "calendar" && others.length ? groupTitle("calendar")
        : c.domain === "person" && firstNames.get(given(c)) === 1 ? cutBytes(words(c.name)[0], 80) : labelOf(c, "");
      return plan(c, label, input, room, { first, others, live: index < (input.screen.liveTiles ?? 1) });
    });
    // The alarm and the cameras make the house's security: one section for both on a large screen.
    const title = groupTitle(group === "alarm" ? "security" : group);
    units.push({ key: `house:${group}`, title, icon: GROUP_ICONS[group], tiles, page: home, pageIcon: "home", kind: "house", room: home });
  }
  return units;
}

/** Every unit, in the order the pages take them: the screen's own room, the house, the rooms in Home Assistant's order
 * (by floor), then what has no area. */
function units(input: AutoInput, room: Room): { list: Unit[]; rooms: number } {
  const all = candidates(input);
  const areas = new Map(input.facts.areas.map((area) => [area.id, area]));
  const areaNames = new Map(input.facts.areas.map((area) => [area.id, area.name]));
  const floorOrder = new Map(input.facts.floors.map((floor, i) => [floor.id, i]));
  const areaOrder = [...input.facts.areas].map((area, i) => ({ area, i }))
    .sort((a, b) => (floorOrder.get(a.area.floor ?? "") ?? 1e3) - (floorOrder.get(b.area.floor ?? "") ?? 1e3) || a.i - b.i).map(({ area }) => area);
  const own = input.screen.area ? areaOrder.find((area) => fold(area.name) === fold(input.screen.area!)) : undefined;
  if (own) { areaOrder.splice(areaOrder.indexOf(own), 1); areaOrder.unshift(own); }
  const pageCells = room.grid.columns * room.grid.rows;
  const out: Unit[] = [];
  let rooms = 0;
  const floors = new Map(input.facts.floors.map((floor) => [floor.id, floor.name]));
  const addRoom = (key: string, name: string, members: Candidate[], area?: HomeArea, first = false) => {
    const summary = summaryOf(area, members);
    const tiles = roomTiles(members, name, input, room, input.screen.sections ? summary : undefined);
    if (!tiles.length) return;
    rooms++;
    const icon = areaIcon(area?.icon, ICONS), floor = area?.floor ? floors.get(area.floor) : undefined;
    const cells = tiles.reduce((sum, tile) => sum + tile.columns * tile.rows, 0);
    if (!input.screen.sections || cells <= pageCells * 0.6) {
      out.push({ key, title: name, icon, summary, tiles, page: name, pageIcon: icon, kind: first ? "house" : "room", room: key, floor });
      return;
    }
    // A room that fills most of a page: a section for each of its groups. A group of one small tile joins the others of
    // its kind under one title, or the group before it when it is the only one.
    let parts: { group: Group; tiles: Planned[] }[] = ROOM_GROUPS.map((group) => ({ group, tiles: tiles.filter((tile) => tile.candidate.group === group) })).filter((part) => part.tiles.length);
    const small = (part: { tiles: Planned[] }) => part.tiles.length === 1 && part.tiles[0].columns * part.tiles[0].rows === 1;
    const singles = parts.filter(small);
    if (singles.length >= 2) parts = [...parts.filter((part) => !singles.includes(part)), { group: "others", tiles: singles.flatMap((part) => part.tiles) }];
    else if (singles.length === 1 && parts.length > 1) {
      const at = parts.indexOf(singles[0]), host = parts[at > 0 ? at - 1 : 1];
      host.tiles = [...host.tiles, ...singles[0].tiles];
      parts = parts.filter((part) => part !== singles[0]);
    }
    const climate = parts.some((part) => part.group === "climate");
    for (const part of parts) {
      out.push({ key: `${key}:${part.group}`, title: groupTitle(part.group), icon: GROUP_ICONS[part.group], tiles: part.tiles, page: name, pageIcon: icon,
        summary: part.group === "climate" || (part === parts[0] && !climate) ? summary : undefined, kind: "own", room: key, floor });
    }
  };
  const roomless = all.filter((c) => !c.house && !areas.has(c.area));
  const withRooms = new Set(all.filter((c) => !c.house && areas.has(c.area)).map((c) => c.area)).size >= 2;
  if (own) addRoom(own.id, own.name, all.filter((c) => !c.house && c.area === own.id), own, true);
  out.push(...houseUnits(all.filter((c) => c.house), input, room, areaNames));
  if (withRooms) {
    // A home of rooms: what has none is the house's, its lights, climate, players, covers, locks and scenes by kind (as Home
    // Assistant's home page shows them), the rest (a device's own switches and sensors) left to the library.
    const home = t("editor.auto.home");
    for (const group of ROOM_GROUPS) {
      const members = roomless.filter((c) => c.group === group && ROOMLESS.has(c.domain)).slice(0, group === "actions" ? 6 : 12);
      const tiles = roomTiles(members, "", input, room);
      if (tiles.length) out.push({ key: `house:${group}`, title: groupTitle(group), icon: GROUP_ICONS[group], tiles, page: home, pageIcon: "home", kind: "house", room: home });
    }
  }
  for (const area of areaOrder) if (area !== own) addRoom(area.id, area.name, all.filter((c) => !c.house && c.area === area.id), area);
  if (!withRooms) for (const cluster of clusters(roomless)) addRoom(`cluster:${cluster.title}`, cluster.title, cluster.members);
  return { list: out, rooms };
}

// ---- Packing ----

type Place = { tile: Planned; row: number; column: number };
/** Tiles in reading order into `columns` columns from the top, each at the first place it fits. */
function pack(tiles: Planned[], columns: number) {
  const taken = new Set<string>(), places: Place[] = [];
  let height = 0;
  for (const tile of tiles) {
    const w = Math.min(tile.columns, columns);
    for (let row = 0; ; row++) {
      let column = -1;
      for (let c = 0; c + w <= columns && column < 0; c++) {
        let free = true;
        for (let y = row; y < row + tile.rows && free; y++) for (let x = c; x < c + w; x++) if (taken.has(`${y}:${x}`)) { free = false; break; }
        if (free) column = c;
      }
      if (column < 0) continue;
      for (let y = row; y < row + tile.rows; y++) for (let x = column; x < column + w; x++) taken.add(`${y}:${x}`);
      places.push({ tile, row, column });
      height = Math.max(height, row + tile.rows);
      break;
    }
  }
  return { places, rows: height };
}
type Shape = { columns: number; rows: number; places: Place[]; waste: number };
/** The shapes a unit's block may take on a grid: each width its tiles fit, the rows they then take. */
function shapes(unit: Unit, grid: { columns: number; rows: number }): Shape[] {
  const widest = Math.max(...unit.tiles.map((tile) => tile.columns));
  const area = unit.tiles.reduce((sum, tile) => sum + tile.columns * tile.rows, 0);
  const out: Shape[] = [];
  for (let columns = Math.min(widest, grid.columns); columns <= grid.columns; columns++) {
    const { places, rows } = pack(unit.tiles, columns);
    if (rows <= grid.rows && !out.some((shape) => shape.rows === rows)) out.push({ columns, rows, places, waste: columns * rows - area });
  }
  return out;
}
/** A unit cut into parts that each fit a page: the tiles in reading order on the page's width, a page high each. */
function split(unit: Unit, grid: { columns: number; rows: number }): Unit[] {
  if (shapes(unit, grid).length) return [unit];
  const parts: Unit[] = [];
  let current: Planned[] = [];
  for (const tile of unit.tiles) {
    if (current.length && pack([...current, tile], grid.columns).rows > grid.rows) { parts.push({ ...unit, tiles: current }); current = []; }
    current.push(tile);
  }
  if (current.length) parts.push({ ...unit, tiles: current });
  return parts.map((part, i) => ({ ...part, key: `${unit.key}:${i}` }));
}

type Block = { unit: Unit; row: number; column: number; shape: Shape };
type Sheet = { blocks: Block[]; taken: Set<string> };
const freeAt = (sheet: Sheet, row: number, column: number, shape: { columns: number; rows: number }, grid: { columns: number; rows: number }) => {
  if (row + shape.rows > grid.rows || column + shape.columns > grid.columns) return false;
  for (let y = row; y < row + shape.rows; y++) for (let x = column; x < column + shape.columns; x++) if (sheet.taken.has(`${y}:${x}`)) return false;
  return true;
};
/** Where a unit goes on a page: the first free place in reading order for any of its shapes, the least waste there. */
function placeOn(sheet: Sheet, unit: Unit, grid: { columns: number; rows: number }): Block | null {
  const options = shapes(unit, grid);
  for (let row = 0; row < grid.rows; row++) for (let column = 0; column < grid.columns; column++) {
    const fitting = options.filter((shape) => freeAt(sheet, row, column, shape, grid)).sort((a, b) => a.waste - b.waste || b.columns - a.columns);
    if (fitting.length) return { unit, row, column, shape: fitting[0] };
  }
  return null;
}
const claim = (sheet: Sheet, block: Block) => {
  sheet.blocks.push(block);
  for (let y = block.row; y < block.row + block.shape.rows; y++) for (let x = block.column; x < block.column + block.shape.columns; x++) sheet.taken.add(`${y}:${x}`);
};
/** A page's blocks grown a little, so the panels line up: each as low as the tallest block beside it (a shelf), then into a
 * gap of one column or one row that no block could fill. Their tiles laid out again on the width they have now. */
function grow(sheet: Sheet, grid: { columns: number; rows: number }) {
  const free = (y: number, x: number) => y >= 0 && x >= 0 && y < grid.rows && x < grid.columns && !sheet.taken.has(`${y}:${x}`);
  const take = (cells: [number, number][]) => { for (const [y, x] of cells) sheet.taken.add(`${y}:${x}`); };
  const right = (b: Block) => Array.from({ length: b.shape.rows }, (_, i) => [b.row + i, b.column + b.shape.columns] as [number, number]);
  const below = (b: Block) => Array.from({ length: b.shape.columns }, (_, i) => [b.row + b.shape.rows, b.column + i] as [number, number]);
  const ordered = [...sheet.blocks].sort((a, b) => a.row - b.row || a.column - b.column);
  // A shelf: one row lower where the block beside it, at the same top, is one row lower.
  for (const block of ordered) {
    const shelf = Math.max(...sheet.blocks.filter((other) => other.row === block.row).map((other) => other.row + other.shape.rows));
    if (shelf === block.row + block.shape.rows + 1 && below(block).every(([y, x]) => free(y, x))) {
      take(below(block)); block.shape = { ...block.shape, rows: block.shape.rows + 1 };
    }
  }
  // A gap of one column to the right or one row below that stays empty otherwise.
  for (const block of ordered) {
    const column = right(block);
    if (column.every(([y, x]) => free(y, x)) && column.every(([y, x]) => !free(y, x + 1))) { take(column); block.shape = { ...block.shape, columns: block.shape.columns + 1 }; }
    const row = below(block);
    if (row.every(([y, x]) => free(y, x)) && row.every(([y, x]) => !free(y + 1, x))) { take(row); block.shape = { ...block.shape, rows: block.shape.rows + 1 }; }
  }
  for (const block of ordered) {
    const again = pack(block.unit.tiles, block.shape.columns);
    if (again.rows <= block.shape.rows) block.shape = { ...block.shape, places: again.places };
  }
}

/** Pages of sections: each unit at the first free place of its page, a few later ones of the same kind pulled forward to
 * fill a page before the next begins; a room of its own on pages of its own. */
function sectionSheets(list: Unit[], grid: { columns: number; rows: number }) {
  type Sheet2 = { sheet: Sheet; units: Unit[]; kind: Unit["kind"]; room: string };
  const sheets: Sheet2[] = [];
  const queue = list.flatMap((unit) => split(unit, grid));
  const same = (page: Sheet2, unit: Unit) => page.kind === unit.kind && (unit.kind !== "own" || page.room === unit.room);
  let current: Sheet2 | null = null;
  const room = (page: Sheet2) => page.sheet.blocks.length < SECTIONS_MAX;
  const deferred = new Set<Unit>();
  // What is left of a room's page takes the house's own groups that fit there, the largest first (the weather beside a
  // room, as a person would put it).
  const area = (unit: Unit) => unit.tiles.reduce((n, x) => n + x.columns * x.rows, 0);
  const close = () => {
    if (!current) return;
    const page: Sheet2 = current;
    if (page.kind !== "house")
      for (const next of queue.filter((item) => item.kind === "house" && item.key.startsWith("house:") && HOUSE_WIDE.has(item.key.split(":")[1] as Group))
        .sort((a, b) => area(b) - area(a))) {
        const fits = room(page) ? placeOn(page.sheet, next, grid) : null;
        if (!fits) continue;
        claim(page.sheet, fits);
        page.units.push(next);
        queue.splice(queue.indexOf(next), 1);
      }
    grow(page.sheet, grid);
    sheets.push(page);
    current = null;
  };
  while (queue.length) {
    const unit = queue[0];
    // Closing a page may take house groups out of the queue for its holes: then look at the queue's head again.
    if (current && !same(current, unit)) { close(); continue; }
    if (!current) current = { sheet: { blocks: [], taken: new Set() }, units: [], kind: unit.kind, room: unit.room };
    const block = room(current) ? placeOn(current.sheet, unit, grid) : null;
    if (block) { claim(current.sheet, block); current.units.push(unit); queue.shift(); continue; }
    // A later unit of the same kind that fits fills the page first (at most four ahead).
    const page: Sheet2 = current;
    const ahead = queue.slice(1, 5).findIndex((next) => same(page, next) && room(page) && placeOn(page.sheet, next, grid));
    if (ahead >= 0) {
      const next = queue.splice(ahead + 1, 1)[0];
      claim(page.sheet, placeOn(page.sheet, next, grid)!);
      page.units.push(next);
      continue;
    }
    if (!current.sheet.blocks.length) { queue.shift(); continue; }
    // The house's groups that find no room on its page wait for the holes of the rooms' pages, and get a page of their
    // own only when none takes them.
    if (page.kind === "house" && !deferred.has(unit)) {
      const later = queue.filter((item) => item.kind === "house");
      later.forEach((item) => deferred.add(item));
      queue.splice(0, queue.length, ...queue.filter((item) => item.kind !== "house"), ...later);
    }
    close();
  }
  close();
  return sheets.map((page) => ({ sheet: page.sheet, ...titleOf(page.units) }));
}
/** A page's title and icon from its units: its first one's for the house and a room of its own; for rooms sharing a page
 * their names ("Kitchen & Hall"), their floor's when there are more of one floor, else the first and how many more. */
function titleOf(units: Unit[]): { title: string; icon?: string } {
  const first = units[0];
  if (first.kind !== "room") return { title: first.page, icon: first.pageIcon };
  const rooms = units.filter((unit) => unit.kind === "room"), names = [...new Set(rooms.map((unit) => unit.page))];
  if (names.length === 1) return { title: names[0], icon: first.pageIcon };
  if (names.length === 2) return { title: t("editor.auto.two_rooms", { a: names[0], b: names[1] }) };
  const floors = new Set(rooms.map((unit) => unit.floor));
  if (floors.size === 1 && first.floor) return { title: first.floor };
  const all = t("editor.auto.room_list", { list: names.slice(0, -1).join(", "), last: names.at(-1) });
  return { title: all.length <= 40 ? all : t("editor.auto.more_rooms", { a: names[0], n: names.length - 1 }) };
}

/** Pages of plain tiles (no sections): a room or group on a page of its own, continued on the next where it runs over;
 * rooms that each fill little share a page when the screen has fewer pages than rooms. */
function plainSheets(list: Unit[], grid: { columns: number; rows: number }, pages: number) {
  type Plain = { title: string; icon?: string; places: Place[]; rooms: string[] };
  // A unit's tiles: the house's groups together on its own pages, every other unit on its own.
  const merged: Unit[] = [];
  for (const unit of list) {
    const last = merged.at(-1);
    if (last && last.room === unit.room) last.tiles = [...last.tiles, ...unit.tiles];
    else merged.push({ ...unit, tiles: [...unit.tiles] });
  }
  // A room that runs a tile or two onto a page of its own, where the screen has fewer pages than that takes: those last
  // tiles, the least wanted of it, go to the library instead.
  const cells = grid.columns * grid.rows, size = (tiles: Planned[]) => tiles.reduce((n, tile) => n + tile.columns * tile.rows, 0);
  let dropped = 0;
  if (merged.reduce((n, unit) => n + Math.ceil(size(unit.tiles) / cells), 0) > pages)
    for (const unit of merged) {
      const over = size(unit.tiles) % cells;
      if (size(unit.tiles) <= cells || over === 0 || over > Math.max(1, Math.floor(cells / 3))) continue;
      const worst = [...unit.tiles].map((tile, i) => ({ tile, i })).sort((a, b) => b.tile.rank - a.tile.rank || b.i - a.i);
      let freed = 0;
      const gone = new Set<Planned>();
      for (const { tile } of worst) { if (freed >= over) break; gone.add(tile); freed += tile.columns * tile.rows; }
      unit.tiles = unit.tiles.filter((tile) => !gone.has(tile));
      dropped += gone.size;
    }
  let out: Plain[] = merged.flatMap((unit) => split({ ...unit, tiles: unit.tiles }, grid).map((part) => ({
    title: unit.page, icon: unit.pageIcon, places: pack(part.tiles, grid.columns).places, rooms: [unit.room] })));
  // Too many pages: two neighbouring pages whose tiles fit one page become one, the smallest pair first.
  while (out.length > pages) {
    let best = -1, least = Infinity;
    for (let i = 0; i + 1 < out.length; i++) {
      const tiles = [...out[i].places, ...out[i + 1].places].map((place) => place.tile);
      const fit = pack(tiles, grid.columns).rows <= grid.rows;
      if (fit && tiles.length < least) { best = i; least = tiles.length; }
    }
    if (best < 0) break;
    const a = out[best], b = out[best + 1];
    const names = [...new Set([a.title, b.title])];
    const title = names.length === 1 ? names[0] : t("editor.auto.two_rooms", { a: names[0], b: names[1] });
    out = [...out.slice(0, best), { title, icon: names.length === 1 ? a.icon : undefined, places: pack([...a.places, ...b.places].map((p) => p.tile), grid.columns).places,
      rooms: [...a.rooms, ...b.rooms] }, ...out.slice(best + 2)];
  }
  return { sheets: out, dropped };
}

// ---- Room on the screen: tiles, pages, memory ----

/** The candidates' planned tiles trimmed to what the screen holds: its tile ceiling and its memory, the least wanted
 * (largest rank, latest) going first; a rich card that costs too much becomes a plain one before it goes. */
function trim(list: Unit[], screen: AutoScreen, pages: number, cells: number) {
  const all = list.flatMap((unit) => unit.tiles.map((tile, order) => ({ unit, tile, order })));
  const memory = screen.memory && screen.memory.room !== null && screen.memory.room !== undefined ? screen.memory : null;
  const cost = (tile: Planned) => memory ? tileCost({ entity: tile.candidate.id, options: {} }, memory) : 0;
  const budget = memory ? (memory.room ?? 0) * 0.9 - pages * pageCost({ topbar: { trailing: [] } }, memory) : Infinity;
  // Cells: a page leaves room unused around sections; aim at three quarters of them.
  const room = cells * 0.75;
  let kept = all.slice();
  // Some room left for what the person adds: about one tile in seven of the screen's ceiling stays free.
  const ceiling = screen.tiles - Math.min(Math.round(screen.tiles * 0.15), Math.max(0, screen.tiles - 1));
  const over = () => kept.length > ceiling || kept.reduce((sum, item) => sum + cost(item.tile), 0) > budget
    || kept.reduce((sum, item) => sum + item.tile.columns * item.tile.rows, 0) > room;
  const index = new Map(all.map((item, i) => [item, i]));
  while (kept.length && over()) {
    // The least wanted: the largest rank, then the latest unit.
    const drop = kept.reduce((worst, item) => item.tile.rank > worst.tile.rank || (item.tile.rank === worst.tile.rank && index.get(item)! > index.get(worst)!) ? item : worst);
    kept = kept.filter((item) => item !== drop);
  }
  const left = all.length - kept.length;
  const keep = new Set(kept.map((item) => item.tile));
  return { list: list.map((unit) => ({ ...unit, tiles: unit.tiles.filter((tile) => keep.has(tile)) })).filter((unit) => unit.tiles.length), left };
}

const tileOf = (place: Place, offset = { row: 0, column: 0 }): PageTile => ({
  id: instanceId(), ...JSON.parse(JSON.stringify(place.tile.tile)),
  placement: { row: place.row - offset.row, column: place.column - offset.column, columns: place.tile.columns, rows: place.tile.rows },
});
function pageWith(title: string, icon: string | undefined, input: AutoInput): Page {
  const page = emptyPage(input.screen.topbar ? copyBar(input.screen.topbar) : undefined);
  const text = cutBytes(title, 96);
  page.topbar.title = text ? { source: "text", text } : { source: "screen" };
  if (icon && ICONS.has(icon)) page.icon = icon;
  return page;
}

/** The first layout for a screen: every room, the house and what has no room, as the screen's grid, sizes, sections,
 * memory and limits take them. */
export function autoLayout(input: AutoInput): AutoResult {
  const grid = input.screen.grid;
  const level = Math.min(grid.columns, grid.rows) >= 4 ? "rich" : Math.min(grid.columns, grid.rows) >= 3 ? "roomy" : "plain";
  const room: Room = { grid, sizes: new Set(input.screen.sizes?.length ? input.screen.sizes : sizesOn(grid)), level };
  // Sections where the board draws them and a page has room for more than one: three by three cells and up.
  const sectioned = input.screen.sections && level !== "plain";
  const made = units({ ...input, screen: { ...input.screen, sections: sectioned } }, room);
  const pagesMax = Math.max(1, input.screen.pages);
  const { list, left } = trim(made.list, input.screen, pagesMax, pagesMax * grid.columns * grid.rows);
  const pages: Page[] = [];
  let leftOut = left, sections = 0;
  if (sectioned) {
    for (const sheet of sectionSheets(list, grid)) {
      if (pages.length >= pagesMax) { leftOut += sheet.sheet.blocks.reduce((sum, block) => sum + block.unit.tiles.length, 0); continue; }
      const page = pageWith(sheet.title, sheet.icon, input);
      page.sections = sheet.sheet.blocks.sort((a, b) => a.row - b.row || a.column - b.column).map((block): Section => ({
        id: instanceId(), title: cutBytes(block.unit.title, SECTION_TITLE_BYTES) || "·",
        ...(block.unit.icon && ICONS.has(block.unit.icon) ? { icon: block.unit.icon } : {}),
        ...(block.unit.summary ? { summary: block.unit.summary } : {}),
        placement: { row: block.row, column: block.column, columns: block.shape.columns, rows: block.shape.rows },
        tiles: block.shape.places.map((place) => tileOf(place)),
      }));
      sections += page.sections.length;
      pages.push(page);
    }
  } else {
    const plain = plainSheets(list, grid, pagesMax);
    leftOut += plain.dropped;
    for (const sheet of plain.sheets) {
      if (pages.length >= pagesMax) { leftOut += sheet.places.length; continue; }
      const page = pageWith(sheet.title, sheet.icon, input);
      page.tiles = sheet.places.map((place) => tileOf(place));
      pages.push(page);
    }
  }
  if (!pages.length) pages.push(pageWith("", undefined, input));
  const tiles = pages.reduce((sum, page) => sum + page.tiles.length + (page.sections ?? []).reduce((n, s) => n + s.tiles.length, 0), 0);
  return { layout: { title: input.screen.title, homePageId: pages[0].id, pages }, tiles, sections, rooms: made.rooms, leftOut };
}

/** The pages of a first layout after the pages a screen has (made with what the screen still takes): Home stays where it was. */
export function appendPages(current: PageLayout, made: PageLayout): PageLayout {
  const added = made.pages.filter((page) => page.tiles.length || page.sections?.length);
  return { ...current, pages: [...current.pages, ...added] };
}
