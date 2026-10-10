// A store's lookups: what only reads the store and answers (an entity's name, a card's icon, a screen's status line), as a
// getter rather than an action. Pinia makes every function a setup store returns an action, and an action costs its
// bookkeeping on every call (the active pinia set, the arguments copied, two sets and two callbacks made, every
// $onAction told), where a card on the mockup asks the same few lookups many times each time it is drawn. A lookup is a
// getter whose value is the function itself: made once, read like any other getter (`entities.entityName(id)`), and
// what it reads when it is called is followed by whoever calls it, as before. Actions stay actions: whatever changes the
// store or asks the add-on (a lookup that asks for what it does not have yet, as plugins.choicesFor does, is still a
// lookup: it answers at once and fills itself in later).
import { computed, type ComputedRef } from "vue";

type Lookups<T> = { [K in keyof T]: ComputedRef<T[K]> };

/** The store's lookups, each a getter whose value is the function: `return { ...lookups({ entityName }), loadStates }`. */
export function lookups<T extends Record<string, (...args: any[]) => any>>(functions: T): Lookups<T> {
  return Object.fromEntries(Object.entries(functions).map(([name, lookup]) => [name, computed(() => lookup)])) as Lookups<T>;
}
