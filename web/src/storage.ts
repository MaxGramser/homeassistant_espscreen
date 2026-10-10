// This browser's storage, for what the editor remembers of itself (the library's height, the sidebar's width, the
// preview screens). A private window, a full storage or an iframe that blocks it throws on every read or write: a read
// then finds nothing and the editor starts as it always does, and a write says whether it was kept.
export function readStored(key: string): string | null {
  try { return localStorage.getItem(key); } catch { return null; }
}
export function writeStored(key: string, value: string): boolean {
  try { localStorage.setItem(key, value); return true; } catch { return false; }
}
