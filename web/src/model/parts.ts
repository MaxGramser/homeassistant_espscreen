// ---- Pages of parts (docs/PAGES.md, "Pages of parts"): one way for every page that holds many things ----
// The app's Settings, a screen's Settings tab and Events open on a list of their parts, the way Home Assistant's own
// Settings does: a few cards of rows, each row a part with its round coloured icon, its name and one line of what is set
// now, and a part opens as a page of its own with the way back to the list. The part is in the address, so a link, a
// reload and Back reach it. A page that grows gets one more part, never a longer page.
// The components are in components/parts/: PartsPage (a whole page), PartList (the cards of rows), PartLink (a row),
// PartHead (the head of an open part).
import type { IconName } from "./ui-icons";

/** The colours of the round icons: the --tone-* tokens of styles/tokens.css. */
export type Tone = "teal" | "cyan" | "blue" | "indigo" | "violet" | "green" | "orange" | "yellow" | "rose";

/** A part as its list shows it: its icon and colour, the card it stands in, its name, and one line of what is set now
 *  (a badge for news, such as updates waiting). */
export type PartRow<Id extends string = string> = {
  id: Id; icon: IconName; tone: Tone; card: number; title: string; summary?: string; badge?: string;
};

/** Parts in the cards of the list they stand in, in order; a card with none of them is left out. */
export function cardsOf<T extends { card: number }>(rows: readonly T[]): T[][] {
  const cards: T[][] = [];
  for (const row of rows) (cards[row.card] ||= []).push(row);
  return cards.filter(Boolean);
}
