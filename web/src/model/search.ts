// The editor's searches, one way everywhere (the library, ⌘K, the pickers, New screen, the plugins): what is typed is
// compared without case in the language's own way, against the fields of a thing joined by spaces, so a query may run
// from one field into the next as it always could. A query of several words that must each be somewhere is
// matchesWords; the order Spotlight gives (a name that starts with it, then one with a word that does) is prefixRank.

/** The query as it is compared: without the spaces around it, in lower case. */
export const normalizedQuery = (query: string) => query.trim().toLocaleLowerCase();
/** The words of a query, in lower case. */
export const queryWords = (query: string) => query.toLocaleLowerCase().split(/\s+/).filter(Boolean);
// The fields of a thing as one text: an empty field still takes its place between the spaces.
const haystack = (fields: readonly (string | number | null | undefined)[]) => fields.map((field) => field ?? "").join(" ").toLocaleLowerCase();

/** Whether the fields hold what is typed; an empty query matches everything. */
export function matchesQuery(query: string, ...fields: (string | number | null | undefined)[]) {
  const wanted = normalizedQuery(query);
  return !wanted || haystack(fields).includes(wanted);
}
/** Whether every word is somewhere in the fields (words in lower case, as queryWords gives them). */
export function matchesWords(words: readonly string[], ...fields: (string | number | null | undefined)[]) {
  const text = haystack(fields);
  return words.every((word) => text.includes(word));
}
/** The words of a name: split at spaces, dashes and underscores. */
export const nameWords = (name: string) => name.toLocaleLowerCase().split(/[\s_-]+/);
/** How well a name answers a query, for the order of what is found: 0 when it starts with it, 1 when one of its words
 * does, 2 otherwise. */
export function prefixRank(name: string, query: string) {
  const wanted = normalizedQuery(query), lower = name.toLocaleLowerCase();
  return lower.startsWith(wanted) ? 0 : nameWords(name).some((word) => word.startsWith(wanted)) ? 1 : 2;
}
/** The values that match what is typed, ignoring case, spaces, dashes and underscores ("vol" finds VOLUME_UP): those
 * that start with it or have a word that does first, then those that have it anywhere. */
export function rankedValues(values: readonly string[], typed: string) {
  const fold = (text: string) => text.toLocaleLowerCase().replace(/[\s_-]+/g, "");
  const wanted = fold(typed);
  if (!wanted) return [...values];
  const first = values.filter((value) => fold(value).startsWith(wanted) || nameWords(value).some((word) => word.startsWith(wanted)));
  return [...first, ...values.filter((value) => !first.includes(value) && fold(value).includes(wanted))];
}
/** The icons of each group that match what is typed (the tile's icon picker, Alerts' list): by their label, their name
 * with or without its dashes ("alarm-light", "alarm light") and their group's label. Groups left empty go. */
export function iconGroupsMatching<I extends { name: string; label?: string }>(groups: readonly { label: string; icons: readonly I[] }[], query: string) {
  return groups.map((group) => ({ label: group.label,
    icons: group.icons.filter((icon) => matchesQuery(query, icon.label, icon.name, icon.name.replaceAll("-", " "), group.label)) }))
    .filter((group) => group.icons.length);
}
