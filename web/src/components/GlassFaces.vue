<script setup lang="ts">
// The firmware behind the editor (docs/EMULATOR_ARCHITECTURE.md, "The page editor's own cards"): one preview that
// nobody sees, which draws the cards that are asked for (stores/faces.ts) and nothing else. What it runs is not the
// draft: it is a layout made of the asked tiles alone, each at a place of its own on pages of the screen's grid, so the
// add-on shapes messages only for those tiles, and each card is drawn in the screen's own look, whatever section it
// stands in on its page. A tile on a page is drawn with what it reads now, a tile on no page with its type's example.
//
// Asked, not polled. The firmware is handed a new layout when what is asked for changes, and new values when the
// add-on has them. Its clock has to run for a card that counts on it, so it takes one step a second while a face is
// asked for and the page is in sight, and stops entirely otherwise. A card is copied only when the firmware says its
// pixels changed (preview_cards' count), so a step in which nothing changed copies nothing. With more cards than one
// page holds, the glass stays where it is until another page has something to draw: a face never drawn, or values that
// came in new for a tile on it. A page turned to asks for its pictures again, so it is not turned to for nothing.
import { useDocumentVisibility, useIntervalFn, useTimeoutFn } from "@vueuse/core";
import { computed, onBeforeUnmount, ref, shallowRef, watch } from "vue";
import { isPluginTile } from "../model/plugins";
import { arrangeTiles, emptyLayout, pageLimit } from "../model/pages";
import { previewShapeOf } from "../model/preview";
import { useDocumentStore } from "../stores/document";
import { useFacesStore, type GlassCard } from "../stores/faces";
import { useInventoryStore } from "../stores/inventory";
import { usePluginCodeStore } from "../stores/plugin-code";
import { drawsPictures, useScreenStore } from "../stores/screen";
import type { PageLayout, Tile } from "../types";
import FirmwarePreview from "./FirmwarePreview.vue";

const scr = useScreenStore();
const doc = useDocumentStore();
const faces = useFacesStore();
const code = usePluginCodeStore();
const inv = useInventoryStore();
const sight = useDocumentVisibility();
const { pageOf, grid } = doc.editorLayout;

// The draft's way and grid, as the Preview takes them (NavigationPreview.vue).
const live = computed(() => (scr.currentScreen ? previewShapeOf({ shape: doc.screenShape }, doc.documentGrid) : null));
// The code the firmware is loaded with: the screen's plugins that have a module, as one word (another set is another
// firmware), and null until the add-on has said which. Asked again whenever what the screen runs is another thing: a
// plugin added or updated while the page is open, and the add-on's plugins coming in after the screen was chosen.
// Asking also tells the store which tiles the firmware can draw (plugin-code.ts drawnBy).
const runs = computed(() => (scr.currentScreen ? `${scr.currentScreen.id}|${code.runsOn(scr.currentScreen)}` : ""));
const loaded = ref<string | null>(null);
watch(runs, async (asked) => {
  loaded.value = null;
  const found = await code.codeFor(scr.currentScreen);
  if (runs.value === asked) loaded.value = found.map((plugin) => plugin.id).sort().join(",");
}, { immediate: true });

// ---- What a card is drawn for ----
// The glass: the screen (which stands for what is installed on it and how it is set), its pixels and grid, its
// density, its look and its language. Every face is keyed by it, so the cards of another glass are other cards, and the
// cards kept at the last visit to this one stand at once (stores/faces.ts drawFor).
const dark = computed(() => scr.currentScreen?.settings?.values?.dark_mode === true);
const glass = computed(() => (live.value && scr.currentScreen && !scr.currentScreen.virtual
  ? `${scr.currentScreen.id}:${live.value.width}x${live.value.height}:${live.value.columns}x${live.value.rows}:${live.value.dpi}:${dark.value ? "dark" : "light"}:${inv.inventory.language?.effective || "en"}`
  : ""));
watch(glass, (now) => void faces.drawFor(now), { immediate: true });

