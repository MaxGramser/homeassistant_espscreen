// Fake homes for the first layout's tests (auto-layout.spec.ts): one with areas and floors, as Home Assistant reports it.
import type { Capability, Entity, ScreenMemory } from "../src/types";
import type { AutoScreen, HomeFact, HomeFacts } from "../src/model/auto-layout";
import { controlKeys, displayKeys } from "../src/model/catalogue";

export type Thing = Partial<Entity> & Partial<HomeFact> & { id: string; name: string };
/** A home: its entities as the inventory and the registries give them, and what Home Assistant says each can do. */
export function home(things: Thing[], areas: HomeFacts["areas"] = [], floors: HomeFacts["floors"] = []) {
  const entities: Entity[] = things.map(({ id, name, state = "on", device: _d, ...rest }) => ({ id, name, state, area: areas.find((a) => a.id === rest.area)?.name ?? "", ...(rest.tile === false ? { tile: false } : {}) }));
  const facts: HomeFacts = {
    entities: things.map(({ id, area, device, category, hidden, platform, class: kind, stateClass, unit, members, screen, features }) =>
      ({ id, area, device, category, hidden, platform, class: kind, stateClass, unit, members, screen, features })),
    areas, floors,
    devices: Object.fromEntries(things.filter((t) => t.device).map((t) => [t.device!, { name: t.device!.replace(/^d-/, "").replace(/_/g, " ") }])),
  };
  // Home Assistant offers every control and display of the catalogue, as for an entity that supports them all.
  const capabilities: Record<string, Capability> = Object.fromEntries(things.map((t) => {
    const domain = t.id.split(".")[0];
    return [t.id, { toggle: true, inline: true, controls: controlKeys(domain), displays: displayKeys(domain) }];
  }));
  return { entities, facts, capabilities };
}

export const AREAS: HomeFacts["areas"] = [
  { id: "living", name: "Living room", floor: "ground", icon: "mdi:sofa", temperature: "sensor.living_room_temperature" },
  { id: "kitchen", name: "Kitchen", floor: "ground", icon: "mdi:silverware-fork-knife" },
  { id: "bedroom", name: "Bedroom", floor: "first", icon: "mdi:bed-king" },
  { id: "bathroom", name: "Bathroom", floor: "first", icon: "mdi:shower" },
  { id: "hall", name: "Hall", floor: "ground" },
  { id: "garden", name: "Garden" },
];
export const FLOORS = [{ id: "ground", name: "Ground floor", level: 0 }, { id: "first", name: "First floor", level: 1 }];
export const HOUSE: Thing[] = [
  // The living room: a light group with its lamps, two players, an airco, its temperature and humidity.
  { id: "light.living_room", name: "Living room", area: "living", members: ["light.living_room_ceiling", "light.living_room_table"] },
  { id: "light.living_room_ceiling", name: "Living room Ceiling", area: "living" },
  { id: "light.living_room_table", name: "Living room Table lamp", area: "living" },
  { id: "light.spot_1", name: "Spot 1", area: "living" },
  { id: "light.spot_2", name: "Spot 2", area: "living" },
  { id: "media_player.sonos_living", name: "Sonos Living room", area: "living", class: "speaker" },
  { id: "media_player.apple_tv", name: "Apple TV", area: "living", class: "tv" },
  { id: "climate.airco", name: "Living room Airco", area: "living", features: 395 },
  { id: "sensor.living_room_temperature", name: "Living room Temperature", area: "living", class: "temperature", unit: "°C" },
  { id: "sensor.living_room_humidity", name: "Living room Humidity", area: "living", class: "humidity", unit: "%" },
  { id: "binary_sensor.balcony_door", name: "Balcony door", area: "living", class: "door" },
  // The kitchen.
  { id: "light.kitchen", name: "Kitchen", area: "kitchen", members: ["light.kitchen_spot", "light.kitchen_counter"] },
  { id: "light.kitchen_spot", name: "Kitchen spot", area: "kitchen" },
  { id: "light.kitchen_counter", name: "Kitchen counter", area: "kitchen" },
  { id: "switch.coffee", name: "Coffee machine", area: "kitchen" },
  { id: "sensor.kitchen_temperature", name: "Kitchen temperature", area: "kitchen", class: "temperature" },
  // The bedroom, the bathroom, the hall.
  { id: "light.bedroom", name: "Bedroom ceiling", area: "bedroom" },
  { id: "cover.curtains", name: "Curtains", area: "bedroom" },
  { id: "media_player.sonos_bedroom", name: "Bedroom Sonos", area: "bedroom" },
  { id: "sensor.bedroom_temperature", name: "Bedroom temperature", area: "bedroom", class: "temperature" },
  { id: "light.bath_1", name: "Bathroom Spot 1", area: "bathroom" },
  { id: "light.bath_mirror", name: "Mirror", area: "bathroom" },
  { id: "light.hall", name: "Hall", area: "hall" },
  // The house: weather, the alarm, people, the meter, a camera, the vacuum, a list, two calendars.
  { id: "weather.home", name: "Home" },
  { id: "weather.other", name: "Other forecast" },
  { id: "alarm_control_panel.house", name: "Alarm" },
  { id: "person.ann", name: "Ann" }, { id: "person.ben", name: "Ben" },
  { id: "sensor.power_consumption", name: "Power consumption", class: "power", stateClass: "measurement", platform: "dsmr" },
  { id: "sensor.plug_power", name: "Plug power", area: "kitchen", class: "power" },
  { id: "camera.garden", name: "Garden camera", area: "garden" },
  { id: "vacuum.robot", name: "Robbie", area: "living" },
  { id: "todo.shopping_list", name: "Shopping list" },
  { id: "calendar.family", name: "Family" }, { id: "calendar.birthdays", name: "Birthdays" },
  // Noise: what no wall wants.
  { id: "sensor.lamp_signal", name: "Lamp signal", area: "living", class: "signal_strength", category: "diagnostic" },
  { id: "switch.lamp_led", name: "Lamp LED", area: "living", category: "config" },
  { id: "light.hidden_one", name: "Hidden", area: "living", hidden: true },
  { id: "light.broken", name: "Broken", area: "living", state: "unavailable" },
  { id: "switch.hall_screen_backlight", name: "Hall screen Backlight", area: "hall", screen: true },
  { id: "automation.morning", name: "Morning" }, { id: "script.bedtime", name: "Bedtime" },
  { id: "button.restart", name: "Restart" }, { id: "input_number.target", name: "Target" },
  { id: "sensor.phone_battery", name: "Phone battery", class: "battery" },
  { id: "binary_sensor.motion", name: "Hall motion", area: "hall", class: "motion" },
];
export const NOISE = ["sensor.lamp_signal", "switch.lamp_led", "light.hidden_one", "light.broken", "switch.hall_screen_backlight", "automation.morning",
  "script.bedtime", "button.restart", "input_number.target", "sensor.phone_battery", "binary_sensor.motion", "weather.other", "sensor.plug_power"];

