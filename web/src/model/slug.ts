// A name as the add-on and ESPHome write it into an id or a file name: lower case letters and digits, every other run of
// characters one separator. "Living room" is living-room as a preview screen's id and a layout's file, living_room as the
// start Home Assistant gives its entity ids (the add-on's core.entity_slug), and living-room as an ESPHome node name,
// which also drops accents, starts with a letter and keeps to 30 characters.

/** The name in lower case ASCII letters and digits with `separator` between them; trimmed of separators at either end
 * unless `trim` is false. */
export function slug(text: string, { separator = "-", trim = true }: { separator?: string; trim?: boolean } = {}) {
  const joined = text.toLowerCase().replace(/[^a-z0-9]+/g, separator);
  if (!trim || !separator) return joined;
  const edge = separator.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return joined.replace(new RegExp(`^(${edge})+|(${edge})+$`, "g"), "");
}
/** The start Home Assistant gives the entity ids of a device with this name (core.entity_slug). */
export const entitySlug = (text: string) => slug(text, { separator: "_" });
/** ESPHome's rule for a node name: lower case ASCII, digits and dashes, starting with a letter, at most 30 characters;
 * "screen" for a name with nothing of that left. */
export function nodeName(text: string) {
  const clean = slug(text.normalize("NFD").replace(/[̀-ͯ]/g, ""), { trim: false })
    .replace(/^[^a-z]+/, "").slice(0, 30).replace(/-+$/, "");
  return clean || "screen";
}