// ---- The layout of what is asked for ----
// Each asked face at a place of its own, in the order it was asked for, on as many pages as a screen takes.
type Placed = { key: string; tile: Tile; slot: number; example: boolean };
const placed = computed<Placed[]>(() => {
  const columns = grid.columns, rows = grid.rows, cells = grid.slots, most = pageLimit(doc.documentGrid ?? { columns, rows });
  const taken: boolean[][] = [], out: Placed[] = [];
  const free = (page: number, at: number, wide: number, high: number) => {
    const column = at % columns, row = Math.floor(at / columns);
    if (column + wide > columns || row + high > rows) return false;
    for (let y = row; y < row + high; y++) for (let x = column; x < column + wide; x++) if (taken[page]?.[y * columns + x]) return false;
    return true;
  };
  for (const ask of faces.asks.values()) {
    if (ask.columns > columns || ask.rows > rows) continue;
    search: for (let page = 0; page < most; page++) {
      for (let at = 0; at < cells; at++) {
        if (!free(page, at, ask.columns, ask.rows)) continue;
        taken[page] ??= [];
        for (let y = 0; y < ask.rows; y++) for (let x = 0; x < ask.columns; x++) taken[page]![at + y * columns + x] = true;
        out.push({ key: ask.key, tile: ask.tile, slot: page * cells + at, example: ask.example });
        break search;
      }
    }
  }
  return out;
});
// That layout as a document the add-on takes. The firmware keeps the last one while nothing is asked for, so a face
// asked again soon finds it running.
const layout = shallowRef<PageLayout | null>(null);
watch(placed, (now) => {
  if (!now.length || !doc.documentGrid) return;
  try {
    layout.value = arrangeTiles(emptyLayout(doc.document?.title || ""), { ...doc.documentGrid, plugins: true },
      now.map(({ tile, slot }) => ({ tile: { ...tile, id: undefined, slot }, slot })));
  } catch { /* A layout the add-on would refuse: the cards keep the editor's own drawing. */ }
}, { immediate: true });
const examples = computed(() => placed.value.filter((item) => item.example).map((item) => item.slot));
const pages = computed(() => [...new Set(placed.value.map((item) => pageOf(item.slot)))].sort((a, b) => a - b));

// ---- The firmware ----
// It lives while a face is asked for, and a minute after the last one was given back: a library scrolled past its
// plugin tiles and back does not start a firmware anew each time. That minute is the glass's own (`kept`, the glass a
// face was last asked for on): on another screen, in another look or language, the firmware of the glass before goes
// at once, so a screen that asks for no face runs nothing, not for a minute either.
const asked = computed(() => Boolean(glass.value && live.value && faces.asks.size));
const kept = ref("");
const rest = useTimeoutFn(() => { kept.value = ""; }, 60000, { immediate: false });
watch(() => (asked.value ? glass.value : ""), (now) => { if (now) { rest.stop(); kept.value = now; } else rest.start(); }, { immediate: true });
const alive = computed(() => Boolean(glass.value) && kept.value === glass.value);
// A firmware that cannot go on (it did not load, as in a browser that cannot run it, or it threw in a frame) ends it
// for this glass and this code: the cards keep the editor's own drawing. A refresh that failed does not: the add-on
// restarting or refusing one write is asked again by the preview itself, and nothing is copied until it answers.
const failed = ref(false);
watch(() => `${glass.value}:${loaded.value}`, () => { failed.value = false; });
function stopped(_message: string, final: boolean) {
  if (final) failed.value = true;
}
type Shot = { cards: GlassCard[]; canvas: () => HTMLCanvasElement };
const preview = ref<{ capture(page: number): Shot | null } | null>(null);

