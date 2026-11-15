// The room a page's sections take from the cards inside them (docs/PAGES.md "Sections", model/sections.ts): DevicePage
// provides it, a card and an empty cell take their margins from it, so the mockup lays a page out with sections the way
// the glass does (module_sections.h place). The page's rows stay what they are. Without a page around it (the overview,
// a card carried in a drag), a card stands in its plain cell.
import { inject, type ComputedRef, type InjectionKey } from "vue";

export type CellMargins = { left: number; right: number; top: number; bottom: number };
export type SectionGrid = {
  // The margins, in glass pixels, of a card of `columns` x `rows` at (`column`, `row`) of the page: the panel's padding at
  // a section's sides, and the header and padding its section takes from its rows (negative where a card reaches into
  // the gap below its cell).
  margins(column: number, row: number, columns: number, rows: number): CellMargins;
  // Whether a card there stands in a section whose tiles follow its contrast: drawn in the other look.
  otherLook(column: number, row: number, columns: number, rows: number): boolean;
  // Whether a card there stands in a contrast section whose tiles keep their own look: its hairline is the other look's
  // line, the one that sets it off from that panel (module_sections.h stands_out).
  standsOut(column: number, row: number, columns: number, rows: number): boolean;
};
export const NO_MARGINS: CellMargins = { left: 0, right: 0, top: 0, bottom: 0 };
export const PLAIN_GRID: SectionGrid = { margins: () => NO_MARGINS, otherLook: () => false, standsOut: () => false };
export const SECTION_GRID: InjectionKey<ComputedRef<SectionGrid>> = Symbol("section-grid");
export const useSectionGrid = () => inject(SECTION_GRID, null);
