// The screensaver of the open screen as the editor shows it (app 0.4.48): what it shows in standby, in the order the screen
// tries it, and the clock's row of entities (app 0.4.81). The card in the settings and the drawer of one step both read
// and change it here; every change goes to the add-on through the screen store's setScreensaver, the latest one winning.
import { defineStore } from "pinia";
import { computed } from "vue";
import { t } from "../i18n";
import { clockSample } from "../model/clock";
import { moved } from "../model/reorder";
import { openSaverItem, openSaverStep } from "../store";
import type { HeaderItem, SaverKind, ScreensaverChoice } from "../types";
import { useEntitiesStore } from "./entities";
import { useInventoryStore } from "./inventory";
import { lookups } from "./lookup";
import { useRegionStore } from "./region";
import { useScreenStore } from "./screen";
import { useSettingsStore } from "./settings";
import { itemList, useTopbarStore } from "./topbar";
import { useUiStore } from "./ui";

export const SAVER_MIN_FIRMWARE = "0.29.0";
export const SAVER_ICONS: Record<SaverKind, string> = { media: "F075A", camera: "F07AE", clock: "F0150" };
export const MAX_PLAYERS = 4;
// The clock's row of entities: the top bar's entity items, shown by their state, their icon or both, in the drawer the top
// bar uses. At most four, in the order they stand on the glass after the temperature.
export const SAVER_ITEMS_MAX = 4;
const DOMAINS: Record<"media" | "camera", string[]> = { media: ["media_player"], camera: ["camera", "image"] };
const key = (name: string) => `editor.screen_settings.screensaver.${name}`;
/** A step's name: Music, Camera or Clock. */
export const saverLabel = (kind: SaverKind) => t(key(`kinds.${kind}`));

