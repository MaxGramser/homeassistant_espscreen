// New screen (app 0.4.32), as one flow its steps share (components/InstallerView.vue and components/install/): the form
// and which step it is at, what the add-on says of its boards, ports, Wi-Fi and firmware job (useFirmwareJob), and the
// installation once it runs, through this browser's own writing when that is the way. The steps only show and hide; the
// form, what it sends and when, is the one it always was. What it works out is model/installer.ts and
// model/install-progress.ts; whether the screen arrived on the network is useArrival.
import { computed, onBeforeUnmount, onMounted, proxyRefs, reactive, ref, watch } from "vue";
import { send } from "../api";
import { t } from "../i18n";
import { afterBrowserBuild, errorLine, firmwareImage, memoryText } from "../model/firmware-job";
import { customPreview, previewProfiles } from "../model/preview";
import { boardAbilities, boardList } from "../model/boards";
import { bestGrid as bestOf, boardOrientations, familyOf, goLabel, gridRange, installWays, nameClash, profileRequest, wayHint, wayTarget,
  type InstallForm, type SizeFilter } from "../model/installer";
import { elapsedText, followDetail, followTitle, installProgress, type Follow } from "../model/install-progress";
import { nodeName } from "../model/slug";
import { flashSupport } from "../flasher/logic";
import { useBrowserFlash } from "../flasher/session";
import type { BoardChoice, Orientation } from "../types";
import { useArrival } from "./useArrival";
import { useBusy } from "./useBusy";
import { useClock } from "./useClock";
import { useFirmwareJob } from "./useFirmwareJob";
import { useSessionStore } from "../stores/session";
import { useUiStore } from "../stores/ui";

