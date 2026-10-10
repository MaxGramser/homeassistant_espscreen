// The screensaver of the open screen as the editor shows it (app 0.4.48): what it shows in standby, in the order the
// screen tries it. The card in the settings and the drawer of one step both read and change it through here.
import { computed } from "vue";
import { t } from "./i18n";
import { moved } from "./model/reorder";
import { clockSample } from "./model/clock";
import { currentScreen, openSaverStep, saverItems, setScreensaver, settingValues, state, topbarLabel } from "./store";
import type { SaverKind, ScreensaverChoice } from "./types";
import { useUiStore } from "./stores/ui";
import { useRegionStore } from "./stores/region";
import { useEntitiesStore } from "./stores/entities";

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
  const entities = useEntitiesStore();
  if (kind === "media") {
    if (!players.value.length) return { text: t(key("summary.media_none")), missing: true };
    return { text: players.value.map((id) => entities.entityName(id)).join(", ") };
  }
  if (kind === "camera") {
    if (!saver.value?.camera) return { text: t(key("summary.camera_none")), missing: true };
    return { text: entities.entityName(saver.value.camera) };
  }
  const weather = saver.value?.weather ?? "auto";
  const first = weather === "auto" ? t(key("summary.temperature")) : weather ? entities.entityName(weather) : t(key("summary.time_date"));
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
  const clock = clockSample(useUiStore().now, useRegionStore().clock24, useRegionStore().screenLanguage);
  const degrees = weatherSource.value ? useEntitiesStore().liveOf(weatherSource.value)?.a?.temperature : undefined;
  return {
    time: clock.time,
    date: clock.date,
    temperature: degrees !== undefined && degrees !== null && degrees !== "" ? `${Math.round(Number(degrees))}°` : null,
  };
});


// The way back from an entity of the clock: the clock's own drawer.
export const clockCrumb = () => ({ text: saverLabel("clock"), open: () => openSaverStep("clock") });
