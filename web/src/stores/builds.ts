// ---- Builds: one source for "something is building" ----
// The add-on says per screen what is being built for it now, whoever asked (inventory.builds, Manager.builds): an update,
// a plugin build, an install from Firmware & USB. Every part of the page that shows a build reads it here: the screen
// list, the Plugins entry and tab, the settings' Updates card and the build log. `updating` holds the screens the page
// just asked to build, for the moment until the add-on's builds name them. Updates start here too (one screen, all of
// them, automatic), and the add-on's firmware job is asked for here, once for whoever follows it.
import { defineStore } from "pinia";
import { computed, onScopeDispose, ref, shallowRef } from "vue";
import { getJson, send } from "../api";
import { t } from "../i18n";
import * as status from "../model/screen-status";
import { refresh, state } from "../store";
import type { Build, Screen } from "../types";
import { lookups } from "./lookup";
import { useUiStore } from "./ui";

// How often the firmware job is asked for while someone follows it (composables/useFirmwareJob.ts), unless one wants more.
export const FIRMWARE_POLL_MS = 3000;
export type FirmwareJob = { job: any; logs: string[] };

export const useBuildsStore = defineStore("builds", () => {
  const ui = useUiStore();

  const updating = ref<string[]>([]);
  const buildOf = (screen: Screen): Build | null => state.inventory.builds?.[screen.id] ?? null;
  const asked = (screen: Screen) => updating.value.includes(screen.id);
  /** What the page knows of a screen's build (model/screen-status.ts): the add-on's, and whether the page just asked. */
  const building = (screen: Screen): status.Building => ({ build: buildOf(screen), asked: asked(screen) });
  const isBuilding = (screen: Screen) => status.isBuilding(building(screen));
  const anyBuilding = computed(() => Object.values(state.inventory.builds || {}).some((build) => build.state === "running") || updating.value.length > 0);
  // The screens with a build on the way, running first.
  const buildingScreens = computed(() => state.inventory.screens.filter((screen) => buildOf(screen) || asked(screen))
    .sort((a, b) => Number(isBuilding(b)) - Number(isBuilding(a))));
  // What a running build is doing in words, and how far it is (model/screen-status.ts).
  const buildText = (screen: Screen) => status.buildText(screen, buildOf(screen));
  const buildProgress = (screen: Screen) => status.buildProgress(screen, building(screen));
  // ---- Updates with content (app 0.2.73): what a screen gets ----
  const whatsNew = (screen: Screen) => status.whatsNew(screen, state.inventory.changelog, state.inventory.updates?.target);

  /** A new inventory: a screen the add-on names a build for is no longer only asked for. */
  function prune() {
    for (const screen of state.inventory.screens) if (buildOf(screen)) forget(screen.id);
  }
  /** A screen that went (removed) or whose build could not start. */
  function forget(id: string) {
    if (updating.value.includes(id)) updating.value = updating.value.filter((other) => other !== id);
  }

  // ---- Updates ----
  // `reinstall` builds the screen again although it runs this firmware: the dev channel's newest dev keeps its number.
  async function startUpdate(screen: Screen, host?: string, reinstall = false) {
    updating.value.push(screen.id);
    try {
      await send(`screens/${encodeURIComponent(screen.id)}/update`, "POST", { ...(host ? { host } : {}), ...(reinstall ? { reinstall } : {}) });
      await refresh();
    } catch (e: any) {
      forget(screen.id);
      ui.toast(e.message);
    }
  }
  async function runUpdateAll() {
    try {
      await send("updates/run", "POST");
      await refresh();
    } catch (e: any) {
      ui.toast(e.message);
    }
  }
  async function setAutoUpdate(auto: boolean) {
    try {
      await send("updates", "PUT", { auto });
      if (state.inventory.updates) state.inventory.updates.auto = auto;
      ui.toast(t(auto ? "editor.settings.updates.auto_on" : "editor.settings.updates.auto_off"));
    } catch (e: any) {
      ui.toast(e.message);
    }
  }

  // ---- The add-on's firmware job (api/firmware), asked for once whoever follows it ----
  // New screen, Firmware & USB, a YAML check and the build log all read the same answer: whoever asks while a request is on
  // its way gets its answer, and one asking with `fresh` (how old an answer may be) takes the last one when it is that
  // young. The one poll they all follow is composables/useFirmwareJob.ts. The newest answer is `answer`, and the job and
  // its log are kept for the build log (BuildLog).
  const answer = shallowRef<any>(null);
  const firmwareJob = ref<FirmwareJob | null>(null);
  let flight: Promise<any> | null = null, answeredAt = 0;
  function fetchFirmware(fresh = 0): Promise<any> {
    if (fresh && answer.value && Date.now() - answeredAt < fresh) return Promise.resolve(answer.value);
    if (flight) return flight;
    const asking: Promise<any> = getJson("firmware").then((data) => {
      if (flight === asking) {
        answer.value = data; answeredAt = Date.now();
        firmwareJob.value = { job: data.job, logs: data.logs || [] };
      }
      return data;
    }).finally(() => { if (flight === asking) flight = null; });
    return (flight = asking);
  }
  async function loadFirmwareJob() {
    try { await fetchFirmware(); } catch { /* Keep what we have. */ }
  }
  // A request on its way when the store goes keeps its answer to itself.
  onScopeDispose(() => { flight = null; });

  return {
    updating, ...lookups({ buildOf, building, isBuilding, buildText, buildProgress, whatsNew }), anyBuilding, buildingScreens, prune, forget,
    startUpdate, runUpdateAll, setAutoUpdate, answer, firmwareJob, fetchFirmware, loadFirmwareJob,
  };
});
