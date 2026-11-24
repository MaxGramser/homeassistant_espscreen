// The screen's own colours where the editor draws its glass: the mockup's page (.device) and the strip the library's
// tiles stand on (LibraryShelf.vue). They are the firmware's roles (components/smart_display/theme.h, read at build time
// into virtual:esp-screens-theme), in the light look the mockup draws, set once on the page's root as CSS variables, so
// no stylesheet writes the glass's colours as numbers of its own. Tested by tests/glass-colours.spec.ts.
import theme from "virtual:esp-screens-theme";

const hex = (color: number) => `#${color.toString(16).padStart(6, "0")}`;
const ROLES = { "--glass-page": "PAGE", "--glass-ink": "INK", "--glass-ink-soft": "INK_SOFT", "--glass-muted": "MUTED" } as const;

/** The glass's colours as CSS variables: the page behind the cards, and its words, strong, soft and quiet. */
export const glassColours = (): Record<string, string> =>
  Object.fromEntries(Object.entries(ROLES).map(([name, role]) => [name, hex(theme.roles[role].light)]));

/** Sets them on an element, the page's root by default, so everything under it and every popup reads them. */
export function applyGlassColours(target: HTMLElement = document.documentElement) {
  for (const [name, value] of Object.entries(glassColours())) target.style.setProperty(name, value);
}
