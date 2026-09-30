// What the page takes from the translations (app 0.2.90), for vite.config.ts and the tests. Every language is one file
// in screen_manager/translations, shared with the firmware and the add-on.
import { join } from "node:path";

export const TRANSLATIONS = join(__dirname, "..", "screen_manager", "translations");
// Of the screens' texts the page takes the ones its mockup draws: Home Assistant's words, times, dates, numbers and the
// page label. The draft validator also shares the add-on's page/card errors.
const SCREEN_PARTS = ["ha", "time", "date", "number", "navigation", "climate", "cover", "script"];

// An empty text is one the language doesn't have yet: it stays out, so English shows, as on the screens. A space is
// a text (French writes 1 234,5).
function filled(node: unknown): unknown {
  if (typeof node === "string") return node === "" ? undefined : node;
  if (Array.isArray(node)) return node.every((item) => typeof item === "string" && item !== "") ? node : undefined;
  if (!node || typeof node !== "object") return undefined;
  const kept = Object.entries(node).map(([key, value]) => [key, filled(value)]).filter(([, value]) => value !== undefined);
  return kept.length ? Object.fromEntries(kept) : undefined;
}
/** The part of a language's file the page takes: the editor's texts and the screens' words its mockup draws. */
export function pageTexts(data: any) {
  const screen = data?.screen || {};
  const words: Record<string, unknown> = Object.fromEntries(SCREEN_PARTS.filter((part) => part in screen).map((part) => [part, screen[part]]));
  if (screen.tile?.page !== undefined) words.tile = { page: screen.tile.page };
  const errors = Object.fromEntries(['pages', 'layout', 'top_bar'].filter((key) => data?.addon?.errors?.[key])
    .map((key) => [key, data.addon.errors[key]]));
  return (filled({ editor: data?.editor, screen: words, addon: { errors } }) || {}) as Record<string, unknown>;
}
