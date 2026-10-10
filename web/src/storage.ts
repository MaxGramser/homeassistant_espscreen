// This browser's storage for the preview screens (store.ts), which are not a preference but the screens themselves: a
// write has to say whether it was kept, since a preview screen that was not kept is not changed either and the editor
// says so (editor.preview.not_kept). What the editor remembers of itself goes through usePreference. A private window, a
// full storage or an iframe that blocks it throws on every read or write: a read then finds nothing, and a write says
// it was not kept.
export function readStored(key: string): string | null {
  try { return localStorage.getItem(key); } catch { return null; }
}
export function writeStored(key: string, value: string): boolean {
  try { localStorage.setItem(key, value); return true; } catch { return false; }
}
