// The settings several chosen tiles share (docs/PAGES.md, "Several tiles at once"). For each plain choice of a tile's
// inspector (TileInspector.vue, the same conditions): whether a tile offers it, with which choices, and what it has now.
// A setting is shared when every chosen tile offers it with the same choices, so three blinds of the same kind share
// what a blind can be set to, and a blind and a lamp only what any tile has. Its value is the one they all have, or
// none where they differ, and a pick writes it to every tile as one step of undo. What belongs to one tile alone stays
// in its own inspector: its name, its entity, the page a link goes to, and what is of one entity (a favourite, a map, a
// calendar, a to-do list, a meter, a template, a light's presets, the action to perform, a value on the second line).
import { t } from "../i18n";
import { inlineControlKind, pageTarget } from "../model/layout";
import rules from "../model/page-rules.json";
import { coverPrimary, coverTiltKind, hasCoverTilt, withCoverTilt } from "../model/tall-controls";
import { controlChoices, displayChoices, offeredChoices, roomHere, sliderOffered, subChoices, tapChoices, tileControls, tileDisplay, tiltOffered } from "../model/tile-options";
import type { IconName } from "../model/ui-icons";
import { useDocumentStore } from "../stores/document";
import { useEntitiesStore } from "../stores/entities";
import { useInventoryStore } from "../stores/inventory";
import { usePluginsStore } from "../stores/plugins";
import { useScreenStore } from "../stores/screen";
import type { Tile } from "../types";
import { setTileOption, tilePanel } from "./tiles";

export type SharedKind = "choice" | "switch" | "icon" | "background";
export type SharedSection = "look" | "controls" | "style";
type Choice = [string | number, string];
type Value = string | number | boolean;
/** One setting as one tile offers it. `text` names its value where that is none of the choices to pick from. */
type Offer = { section: SharedSection; kind: SharedKind; label: string; icon?: IconName; choices: Choice[]; value: Value; text?: string;
  write: (value: unknown, field: string) => void };
/** One setting the chosen tiles share. `value` is null where the tiles differ. */
export type SharedRow = Omit<Offer, "write" | "value"> & { key: string; value: Value | null };

