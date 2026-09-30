/** A tile's options as the add-on keeps them, and which choices the inspector may offer (app 0.4.0, GitHub #47).
 *
 * The add-on refuses a page document whose options its own normalizer would still change
 * (page_layout.validate_document: "Tile options need normalization"). So the editor stores the canonical form,
 * and a choice is offered only when the tile, with that choice applied the way the editor applies it, still passes
 * the same card check the save runs (validateCardOptions). Both ask here, so a choice that shows is a choice that saves.
 */
import rules from "./page-rules.json";
import { validateCardOptions } from "./page-validation";
import type { PageTile, Tile, TileOptions } from "../types";

const APPEARANCE = { display: "display", icon: "icon", background: "background", historyHours: "history_hours", refresh: "refresh", subtitle: "sub", fit: "fit", overlay: "overlay" } as const;
const INTERACTION = ["tap", "inline", "controls", "action"] as const;
const PICTURE_OWN = ["refresh", ...Object.keys(rules.picture)];
const TALLER = ["tall", "square"];
// What a choice that asks a second step stands for while the inspector tries it: Perform action asks which action,
// a value of the entity which value, words of your own the words. The step itself is checked when it is taken.
const SAMPLE_ACTION = { action: "homeassistant.turn_on" };
// The value an option means when it is not stored, where the add-on drops the stored one (core.validate_layout).
export const DEFAULTS: Record<string, unknown> = { sub: "auto", fit: rules.picture.fit[0], overlay: rules.picture.overlay[0] };

const pageTile = (entity: string) => /^screen\.page_\d+$/.test(entity);

/** Mirrors core.validate_layout's normalization, so the document the editor saves is already canonical. */
export function canonicalOptions(entity: string, options: TileOptions = {}, key = false): TileOptions {
  const out: TileOptions = { ...options };
  if (typeof out.sub === "string" && out.sub.startsWith("text:")) {
    const words = out.sub.slice(5).trim();
    out.sub = words ? `text:${words}` : "none";
  }
  if (out.sub === "auto") delete out.sub;
  // Perform action keeps its action; another tap choice leaves none behind.
  if (out.tap !== "action") delete out.action;
  // A live picture's pace and fill belong to the live picture, and their defaults are not stored. A bedside clock's key
  // keeps whether its name shows (`overlay`, firmware 0.17.0), as a picture does.
  if (out.display !== "live") for (const field of PICTURE_OWN) if (!(key && field === "overlay")) delete out[field];
  for (const [key, value] of Object.entries(DEFAULTS)) if (out[key] === value) delete out[key];
  // A Go to page tile has a name, an icon, a colour and a width, nothing else.
  if (pageTile(entity)) for (const key of ["display", "inline", "controls", "history_hours"]) delete out[key];
  if (rules.wideOnly.includes(String(out.display)) && !["wide", "square", "full"].includes(String(out.size ?? "single"))) out.size = "wide";
  return out;
}

/** What else changes with one choice, as the inspector applies it: a watch face has no slider or controls, a slider
 * no controls, direct controls the standard face. `controlled`: the domain has direct controls at all. */
export function coupledOptions(options: TileOptions = {}, key: string, value: unknown, controlled: boolean): TileOptions {
  const out: TileOptions = { ...options, [key]: value };
  const size = String(out.size ?? "single");
  if (key === "display" && value === "watch") { out.inline = "none"; if (controlled) out.controls = "none"; }
  if (key === "inline" && value === "slider") { out.display = "standard"; if (controlled) out.controls = "none"; }
  if (key === "controls" && value === "none" && TALLER.includes(size)) out.inline = "none";
  if (key === "controls" && value !== "none") { if (out.display !== "cover") out.display = "standard"; out.inline = "none"; }
  // Choosing an action is choosing Perform action.
  if (key === "action") out.tap = "action";
  return out;
}

/** The card the add-on checks, built from a tile and a set of options. */
function cardOf(tile: Tile, options: TileOptions): PageTile {
  const appearance: PageTile["appearance"] = { label: tile.name };
  for (const [key, wire] of Object.entries(APPEARANCE)) if (options[wire] !== undefined) Object.assign(appearance, { [key]: options[wire] });
  const interaction: PageTile["interaction"] = {};
  for (const key of INTERACTION) if (options[key] !== undefined) Object.assign(interaction, { [key]: options[key] });
  const content: PageTile["content"] = pageTile(tile.entity) ? { kind: "navigation", target: { kind: "home" } }
    : tile.entity === "screen.clock" || tile.entity === "screen.nightstand" || tile.entity === "screen.settings" ? { kind: "builtin", name: tile.entity.slice(7) as "clock" | "nightstand" | "settings" }
    : { kind: "entity", entityId: tile.entity };
  return { id: tile.id || "trial", content, appearance, interaction, placement: { row: 0, column: 0, columns: 1, rows: 1 } };
}

/** Whether the add-on would save a tile with these options as they are. */
export function optionsSave(tile: Tile, options: TileOptions): boolean {
  try {
    validateCardOptions(cardOf(tile, options), tile.entity, String(options.size ?? "single"));
    return true;
  } catch {
    return false;
  }
}

/** Whether the inspector may offer `value` for `key`: applied as the inspector applies it, the tile still saves and the
 * choice is still there (a default the add-on drops counts as there). A choice with a second step is tried with a
 * sample of that step. */
export function choiceOffered(tile: Tile, key: string, value: unknown, controlled: boolean): boolean {
  let options = canonicalOptions(tile.entity, coupledOptions(tile.options, key, value, controlled), tile.in !== undefined);
  if (key === "tap" && value === "action" && !options.action) options = { ...options, action: tile.options?.action ?? SAMPLE_ACTION };
  if (!optionsSave(tile, options)) return false;
  const kept = options[key];
  return JSON.stringify(kept) === JSON.stringify(value) || (kept === undefined && DEFAULTS[key] === value);
}

/** The choices of one field the inspector may show: those `choiceOffered` allows, and the one the tile has now, so a
 * stored choice never disappears from sight. */
export function offeredChoices<T extends string | number>(tile: Tile, key: string, choices: [T, string][], current: unknown, controlled: boolean,
  sample: (value: T) => unknown = (value) => value): [T, string][] {
  return choices.filter(([value]) => value === current || choiceOffered(tile, key, sample(value), controlled));
}
