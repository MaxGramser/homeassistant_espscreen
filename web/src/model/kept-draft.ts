// A screen's unsaved draft as this browser keeps it (stores/drafts.ts), so work survives a reload, a closed tab or a
// browser that crashed: the layout, its grid and the way it hangs, the revision of the saved layout it started from, when
// it was last changed and which tab wrote it. Kept in localStorage under esp-screens.draft.<screen>, which the editor
// shares with Home Assistant inside its iframe, so a draft is written without spaces, one screen's at a time, and goes
// after two weeks or when more than a few screens keep one. Pure: what is read is checked here, the reading and writing
// is the store's.
import type { PageGrid, PageLayout } from "../types";
import { clockText, dateText } from "./topbar";

export type KeptDraft = {
  v: 1;
  /** The tab that wrote it (stores/drafts.ts), so another tab's draft is never taken away by this one. */
  tab: string;
  /** The saved layout's revision the draft started from; another one means the screen was saved since. */
  revision: string | null;
  /** When the draft was last changed (ms). */
  at: number;
  layout: PageLayout;
  grid: { columns: number; rows: number };
  upright: boolean | null;
};

export const KEPT_PREFIX = "esp-screens.draft.";
/** A draft older than this is forgotten. */
export const KEPT_MS = 14 * 86400000;
/** The most screens whose drafts are kept; the oldest goes first. */
export const KEPT_SCREENS = 8;
export const keptKey = (screen: string) => `${KEPT_PREFIX}${screen}`;

const isGrid = (grid: unknown): grid is PageGrid => Boolean(grid) && typeof grid === "object" &&
  Number.isInteger((grid as PageGrid).columns) && Number.isInteger((grid as PageGrid).rows);
const isLayout = (layout: unknown): layout is PageLayout => Boolean(layout) && typeof layout === "object" &&
  typeof (layout as PageLayout).title === "string" && typeof (layout as PageLayout).homePageId === "string" && Array.isArray((layout as PageLayout).pages);

/** A kept draft from its text, or null for one that does not read as one (another version, a hand-edited value). */
export function readKept(raw: string | null): KeptDraft | null {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw);
    if (value?.v !== 1 || typeof value.tab !== "string" || typeof value.at !== "number" || !isLayout(value.layout) || !isGrid(value.grid)) return null;
    if (value.revision !== null && typeof value.revision !== "string") return null;
    return { v: 1, tab: value.tab, revision: value.revision, at: value.at, layout: value.layout, grid: { columns: value.grid.columns, rows: value.grid.rows },
      upright: typeof value.upright === "boolean" ? value.upright : null };
  } catch { return null; }
}
export const writeKept = (draft: KeptDraft) => JSON.stringify(draft);
export const staleKept = (draft: { at: number }, now: number) => now - draft.at > KEPT_MS;

/** The keys to forget among `kept` (key, time): the stale ones, and past the most screens kept the oldest, leaving room
 * for `room` more. */
export function keptToForget(kept: { key: string; at: number | null }[], now: number, room = 0): string[] {
  const gone = kept.filter((item) => item.at === null || staleKept({ at: item.at }, now)).map((item) => item.key);
  const left = kept.filter((item) => !gone.includes(item.key)).sort((a, b) => b.at! - a.at!);
  return [...gone, ...left.slice(Math.max(0, KEPT_SCREENS - room)).map((item) => item.key)];
}

/** When a draft was last changed, as the editor says it: the time today, else the day and the time. */
export function keptWhen(at: number, now: number, clock24: boolean, locale: string) {
  const then = new Date(at), today = new Date(now);
  const time = clockText(clock24, then, clock24 ? undefined : locale);
  return then.toDateString() === today.toDateString() ? time : `${dateText(then, locale)}, ${time}`;
}