/** What one tile offers, by the key of the setting, in the order of its inspector. */
function offersOf(tile: Tile): Map<string, Offer> {
  const out = new Map<string, Offer>();
  const inv = useInventoryStore(), scr = useScreenStore(), entities = useEntitiesStore(), plugins = usePluginsStore();
  // A plugin's tile has settings of its own, and a key under a bedside clock follows its clock: neither shares here.
  if (plugins.pluginTileOf(tile.entity) || tile.in !== undefined) return out;
  const domain = tile.entity.split(".")[0], panel = tilePanel(tile), catalogue = inv.inventory.controls?.[domain];
  const option = (key: string, fallback: unknown) => tile.options?.[key] ?? fallback;
  const offer = <T extends string | number>(key: string, choices: [T, string][], now: unknown) => offeredChoices(tile, key, choices, now, Boolean(catalogue));
  const set = (key: string, as: (value: unknown) => unknown = (value) => value) => (value: unknown, field: string) => setTileOption(tile, key, as(value), field);
  const add = (key: string, row: Omit<Offer, "text"> & { all?: Choice[] }) => {
    const { all, ...rest } = row;
    out.set(key, { ...rest, text: (all ?? row.choices).find(([choice]) => String(choice) === String(row.value))?.[1] });
  };
  const goesTo = pageTarget(tile.entity), bedside = tile.entity === "screen.nightstand", display = tileDisplay(tile);
  const lookShown = !goesTo && !bedside && (tile.entity !== "screen.settings" || display === "live" || domain === "sensor");

  // ---- What the card shows ----
  if ((lookShown || !bedside) && domain !== "calendar" && tile.entity !== "screen.text") {
    const energy = tile.entity === "screen.energy";
    if (lookShown && tile.entity !== "screen.settings" && tile.entity !== "screen.map" && !energy)
      add("display", { section: "look", kind: "choice", label: t("editor.tile.display.label"), icon: "eye-outline", choices: displayChoices(tile, panel), value: display, write: set("display") });
    if (!bedside && display !== "map" && !energy && !(display === "meter" && domain === "sensor")) {
      const sub = String(option("sub", "auto")), kind = sub.startsWith("attr:") ? "attr" : sub.startsWith("text:") ? "text" : sub;
      const all = subChoices(tile, panel, kind, (entities.subtitleValues[tile.entity] ?? []).length, sub.startsWith("attr:") ? sub.slice(5) : "");
      // A value of the entity and words of one's own are one tile's: shared are the screen's own line and none.
      const value = kind === "attr" || kind === "text" ? sub : kind;
      out.set("sub", { section: "look", kind: "choice", label: t("editor.tile.sub.label"), icon: "text-short", choices: all.filter(([choice]) => choice === "auto" || choice === "none"),
        value, text: all.find(([choice]) => choice === kind)?.[1], write: set("sub") });
    }
    if (lookShown && domain === "sensor") {
      const hours = Number(option("history_hours", 24));
      add("history_hours", { section: "look", kind: "choice", label: t("editor.tile.history.label"), icon: "clock-outline",
        choices: offer("history_hours", [1, 6, 24].map((n) => [n, t("editor.tile.history.hours", n)] as [number, string]), hours), value: hours, write: set("history_hours", Number) });
    }
    if (lookShown && display === "live") {
      const live = domain === "camera" && Boolean(scr.currentScreen?.live_camera), refresh = Number(option("refresh", live ? 0 : 15));
      add("refresh", { section: "look", kind: "choice", label: t("editor.tile.refresh.label"), icon: "refresh", value: refresh, write: set("refresh", Number),
        choices: offer("refresh", rules.refresh.filter((seconds) => seconds !== 0 || live)
          .map((seconds) => [seconds, seconds === 0 ? t("editor.tile.refresh.live") : t("editor.tile.refresh.seconds", { n: seconds })] as [number, string]), refresh) });
      for (const [key, icon] of [["fit", "resize"], ["overlay", "format-title"]] as const) {
        const now = String(option(key, rules.picture[key][0]));
        add(key, { section: "look", kind: "choice", label: t(`editor.tile.picture.${key}.label`), icon, value: now, write: set(key),
          choices: offer(key, rules.picture[key].map((value) => [value, t(`editor.tile.picture.${key}.${value}`)] as [string, string]), now) });
      }
    }
  }

  // ---- What a finger does to it ----
  const controls = tileControls(tile, panel, inlineControlKind(domain));
  const primary = domain === "cover" ? coverPrimary(controls) : controls, tilted = domain === "cover" && hasCoverTilt(controls);
  const slider = sliderOffered(tile, panel), controlsHere = Boolean(catalogue) && (String(option("size", "single")) !== "single" || roomHere(tile, panel));
  if (!goesTo && (domain !== "screen" || controlsHere || slider)) {
    if (domain !== "screen") {
      const tap = String(option("tap", "auto")), taps = tapChoices(tile, panel, tap, plugins.pluginsEnabled ? plugins.tapActionsFor(scr.currentScreen, domain) : []);
      // Perform action asks which action, and that is one tile's.
      add("tap", { section: "controls", kind: "choice", label: t("editor.tile.tap.label"), icon: "gesture-tap", choices: taps.filter(([choice]) => choice !== "action"), all: taps, value: tap, write: set("tap") });
    }
    if (domain === "lock") {
      const guard = String(option("guard", "confirm"));
      add("guard", { section: "controls", kind: "choice", label: t("editor.tile.guard.label"), icon: "check-circle", value: guard, write: set("guard"),
        choices: offer("guard", ["confirm", "lock_only"].map((key) => [key, t(`editor.tile.guard.${key}`)] as [string, string]), guard) });
    }
    const open = String(option("tilt_open", "100")), state = entities.liveOf(tile.entity);
    if (domain === "cover" && (open !== "100" || Boolean(state && coverTiltKind(state.state, state.a))))
      add("tilt_open", { section: "controls", kind: "choice", label: t("editor.tile.tilt_open.label"), icon: "sort-variant", value: open, write: set("tilt_open"),
        choices: offer("tilt_open", ["100", "50"].map((key) => [key, t(`editor.tile.tilt_open.${key}`)] as [string, string]), open) });
    if (controlsHere)
      add("controls", { section: "controls", kind: "choice", label: t("editor.tile.controls.label"), icon: "tune-variant", choices: controlChoices(tile, panel, controls), value: primary,
        write: set("controls", (value) => domain === "cover" ? withCoverTilt(String(value), tilted) : value) });
    if (tiltOffered(tile, panel, controls))
      add("tilt", { section: "controls", kind: "switch", label: t("editor.tile.controls.tilt"), choices: [], value: tilted, write: set("controls", (on) => withCoverTilt(primary, Boolean(on))) });
    if (slider)
      add("slider", { section: "controls", kind: "switch", label: t("editor.tile.slider.label"), choices: [], value: option("inline", "none") === "slider",
        write: set("inline", (on) => on ? "slider" : "none") });
  }

  // ---- Its icon and its colour ----
  if (Boolean(inv.inventory.icons) && (domain !== "screen" || goesTo > 0) && !["forecast", "sunpath"].includes(display))
    add("icon", { section: "style", kind: "icon", label: t("editor.icon.label"), icon: "tablet-dashboard", choices: [], value: String(option("icon", "auto")), write: set("icon") });
  const backgrounds = Object.entries(inv.inventory.backgrounds || {}).map(([key, choice]) => [key, choice.label] as [string, string]);
  if (backgrounds.length)
    add("background", { section: "style", kind: "background", label: t("editor.tile.background.label"), icon: "palette-outline", choices: backgrounds, value: String(option("background", "auto")), write: set("background") });
  return out;
}

/** The settings every one of `tiles` offers with the same choices, in the order of a tile's inspector. */
export function sharedRows(tiles: Tile[]): SharedRow[] {
  if (tiles.length < 2) return [];
  const each = tiles.map(offersOf), rows: SharedRow[] = [];
  for (const [key, first] of each[0]) {
    const offers = each.map((offers) => offers.get(key));
    if (!offers.every((offer) => offer && offer.kind === first.kind && JSON.stringify(offer.choices) === JSON.stringify(first.choices))) continue;
    const alike = offers.every((offer) => offer!.value === first.value);
    rows.push({ key, section: first.section, kind: first.kind, label: first.label, icon: first.icon, choices: first.choices, value: alike ? first.value : null, text: alike ? first.text : undefined });
  }
  return rows;
}

/** One shared setting written to every one of `tiles`, as one step of undo. */
export function setShared(tiles: Tile[], key: string, value: unknown) {
  const doc = useDocumentStore(), field = `shared:${key}`;
  // Edits of one field right after each other are one step (stores/document.ts applyEdit).
  doc.beginFieldEdit(field);
  for (const id of tiles.map((tile) => tile.id)) {
    // Read anew: the edit of the tile before made a new draft.
    const now = doc.layout?.tiles.find((item) => item.id === id);
    if (now) offersOf(now).get(key)?.write(value, field);
  }
  doc.endFieldEdit();
}
