// Cards as the firmware drew them (docs/EMULATOR_ARCHITECTURE.md, "The page editor's own cards"). The editor draws its
// own mockup of every card, from the firmware's numbers; a card it cannot draw well enough that way is shown as the
// editor's firmware preview drew it, cut from the firmware's frame. This store is the one road for that: a card is asked
// for by what is drawn (a tile, its cells, the glass), the firmware behind the editor draws what is asked for
// (components/GlassFaces.vue), and whoever asked shows the picture on its own card, which stays the editor's to choose,
// drag, resize and remove.
//
// A face has one key, made from the tile itself and never from where it stands: a tile moved to another cell, a copy of
// it, and the same tile shown in the library ask the same question and share one picture, here and in the browser's
// keeping between visits (model/face-cache.ts). This store knows a tile, a size and a glass. Which tiles take a
// firmware-drawn face, and what drew them, is decided by whoever asks (today a plugin's tile whose plugin has code in
// the preview: stores/plugin-code.ts drawnBy).
import { defineStore } from "pinia";
import { computed, onScopeDispose, ref, shallowReactive, watch, type ComputedRef } from "vue";
import { forgetOldFaces, keepFace, keptFaces } from "../model/face-cache";
import type { Tile } from "../types";

// A card on the firmware's glass (web/wasm/firmware_preview.cpp preview_cards): the tile's index and slot in the layout
// the firmware runs, its box in the frame, its corner radius, whether a plugin's own code drew it, and a count that
// goes up each time its pixels changed.
export type GlassCard = { i: number; slot: number; x: number; y: number; w: number; h: number; r: number; plugin: boolean; n: number };
// The picture of one card, in the firmware's own pixels, with the cells it was drawn for and a count that goes up each
// time it was drawn again. `kept`: it is the card of an earlier visit, shown until the firmware has drawn it again.
export type Face = { canvas: HTMLCanvasElement; width: number; height: number; columns: number; rows: number; stamp: number; kept: boolean };
// What is asked for: the tile as the screen would get it, the cells it covers, whether it shows its type's own example
// instead of what it reads now (a tile that is on no page yet has nothing of its own to show), and what draws it: a
// word that is another one when the code that draws this kind of card is another (a plugin's version).
export type FaceAsk = { tile: Tile; columns: number; rows: number; example: boolean; by: string };
export type Asked = FaceAsk & { key: string; count: number };

// Keys in the order they are written, so two tiles with the same options give the same text.
const ordered = (value: unknown): unknown => Array.isArray(value) ? value.map(ordered)
  : value && typeof value === "object" ? Object.fromEntries(Object.keys(value as object).sort().map((key) => [key, ordered((value as Record<string, unknown>)[key])]))
    : value;

/** A face's key: everything the picture depends on, as text, and nothing else. `glass`: what the firmware draws for
 * (GlassFaces.vue). Never the tile's id or its place: those do not change what is drawn. The key is its own full text,
 * not a short hash of it: it names a picture kept for weeks, and two keys must never meet. */
export function faceKey(glass: string, ask: FaceAsk): string {
  return JSON.stringify([glass, ask.by, ask.tile.entity, ask.columns, ask.rows, ask.example, ask.tile.name || "", ordered(ask.tile.options ?? {})]);
}

