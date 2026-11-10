// The editor's searches, one way everywhere (the library, ⌘K, the pickers, New screen, the plugins): each word typed
// must be somewhere in the fields of a thing, in any order and in any field ("kitchen lamp" finds a Lamp in the room
// Kitchen). Case, accents, and whether a word is joined by a space, a dash or an underscore make no difference. That is
// matchesQuery from the text as typed and matchesWords from queryWords; the order Spotlight gives (a name that starts
// with it, then one with a word that does) is prefixRank.

// A text as it is compared: in lower case, without accents, and one space wherever spaces, dashes or underscores stand.
const plain = (text: string) => text.normalize("NFD").replace(/\p{M}/gu, "").toLocaleLowerCase().replace(/[\s_-]+/g, " ").trim();
/** The words of a query, as they are compared. */
export const queryWords = (query: string) => plain(query).split(" ").filter(Boolean);
// The fields of a thing as one text.
const haystack = (fields: readonly (string | number | null | undefined)[]) => plain(fields.map((field) => field ?? "").join(" "));

/** Whether every word typed is somewhere in the fields; an empty query matches everything. */
export const matchesQuery = (query: string, ...fields: (string | number | null | undefined)[]) => matchesWords(queryWords(query), ...fields);
/** Whether every word is somewhere in the fields (words as queryWords gives them). */
export function matchesWords(words: readonly string[], ...fields: (string | number | null | undefined)[]) {
  const text = haystack(fields);
  return words.every((word) => text.includes(word));
}
/** The words of a name: split at spaces, dashes and underscores. */
export const nameWords = (name: string) => name.toLocaleLowerCase().split(/[\s_-]+/);
/** How well a name answers a query, for the order of what is found: 0 when it starts with it, 1 when each word typed
 * starts a word of the name, 2 when the name holds them all, 3 when it took the other fields to find it. */
export function prefixRank(name: string, query: string) {
  const wanted = plain(query), lower = plain(name), asked = wanted.split(" "), words = lower.split(" ");
  if (lower.startsWith(wanted)) return 0;
  if (asked.every((word) => words.some((own) => own.startsWith(word)))) return 1;
  return asked.every((word) => lower.includes(word)) ? 2 : 3;
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
