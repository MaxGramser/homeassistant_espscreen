// The listeners of one gesture (a row held, an edge or a tile's side dragged, a page carried on the map): they are added
// when it begins, in a scope of the component's, and go when it ends, when another begins, or when the component goes
// in the middle of it. Inside `listen` anything a component uses works (useEventListener, useTimeoutFn).
import { tryOnScopeDispose } from "@vueuse/core";
import { effectScope, getCurrentScope, type EffectScope } from "vue";

export function useGesture() {
  const owner = getCurrentScope();
  let scope: EffectScope | null = null;
  /** The gesture begins: `listen` adds what follows it. */
  function begin(listen: () => void) {
    end();
    const next = (owner ? owner.run(() => effectScope()) : effectScope())!;
    scope = next;
    next.run(listen);
  }
  /** Adds to the gesture under way. */
  const add = (listen: () => void) => scope?.run(listen);
  /** The gesture ends: its listeners go. */
  function end() {
    scope?.stop();
    scope = null;
  }
  tryOnScopeDispose(end);
  return { begin, add, end, active: () => scope !== null };
}
