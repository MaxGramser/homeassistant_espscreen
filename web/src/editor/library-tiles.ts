// The library's shelf (components/LibraryShelf.vue, docs/PAGES.md "The library"): an entity shown as the tiles it can be
// on this screen, at up to three sizes, each as rich as the screen draws it there. The shelf shows one of them, the size
// that suits its type best or the one the person chose, and the card that opens over it shows them all. A click or a
// drag puts that very tile on the page. What a size may hold comes from the catalogue and the add-on's rules, as everywhere else in
// the editor (model/tile-options.ts): this file only chooses among what they offer. Tested by library-tiles.test.ts.
import { canonicalOptions, controlSets, displayChoices, optionsSave } from "../model/tile-options";
import { controlParts, growOrder, resolveControls, shelfOf, showcaseOf } from "../model/catalogue";
import { dimensions } from "../model/layout";
import { presetsOf, starterPresets } from "../model/light-presets";
import type { ShelfView } from "../model/library";
import type { Size } from "../model/sizes";
import { useDocumentStore } from "../stores/document";
import { useEntitiesStore } from "../stores/entities";
import type { Tile } from "../types";
import { startTile, tilePanel, tileSizeChoices } from "./tiles";

/** One tile the library offers: the tile as it lands, its cells, and the controls it draws ("none" for none). */
export type Sample = { size: Size; tile: Tile; columns: number; rows: number; controls: string };

// The three sizes an entity is shown at, smallest first: one cell, a row of two, and two rows of two. A screen whose grid
// has no 2 x 2 shows the tall one instead, and a size the screen or the type does not take is left out.
const SHOWN: Size[][] = [["single"], ["wide"], ["square", "tall"]];

/** The tiles an entity can be on this screen, at the sizes the library shows. */
export function samplesOf(id: string): Sample[] {
  const start = startTile(id), offered = tileSizeChoices(start), { grid } = useDocumentStore().editorLayout;
  const first = (start.options?.size as Size | undefined) ?? "single";
  const sample = (size: Size, tile: Tile): Sample => ({ size, tile, ...dimensions(size, grid), controls: resolveControls(tile) ?? "none" });
  const samples: Sample[] = [];
  for (const choices of SHOWN) {
    const size = choices.find((choice) => offered.includes(choice));
    if (size) samples.push(sample(size, richest(start, size)));
  }
  // A tile that starts larger than a cell (a calendar, the energy card, a plugin's) is offered at that size too. Not the
  // whole page: that is the inspector's choice, and it would stand larger than the page beside it.
  if (!samples.some((item) => item.size === first) && offered.includes(first) && first !== "full") samples.push(sample(first, start));
  return samples;
}

const STEP: Record<Exclude<ShelfView, "best">, number> = { small: 0, wide: 1, large: 2 };
const stepOf = (size: Size) => SHOWN.findIndex((choices) => choices.includes(size));
/** The size the shelf's three steps stand for on this screen, for the words of their keys: a grid without a 2 x 2 has
 * the tall one as its largest. */
export function shelfSizes(): Size[] {
  const { grid } = useDocumentStore().editorLayout;
  return [SHOWN[0][0], SHOWN[1][0], grid.columns >= 2 && grid.rows >= 2 ? "square" : "tall"];
}
/** The one tile of `samples` the shelf shows. Best: the size its type names (catalogue `shelf`), else the size the tile
 * starts at (a bedside clock and the energy card start at two rows, and are drawn for that). A chosen size: that size, and where the entity does not take it the largest it takes under it, so nothing
 * leaves the shelf for the size it is shown at. An entity that only comes larger stands at its smallest. */
export function shelfSample(samples: Sample[], view: ShelfView, entity: string, start?: Size): Sample | undefined {
  if (!samples.length) return undefined;
  const wanted = view === "best" ? (shelfOf(entity.split(".")[0]) ?? start ?? "single") : null;
  if (wanted) {
    const exact = samples.find((item) => item.size === wanted);
    if (exact) return exact;
  }
  const step = wanted ? stepOf(wanted) : STEP[view as Exclude<ShelfView, "best">];
  // A size outside the three steps (a calendar's own, the energy card's) has no step: it stands as it starts.
  if (step < 0) return samples[samples.length - 1];
  for (let at = step; at >= 0; at--) {
    const match = samples.find((item) => stepOf(item.size) === at);
    if (match) return match;
  }
  return samples[0];
}
/** The tile the shelf shows of an entity, for the key that adds what is in focus (Library.vue). */
export function shelfTile(id: string, view: ShelfView): Tile | undefined {
  return shelfSample(samplesOf(id), view, id, startTile(id).options?.size as Size | undefined)?.tile;
}

/** The tile at a size as rich as the screen draws it there: from two cells up the face its type is shown in (catalogue
 * `showcase`: a sensor's curve, a player's cover), and of the control sets that fit, the one with the most parts (a
 * light's brightness with its presets, a thermostat's temperature with its modes), the type's `grow` order between
 * equals. Each step is kept only where the add-on saves it. */
export function richest(start: Tile, size: Size): Tile {
  const domain = start.entity.split(".")[0];
  const options = { ...start.options, size } as NonNullable<Tile["options"]>;
  if (size === "single") delete options.size;
  let tile: Tile = { ...start, options };
  if (size === ((start.options?.size as Size | undefined) ?? "single")) tile = start;
  const panel = tilePanel(tile), face = showcaseOf(domain);
  if (face && size !== "single" && displayChoices(tile, panel).some(([key]) => key === face)) {
    const shown: Tile = { ...tile, options: canonicalOptions(start.entity, { ...tile.options, display: face }, false) };
    if (saves(shown, size)) tile = shown;
  }
  const sets = controlSets(tile, panel, size);
  if (!sets.length || !["standard", "cover"].includes(String(tile.options?.display ?? "standard"))) return tile;
  const order = growOrder(domain), rank = (key: string) => { const at = order.indexOf(key); return at < 0 ? order.length : at; };
  const controls = [...sets].sort((a, b) => controlParts(domain, b).length - controlParts(domain, a).length || rank(a) - rank(b))[0];
  const rich: Tile = { ...tile, options: { ...tile.options, controls } };
  // Direct controls take the standard face without the small slider (tile-options.ts coupledOptions).
  delete rich.options!.inline;
  // A light's presets come with a first set that suits it, so the tile shows them (model/light-presets.ts).
  if (controlParts(domain, controls).includes("presets") && !presetsOf(rich.options).length)
    rich.options!.presets = starterPresets(useEntitiesStore().liveOf(start.entity)) as never;
  return saves(rich, size) ? rich : tile;
}

// Whether the add-on takes the tile at this size as it is: the library never offers a tile the save would refuse.
const saves = (tile: Tile, size: Size) => optionsSave(tile, { ...tile.options, ...(size === "single" ? {} : { size }) });
