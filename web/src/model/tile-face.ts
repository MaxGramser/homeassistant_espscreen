// Which face a card on the mockup takes, and the controls it draws, as the screens decide them (runtime_tiles render,
// render_tall, big_key, tile_controls::keys_for): a bedside clock, a plugin's tile, the energy diagram, a clock face, a
// graph, a favourite or a live picture, a Big number, a card over the whole page, a big key, a tall card, a wide card or
// the standard one. TileCard draws the face this names (components/tile/). Pure: what the card is, how large, what Home
// Assistant reports and what its screen's firmware draws come in; nothing is read from a store.
import { drawable } from "./catalogue";
import { inlineControlKind, pageTarget } from "./layout";
import { availableControl, controlKeys, coverPrimary, hasCoverTilt, type ControlKey } from "./tall-controls";
import type { Live } from "./tile-text";
import type { TileOptions } from "../types";

export type FaceKind = "bedside" | "plugin-live" | "plugin" | "energy" | "analog" | "dial" | "flip-wide" | "flip" | "digital" | "graph"
  | "favorite" | "camera" | "watch" | "full" | "big-key" | "tall" | "wide" | "standard";

export type FaceInput = {
  entity: string;
  options?: TileOptions;
  /** Columns and rows the card takes on its grid. */
  shape: { columns: number; rows: number };
  /** Over the whole page, or wider than a column (the whole page aside). */
  full: boolean;
  wide: boolean;
  live: Live | null | undefined;
  /** The control set the add-on sends for it (layout.ts effectiveControls). */
  chosen: string | null;
  /** The screen draws a thermostat's range on its -/+ (firmware 0.19.0+). */
  rangeReady: boolean;
  /** The screen's firmware is 0.17.0 or newer: big keys, the wide flip clock and a bedside clock's AM or PM. */
  bigKeys: boolean;
  /** A favourite with something to play (app 0.4.42). */
  favorite: boolean;
  /** A plugin's tile, and whether the add-on drew a row of it to show. */
  plugin: boolean;
  pluginRow: boolean;
  /** A Big number laid out on the glass (ui-scale watchCard); only a card of the editor's own screen in a cell has one. */
  watch: boolean;
};

export type Face = {
  kind: FaceKind;
  domain: string;
  /** The face chosen for it; a settings card is a plain card whatever it carries (GitHub #47). */
  display: string;
  full: boolean;
  wide: boolean;
  tall: boolean;
  /** A thermostat: a climate, or a humidifier drawn with its parts in percent (firmware 0.42.0+). */
  thermostat: boolean;
  /** A thermostat's modes under its -/+ on a card of two rows or more. */
  climateModes: boolean;
  /** A blind with slats, two rows or more: its slats beside its own control. */
  coverExtended: boolean;
  /** A tall card that only opens something: the settings, or a page. */
  tallAction: boolean;
  /** A tall card that only switches: one centred stack. */
  tallStack: boolean;
  bigKey: boolean;
  /** The control set the card draws beside its name (a wide card, the whole page), or null. */
  controls: string | null;
  /** The control under a tall card's head, '' for none. */
  tallControls: string;
  /** The keys of a tall card's control and of a wide or full card's, as the screen draws them for this entity. */
  tallKeys: ControlKey[];
  panelKeys: ControlKey[];
  /** A thermostat's modes as its mode bar, on a card of one row or the whole page. */
  modeBar: boolean;
  /** The control fills the content width of one cell (runtime_tiles::cell_content_width). */
  fillsCell: boolean;
};

// A card that only switches or only runs, two rows tall, is one big key (firmware 0.17.0 big_key).
const BIG_KEY_DOMAINS = ["light", "switch", "input_boolean", "fan", "script", "scene", "button", "input_button"];
// Controls whose keys are not a row of keys: a toggle, a -/+, a slider, a run key.
const NOT_KEYS = ["toggle", "setpoint", "volume", "run", "stepper", "slider", "brightness", "speed", "position"];
// The screens give a control that fills its room the content width of one cell, so its edges stand where the cards
// above and below have theirs; keys, a switch and a run key keep their own size.
const FILLS_CELL = ["brightness", "speed", "position", "slider", "volume", "setpoint", "mode"];
const CLOCK_FACES = ["dial", "flip", "digital"];

/** The display a card shows: a settings card stays a plain card, as the screen draws it. */
export const displayOf = (entity: string, options?: TileOptions) => (entity === "screen.settings" ? "standard" : String(options?.display || "standard"));

