// The screensaver of the open screen as the editor shows it (app 0.4.48): what it shows in standby, in the order the screen
// tries it, and the clock's row of entities (app 0.4.81). The card in the settings and the drawer of one step both read
// and change it here; every change goes to the add-on through the screen store's setScreensaver, the latest one winning.
// Since app 0.4.89 also the photos of a folder of Home Assistant's media, and the screensavers of the plugins the screen
// runs (plugin API 0.14): a face of the clock, the music or the photos, or a step of its own in the order.
import { defineStore } from "pinia";
import { computed, reactive } from "vue";
import { getJson } from "../api";
import { t } from "../i18n";
import { clockSample } from "../model/clock";
import type { SaverFaceKind } from "../model/clock-faces";
import { moved } from "../model/reorder";
import { itemKey } from "../model/topbar";
import { pluginDefaults, text } from "../model/plugins";
import type { HeaderItem, PluginSaverKey, PluginValue, SaverKind, SaverPhotos, SaverPluginSetting, SaverStep, ScreensaverChoice } from "../types";
import { useEntitiesStore } from "./entities";
import { useInspectorStore } from "./inspector";
import { useInventoryStore } from "./inventory";
import { usePluginsStore } from "./plugins";
import { lookups } from "./lookup";
import { useRegionStore } from "./region";
import { useScreenStore } from "./screen";
import { useSettingsStore } from "./settings";
import { itemList, useTopbarStore } from "./topbar";
import { useUiStore } from "./ui";

