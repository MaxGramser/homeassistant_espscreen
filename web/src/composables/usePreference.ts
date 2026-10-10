// What the editor remembers of itself in this browser: the sidebar's width and fold, the library drawer open or folded
// and how tall, the whole editor on a phone, the simple or advanced editor per screen, when to ask for support again. A
// convenience of this computer, not a setting of the screens: kept in localStorage under the names and the values it
// always had ("1" and "0" where it wrote those), so nothing a browser kept before is lost.
//
// On VueUse's useStorage, with what the editor needs of it: a browser that keeps nothing (a private window, an iframe
// that blocks storage, a full storage) reads the default and writes nothing, without an exception; the default is never
// written by itself; a value is written as it changes (flush "sync"), and only when it differs from what is stored. A
// change another tab makes is followed only where `listen` asks for it, and the storage is looked up at each read and
// write, so a test that puts another in place (vi.stubGlobal) or a browser that refuses it is met where it is.
import { customStorageEventName, useEventListener, useStorage, type RemovableRef, type Serializer, type StorageEventLike, type StorageLike } from "@vueuse/core";
import { effectScope, toValue, type EffectScope, type MaybeRefOrGetter, type WatchOptions } from "vue";

const browserStorage: StorageLike = {
  getItem: (key) => localStorage.getItem(key),
  setItem: (key, value) => localStorage.setItem(key, value),
  removeItem: (key) => localStorage.removeItem(key),
};

/** On or off as "1" and "0". */
export const flagSerializer: Serializer<boolean> = { read: (raw) => raw === "1", write: (on) => (on ? "1" : "0") };

export type PreferenceOptions<T> = {
  /** How the value is read from its text and written as one; plain JSON when none is given. */
  serializer?: Serializer<T>;
  /** Follow a change another tab of this browser makes (the storage event). Off by default: a tab keeps what it shows. */
  listen?: boolean;
  /** When a change is written: at once (default) or before the next render. */
  flush?: WatchOptions["flush"];
};

const json = <T>(): Serializer<T> => ({ read: (raw) => JSON.parse(raw) as T, write: (value) => JSON.stringify(value) });

/** A value kept in this browser under `key` (a name, or a getter for one that changes, such as a screen's), `initial`
 * until something is kept. Writing the ref keeps the new value. */
export function usePreference<T>(key: MaybeRefOrGetter<string>, initial: MaybeRefOrGetter<T>, options: PreferenceOptions<T> = {}): RemovableRef<T> {
  // useStorage follows a storage it was handed by its own event: another tab's change of this key is passed on as one.
  if (options.listen) useEventListener(window, "storage", (event: StorageEvent) => {
    try { if (event.storageArea !== localStorage || event.key !== toValue(key)) return; } catch { return; }
    const detail: StorageEventLike = { key: event.key, oldValue: event.oldValue, newValue: event.newValue, storageArea: browserStorage };
    window.dispatchEvent(new CustomEvent(customStorageEventName, { detail }));
  }, { passive: true });
  return useStorage<T>(key, initial, browserStorage, {
    serializer: options.serializer ?? json<T>(),
    writeDefaults: false,
    listenToStorageChanges: options.listen ?? false,
    flush: options.flush ?? "sync",
    onError: () => { /* Nothing kept: the default stands, and the editor goes on as it always does. */ },
  });
}

/** For a module that keeps preferences while the page is open, outside any component (the sidebar, the store): each call
 * makes them again in a scope of their own and stops the ones the call before made, so a test that starts over
 * (src/resets.ts) reads the storage as it is then, and the old ones write nothing more. */
export function renewable<T>(make: () => T): () => T {
  let scope: EffectScope | undefined;
  return () => {
    scope?.stop();
    scope = effectScope(true);
    return scope.run(make) as T;
  };
}
