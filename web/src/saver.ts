// The screensaver of the open screen as the editor shows it (app 0.4.48): what it shows in standby, in the order the
// screen tries it. The card in the settings and the drawer of one step both read and change it through here.
import { computed, ref, type Ref } from "vue";
import { t } from "./i18n";
import { dropIndex, moved } from "./model/reorder";
import { clockText, dateText } from "./model/topbar";
import { clock24, currentScreen, entityName, liveOf, openSaverStep, saverItems, screenLanguage, setScreensaver, settingValues, state, topbarLabel } from "./store";
import type { SaverKind, ScreensaverChoice } from "./types";

export const SAVER_MIN_FIRMWARE = "0.29.0";
export const SAVER_ICONS: Record<SaverKind, string> = { media: "F075A", camera: "F07AE", clock: "F0150" };
export const MAX_PLAYERS = 4;
const DOMAINS: Record<"media" | "camera", string[]> = { media: ["media_player"], camera: ["camera", "image"] };
const key = (name: string) => `editor.screen_settings.screensaver.${name}`;

export const saver = computed(() => currentScreen.value?.screensaver);
export const saverReady = computed(() => Boolean(saver.value?.ready));
export const standbyOn = computed(() => settingValues().standby_enabled !== false && settingValues().standby_enabled !== 0);
export const saverLabel = (kind: SaverKind) => t(key(`kinds.${kind}`));
export const isOn = (kind: SaverKind) => !saver.value?.off.includes(kind);

export function changeSaver(patch: Partial<ScreensaverChoice>) {
  if (currentScreen.value) setScreensaver(currentScreen.value, patch);
}
export function toggleStep(kind: SaverKind, on = !isOn(kind)) {
  const off = (saver.value?.off || []).filter((k) => k !== kind);
  changeSaver({ off: on ? off : [...off, kind] });
}

// The steps in the order the screen tries them. A board without pictures shows the clock alone.
export const savedOrder = computed<SaverKind[]>(() => saver.value?.order || ["media", "camera", "clock"]);
export function stepsShown(live: SaverKind[] | null) {
  const list = live || savedOrder.value;
  return saver.value?.pictures ? list : list.filter((kind) => kind === "clock");
}
export function moveStep(kind: SaverKind, by: number) {
  const list = savedOrder.value, from = list.indexOf(kind);
  if (from < 0 || from + by < 0 || from + by >= list.length) return;
  changeSaver({ order: moved(list, from, from + by) });
}

// The players of the music step (app 0.4.54), the first that plays with a cover shows.
export const players = computed(() => [saver.value?.media, ...(saver.value?.more || [])].filter((id): id is string => Boolean(id)));
export const setPlayers = (list: string[]) => changeSaver({ media: list[0] || "", more: list.slice(1) });
export const addPlayer = (id: string) => players.value.length < MAX_PLAYERS && !players.value.includes(id) && setPlayers([...players.value, id]);
export const removePlayer = (id: string) => setPlayers(players.value.filter((p) => p !== id));

const entityArea = (id: string) => state.inventory.entities.find((e) => e.id === id)?.area || "";
export const entityPlace = (id: string) => entityArea(id);
// What one can choose for a step, by name and the area it is in.
export function entitiesOf(kind: "media" | "camera", taken: string[] = []) {
  return state.inventory.entities
    .filter((e) => DOMAINS[kind].includes(e.id.split(".")[0]) && !taken.includes(e.id))
    .map((e) => ({ id: e.id, name: e.name, area: e.area || "" }))
    .sort((a, b) => a.name.localeCompare(b.name));
}
export const cameraChoices = computed(() => [
  ["", t(key("choose_camera"))] as const,
  ...entitiesOf("camera").map((e) => [e.id, e.area ? `${e.name} · ${e.area}` : e.name] as const),
]);
// The temperature under the clock (app 0.4.52): Home Assistant's own by default, one of your choice, or none.
export const weatherChoices = computed(() => [
  ["auto", t(key("weather_auto"))] as const,
  ["", t(key("weather_none"))] as const,
  ...state.inventory.entities
    .filter((e) => e.id.startsWith("weather."))
    .map((e) => [e.id, e.area ? `${e.name} · ${e.area}` : e.name] as const)
    .sort((a, b) => a[1].localeCompare(b[1])),
]);

// One line that says what a step will show, so the list reads without opening a step.
export function summary(kind: SaverKind): { text: string; missing?: boolean } {
  if (kind === "media") {
    if (!players.value.length) return { text: t(key("summary.media_none")), missing: true };
    return { text: players.value.map(entityName).join(", ") };
  }
  if (kind === "camera") {
    if (!saver.value?.camera) return { text: t(key("summary.camera_none")), missing: true };
    return { text: entityName(saver.value.camera) };
  }
  const weather = saver.value?.weather ?? "auto";
  const first = weather === "auto" ? t(key("summary.temperature")) : weather ? entityName(weather) : t(key("summary.time_date"));
  return { text: [first, ...saverItems().map(topbarLabel)].join(", ") };
}