export const useScreensaverStore = defineStore("screensaver", () => {
  const inv = useInventoryStore();
  const ui = useUiStore();
  const scr = useScreenStore();
  const settings = useSettingsStore();
  const entities = useEntitiesStore();
  const region = useRegionStore();
  const topbar = useTopbarStore();

  const saver = computed(() => scr.currentScreen?.screensaver);
  const saverReady = computed(() => Boolean(saver.value?.ready));
  const standbyOn = computed(() => {
    const standby = settings.settingValues().standby_enabled;
    return standby !== false && standby !== 0;
  });
  const isOn = (kind: SaverKind) => !saver.value?.off.includes(kind);

  function changeSaver(patch: Partial<ScreensaverChoice>) {
    if (scr.currentScreen) scr.setScreensaver(scr.currentScreen, patch);
  }
  function toggleStep(kind: SaverKind, on = !isOn(kind)) {
    const off = (saver.value?.off || []).filter((k) => k !== kind);
    changeSaver({ off: on ? off : [...off, kind] });
  }

  // The steps in the order the screen tries them. A board without pictures shows the clock alone.
  const savedOrder = computed<SaverKind[]>(() => saver.value?.order || ["media", "camera", "clock"]);
  function stepsShown(live: SaverKind[] | null) {
    const list = live || savedOrder.value;
    return saver.value?.pictures ? list : list.filter((kind) => kind === "clock");
  }
  function moveStep(kind: SaverKind, by: number) {
    const list = savedOrder.value, from = list.indexOf(kind);
    if (from < 0 || from + by < 0 || from + by >= list.length) return;
    changeSaver({ order: moved(list, from, from + by) });
  }

  // The players of the music step (app 0.4.54), the first that plays with a cover shows.
  const players = computed(() => [saver.value?.media, ...(saver.value?.more || [])].filter((id): id is string => Boolean(id)));
  const setPlayers = (list: string[]) => changeSaver({ media: list[0] || "", more: list.slice(1) });
  const addPlayer = (id: string) => players.value.length < MAX_PLAYERS && !players.value.includes(id) && setPlayers([...players.value, id]);
  const removePlayer = (id: string) => setPlayers(players.value.filter((p) => p !== id));

  const entityPlace = (id: string) => inv.entityOf(id)?.area || "";
  // What one can choose for a step, by name and the area it is in.
  function entitiesOf(kind: "media" | "camera", taken: string[] = []) {
    return inv.inventory.entities
      .filter((e) => DOMAINS[kind].includes(e.id.split(".")[0]) && !taken.includes(e.id))
      .map((e) => ({ id: e.id, name: e.name, area: e.area || "" }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }
  const cameraChoices = computed(() => [
    ["", t(key("choose_camera"))] as const,
    ...entitiesOf("camera").map((e) => [e.id, e.area ? `${e.name} · ${e.area}` : e.name] as const),
  ]);
  // The temperature under the clock (app 0.4.52): Home Assistant's own by default, one of your choice, or none.
  const weatherChoices = computed(() => [
    ["auto", t(key("weather_auto"))] as const,
    ["", t(key("weather_none"))] as const,
    ...inv.inventory.entities
      .filter((e) => e.id.startsWith("weather."))
      .map((e) => [e.id, e.area ? `${e.name} · ${e.area}` : e.name] as const)
      .sort((a, b) => a[1].localeCompare(b[1])),
  ]);

  // ---- The clock's row of entities (app 0.4.81) ----
  const saverItems = computed<HeaderItem[]>(() => scr.currentScreen?.screensaver?.items || []);
  function setSaverItems(items: HeaderItem[]) {
    const screen = scr.currentScreen;
    if (screen) scr.setScreensaver(screen, { items });
  }
  const saverList = itemList({
    items: () => saverItems.value, set: setSaverItems, max: () => SAVER_ITEMS_MAX, open: openSaverItem, inspector: "saver-item",
    label: (item) => topbar.topbarLabel(item), toast: (message, action) => ui.toast(message, action),
    // One entity once: the clock has no room for the same one twice, whatever it shows of it.
    same: (a, b) => a.entity === b.entity,
    full: () => t("editor.screen_settings.screensaver.items_full", { n: SAVER_ITEMS_MAX }),
    already: () => t("editor.screen_settings.screensaver.items_already"),
    removed: (name) => t("editor.screen_settings.screensaver.items_removed", { name }),
    // An entity taken off in its own drawer leads back to the clock it stood on.
    back: () => openSaverStep("clock"),
  });

  // One line that says what a step will show, so the list reads without opening a step.
  function summary(kind: SaverKind): { text: string; missing?: boolean } {
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
    return { text: [first, ...saverItems.value.map((item) => topbar.topbarLabel(item))].join(", ") };
  }

  // The clock as the glass draws it, for the small preview: the time, the date and the bottom line.
  // The temperature's entity: the one chosen, else (automatic) Home Assistant's first weather entity, as the add-on picks.
  const weatherSource = computed(() => {
    const weather = saver.value?.weather ?? "auto";
    return weather === "auto" ? inv.inventory.entities.find((e) => e.id.startsWith("weather."))?.id || "" : weather;
  });
  // The glass's proportions, so the preview is the screen's own shape (a square Guition, a wide 7-inch).
  const glassRatio = computed(() => {
    const shape = scr.currentScreen?.shape as { width?: number; height?: number } | undefined;
    return shape?.width && shape?.height ? `${shape.width} / ${shape.height}` : "16 / 10";
  });
  const clockPreview = computed(() => {
    const clock = clockSample(ui.now, region.clock24, region.screenLanguage);
    const degrees = weatherSource.value ? entities.liveOf(weatherSource.value)?.a?.temperature : undefined;
    return {
      time: clock.time,
      date: clock.date,
      temperature: degrees !== undefined && degrees !== null && degrees !== "" ? `${Math.round(Number(degrees))}°` : null,
    };
  });
  // The way back from an entity of the clock: the clock's own drawer.
  const clockCrumb = () => ({ text: saverLabel("clock"), open: () => openSaverStep("clock") });

  return {
    saver, saverReady, standbyOn, savedOrder, players, cameraChoices, weatherChoices, saverItems, weatherSource, glassRatio, clockPreview,
    // What the card and the drawers read as they draw (stores/lookup.ts).
    ...lookups({ isOn, stepsShown, entityPlace, entitiesOf, summary, clockCrumb }),
    changeSaver, toggleStep, moveStep, setPlayers, addPlayer, removePlayer, setSaverItems,
    addSaverItem: saverList.add, updateSaverItem: saverList.update, moveSaverItem: saverList.move, removeSaverItem: saverList.remove,
  };
});
