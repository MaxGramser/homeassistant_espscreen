// The widths at which the editor lays itself out another way, one table for the script: a phone (640 px and narrower) gets
// the editor of everyday changes, and from 700 px down the pages stand one at a time. The style sheets keep their own
// @media rules at these numbers, and at the others they use (760, 860 and 960 px), which no script needs.
import { useBreakpoints } from "@vueuse/core";

export const WIDTHS = { phone: 640, narrow: 700 } as const;
export type Width = keyof typeof WIDTHS;

/** Whether the window is at most that wide now, read once (as the page loads). */
export const atMost = (width: Width) =>
  typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia(`(max-width: ${WIDTHS[width]}px)`).matches;

/** Follows the window while the component or scope lives: true while it is at most that wide. */
export const useAtMost = (width: Width) => useBreakpoints(WIDTHS).smallerOrEqual(width);