export function useInstaller() {
  const ui = useUiStore(), session = useSessionStore();

  // Download: ESP Screens builds, the owner flashes the file from their own computer with ESPHome Web (ESPHOME_WEB).
  const form = reactive<InstallForm>({ board: "", orientation: "landscape", grid: { columns: 2, rows: 3 }, choices: {}, friendly_name: "", name: "",
    wifi_ssid: "", wifi_password: "", target: "" });
  const mode = ref<"physical" | "virtual">("physical");
  const installer = reactive({
    view: "setup" as "setup" | "progress" | "done", file: null as string | null, friendly: "", calibrate: false, target: "",
    apiKey: null as string | null, nodeEdited: false, jobState: null as string | null, picked: false, action: null as string | null,
    browser: false, chip: null as string | null,
  });
  // This computer (browser): the add-on builds as for Download, and this page writes the image over Web Serial, in Chrome
  // or Edge on a page served over https. The fallback for a screen that can't reach the Home Assistant machine; Download
  // stays for a browser that can't.
  const flash = useBrowserFlash();
  const support = flashSupport();
  const data = ref<any>(null);
  const job = ref<any>(null);
  const logs = ref<string[]>([]);
  const note = ref("");
  const status = ref("");
  const { busy: submitting, run: whileSubmitting } = useBusy();
  const logOpen = ref(false);
  const step = ref<1 | 2 | 3>(1);
  const query = ref("");
  const size = ref<SizeFilter>("");
  // Ready Wi-Fi can still be the wrong one: "Another network" asks for both lines again, written before the build.
  const wifiOther = ref(false);

  watch(() => form.friendly_name, () => { if (!installer.nodeEdited) form.name = nodeName(form.friendly_name); });
  // The boards and everything said about them come from the add-on (boards.yaml and the board files, through
  // boards.json): the list, each board's glass drawn to one scale, its abilities, its choices. Nothing here names a board.
  const boards = computed<Record<string, BoardChoice>>(() => data.value?.boards || {});
  const boardRows = computed(() => boardList(boards.value));
  const previews = computed(() => previewProfiles(boards.value));
  const previewForm = reactive({ profile: customPreview.key, width: 720, height: 720, columns: 2, rows: 3 });
  const previewProfile = computed(() => previews.value.find((profile) => profile.key === previewForm.profile) || customPreview);
  watch(() => previewForm.profile, () => Object.assign(previewForm, previewProfile.value.shape));
  const chosen = computed(() => boards.value[form.board]);
  const abilities = computed(() => (chosen.value ? boardAbilities(chosen.value) : []));
  // The choices besides the orientation (a CYD's display controller): each starts at the board file's own value. A value
  // says what it is (the display controller's model), and its first value is what most boards have.
  const choices = computed(() => Object.entries(chosen.value?.choices || {}).map(([key, options]) => ({ key, options })));
  // The first board until someone picks one, once the add-on has said which there are.
  watch(boardRows, (rows) => { if (!boards.value[form.board] && rows.length) form.board = rows[0].key; }, { immediate: true });
  // Which way the chosen board may hang, with the canvas and the cells of a page for each. A board this add-on has not
  // heard of asks nothing either, and builds lying down, which is what every board did before this choice existed.
  const orientations = computed(() => boardOrientations(boards.value[form.board]));
  // The grid it starts with (app 0.4.85): the board's own for the way it hangs, the best that board has, unless Advanced
  // chose another within the range that way takes. The editor changes it later beside the pages, without a new build.
  const side = computed(() => chosen.value?.orientations[form.orientation] || chosen.value?.orientations.landscape);
  const range = computed(() => gridRange(side.value));
  const bestGrid = () => { form.grid = bestOf(side.value); };
  const gridChosen = computed(() => form.grid.columns !== side.value?.columns || form.grid.rows !== side.value?.rows);
  // A board that hangs one way only is always built lying down; a board that was asked about keeps whatever was chosen.
  // Resetting it on every board change would throw away an answer the person just gave.
  watch(() => form.board, () => {
    if (!orientations.value.length) form.orientation = "landscape";
    form.choices = Object.fromEntries(choices.value.map((choice) => [choice.key, choice.options[0]]));
    bestGrid();
  }, { immediate: true });
  // Another way of hanging starts at that way's own grid.
  watch(() => form.orientation, bestGrid);
  const siblings = computed(() => familyOf(boardRows.value, chosen.value));
  // Names the screens this app knows already carry (app 0.2.123), said before anything is built.
  const clash = computed(() => nameClash(data.value?.taken || { nodes: [], prefixes: [] }, form.friendly_name, form.name));
  const ports = computed<string[]>(() => data.value?.ports || []);
  const wifi = computed(() => data.value?.wifi);
  const askWifi = computed(() => wifi.value?.state === "new" || wifi.value?.state === "missing");
  const wifiMissing = computed<string[]>(() => wifi.value?.missing || []);
  const wifiNote = computed(() => wifi.value?.state === "ready" ? t("editor.installer.wifi.ready") : wifi.value?.state === "invalid" ? t("editor.installer.wifi.invalid") : "");
  const busyElsewhere = computed(() => data.value?.job?.state === "running" && !(installer.file && data.value.job.file === installer.file));
  const goDisabled = computed(() => submitting.value || wifi.value?.state === "invalid" || form.target === "usb" ||
    (form.target === "browser" && support !== "ok") ||
    clash.value.node || clash.value.name || (!!form.target && (busyElsewhere.value || !data.value?.available)));
  const ways = computed(() => installWays(ports.value));
  // The drawing of the chosen screen, which way it hangs and with the name typed so far.
  const art = computed(() => {
    if (mode.value === "virtual") return { width: previewForm.width, height: previewForm.height, columns: previewForm.columns, rows: previewForm.rows };
    return { width: side.value?.width || chosen.value?.width || 480, height: side.value?.height || chosen.value?.height || 480, columns: form.grid.columns, rows: form.grid.rows };
  });

  // ---- The job, followed every few seconds while the page is in sight: every answer, this page's own or another's ----
  const firmware = useFirmwareJob({ onAnswer: take, onError: (e) => { note.value = e.message; } });
  async function refresh() {
    try { await firmware.refresh(); } catch (e: any) { note.value = e.message; }
  }
  function take(next: any) {
    data.value = next;
    const current = next.job;
    const ours = current && installer.file && current.file === installer.file;
    if (ours) installer.jobState = current.state;
    if (installer.view === "setup") {
      if (ours && current.state === "running") { showProgress(current, next.logs || []); return; }
      form.target = wayTarget(form.target, installer.picked, ports.value);
      note.value = busyElsewhere.value
        ? t("editor.installer.busy", { file: current.file })
        : !next.available && form.target ? t("editor.installer.no_cli") : wifiNote.value;
    } else if (installer.view === "progress" && ours) {
      job.value = current;
      logs.value = next.logs || [];
      if (current.state !== "running" && current.state !== "success") logOpen.value = true;
    }
  }
  function showProgress(current: any, lines: string[]) {
    installer.view = "progress";
    installer.jobState = current.state;
    installer.action = current.action;
    job.value = current;
    logs.value = lines;
  }
  // From this browser the job only builds; the installation is done once the page has written the image.
  const flashing = computed(() => installer.browser && job.value?.state === "success" && flash.state.phase !== "done" && flash.state.phase !== "failed");
  const running = computed(() => job.value?.state === "running" || flashing.value);
  const ok = computed(() => installer.view === "done" || (job.value?.state === "success" && (!installer.browser || flash.state.phase === "done")));
  const download = computed(() => installer.action === "download" && !installer.browser);
  // The build is done: write it, erased first as ESPHome does for a new device. A retry after a finished build connects
  // again, and that writes the image it already has.
  watch(() => [job.value?.state, flash.state.phase], ([state, phase]) => {
    if (installer.browser && installer.file && afterBrowserBuild(state, phase) === "write") flash.install(installer.file, true);
  });
  // A build that fails lets go of the port. Only when the build ends: a retry connects while the failed job is on screen.
  watch(() => job.value?.state, (state) => {
    if (installer.browser && afterBrowserBuild(state, flash.state.phase) === "release") flash.cancel();
  });
  // The memory the build has (build_memory.py, app 0.4.65): why it runs with fewer compilers, or why it stopped.
  const memory = computed(() => memoryText(job.value));
  const follow = computed<Follow>(() => ({ saved: installer.view === "done", running: running.value, ok: ok.value, download: download.value,
    browser: installer.browser, writing: job.value?.stage === "upload" || flashing.value, calibrate: installer.calibrate,
    built: job.value?.state === "success", stopped: memory.value?.reason === "out" || memory.value?.reason === "limit",
    name: installer.friendly, file: installer.file || "" }));
  const progressTitle = computed(() => followTitle(follow.value));
  const progressDetail = computed(() => followDetail(follow.value, errorLine(logs.value)));
  const image = computed(() => firmwareImage(installer.file || ""));
  const progress = computed(() => installProgress(job.value, logs.value, { browser: installer.browser, mode: download.value ? "download" : "install", flash: flash.state }));
  // The clock of the time it takes, every second while the page is in sight.
  const now = useClock(1000);
  const elapsed = computed(() => elapsedText(Number(job.value?.started) * 1000, job.value?.finished ? Number(job.value.finished) * 1000 : null, now.value));
  const artState = computed(() => running.value ? "working" : ok.value ? "done" : installer.view === "progress" ? "failed" : "idle");
  // Whether it reached the Wi-Fi, once it is on and the page waits for it.
  const waitsForWifi = computed(() => ok.value && !download.value && installer.view === "progress");
  const { arrival, restart } = useArrival(() => waitsForWifi.value, () => installer.file, now);

  // ---- What a click does ----
  async function submit(event: Event) {
    if (!(event.target as HTMLFormElement).reportValidity()) return;
    if (mode.value === "virtual") {
      try {
        const { width, height, columns, rows } = previewForm;
        session.createVirtualScreen(form.friendly_name, { ...previewProfile.value, shape: { ...previewProfile.value.shape, width, height, columns, rows } });
        ui.toast(t("editor.preview.created", { name: form.friendly_name.trim() }));
        ui.go("");
      } catch (err: any) { status.value = err.message; }
      return;
    }
    if (!installer.nodeEdited) form.name = nodeName(form.friendly_name);
    await whileSubmitting(install);
  }
  async function install() {
    status.value = "";
    const browser = form.target === "browser";
    // The port picker opens only from this click, so it comes before anything else waits; nothing is written or built
    // when no port is chosen, or the board on it has another chip than the chosen board (ESPHome's order).
    if (browser && !(await flash.connect(chosen.value?.chip))) return;
    try {
      const payload = profileRequest(form, { choices: choices.value, gridChosen: gridChosen.value, wifiMissing: askWifi.value ? wifiMissing.value : null, browser });
      if (wifiOther.value) await saveWifi();
      const result = await send("firmware/profiles", "POST", payload);
      Object.assign(installer, { file: result.file, apiKey: result.api_key, friendly: form.friendly_name.trim(), calibrate: !!chosen.value?.calibrate,
        target: form.target, browser, chip: chosen.value?.chip || null });
      form.wifi_password = "";
      if (result.job) showProgress(result.job, []);
      else installer.view = "done";
    } catch (err: any) {
      status.value = err.message;
      if (browser) flash.cancel();
    }
  }
  async function retry() {
    try {
      if (installer.browser) {
        // Again from this click: pick the port, then write the image that is already built, or build it first.
        if (!(await flash.connect(installer.chip))) return;
        if (job.value?.state === "success") return;
        showProgress(await send("firmware/jobs", "POST", { file: installer.file, action: "download" }), []);
        return;
      }
      if (!download.value) {
        const { ports: fresh } = await firmware.refresh();
        // The board may have been replugged; a single visible port is unambiguous.
        if (!fresh.includes(installer.target) && fresh.length === 1) installer.target = fresh[0];
      }
      const next = await send("firmware/jobs", "POST", download.value
        ? { file: installer.file, action: "download" }
        : { file: installer.file, action: "install", target: installer.target });
      showProgress(next, []);
    } catch (err: any) {
      ui.toast(err.message);
    }
  }
  function reset() {
    mode.value = "physical";
    flash.cancel();
    Object.assign(installer, { view: "setup", file: null, apiKey: null, nodeEdited: false, jobState: null, target: "", picked: false, action: null, browser: false, chip: null });
    Object.assign(form, { board: boardRows.value[0]?.key || "", orientation: "landscape" as Orientation, choices: {}, friendly_name: "", name: "", wifi_ssid: "", wifi_password: "", target: "" });
    bestGrid();
    step.value = 1; query.value = ""; size.value = ""; wifiOther.value = false; restart();
    job.value = null; logs.value = []; status.value = ""; note.value = ""; logOpen.value = false;
    refresh();
  }
  function close() {
    if (installer.view === "progress" && installer.jobState !== "running") installer.view = "done";
    ui.go("");
  }
  function back() { if (step.value > 1) step.value = (step.value - 1) as 1 | 2; }
  function tryVirtual() { mode.value = "virtual"; step.value = 2; }
  function realScreen() { mode.value = "physical"; step.value = 1; }
  function pickWay(value: string) { form.target = value; installer.picked = true; refresh(); }
  async function saveWifi() {
    await send("firmware/wifi", "PUT", { wifi_ssid: form.wifi_ssid, wifi_password: form.wifi_password });
    form.wifi_password = "";
  }
  // The right network, then the same installation again: over the same cable, or from this computer after its click.
  const { busy: fixing, run: whileFixing } = useBusy();
  async function fixWifi(event: Event) {
    if (!(event.target as HTMLFormElement).reportValidity()) return;
    await whileFixing(async () => {
      try {
        await saveWifi();
        restart();
        await retry();
      } catch (err: any) { ui.toast(err.message); }
    });
  }
  // The first look at the job; from there it is followed (useFirmwareJob), and a hidden tab asks the add-on nothing.
  onMounted(refresh);
  onBeforeUnmount(() => flash.cancel());

  return proxyRefs({
    form, mode, installer, flash, support, logs, note, status, logOpen, step, query, size, wifiOther, submitting, fixing,
    boardRows, previews, previewForm, chosen, abilities, choices, orientations, range, gridChosen, siblings, clash, wifi, askWifi, wifiMissing,
    wifiNote, goDisabled, goLabel: computed(() => goLabel(form.target)), wayHint: computed(() => wayHint(form.target, support, ports.value)),
    ways, art, running, ok, download, memory, progressTitle, progressDetail, image, progress, elapsed, artState, arrival,
    bestGrid, submit, retry, reset, close, back, tryVirtual, realScreen, pickWay, fixWifi,
  });
}
export type Installer = ReturnType<typeof useInstaller>;
