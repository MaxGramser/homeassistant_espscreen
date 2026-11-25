// ---- Builds: one source for "something is building" ----
// The add-on builds one firmware at a time, and everything that builds waits its turn in its one build line
// (build_queue.py, docs/BUILDS.md): updates, plugin builds, New screen, Firmware & USB and the YAML check. Every live
// answer of the add-on (the inventory, pushed whenever the line changes) holds the line itself (`line`: every build by
// its id, what runs, what waits and the last ones that ended with their outcome) and, from the same look at it, what is
// built for each screen now (`builds`, Manager.builds). That one answer is the one source; the firmware answer
// (api/firmware), asked only while something builds, adds ESPHome's log of the build that runs. Every part of the page
// that shows a build reads it here: the screen list, the Plugins entry and tab,
// the settings' Updates card, the build log, New screen, Firmware & USB and the YAML check (useLineBuild follows one).
// `updating` holds the screens the page just asked to update, for the moment until the add-on's builds name them.
// Updates start here too (one screen, all of them, automatic), and so does every other build the page asks for
// (askBuild), and the add-on's firmware job is asked for here, once for whoever follows it.
import { defineStore } from "pinia";
import { computed, onScopeDispose, ref, shallowRef } from "vue";
import { getJson, send } from "../api";
import { t } from "../i18n";
import { type BuildFilesView, freedBy, sizeText } from "../model/build-files";
import * as status from "../model/screen-status";
import type { Build, LineBuild, Screen } from "../types";
import { askConfirm } from "../composables/useConfirm";
import { useInventoryStore } from "./inventory";
import { lookups } from "./lookup";
import { useUiStore } from "./ui";

// How often the firmware job is asked for while someone follows it (composables/useFirmwareJob.ts), unless one wants more.
export const FIRMWARE_POLL_MS = 3000;
export type FirmwareJob = { job: any; logs: string[] };
/** Where a build log the add-on keeps on disk is downloaded (build_logs.py): relative, so it works behind ingress. */
export const buildLogHref = (key: string) => `api/firmware/logs/${encodeURIComponent(key)}`;
/** A build log kept on disk, as api/firmware/logs lists it (newest first). */
export type KeptLog = { key: string; by?: string; file?: string | null; screen?: string | null; plugins?: string[];
  started?: number; finished?: number; state: string; reason?: string | null; size: number };