// The clock as the glass draws it, for the small preview: the time, the date and the bottom line.
// The temperature's entity: the one chosen, else (automatic) Home Assistant's first weather entity, as the add-on picks.
export const weatherSource = computed(() => {
  const weather = saver.value?.weather ?? "auto";
  return weather === "auto" ? state.inventory.entities.find((e) => e.id.startsWith("weather."))?.id || "" : weather;
});
// The glass's proportions, so the preview is the screen's own shape (a square Guition, a wide 7-inch).
export const glassRatio = computed(() => {
  const shape = currentScreen.value?.shape as { width?: number; height?: number } | undefined;
  return shape?.width && shape?.height ? `${shape.width} / ${shape.height}` : "16 / 10";
});
export const clockPreview = computed(() => {
  const now = new Date(state.now);
  const degrees = weatherSource.value ? liveOf(weatherSource.value)?.a?.temperature : undefined;
  return {
    time: clockText(clock24.value, now, screenLanguage.value),
    date: dateText(now, screenLanguage.value),
    temperature: degrees !== undefined && degrees !== null && degrees !== "" ? `${Math.round(Number(degrees))}°` : null,
  };
});


// One dragged list: its rows follow the pointer and the new order is kept on release. Mouse and touch: a finger on the
// grip drags at once (the grip takes no scroll), a finger elsewhere on the row after a short hold, so the panel still
// scrolls. A finger on a control in the row is no drag. The arrow keys move the focused row.
export function sorter<T>(rows: string, items: () => readonly T[], commit: (list: T[]) => void, skip: string, enabled: () => boolean) {
  const drag = ref({ index: -1, active: false });
  const live = ref<T[] | null>(null) as Ref<T[] | null>;
  let start: { x: number; y: number } | null = null, timer = 0, pointerId: number | null = null, dragged = false;
  const all = () => [...document.querySelectorAll<HTMLElement>(rows)];
  function begin() {
    drag.value.active = true;
    live.value = [...items()];
    document.addEventListener("touchmove", block, { passive: false });
  }
  function block(e: TouchEvent) { if (drag.value.active) e.preventDefault(); }
  function track(e: PointerEvent) {
    if (e.pointerId !== pointerId || !start) return;
    if (!drag.value.active) {
      const distance = Math.hypot(e.clientX - start.x, e.clientY - start.y);
      if (e.pointerType === "touch") { if (distance > 10) { clearTimeout(timer); start = null; } return; }
      if (distance < 6) return;
      begin();
    }
    const to = dropIndex(all().map((row) => row.getBoundingClientRect()), drag.value.index, e.clientY);
    if (to !== drag.value.index && live.value) {
      live.value = moved(live.value, drag.value.index, to);
      drag.value.index = to;
    }
  }
  function end(e: PointerEvent) {
    if (e.pointerId !== pointerId) return;
    clearTimeout(timer);
    document.removeEventListener("pointermove", track);
    document.removeEventListener("pointerup", end);
    document.removeEventListener("pointercancel", end);
    document.removeEventListener("touchmove", block);
    dragged = drag.value.active;
    if (drag.value.active && e.type !== "pointercancel" && live.value && live.value.join() !== items().join()) commit(live.value);
    live.value = null;
    drag.value = { index: -1, active: false };
    start = null; pointerId = null;
  }
  function down(e: PointerEvent, i: number) {
    const el = e.target as HTMLElement;
    dragged = false;
    if (e.button !== 0 || !enabled() || pointerId !== null || el.closest(skip)) return;
    const grip = Boolean(el.closest(".grip"));
    if (grip) e.stopPropagation();
    if (e.pointerType !== "touch" && grip) e.preventDefault();
    drag.value = { index: i, active: false };
    start = { x: e.clientX, y: e.clientY };
    pointerId = e.pointerId;
    clearTimeout(timer);
    if (e.pointerType === "touch") { if (grip) begin(); else timer = window.setTimeout(begin, 260); }
    document.addEventListener("pointermove", track);
    document.addEventListener("pointerup", end);
    document.addEventListener("pointercancel", end);
  }
  // A drag that ends on the row it started on is no click: the row doesn't open after it.
  function click(e: MouseEvent) {
    if (!dragged) return false;
    dragged = false;
    e.preventDefault();
    e.stopPropagation();
    return true;
  }
  function key(e: KeyboardEvent, i: number) {
    if (e.target !== e.currentTarget) return;
    const step = ({ ArrowUp: -1, ArrowDown: 1 } as Record<string, number>)[e.key];
    const list = items();
    if (!step || i + step < 0 || i + step >= list.length) return;
    e.preventDefault();
    e.stopPropagation();
    commit(moved(list, i, i + step));
    requestAnimationFrame(() => all()[i + step]?.focus());
  }
  return { drag, live, down, key, click };
}

// The way back from an entity of the clock: the clock's own drawer.
export const clockCrumb = () => ({ text: saverLabel("clock"), open: () => openSaverStep("clock") });
