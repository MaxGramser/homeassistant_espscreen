/** How a sensor tile looks when it is added (docs/METER.md, "The first look"): a number that goes up and down starts as
 * a meter, with the look and the range that suit what it measures, so nobody has to find the meter to see it. A
 * percentage is a ring from 0 to 100, a battery a bar of cells, a temperature a tape over the range of a room, any other
 * number a bar over a round range around its value now. A counter (an energy meter's kWh, a total), a sensor whose state
 * is no number, and a screen without the meter (firmware older than 0.56.0) keep the plain value.
 * The looks a new sensor is offered (LookTip) are the meter's three, its graph, the large value and the plain value, each with the same
 * range. Pure: what Home Assistant reports and what the screen's firmware draws come in. */
import type { TileOptions } from "../types";
import { suggestRange } from "./meter";

export type SensorFacts = { state?: string | null; a?: Record<string, unknown> | null };
export type Supports = (major: number, minor: number, patch: number) => boolean;
export type LookKey = "ring" | "tape" | "bar" | "graph" | "watch" | "standard";
export const LOOK_KEYS: LookKey[] = ["ring", "tape", "bar", "graph", "watch", "standard"];

// What only grows: a meter of it would fill and stay full (Home Assistant's SensorStateClass).
const COUNTERS = new Set(["total", "total_increasing"]);
// A room's temperature: a tape over it reads like a thermometer on the wall.
const ROOM = { "°C": [10, 30], "°F": [50, 86] } as Record<string, [number, number]>;

const numberOf = (state: unknown) => {
  if (typeof state !== "string" || !state.trim()) return null;
  const value = Number(state);
  return Number.isFinite(value) ? value : null;
};

/** The range a sensor's meter starts with: none for a percentage (Home Assistant's 0 to 100), a room's temperatures
 * widened to hold the value, else a round range around the value. */
export function startRange(facts: SensorFacts): [number, number] | null {
  const value = numberOf(facts.state), unit = String(facts.a?.unit_of_measurement ?? "");
  if (value === null || unit === "%") return null;
  const room = facts.a?.device_class === "temperature" ? ROOM[unit] : undefined;
  if (room) {
    const step = 5;
    return [Math.min(room[0], Math.floor(value / step) * step), Math.max(room[1], Math.ceil(value / step) * step)];
  }
  return suggestRange(value);
}

/** The look a sensor starts with as a meter (ring, tape or bar), or null when it keeps the plain value. */
export function startMeter(entity: string, facts: SensorFacts | null | undefined, supports: Supports): "ring" | "tape" | "bar" | null {
  if (!entity.startsWith("sensor.") || !facts || !supports(0, 56, 0)) return null;
  const a = facts.a ?? {}, unit = a.unit_of_measurement, kind = a.device_class;
  // A number Home Assistant draws as one: a unit or a state class, and a state that is a number now.
  if (numberOf(facts.state) === null || (typeof unit !== "string" && typeof a.state_class !== "string")) return null;
  if (typeof a.state_class === "string" && COUNTERS.has(a.state_class)) return null;
  if (kind === "battery") return "bar";
  if (kind === "temperature") return "tape";
  if (unit === "%") return "ring";
  return "bar";
}

/** The options a look sets on the tile, the range kept across the meter's looks so moving between them loses nothing. */
export function lookOptions(look: LookKey, range: [number, number] | null): TileOptions {
  if (look === "graph" || look === "watch" || look === "standard") return { display: look };
  // The ring is the meter's own default, which the add-on never stores (meter.validate): the tile leaves it out.
  return { display: "meter", ...(look === "ring" ? {} : { meter: look }), ...(range ? { min: range[0], max: range[1] } : {}) };
}

/** The options a new sensor tile starts with, or none. */
export function startLook(entity: string, facts: SensorFacts | null | undefined, supports: Supports): TileOptions | null {
  const meter = startMeter(entity, facts, supports);
  return meter ? lookOptions(meter, startRange(facts!)) : null;
}

/** Which of the looks a tile wears now. */
export function lookOf(options: TileOptions | undefined): LookKey {
  const display = options?.display;
  if (display === "meter") return (["ring", "tape", "bar"].includes(String(options?.meter)) ? options!.meter : "ring") as LookKey;
  return display === "graph" || display === "watch" ? display : "standard";
}