export const useFacesStore = defineStore("faces", () => {
  // What the firmware behind the editor draws for now: "" while there is none (a glass the preview cannot draw).
  const glass = ref("");
  const faces = shallowReactive(new Map<string, Face>());
  // What is asked for now, each with how many ask for it.
  const asks = shallowReactive(new Map<string, Asked>());
  // The faces the firmware drew since they were last put in the browser's keeping.
  const drawn = new Set<string>();

  const keyOf = (ask: FaceAsk) => (glass.value ? faceKey(glass.value, ask) : "");
  const of = (key: string) => (key ? faces.get(key) : undefined);

  /** Ask for a face for as long as something shows it; the answer gives the asking back. Nothing is asked while there
   * is no glass to draw for. */
  function ask(wanted: FaceAsk): { key: string; release: () => void } {
    const key = keyOf(wanted);
    if (!key) return { key, release: () => {} };
    const before = asks.get(key);
    asks.set(key, { ...(before ?? wanted), key, count: (before?.count ?? 0) + 1 });
    let held = true;
    return { key, release: () => {
      if (!held) return;
      held = false;
      const now = asks.get(key);
      if (!now) return;
      if (now.count <= 1) asks.delete(key); else asks.set(key, { ...now, count: now.count - 1 });
    } };
  }

  /** The card of an asked face, cut from the firmware's frame with its corners left clear, so the editor's own card
   * shows around them. */
  function take(key: string, frame: HTMLCanvasElement, card: GlassCard) {
    const asked = asks.get(key);
    if (!asked) return;
    const before = faces.get(key);
    const canvas = before && before.width === card.w && before.height === card.h ? before.canvas : document.createElement("canvas");
    canvas.width = card.w; canvas.height = card.h;
    const paint = canvas.getContext("2d");
    if (!paint) return;
    paint.clearRect(0, 0, card.w, card.h);
    paint.save();
    paint.beginPath();
    paint.roundRect(0, 0, card.w, card.h, Math.min(card.r, card.w / 2, card.h / 2));
    paint.clip();
    paint.drawImage(frame, card.x, card.y, card.w, card.h, 0, 0, card.w, card.h);
    paint.restore();
    faces.set(key, { canvas, width: card.w, height: card.h, columns: asked.columns, rows: asked.rows, stamp: (before?.stamp ?? 0) + 1, kept: false });
    drawn.add(key);
  }

  // What the firmware drew since the last time goes into the browser's keeping, for the next visit.
  function remember() {
    for (const key of drawn) {
      const face = faces.get(key);
      if (face && !face.kept && glass.value) void keepFace(glass.value, key, face.canvas, face.columns, face.rows);
    }
    drawn.clear();
  }

  /** The glass the firmware draws for from now on. Faces are keyed by their glass, so those of another one are other
   * faces: they go, whoever shows one asks again under the new glass, and the cards kept at the last visit to this one
   * stand at once, until drawn again. */
  async function drawFor(next: string) {
    if (next === glass.value) return;
    remember();
    glass.value = next;
    faces.clear();
    if (!next) return;
    for (const kept of await keptFaces(next)) {
      if (glass.value !== next || faces.has(kept.key)) continue;
      try {
        const picture = await createImageBitmap(kept.blob);
        if (glass.value !== next || faces.has(kept.key)) continue;
        const canvas = document.createElement("canvas");
        canvas.width = kept.width; canvas.height = kept.height;
        canvas.getContext("2d")?.drawImage(picture, 0, 0);
        faces.set(kept.key, { canvas, width: kept.width, height: kept.height, columns: kept.columns, rows: kept.rows, stamp: 1, kept: true });
      } catch { /* A picture that no longer reads is simply not shown. */ }
    }
    void forgetOldFaces();
  }

  // The firmware could not draw: nobody is shown a card of an earlier visit as if it were today's.
  function forget() {
    faces.clear(); drawn.clear();
  }

  return { glass, faces, asks, keyOf, of, ask, take, remember, drawFor, forget };
});

/** The face of a tile, for as long as the calling component stands: asked for while it is wanted (`wanted` gives what,
 * or null for a card the editor draws itself), given back when it no longer is. While a new question has no picture
 * yet (an option being typed), the last picture of the same size stays, so the card does not fall back to the editor's
 * drawing between two answers. */
export function useFace(wanted: () => FaceAsk | null): ComputedRef<Face | undefined> {
  const faces = useFacesStore();
  const key = ref("");
  let held: { key: string; release: () => void } | null = null, last: Face | undefined;
  watch(() => { const now = wanted(); return now ? { key: faces.keyOf(now), now } : null; }, (next) => {
    if (next?.key === held?.key) return;
    const before = held;
    held = next?.key ? faces.ask(next.now) : null;
    before?.release();
    key.value = held?.key ?? "";
  }, { immediate: true });
  onScopeDispose(() => { held?.release(); held = null; });
  return computed(() => {
    const now = wanted(), found = faces.of(key.value);
    if (!now || !key.value) return (last = undefined);
    if (found) return (last = found);
    return last && last.columns === now.columns && last.rows === now.rows ? last : undefined;
  });
}