export const memory = (room: number, psram = true): ScreenMemory => ({ room, used: 0, psram, tile: 64, extra: 96, page: 32 });
export const TEN: AutoScreen = { grid: { columns: 5, rows: 5 }, pages: 8, tiles: 64, sections: true, features: null, pictures: true, liveCamera: true,
  todoLists: true, firmware: "0.61.0", memory: memory(4_000_000), title: "Hall", area: "Living room" };
export const MIDDLE: AutoScreen = { ...TEN, grid: { columns: 3, rows: 3 }, area: undefined, liveCamera: false };
export const CYD: AutoScreen = { grid: { columns: 2, rows: 3 }, pages: 8, tiles: 48, sections: false, features: new Set(), pictures: false, liveCamera: false,
  todoLists: false, firmware: "0.61.0", memory: memory(14_000, false), title: "Kitchen" };


/** A busier home, shaped like real ones: light groups and scenes without an area whose members have one, a player and a
 * camera named after their room, a camera's own switches, plugs with their meters, a screen's own camera, a rain radar,
 * many scenes and people. */
export const BUSY: Thing[] = [
  ...HOUSE,
  { id: "light.lounge_group", name: "Living room", members: ["light.living_room_ceiling", "light.living_room_table", "light.spot_1"] },
  { id: "scene.evening", name: "Evening", members: ["light.living_room_ceiling", "light.spot_2"] },
  { id: "media_player.lg_oled", name: "LG Oled Living room" },
  { id: "camera.front", name: "Camera Living room", device: "d-cam" },
  { id: "switch.cam_privacy", name: "Camera Living room Privacy", device: "d-cam" },
  { id: "switch.cam_ir", name: "Camera Living room Infrared", device: "d-cam" },
  { id: "camera.hall_screen_video", name: "Hall screen Video", platform: "tessera_video" },
  { id: "camera.rain_radar", name: "Rain radar", platform: "radar_weather" },
  { id: "weather.radar", name: "Radar forecast", platform: "radar_weather" },
  { id: "climate.attic", name: "Attic heat pump" },
  { id: "switch.boiler", name: "Boiler Switch", area: "bathroom", device: "d-boiler" },
  { id: "sensor.boiler_power", name: "Boiler Power", area: "bathroom", device: "d-boiler", class: "power" },
  { id: "light.spot_3", name: "Spot 3 Light", area: "living", device: "d-spot_3" },
  ...["Morning", "Movie", "Dinner", "Reading", "Party", "Night", "Away"].map((name) => ({ id: `scene.${name.toLowerCase()}`, name })),
  ...["Cleo Smith", "Dan Smith", "Eve Jones"].map((name) => ({ id: `person.${name.split(" ")[0].toLowerCase()}`, name })),
];