export const useBuildsStore = defineStore("builds", () => {
  const inv = useInventoryStore();
  const ui = useUiStore();

  const updating = ref<string[]>([]);
  const buildOf = (screen: Screen): Build | null => inv.inventory.builds?.[screen.id] ?? null;
  const asked = (screen: Screen) => updating.value.includes(screen.id);
  /** What the page knows of a screen's build (model/screen-status.ts): the add-on's, and whether the page just asked. */
  const building = (screen: Screen): status.Building => ({ build: buildOf(screen), asked: asked(screen) });
  const isBuilding = (screen: Screen) => status.isBuilding(building(screen));
  const anyBuilding = computed(() => Object.values(inv.inventory.builds || {}).some((build) => build.state === "running") || updating.value.length > 0);
  // The screens with a build on the way, running first.
  const buildingScreens = computed(() => inv.inventory.screens.filter((screen) => buildOf(screen) || asked(screen))
    .sort((a, b) => Number(isBuilding(b)) - Number(isBuilding(a))));
  // What a running build is doing in words, and how far it is (model/screen-status.ts).
  const buildText = (screen: Screen) => status.buildText(screen, buildOf(screen));
  const buildProgress = (screen: Screen) => status.buildProgress(screen, building(screen));
  // ---- Updates with content (app 0.2.73): what a screen gets ----
  const whatsNew = (screen: Screen) => status.whatsNew(screen, inv.inventory.changelog, inv.inventory.updates?.target);

  /** A new inventory: a screen the add-on names a build for is no longer only asked for, and a build the page watched
   * that no longer runs has ended (watchEnds). */
  function prune() {
    for (const screen of inv.inventory.screens) if (buildOf(screen)) forget(screen.id, false);
    watchEnds();
  }
  /** A screen that went (removed) or whose build could not start: nothing of it is watched any more either. */
  function forget(id: string, unwatch = true) {
    if (updating.value.includes(id)) updating.value = updating.value.filter((other) => other !== id);
    if (unwatch && watched.value[id]) delete watched.value[id];
  }

  // ---- A build that ends while the page is open (model/screen-status.ts watchOf, buildOutcome) ----
  // Every build this page asked for or saw on its way, by screen, with what the page knew when it began to watch it.
  // One that ended says so on whatever view is open: ready, or failed with the way to its log. What ended before the
  // page was opened is never said: the page did not watch it.
  const watched = ref<Record<string, status.Watched>>({});
  function begin(screen: Screen) {
    watched.value[screen.id] = status.watchOf(screen, buildOf(screen));
  }
  function watchEnds() {
    const ended: { screen: Screen; watch: status.Watched }[] = [];
    const ids = new Set(inv.inventory.screens.map((screen) => screen.id));
    for (const id of Object.keys(watched.value)) if (!ids.has(id)) delete watched.value[id];
    for (const screen of inv.inventory.screens) {
      const build = buildOf(screen), seen = watched.value[screen.id];
      if ((build || asked(screen)) && !seen) begin(screen);
      // An update the page asked for may come back as another kind of build (the add-on's own name for it), and a plugin
      // build may become the update of its screen (the two are one build): the page follows what it is now.
      else if (build && seen && (seen.by !== build.by || seen.id !== (build.id ?? seen.id) || (build.file && seen.file !== build.file)))
        Object.assign(seen, { by: build.by, file: build.file ?? seen.file, id: build.id ?? seen.id });
      else if (!build && !asked(screen) && seen) { ended.push({ screen, watch: seen }); delete watched.value[screen.id]; }
    }
    if (ended.length) told(ended);
  }
  // A plugin build's or an install's outcome is the one the build line keeps for it by its id: in the same answer that
  // no longer names the build for its screen.
  function told(ended: { screen: Screen; watch: status.Watched }[]) {
    const ends: status.BuildEnd[] = [];
    for (const { screen, watch: seen } of ended) {
      const outcome = status.buildOutcome(screen, seen, line.value);
      if (outcome) ends.push({ screen, by: seen.by, outcome });
    }
    const said = status.buildEndText(ends);
    if (!said) return;
    // A failed plugin build goes to its screen's Plugins tab, where it says why with its log; any other to Firmware & USB.
    const plugin = ends.find((end) => end.outcome === "failed" && end.by === "plugins");
    if (said.failed && plugin) ui.toast(said.text, { label: t("editor.build.show_why"), run: () => showPlugins(plugin.screen) });
    else if (said.failed) ui.toast(said.text, { label: t("editor.build.show_log"), run: () => ui.go("#firmware") });
    else if (offerClean()) {
      // The build files grew large (build_files.py `offer`): the build that ended offers the clean-up, once a page.
      offered.value = true;
      ui.toast(said.text, { label: t("editor.settings.build_files.offer", { size: sizeText(inv.inventory.build_files!.sizes!.folders) }), run: () => cleanBuildFiles("folders") });
    }
    else ui.toast(said.text);
  }

  async function showPlugins(screen: Screen) {
    const { useSessionStore } = await import("./session");   // the session store reads this one: asked when needed
    await useSessionStore().openTab(screen.id, "plugins");
  }

  // ---- Build files (build_files.py, docs/BUILDS.md "Build files"): the room the builds take, and the clean-up ----
  const offered = ref(false);
  const cleaningFiles = ref(false);
  /** Whether a build that ended offers the clean-up: the add-on says the build folders are large, nothing more is on its
   * way, and this page did not offer it before. */
  const offerClean = () => !offered.value && !!inv.inventory.build_files?.offer && !!inv.inventory.build_files.sizes
    && !line.value.some((build) => build.state === "queued" || build.state === "running");
  function takeBuildFiles(next: BuildFilesView) {
    inv.inventory = { ...inv.inventory, build_files: next };
  }
  async function cleanBuildFiles(level: "folders" | "all") {
    const files = inv.inventory.build_files;
    const size = sizeText(freedBy(files?.sizes, level));
    const yes = await askConfirm(t(level === "all" ? "editor.settings.build_files.clean_all_confirm" : "editor.settings.build_files.clean_confirm", { size }),
      { confirm: t("editor.settings.build_files.clean_go"), danger: level === "all" });
    if (!yes) return;
    cleaningFiles.value = true;
    try {
      const next = await send<BuildFilesView>("build-files/clean", "POST", { level });
      takeBuildFiles(next);
      ui.toast(next.last?.freed ? t("editor.settings.build_files.cleaned", { size: sizeText(next.last.freed) }) : t("editor.settings.build_files.cleaned_nothing"));
    } catch (e: any) {
      ui.toast(e.message);
    } finally {
      cleaningFiles.value = false;
    }
  }
  async function declineBuildFiles() {
    try { takeBuildFiles(await send<BuildFilesView>("build-files/decline", "POST", {})); } catch (e: any) { ui.toast(e.message); }
  }
  async function setAutoClean(auto: boolean) {
    try {
      takeBuildFiles(await send<BuildFilesView>("build-files", "PUT", { auto }));
      ui.toast(t(auto ? "editor.settings.build_files.auto_on" : "editor.settings.build_files.auto_off"));
    } catch (e: any) { ui.toast(e.message); }
  }

  // ---- Updates ----
  // `reinstall` builds the screen again although it runs this firmware: the dev channel's newest dev keeps its number.
  async function startUpdate(screen: Screen, host?: string, reinstall = false) {
    updating.value.push(screen.id);
    if (!watched.value[screen.id]) begin(screen);
    try {
      await send(`screens/${encodeURIComponent(screen.id)}/update`, "POST", { ...(host ? { host } : {}), ...(reinstall ? { reinstall } : {}) });
      await inv.refresh();
    } catch (e: any) {
      forget(screen.id);
      ui.toast(e.message);
    }
  }
  // `reinstall`: Reinstall all from dev, every screen again with the newest dev (the dev channel's own, docs/RELEASING.md
  // "Testing dev"), one round in the build line like Update all.
  async function runUpdateAll(reinstall = false) {
    try {
      await send("updates/run", "POST", reinstall ? { reinstall } : undefined);
      await inv.refresh(false);
    } catch (e: any) {
      ui.toast(e.message);
    }
  }
  // The hour the nightly round may start (wish 113).
  async function setUpdateHour(hour: number) {
    try {
      await send("updates", "PUT", { hour });
      if (inv.inventory.updates) inv.inventory.updates.hour = hour;
    } catch (e: any) {
      ui.toast(e.message);
    }
  }
  /** The app is the dev version (added from the repository's `#dev` URL): its screens build from the dev branch. */
  const devChannel = computed(() => inv.inventory.updates?.channel === "dev");
  async function setAutoUpdate(auto: boolean) {
    try {
      await send("updates", "PUT", { auto });
      if (inv.inventory.updates) inv.inventory.updates.auto = auto;
      ui.toast(t(auto ? "editor.settings.updates.auto_on" : "editor.settings.updates.auto_off"));
    } catch (e: any) {
      ui.toast(e.message);
    }
  }

  // ---- The build line (the live inventory's `line`): every build by its id ----
  const line = computed<LineBuild[]>(() => inv.inventory.line || []);
  /** A build of the line by its id; null before the add-on named it, or once it is no longer kept. */
  const lineBuild = (id: number | null | undefined): LineBuild | null =>
    id === null || id === undefined ? null : line.value.find((build) => build.id === id) ?? null;
  /** Whether the line knows this build no more: it ended longer ago than the add-on keeps (a newer one is known). */
  const lineForgot = (id: number | null | undefined) =>
    id !== null && id !== undefined && !lineBuild(id) && line.value.some((build) => build.id > id);
  /** The newest build of a profile the line knows, on its way or ended: what a screen's build log shows. */
  const lineOf = (file: string | null | undefined): LineBuild | null =>
    (file && line.value.filter((build) => build.file === file && build.by !== "check").sort((a, b) => b.id - a.id)[0]) || null;
  /** A build that ended: it no longer waits or runs. */
  const lineEnded = (build: LineBuild | null | undefined) => Boolean(build && build.state !== "queued" && build.state !== "running");
  /** One ESPHome action the page asks for (New screen's retry, Firmware & USB, the YAML check). It waits its turn in the
   * line; the answer is the build, followed by its id, and the line comes with the next live answer. */
  // `chip_revision`: what the browser read from the chip on the cable, which the build is made for (docs/CHIP_REVISIONS.md).
  async function askBuild(request: { file: string; action: string; target?: string; chip_revision?: number | null }): Promise<LineBuild> {
    const build = await send<LineBuild>("firmware/jobs", "POST", request);
    await inv.refresh(false).catch(() => null);
    return build;
  }
  // The log of a build that ended is the add-on's to keep (api/firmware/builds/{id}/log), asked once per build; the log of
  // the one that runs is the firmware answer's own (`logs`), which every poll brings.
  const endedLogs = ref<Record<number, string[]>>({});
  const asking = new Map<number, Promise<string[]>>();
  function loadBuildLog(id: number): Promise<string[]> {
    if (endedLogs.value[id]) return Promise.resolve(endedLogs.value[id]);
    if (!asking.has(id))
      asking.set(id, getJson<{ build: LineBuild; logs: string[] }>(`firmware/builds/${id}/log`).then((data) => {
        if (lineEnded(data.build)) endedLogs.value[id] = data.logs || [];
        return data.logs || [];
      }).catch(() => []).finally(() => asking.delete(id)));
    return asking.get(id)!;
  }
  /** The lines of a build's log the page has: ESPHome's own while it runs and builds, its kept ones once it ended. */
  function buildLogOf(build: LineBuild | null | undefined): string[] {
    if (!build || build.state === "queued") return [];
    if (build.state === "running") {
      const job = answer.value?.job;
      return job && job.started && build.started && job.started >= build.started ? answer.value?.logs || [] : [];
    }
    return endedLogs.value[build.id] || [];
  }

  // ---- Build logs kept on disk (api/firmware/logs): every build's, also past a restart of the app ----
  // Asked once a view shows them (Firmware & USB, a screen's builds), and from then on again whenever a build ends
  // (refreshKeptLogs, from followBuilds): one list for every view.
  const keptLogs = ref<KeptLog[]>([]);
  let keptFollowed = false;
  async function loadKeptLogs() {
    keptFollowed = true;
    try { keptLogs.value = (await getJson<{ logs: KeptLog[] }>("firmware/logs")).logs || []; } catch { /* Keep what we have. */ }
  }
  /** A build ended: the kept logs again, when a view asked for them. */
  const refreshKeptLogs = () => (keptFollowed ? loadKeptLogs() : Promise.resolve());
  /** The ids of the builds that ended, as one key: what refreshKeptLogs follows. */
  const endedKey = computed(() => line.value.filter((build) => lineEnded(build)).map((build) => build.id).join(","));

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
    updating, ...lookups({ buildOf, building, isBuilding, buildText, buildProgress, whatsNew, lineBuild, lineForgot, lineOf, lineEnded, buildLogOf }),
    anyBuilding, buildingScreens, prune, forget, watched, line, devChannel,
    startUpdate, runUpdateAll, setAutoUpdate, setUpdateHour, askBuild, cleaningFiles, cleanBuildFiles, declineBuildFiles, setAutoClean, loadBuildLog, keptLogs, loadKeptLogs, refreshKeptLogs, endedKey, answer, firmwareJob, fetchFirmware, loadFirmwareJob,
  };
});
