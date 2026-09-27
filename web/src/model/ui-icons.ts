// The editor's own icons (app 0.3.19): Material Design Icons by their Home Assistant names, drawn from the editor's
// icon font. ui-icons.json is the one list; tools/generate_icons.py puts exactly those glyphs in the font.
import table from "./ui-icons.json";
import { glyph } from "./topbar";

export type IconName = Exclude<keyof typeof table, "_comment">;
export const iconCode = (name: IconName) => (table as Record<string, string>)[name];
export const iconGlyph = (name: IconName) => glyph(iconCode(name));
