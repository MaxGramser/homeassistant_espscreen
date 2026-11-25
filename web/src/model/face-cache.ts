// The cards the firmware drew, kept in this browser between visits (stores/faces.ts). Starting the firmware takes a
// few seconds, more on a slow tablet; a card that was drawn last time is shown at once, dimmed, until the firmware has
// drawn it again. Kept by the face's own key (stores/faces.ts faceKey: what is drawn, for which glass), so a tile moved,
// copied or shown in the library finds the one picture, and found again by its glass; in the browser's own database
// (IndexedDB), apart from the room the drafts are kept in. Nothing here is needed: where the database is not there, or
// is full, every call answers as if nothing was kept.
const DATABASE = "tessera-faces", STORE = "faces";
// A face not shown for this long goes, and so does the oldest past this many.
const KEEP_MS = 30 * 86400 * 1000, MOST = 300;

export type KeptFace = { key: string; glass: string; blob: Blob; width: number; height: number; columns: number; rows: number; at: number };

let opened: Promise<IDBDatabase | null> | undefined;
function open(): Promise<IDBDatabase | null> {
  opened ??= new Promise((resolve) => {
    try {
      if (typeof indexedDB === "undefined") return resolve(null);
      // Version 2: kept by the face's key. What an earlier version kept is let go; it is drawn again.
      const request = indexedDB.open(DATABASE, 2);
      request.onupgradeneeded = () => {
        if (request.result.objectStoreNames.contains(STORE)) request.result.deleteObjectStore(STORE);
        request.result.createObjectStore(STORE, { keyPath: "key" }).createIndex("glass", "glass");
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = request.onblocked = () => resolve(null);
    } catch { resolve(null); }
  });
  return opened;
}
const done = <T>(request: IDBRequest<T>) => new Promise<T | null>((resolve) => {
  request.onsuccess = () => resolve(request.result);
  request.onerror = () => resolve(null);
});

// The faces kept for one glass.
export async function keptFaces(glass: string): Promise<KeptFace[]> {
  const database = await open();
  if (!database) return [];
  try {
    return (await done(database.transaction(STORE).objectStore(STORE).index("glass").getAll(glass))) ?? [];
  } catch { return []; }
}

// Keep a face as it is drawn now.
export async function keepFace(glass: string, key: string, canvas: HTMLCanvasElement, columns: number, rows: number): Promise<void> {
  const database = await open();
  if (!database) return;
  const blob = await new Promise<Blob | null>((resolve) => { try { canvas.toBlob(resolve, "image/png"); } catch { resolve(null); } });
  if (!blob) return;
  try {
    await done(database.transaction(STORE, "readwrite").objectStore(STORE).put(
      { key, glass, blob, width: canvas.width, height: canvas.height, columns, rows, at: Date.now() } satisfies KeptFace));
  } catch { /* A full database keeps what it has. */ }
}

// Old faces go: the ones not kept again for a month, and the oldest past the most this keeps.
export async function forgetOldFaces(): Promise<void> {
  const database = await open();
  if (!database) return;
  try {
    const all = ((await done(database.transaction(STORE).objectStore(STORE).getAll())) ?? []) as KeptFace[];
    const sorted = all.sort((a, b) => b.at - a.at);
    const gone = sorted.filter((face, index) => index >= MOST || Date.now() - face.at > KEEP_MS);
    if (!gone.length) return;
    const store = database.transaction(STORE, "readwrite").objectStore(STORE);
    for (const face of gone) store.delete(face.key);
  } catch { /* Nothing to forget. */ }
}