export const SAVER_MIN_FIRMWARE = "0.29.0";
export const SAVER_ICONS: Record<SaverKind, string> = { media: "F075A", photos: "F02EF", camera: "F07AE", clock: "F0150" };
// The order of a screen that chose none, as the add-on's screen_saver.KINDS.
export const SAVER_ORDER: SaverKind[] = ["media", "photos", "camera", "clock"];
// Steps of plugins in the order, and plugin faces and steps with options kept, at most (screen_saver.PLUGIN_STEPS, PLUGIN_SETTINGS).
export const PLUGIN_STEPS_MAX = 4;
export const PLUGIN_SETTINGS_MAX = 8;
// The photos step (screen_saver.PHOTOS_DEFAULT and its choices): seconds a photo stands, the order and the fit.
export const PHOTOS_DEFAULT: SaverPhotos = { source: "", every: 60, order: "shuffle", fit: "auto", motion: "still" };
export const PHOTO_EVERY = [30, 60, 300, 900, 3600] as const;
export const PHOTO_ORDERS = ["shuffle", "in_order"] as const;
export const PHOTO_FITS = ["auto", "fill", "whole"] as const;
// Still, or a photo that fills the glass moving a pixel at a time (picture_motion.h in the firmware).
export const PHOTO_MOTIONS = ["still", "slow"] as const;
// The steps a plugin's face can stand in for.
export type FaceStep = "clock" | "media" | "photos";
// One level of Home Assistant's media sources (api/screensaver/photos): its folders and how many photos it holds right there.
export type PhotoFolder = { id: string; title: string; folders: { id: string; title: string; thumbnail?: boolean }[]; photos: number; failed?: boolean };
/** Whether a step is a plugin's (`plugin:<plugin>.<saver>`). */
export const isPluginKey = (step: unknown): step is PluginSaverKey => typeof step === "string" && /^plugin:[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$/.test(step);
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
  const insp = useInspectorStore();
  const plugins = usePluginsStore();

  const saver = computed(() => scr.currentScreen?.screensaver);
  const saverReady = computed(() => Boolean(saver.value?.ready));
  const standbyOn = computed(() => {
    const standby = settings.settingValues().standby_enabled;
    return standby !== false && standby !== 0;
  });
  const isOn = (step: SaverStep) => !saver.value?.off.includes(step);

  function changeSaver(patch: Partial<ScreensaverChoice>) {
    if (scr.currentScreen) scr.setScreensaver(scr.currentScreen, patch);
  }
  function toggleStep(step: SaverStep, on = !isOn(step)) {
    const off = (saver.value?.off || []).filter((k) => k !== step);
    changeSaver({ off: on ? off : [...off, step] });
  }

  // ---- The steps in the order the screen tries them ----
  // A board without pictures shows the clock and the plugins' steps; the photos only where the firmware takes them.
  const savedOrder = computed<SaverStep[]>(() => saver.value?.order || SAVER_ORDER);
  // The photos step on this screen: its board draws pictures and its firmware takes the step. Older apps called the flag
  // `photos` in the screen's list; a choice of photos is an object.
  const photosHere = computed(() => Boolean(saver.value?.pictures && (saver.value.photos_step ?? (saver.value.photos as unknown) === true)));
  const visible = (step: SaverStep) => isPluginKey(step) || step === "clock" || (Boolean(saver.value?.pictures) && (step !== "photos" || photosHere.value));
  function stepsShown(live: SaverStep[] | null) {
    return (live || savedOrder.value).filter(visible);
  }
  // The whole order from the steps shown in their new order: a step this screen does not show keeps its place.
  function withHidden(shown: SaverStep[]) {
    let next = 0;
    return savedOrder.value.map((step) => (visible(step) ? shown[next++] : step));
  }
  function setOrder(shown: SaverStep[]) {
    changeSaver({ order: withHidden(shown) });
  }
  function moveStep(step: SaverStep, by: number) {
    const list = stepsShown(null), from = list.indexOf(step);
    if (from < 0 || from + by < 0 || from + by >= list.length) return;
    setOrder(moved(list, from, from + by));
  }
  /** A step's place among those shown: "2 of 4" in its drawer. */
  function stepPlace(step: SaverStep) {
    const list = stepsShown(null);
    return { n: list.indexOf(step) + 1, count: list.length };
  }

  // ---- The screensavers of plugins (plugin API 0.14) ----
  const pluginSavers = computed(() => plugins.saversFor(scr.currentScreen ?? undefined));
  const pluginSteps = computed(() => savedOrder.value.filter(isPluginKey));
  // The steps of their own of the plugins this screen runs that are not in the order yet.
  const addableSteps = computed(() => pluginSavers.value.filter((s) => s.saver.step === "own" && !savedOrder.value.includes(s.key)));
  const canAddStep = computed(() => pluginSteps.value.length < PLUGIN_STEPS_MAX);
  // A plugin's options and entity, kept per face or step. Those no face or step uses any more go once there are too many.
  function withSettings(patch: Partial<ScreensaverChoice>, settings = saver.value?.plugins || {}) {
    const next = { ...saver.value, ...patch } as ScreensaverChoice;
    const used = new Set<string>([...next.order, next.face || "", next.media_face || "", next.photos_face || ""]);
    const kept = Object.keys(settings).length > PLUGIN_SETTINGS_MAX || patch.order
      ? Object.fromEntries(Object.entries(settings).filter(([key]) => used.has(key))) : settings;
    return { ...patch, plugins: kept };
  }
  /** Puts a plugin's step in the order, before the clock (which always shows, so a step after it never would). */
  function addPluginStep(key: PluginSaverKey) {
    if (!canAddStep.value || savedOrder.value.includes(key)) return;
    const order = [...savedOrder.value], clock = order.indexOf("clock");
    order.splice(clock < 0 ? order.length : clock, 0, key);
    changeSaver(withSettings({ order }));
    insp.openSaverStep(key);
  }
  function removePluginStep(key: PluginSaverKey) {
    changeSaver(withSettings({ order: savedOrder.value.filter((step) => step !== key), off: (saver.value?.off || []).filter((step) => step !== key) }));
    if (insp.inspector?.kind === "saver" && insp.inspector.step === key) insp.closeInspector();
  }
  const pluginSetting = (key: string): SaverPluginSetting => saver.value?.plugins?.[key] || { options: {}, entity: "" };
  /** A plugin face's or step's options as they stand: what is chosen over its defaults. */
  const pluginValues = (key: string): Record<string, PluginValue> => {
    const known = plugins.saverOf(key);
    return { ...(known ? pluginDefaults(known.saver) : {}), ...pluginSetting(key).options };
  };
  function setPluginSetting(key: string, patch: Partial<SaverPluginSetting>) {
    const settings = { ...(saver.value?.plugins || {}), [key]: { ...pluginSetting(key), ...patch } };
    changeSaver(withSettings({}, settings));
  }
  const setPluginOption = (key: string, option: string, value: PluginValue) => setPluginSetting(key, { options: { ...pluginSetting(key).options, [option]: value } });
  const setPluginEntity = (key: string, entity: string) => setPluginSetting(key, { entity });
  /** The plugin faces of a step on this screen. */
  const facesFor = (step: FaceStep) => pluginSavers.value.filter((s) => s.saver.step === step);
  /** The plugin face a step shows, '' for the screen's own. */
  function faceOf(step: FaceStep): "" | PluginSaverKey {
    const chosen = step === "clock" ? saver.value?.face : step === "media" ? saver.value?.media_face : saver.value?.photos_face;
    return isPluginKey(chosen) ? chosen : "";
  }
  function setFace(step: FaceStep, key: "" | PluginSaverKey) {
    if (step === "clock") changeSaver(withSettings({ face: key || "digital" }));
    else changeSaver(withSettings(step === "media" ? { media_face: key } : { photos_face: key }));
  }
  /** A step's name and icon: the screen's own, or the plugin's (by its key while the editor does not know it). */
  function stepLabel(step: SaverStep) {
    if (!isPluginKey(step)) return saverLabel(step);
    const known = plugins.saverOf(step);
    return known ? text(known.saver.name) : step.slice("plugin:".length);
  }
  function stepIcon(step: SaverStep) {
    if (!isPluginKey(step)) return SAVER_ICONS[step];
    const known = plugins.saverOf(step);
    return known?.saver.icon || known?.plugin.icon || "F0A66";
  }
  // A plugin's step whose plugin is not on this screen (any more) shows nothing there.
  const pluginHere = (key: string) => pluginSavers.value.some((s) => s.key === key);

  // ---- The photos step (app 0.4.89) ----
  const photos = computed<SaverPhotos>(() => {
    const chosen = saver.value?.photos;
    return chosen && typeof chosen === "object" ? { ...PHOTOS_DEFAULT, ...chosen } : PHOTOS_DEFAULT;
  });
  const setPhotos = (patch: Partial<SaverPhotos>) => changeSaver({ photos: { ...photos.value, ...patch } });
  // The titles of the folders seen while browsing, so the card names the chosen one; asked once for one it never saw.
  const folderTitles = reactive<Record<string, string>>({});
  const asked = new Set<string>();
  async function browseFolder(id: string): Promise<PhotoFolder> {
    try {
      const folder = await getJson<PhotoFolder>(`screensaver/photos?id=${encodeURIComponent(id)}`);
      if (folder.title) folderTitles[folder.id || id] = folder.title;
      for (const sub of folder.folders || []) if (sub.title) folderTitles[sub.id] = sub.title;
      return { ...folder, folders: folder.folders || [], photos: folder.photos || 0 };
    } catch {
      return { id, title: "", folders: [], photos: 0, failed: true };
    }
  }
  function folderTitle(id: string) {
    if (folderTitles[id]) return folderTitles[id];
    if (id && !asked.has(id)) { asked.add(id); void browseFolder(id); }
    // Until then the last part of its id, as a person named the folder.
    const last = id.replace(/\/+$/, "").split(/[/|]/).pop() || id;
    try { return decodeURIComponent(last); } catch { return last; }
  }

  // The players of the music step (app 0.4.54), the first that plays with a cover shows.
  const players = computed(() => [saver.value?.media, ...(saver.value?.more || [])].filter((id): id is string => Boolean(id)));
  // A player that leaves the step takes the devices it counted on along (`play_on`).
  const setPlayers = (list: string[]) => changeSaver({ media: list[0] || "", more: list.slice(1),
    play_on: Object.fromEntries(Object.entries(saver.value?.play_on || {}).filter(([id]) => list.includes(id))) });
  const addPlayer = (id: string) => players.value.length < MAX_PLAYERS && !players.value.includes(id) && setPlayers([...players.value, id]);
  const removePlayer = (id: string) => setPlayers(players.value.filter((p) => p !== id));
  // The devices a player counts on (GitHub #182), by the names of its `source`; none: wherever it plays.
  const playOnOf = (id: string) => saver.value?.play_on?.[id] || [];
  function setPlayOn(id: string, names: string[]) {
    const { [id]: _old, ...rest } = saver.value?.play_on || {};
    changeSaver({ play_on: names.length ? { ...rest, [id]: names } : rest });
  }

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
    items: () => saverItems.value, set: setSaverItems, max: () => SAVER_ITEMS_MAX, open: (index) => insp.openSaverItem(index), inspector: "saver-item",
    label: (item) => topbar.topbarLabel(item), toast: (message, action) => ui.toast(message, action),
    // The new entity lights up briefly in the row at the head, as a new item does in the top bar.
    added: (item) => { topbar.topbarAdded = { key: itemKey(item), time: Date.now() }; },
    // One entity once: the clock has no room for the same one twice, whatever it shows of it.
    same: (a, b) => a.entity === b.entity,
    full: () => t("editor.screen_settings.screensaver.items_full", { n: SAVER_ITEMS_MAX }),
    already: () => t("editor.screen_settings.screensaver.items_already"),
    removed: (name) => t("editor.screen_settings.screensaver.items_removed", { name }),
    // An entity taken off in its own drawer leads back to the clock it stood on.
    back: () => insp.openSaverStep("clock"),
  });

  // One line that says what a step will show, so the list reads without opening a step.
  function summary(kind: SaverStep): { text: string; missing?: boolean } {
    if (isPluginKey(kind)) {
      const known = plugins.saverOf(kind);
      if (!known || !pluginHere(kind)) return { text: t(key("summary.plugin_gone")), missing: true };
      const entity = pluginSetting(kind).entity;
      if (known.saver.domains?.length && !entity) return { text: t(key("summary.plugin_entity")), missing: true };
      return { text: entity ? entities.entityName(entity) : text(known.plugin.name) };
    }
    if (kind === "photos") {
      if (!photos.value.source) return { text: t(key("summary.photos_none")), missing: true };
      return { text: [faceName("photos"), folderTitle(photos.value.source)].filter(Boolean).join(", ") };
    }
    if (kind === "media") {
      if (!players.value.length) return { text: t(key("summary.media_none")), missing: true };
      const named = (id: string) => (playOnOf(id).length ? t(key("play_on_summary"), { name: entities.entityName(id), devices: playOnOf(id).join(", ") })
        : entities.entityName(id));
      return { text: [faceName("media"), ...players.value.map(named)].filter(Boolean).join(", ") };
    }
    if (kind === "camera") {
      if (!saver.value?.camera) return { text: t(key("summary.camera_none")), missing: true };
      return { text: entities.entityName(saver.value.camera) };
    }
    const weather = saver.value?.weather ?? "auto";
    const first = weather === "auto" ? t(key("summary.temperature")) : weather ? entities.entityName(weather) : t(key("summary.time_date"));
    // A plugin's face gets the temperature and the entities as the digital clock has them.
    if (clockPluginFace.value) return { text: [faceName("clock"), first, ...saverItems.value.map((item) => topbar.topbarLabel(item))].join(", ") };
    // Glass and Bauhaus show the face alone; Classic and the digital clock the temperature and the entities too.
    if (face.value === "glass" || face.value === "bauhaus") return { text: t(key(`faces.${face.value}`)) };
    const named = face.value === "classic" ? [t(key("faces.classic"))] : [];
    return { text: [...named, first, ...saverItems.value.map((item) => topbar.topbarLabel(item))].join(", ") };
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
  // ---- The clock's faces (module clock_faces): only where the board has them, and the digital clock everywhere else.
  const facesHere = computed(() => Boolean(saver.value?.faces));
  // A plugin's face of the clock stands in for the digital one (`face` is the screen's own face then).
  const clockPluginFace = computed(() => faceOf("clock"));
  const face = computed<SaverFaceKind>(() => {
    const chosen = saver.value?.face;
    return (facesHere.value && chosen && !isPluginKey(chosen) && chosen) || "digital";
  });
  /** The name of the plugin face a step shows, '' for the screen's own. */
  function faceName(step: FaceStep) {
    const chosen = faceOf(step);
    return chosen ? stepLabel(chosen) : "";
  }
  const glassSize = computed(() => {
    const shape = scr.currentScreen?.shape as { width?: number; height?: number } | undefined;
    return { width: shape?.width || 800, height: shape?.height || 480 };
  });
  // The face's own look: dark, light, or the screen's Dark mode.
  const faceDark = computed(() => {
    const look = saver.value?.look || "dark";
    if (look !== "auto") return look === "dark";
    const dark = settings.settingValues().dark_mode;
    return dark === true || dark === 1;
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

  return {
    saver, saverReady, standbyOn, savedOrder, players, cameraChoices, weatherChoices, saverItems, weatherSource, glassRatio, clockPreview,
    facesHere, face, glassSize, faceDark, photosHere, photos, folderTitles, pluginSteps, addableSteps, canAddStep, clockPluginFace,
    // What the card and the drawers read as they draw (stores/lookup.ts).
    ...lookups({ isOn, stepsShown, stepPlace, entityPlace, entitiesOf, summary, stepLabel, stepIcon, pluginHere, pluginSetting, pluginValues,
      facesFor, faceOf, faceName, folderTitle, playOnOf }),
    changeSaver, toggleStep, moveStep, setOrder, setPlayers, addPlayer, removePlayer, setPlayOn, setSaverItems, addPluginStep, removePluginStep,
    setPluginOption, setPluginEntity, setFace, setPhotos, browseFolder,
    addSaverItem: saverList.add, updateSaverItem: saverList.update, moveSaverItem: saverList.move, removeSaverItem: saverList.remove,
  };
});