/** The control set the screen draws for this entity on this card (catalogue drawable): an older screen gets a thermostat
 * with only a range without its -/+, one without a temperature to set never has them; a card one row high draws the
 * setpoint alone (resolve_controls), and a blind its own control without its slats. */
export function drawnControls(domain: string, chosen: string | null, live: Live | null | undefined, rows: number, rangeReady: boolean) {
  const drawn = chosen ? drawable(domain, chosen, live?.a || {}, rangeReady ? null : new Set<string>()) : null;
  const selected = drawn === "none" ? null : drawn;
  if (selected === "setpoint_mode" && rows < 2) return "setpoint";
  if (domain !== "cover") return selected;
  const primary = coverPrimary(selected);
  return primary === "none" ? null : primary;
}

export function tileFace(input: FaceInput): Face {
  const { entity, options, shape, full, live, chosen } = input;
  const domain = entity.split(".")[0], display = displayOf(entity, options);
  const state = live?.state || "", a = live?.a || {};
  const wide = input.wide && !full;
  const thermostat = domain === "climate" || domain === "humidifier";
  const climateModes = thermostat && chosen === "setpoint_mode" && shape.rows > 1;
  const coverExtended = domain === "cover" && hasCoverTilt(chosen) && shape.rows > 1;
  const tall = shape.rows > 1 && (!full || coverExtended || climateModes) && ["standard", "cover"].includes(display);
  const goesTo = pageTarget(entity);
  const tallAction = tall && (entity === "screen.settings" || Boolean(goesTo));
  const controls = drawnControls(domain, chosen, live, shape.rows, input.rangeReady);
  const tallControls = availableControl(domain, options?.inline === "slider" ? inlineControlKind(domain) : controls, state, a, input.rangeReady);
  const tallStack = tall && tallControls === "toggle";
  const bigKey = tall && !full && input.bigKeys && BIG_KEY_DOMAINS.includes(domain) && options?.inline !== "slider"
    && (!tallControls || tallControls === "toggle" || tallControls === "run");
  const face: Omit<Face, "kind"> = {
    domain, display, full, wide, tall, thermostat, climateModes, coverExtended, tallAction, tallStack, bigKey, controls, tallControls,
    tallKeys: controlKeys(domain, tallControls, state, a),
    panelKeys: controls && !NOT_KEYS.includes(controls) ? controlKeys(domain, controls, state, a) : [],
    modeBar: thermostat && controls === "mode",
    fillsCell: FILLS_CELL.includes(controls || "") || (controls === "stepper" && !domain.endsWith("select")),
  };
  return { kind: faceKind(input, face), ...face };
}

// In the order the screen decides it: what replaces the name and its line first, then the card's own layouts.
function faceKind(input: FaceInput, face: Omit<Face, "kind">): FaceKind {
  const { entity, shape } = input, { domain, display } = face;
  if (entity === "screen.nightstand") return "bedside";
  if (input.plugin) return input.pluginRow ? "plugin-live" : "plugin";
  if (entity === "screen.energy") return "energy";
  if (display === "analog") return "analog";
  if (domain === "screen" && CLOCK_FACES.includes(display)) {
    // The flip clock on a card two columns wide and two rows tall, or a whole page (firmware 0.17.0): the blocks share
    // the width and the day and AM or PM stand on one line under them.
    if (display === "flip") return (face.full || (shape.columns > 1 && shape.rows > 1)) && input.bigKeys ? "flip-wide" : "flip";
    return display as FaceKind;
  }
  if (display === "graph" && domain === "sensor") return "graph";
  if (input.favorite && !face.full) return "favorite";
  if (display === "live" && ["camera", "image"].includes(domain)) return "camera";
  if (input.watch) return "watch";
  if (face.full && !face.tall) return "full";
  if (face.bigKey) return "big-key";
  if (face.tall) return "tall";
  if (face.wide) return "wide";
  return "standard";
}

const sameKeys = (a: ControlKey[], b: ControlKey[]) => a.length === b.length && a.every((key, i) =>
  key.icon === b[i].icon && key.primary === b[i].primary && key.disabled === b[i].disabled && key.mode === b[i].mode && key.cp === b[i].cp);
/** Whether two faces draw the same, so a card keeps the one it has when a report changes nothing of it. */
export function sameFace(a: Face, b: Face) {
  for (const key of Object.keys(a) as (keyof Face)[]) {
    if (key === "tallKeys" || key === "panelKeys") { if (!sameKeys(a[key], b[key])) return false; }
    else if (a[key] !== b[key]) return false;
  }
  return true;
}