// ---- Its steps ----
// A page out of sight is turned to when it has something to draw (`due`): a face never drawn today, or values that
// came in new for a tile on it. Four numbers hold the round, each for one reason.
// A page keeps the glass at least this long: a page just turned to asks for its pictures, and they come a moment
// after its cards. Leaving sooner would cut a card before its picture was on it.
const DWELL = 1500;
// And at most this long while a face on it is still to come: a face that never comes (a picture the add-on cannot
// get) must not keep the other pages waiting.
const LONGEST = 5000;
// A page with nothing new is still looked at once in this long, for a card that follows the clock (a countdown, a
// time of day): out of sight nothing ticks it, and it would stand still for as long as its page is away.
const AGAIN = 60000;
// How many times a page is looked at without finding the card of a face before it is no longer held for it: a plugin
// whose code did not load draws the plain card of a missing plugin, never its own. Three, so one slow start is no miss.
const MISSES = 3;
let page = 0, since = 0;
const visited = new Map<number, number>(), due = new Set<number>();
// The count each face was last copied at, by where it stands, and how many times a page was looked at without finding
// the card of a face (MISSES).
const copied = new Map<string, string>(), missed = new Map<string, number>();
watch(placed, () => { copied.clear(); missed.clear(); visited.clear(); due.clear(); });
const drawn = (key: string) => { const face = faces.of(key); return Boolean(face && !face.kept); };
const waits = (at: number) => placed.value.some((item) => pageOf(item.slot) === at && !drawn(item.key) && (missed.get(item.key) ?? 0) < MISSES);
function step() {
  const view = preview.value, list = pages.value;
  if (!asked.value || failed.value || sight.value === "hidden" || !view || !list.length) return;
  const now = performance.now();
  if (!list.includes(page)) { page = list[0]!; since = now; }
  else if (list.length > 1 && now - since >= DWELL && (!waits(page) || now - since >= LONGEST)) {
    const wants = (other: number) => due.has(other) || waits(other) || now - (visited.get(other) ?? 0) >= AGAIN;
    // The next page that has something to draw, from the one on the glass onwards, so every page gets its turn.
    const at = list.indexOf(page), next = [...list.slice(at + 1), ...list.slice(0, at)].find(wants);
    if (next !== undefined) { page = next; since = now; }
  }
  const shot = view.capture(page);
  if (!shot) return;
  visited.set(page, now); due.delete(page);
  for (const item of placed.value) {
    if (pageOf(item.slot) !== page) continue;
    // A card of a plugin is its face only when the plugin's own code drew it, not the plain card of a missing plugin.
    const card = shot.cards.find((found) => found.slot === item.slot && (found.plugin || !isPluginTile(item.tile.entity)));
    if (!card || card.w <= 0 || card.h <= 0) { missed.set(item.key, (missed.get(item.key) ?? 0) + 1); continue; }
    const count = `${item.slot}:${card.n}`;
    if (drawn(item.key) && copied.get(item.key) === count) continue;
    faces.take(item.key, shot.canvas(), card);
    copied.set(item.key, count);
  }
}
const clock = useIntervalFn(step, 1000, { immediate: false });
watch(() => asked.value && sight.value !== "hidden", (run) => { if (run) clock.resume(); else clock.pause(); }, { immediate: true });
// The firmware has new values. The add-on numbers the tiles of a layout by their place, so the tile it names is the
// one at that rank among the places: its page has something to draw. The page on the glass is looked at now, and once
// more for its pictures.
const soon = useTimeoutFn(step, 60, { immediate: false }), after = useTimeoutFn(step, 450, { immediate: false });
function synced(changed: number[] | null) {
  const slots = placed.value.map((item) => item.slot).sort((a, b) => a - b);
  for (const index of changed ?? slots.map((_, at) => at)) if (slots[index] !== undefined) due.add(pageOf(slots[index]!));
  soon.start(); after.start();
}

// What the firmware drew is kept for the next visit, every while and when the page is left.
useIntervalFn(() => faces.remember(), 20000);
watch(sight, (now) => { if (now === "hidden") faces.remember(); });
// A firmware that cannot draw: nobody is shown a card of an earlier visit as if it were today's.
watch(failed, (now) => { if (now) faces.forget(); });
onBeforeUnmount(() => { faces.remember(); void faces.drawFor(""); });
</script>

<template>
  <div v-if="alive && live && layout && loaded !== null && !failed" class="glass-faces" aria-hidden="true">
    <FirmwarePreview ref="preview" :key="`${glass}:${loaded}`"
      :width="live.width" :height="live.height" :dpi="live.dpi" :columns="live.columns" :rows="live.rows"
      :pictures="drawsPictures(scr.currentScreen)" :dark="dark" :plugins-of="scr.currentScreen"
      :layout="layout" :examples="examples" still manual @synced="synced" @failed="stopped" />
  </div>
</template>

<style scoped>
/* Never seen: the firmware draws here only to be read. */
.glass-faces { position: absolute; width: 0; height: 0; overflow: hidden; visibility: hidden; pointer-events: none; }
</style>
