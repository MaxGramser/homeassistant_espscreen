<script setup lang="ts">
// New screen (app 0.4.32): three steps in one form, the way a setup assistant asks: which screen, what it is called and
// how it hangs, and how it gets its firmware. Then one page follows the installation in the steps a person knows,
// with the screen drawn filling in as it goes and ESPHome's own log a click away. The steps only show and hide; the
// form, what it sends and when, is the one it always was.
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { getJson, send } from "../api";
import { editorLanguage, languageMarks, numberText, t, te } from "../i18n";
import { copyText, createVirtualScreen, go, openIntegrations, refresh, state, toast } from "../store";
import { customPreview, previewProfiles } from "../model/preview";
import { boardAbilities, boardDetail, boardList, boardTitle } from "../model/boards";
import type { BoardChoice, BoardOrientation, Orientation } from "../types";
import BrowserFlash from "./BrowserFlash.vue";
import DeviceArt from "./DeviceArt.vue";
import Icon from "./ui/Icon.vue";
import { installProgress, memoryNote } from "../model/install-progress";
import { flashSupport } from "../flasher/logic";
import { useBrowserFlash } from "../flasher/session";

// Download: ESP Screens builds, the owner flashes the file from their own computer. ESPHome Web is ESPHome's own
// browser flasher; this address opens it with its hint for a downloaded project (as ESPHome Device Builder does).
const ESPHOME_WEB = "https://web.esphome.io/?dashboard_install";
const form = reactive({ board: "", orientation: "landscape" as Orientation, choices: {} as Record<string, string>, friendly_name: "", name: "", wifi_ssid: "", wifi_password: "", target: "" });
const mode = ref<"physical" | "virtual">("physical");
const installer = reactive({
  view: "setup" as "setup" | "progress" | "done", file: null as string | null, friendly: "", calibrate: false, target: "",
  apiKey: null as string | null, nodeEdited: false, jobState: null as string | null, picked: false, action: null as string | null,
  browser: false, chip: null as string | null,
});
// This computer (browser): the add-on builds as for Download, and this page writes the image over Web Serial, in
// Chrome or Edge on a page served over https. The fallback for a screen that can't reach the Home Assistant machine;
// Download stays for a browser that can't.
const flash = useBrowserFlash();
const support = flashSupport();
const data = ref<any>(null);
const job = ref<any>(null);
const logs = ref<string[]>([]);
const note = ref("");
const status = ref("");
const submitting = ref(false);
const logOpen = ref(false);
const keyBox = ref<HTMLElement | null>(null);
let poll = 0;

// ESPHome's node-name rule: lowercase ASCII, digits and dashes, starting with a letter.
function slug(text: string) {
  const clean = text.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "-").replace(/^[^a-z]+/, "").slice(0, 30).replace(/-+$/, "");
  return clean || "screen";
}
function portLabel(port: string) {
  const id = port.replace(/^\/dev\/serial\/by-id\/usb-/, "").replace(/-if\d+(-port\d+)?$/, "").replace(/_/g, " ");
  return `USB · ${id === port ? port.replace(/^\/dev\//, "") : id}`;
}
watch(() => form.friendly_name, () => { if (!installer.nodeEdited) form.name = slug(form.friendly_name); });
// The boards and everything said about them come from the add-on (boards.yaml and the board files, through
// boards.json): the list, each board's glass drawn to one scale, its abilities, its choices. Nothing here names a board.
const boards = computed<Record<string, BoardChoice>>(() => data.value?.boards || {});
const boardRows = computed(() => boardList(boards.value));
const previews = computed(() => previewProfiles(boards.value));
const previewForm = reactive({ profile: customPreview.key, width: 720, height: 720, columns: 2, rows: 3 });
const previewProfile = computed(() => previews.value.find(profile => profile.key === previewForm.profile) || customPreview);
watch(() => previewForm.profile, () => Object.assign(previewForm, previewProfile.value.shape));
const chosen = computed(() => boards.value[form.board]);
// Each board's glass in its own proportions with the cells of one page, all at the same height: the size itself is in
// the words beside it (inches), and a small board drawn to scale would be too small to read.
const glassStyle = (board: BoardChoice) => {
  const side = board.orientations.landscape;
  return { "--glass-aspect": `${board.width} / ${board.height}`, "--glass-columns": side?.columns || 2, "--glass-rows": side?.rows || 3 };
};
const abilities = computed(() => (chosen.value ? boardAbilities(chosen.value) : []));
// The choices besides the orientation (a CYD's display controller): each starts at the board file's own value.
const choices = computed(() => Object.entries(chosen.value?.choices || {}).map(([key, options]) => ({ key, options })));
// A value says what it is (the display controller's model); a number of rows is said in words, and its first value is
// the usual size rather than what most boards have (app 0.4.31).
const optionName = (key: string, option: string) => te(`editor.installer.choice_option.${key}.${option}`) ? t(`editor.installer.choice_option.${key}.${option}`) : option;
const firstNote = (key: string) => t(te(`editor.installer.choice_first.${key}`) ? `editor.installer.choice_first.${key}` : "editor.installer.choice_usual");
// The first board until someone picks one, once the add-on has said which there are.
watch(boardRows, (rows) => { if (!boards.value[form.board] && rows.length) form.board = rows[0].key; }, { immediate: true });
// Which way the chosen board may hang, with the canvas and the cells of a page for each. Square glass hangs one way
// only, and then there is nothing to ask. A board this add-on has not heard of asks nothing either, and builds
// lying down, which is what every board did before this choice existed.
const orientations = computed<(BoardOrientation & { key: Orientation })[]>(() => {
  const board = boards.value[form.board];
  if (!board || board.square) return [];
  const sides = (["landscape", "portrait"] as Orientation[])
    .map((key) => ({ key, side: board.orientations[key] }))
    .filter((row) => row.side && row.side.columns > 0 && row.side.rows > 0);
  return sides.length === 2 ? sides.map((row) => ({ key: row.key, ...(row.side as BoardOrientation) })) : [];
});
// A board that hangs one way only is always built lying down; a board that was asked about keeps whatever was
// chosen. Resetting it on every board change would throw away an answer the person just gave.
watch(() => form.board, () => {
  if (!orientations.value.length) form.orientation = "landscape";
  form.choices = Object.fromEntries(choices.value.map((choice) => [choice.key, choice.options[0]]));
});
const nodePreview = computed(() => form.name || "…");
// Names the screens this app knows already carry (app 0.2.123): their ESPHome device names and the starts Home
// Assistant gave their entity ids. The server refuses a clash, and saying it here means nothing is built first.
// The same slug the add-on makes of a name (core.entity_slug), so both sides read a name the same way.
const taken = computed(() => data.value?.taken || { nodes: [], prefixes: [] });
const entitySlug = (text: string) => text.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
const nodeTaken = computed(() => !!form.name && taken.value.nodes.includes(form.name.trim().toLowerCase()));
const nameTaken = computed(() => {
  const prefix = entitySlug(form.friendly_name.trim());
  return !!prefix && taken.value.prefixes.includes(prefix);
});
const ports = computed<string[]>(() => data.value?.ports || []);
const wifi = computed(() => data.value?.wifi);
const askWifi = computed(() => wifi.value?.state === "new" || wifi.value?.state === "missing");
const wifiMissing = computed<string[]>(() => wifi.value?.missing || []);
const wifiStatus = computed(() => t(wifi.value?.state === "new" ? "editor.installer.wifi.new" : "editor.installer.wifi.missing"));
const wifiNote = computed(() => wifi.value?.state === "ready"
  ? t("editor.installer.wifi.ready")
  : wifi.value?.state === "invalid"
    ? t("editor.installer.wifi.invalid")
    : "");
const targetHint = computed(() => t(form.target === "usb"
  ? "editor.installer.target.usb"
  : form.target === "download"
    ? "editor.installer.target.download"
    : form.target === "browser"
      ? support === "ok" ? "editor.webflash.hint" : `editor.webflash.unavailable.${support}`
    : !form.target
      ? "editor.installer.target.later"
      : ports.value.length > 1
        ? "editor.installer.target.several"
        : "editor.installer.target.once"));
const goLabel = computed(() => (form.target === "download" ? t("editor.firmware.build_download") : form.target === "browser" ? t("editor.webflash.go") : form.target ? t("editor.installer.install") : t("editor.installer.save_profile")));
const busyElsewhere = computed(() => data.value?.job?.state === "running" && !(installer.file && data.value.job.file === installer.file));
const goDisabled = computed(() => submitting.value || wifi.value?.state === "invalid" || form.target === "usb" ||
  (form.target === "browser" && support !== "ok") ||
  nodeTaken.value || nameTaken.value || (!!form.target && (busyElsewhere.value || !data.value?.available)));
// USB on the Home Assistant machine is always listed first, also before a board is plugged in, so nobody
// concludes it isn't possible; "usb" stands for that port until one shows up.
function syncTarget() {
  const current = form.target;
  const kept = current === "download" || current === "browser" || current === "" ? installer.picked : ports.value.includes(current);
  if (!kept) form.target = ports.value[0] || "usb";
}
async function installerRefresh() {
  let next: any;
  try {
    next = await getJson("firmware");
  } catch (e: any) {
    note.value = e.message;
    return;
  }
  data.value = next;
  const current = next.job;
  const ours = current && installer.file && current.file === installer.file;
  if (ours) installer.jobState = current.state;
  if (installer.view === "setup") {
    if (ours && current.state === "running") { showProgress(current, next.logs || []); return; }
    syncTarget();
    note.value = busyElsewhere.value
      ? t("editor.installer.busy", { file: current.file })
      : !next.available && form.target
        ? t("editor.installer.no_cli")
        : wifiNote.value;
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
// The build is done: write it, erased first as ESPHome does for a new device. A retry after a finished build
// connects again, and that writes the image it already has.
watch(() => [job.value?.state, flash.state.phase], ([state, phase]) => {
  if (installer.browser && installer.file && state === "success" && phase === "waiting") flash.install(installer.file, true);
});
// A build that fails lets go of the port. Only when the build ends: a retry connects while the failed job is on screen.
watch(() => job.value?.state, (state) => {
  if (installer.browser && state && state !== "running" && state !== "success" && flash.state.phase === "waiting") flash.cancel();
});
const title = computed(() => t(installer.view === "done"
  ? "editor.installer.title.saved"
  : running.value ? "editor.installer.title.running" : ok.value ? (download.value ? "editor.installer.title.ready" : "editor.installer.title.done") : "editor.installer.title.failed"));
const progressTitle = computed(() => installer.view === "done"
  ? t("editor.installer.progress.saved", { file: installer.file })
  : running.value
    ? job.value?.stage === "upload" || flashing.value ? t("editor.installer.progress.writing", { name: installer.friendly }) : t("editor.installer.progress.building")
    : ok.value
      ? download.value ? t("editor.installer.progress.ready", { name: installer.friendly }) : t("editor.installer.progress.installed", { name: installer.friendly })
      : t(download.value ? "editor.installer.progress.build_failed" : "editor.installer.progress.install_failed"));
const progressDetail = computed(() => installer.view === "done"
  ? t("editor.installer.detail.saved")
  : running.value
    ? job.value?.stage === "upload" || flashing.value
      ? t("editor.installer.detail.uploading")
      : t(installer.browser ? "editor.webflash.building" : download.value ? "editor.installer.detail.building_download" : "editor.installer.detail.building")
    : ok.value
      ? download.value
        ? t("editor.installer.detail.downloaded")
        : t(installer.calibrate ? "editor.installer.detail.booted_calibrate" : "editor.installer.detail.booted")
      : (installer.browser && job.value?.state === "success") || memory.value?.reason === "out" || memory.value?.reason === "limit"
        ? ""  // the card under it says what happened
        : logs.value.filter((l) => /error/i.test(l)).pop() || logs.value.filter((l) => /failed/i.test(l)).pop() || t("editor.installer.detail.see_log"));
// The memory the build has (build_memory.py, app 0.4.65): a card that says why it runs with fewer compilers than the
// machine has cores, that it started again with one after the memory ran out, or why it stopped. The numbers are GB in
// the editor's own language.
const memory = computed(() => {
  const note = memoryNote(job.value);
  if (!note) return null;
  const marks = languageMarks(editorLanguage());
  const params = { free: `${numberText(note.free, marks)} GB`, need: `${numberText(note.need, marks)} GB`, jobs: note.jobs, cores: note.cores };
  return { reason: note.reason, title: t(`editor.installer.memory.${note.reason}_title`, params), text: t(`editor.installer.memory.${note.reason}`, params) };
});
const image = computed(() => ({ href: `api/firmware/profiles/${encodeURIComponent(installer.file || "")}/download`, name: (installer.file || "").replace(/\.yaml$/, "") + ".factory.bin" }));
async function submit(event: Event) {
  const element = event.target as HTMLFormElement;
  if (!element.reportValidity()) return;
  if (mode.value === "virtual") {
    try {
      const { width, height, columns, rows } = previewForm;
      createVirtualScreen(form.friendly_name, { ...previewProfile.value,
        shape: { ...previewProfile.value.shape, width, height, columns, rows } });
      toast(t("editor.preview.created", { name: form.friendly_name.trim() }));
      go("");
    } catch (err: any) { status.value = err.message; }
    return;
  }
  if (!installer.nodeEdited) form.name = slug(form.friendly_name);
  submitting.value = true;
  status.value = "";
  const browser = form.target === "browser";
  // The port picker opens only from this click, so it comes before anything else waits; nothing is written or built
  // when no port is chosen, or the board on it has another chip than the chosen board (ESPHome's order).
  if (browser && !(await flash.connect(chosen.value?.chip))) {
    submitting.value = false;
    return;
  }
  try {
    const payload: Record<string, unknown> = { board: form.board, orientation: form.orientation, friendly_name: form.friendly_name, name: form.name, target: browser ? "download" : form.target };
    // Only a choice that differs from the board file's own goes along: the add-on writes nothing for that one anyway.
    const picked = Object.fromEntries(choices.value.filter((choice) => form.choices[choice.key] !== choice.options[0]).map((choice) => [choice.key, form.choices[choice.key]]));
    if (Object.keys(picked).length) payload.choices = picked;
    if (askWifi.value) { if (wifiMissing.value.includes("wifi_ssid")) payload.wifi_ssid = form.wifi_ssid; if (wifiMissing.value.includes("wifi_password")) payload.wifi_password = form.wifi_password; }
    if (wifiOther.value) await saveWifi();
    const result = await send("firmware/profiles", "POST", payload);
    Object.assign(installer, { file: result.file, apiKey: result.api_key, friendly: form.friendly_name.trim(), calibrate: !!chosen.value?.calibrate, target: form.target,
      browser, chip: chosen.value?.chip || null });
    form.wifi_password = "";
    if (result.job) showProgress(result.job, []);
    else installer.view = "done";
  } catch (err: any) {
    status.value = err.message;
    if (browser) flash.cancel();
  } finally {
    submitting.value = false;
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
      const { ports: fresh } = await getJson("firmware");
      // The board may have been replugged; a single visible port is unambiguous.
      if (!fresh.includes(installer.target) && fresh.length === 1) installer.target = fresh[0];
    }
    const next = await send("firmware/jobs", "POST", download.value
      ? { file: installer.file, action: "download" }
      : { file: installer.file, action: "install", target: installer.target });
    showProgress(next, []);
  } catch (err: any) {
    toast(err.message);
  }
}
function reset() {
  mode.value = "physical";
  flash.cancel();
  Object.assign(installer, { view: "setup", file: null, apiKey: null, nodeEdited: false, jobState: null, target: "", picked: false, action: null, browser: false, chip: null });
  Object.assign(form, { board: boardRows.value[0]?.key || "", orientation: "landscape", choices: {}, friendly_name: "", name: "", wifi_ssid: "", wifi_password: "", target: "" });
  step.value = 1; query.value = ""; size.value = ""; wifiOther.value = false; doneAt.value = 0;
  job.value = null; logs.value = []; status.value = ""; note.value = ""; logOpen.value = false;
  installerRefresh();
}
function close() {
  if (installer.view === "progress" && installer.jobState !== "running") installer.view = "done";
  go("");
}
// ---- The steps of the setup ----
const step = ref<1 | 2 | 3>(1);
const stepTwo = ref<HTMLElement | null>(null);
const query = ref("");
const size = ref<"" | "small" | "medium" | "large">("");
const SIZES = ["", "small", "medium", "large"] as const;
const sizeOf = (inch: number) => inch < 4 ? "small" : inch < 6 ? "medium" : "large";
// Search reads what someone knows of their screen: the brand, the size ("4", "4.3 inch"), what is printed on it, the chip.
const shownBoards = computed(() => {
  const words = query.value.trim().toLocaleLowerCase().replace(/[",]/g, ".").split(/\s+/).filter(Boolean);
  return boardRows.value.filter((board) => (!size.value || sizeOf(board.inch) === size.value) && words.every((word) =>
    `${boardTitle(board)} ${board.name} ${board.model} ${board.inch} ${board.touch} ${board.chip || ""} ${board.key}`.toLocaleLowerCase().includes(word.replace(/inch$/, ""))));
});
// Keep variants together only when brand, glass size, chip and resolution match. A board with a different chip or
// resolution gets its own card and specifications; display-controller variants and board revisions stay in Model.
type Row = (typeof boardRows.value)[number];
const familyKey = (board: BoardChoice) => JSON.stringify([board.name, board.inch, board.chip || "", board.width, board.height]);
const families = computed(() => {
  const found = new Map<string, Row[]>();
  for (const board of shownBoards.value) found.set(familyKey(board), [...(found.get(familyKey(board)) || []), board]);
  return [...found.values()];
});
const siblings = computed(() => chosen.value ? boardRows.value.filter((board) => familyKey(board) === familyKey(chosen.value!)) : []);
function pickFamily(list: Row[]) { if (!list.some((board) => board.key === form.board)) form.board = list[0].key; }
// A family is as far along as its furthest model: stable if one is, else new, else experimental.
const familyStatus = (list: Row[]) => list.some((b) => b.status === "stable") ? "stable" : list.some((b) => b.status === "new") ? "new" : "experimental";
// One model says what is printed on it; several say how many there are, and the next step asks which.
const familyLines = (list: Row[]) => list.length > 1 ? [boardDetail(list[0])[1], t("editor.installer.models", list.length)] : boardDetail(list[0]);
const sizeCount = (key: string) => new Set(boardRows.value.filter((board) => !key || sizeOf(board.inch) === key).map(familyKey)).size;
function pickBoard(key: string) { form.board = key; }
// Step two asks nothing it can't check on the spot: Next goes on only when its fields are filled in as they must be.
function next() {
  if (step.value === 1) { if (form.board || mode.value === "virtual") step.value = 2; return; }
  if (step.value === 2) {
    const fields = [...(stepTwo.value?.querySelectorAll<HTMLInputElement>("input, select") || [])];
    const wrong = fields.find((field) => !field.checkValidity());
    if (wrong) { wrong.reportValidity(); return; }
    if (nodeTaken.value || nameTaken.value) return;
    step.value = 3;
  }
}
// Each step, and the installation after them, starts at its top.
const root = ref<HTMLElement | null>(null);
watch(() => [step.value, installer.view], () => root.value?.scrollTo?.({ top: 0 }));
function back() { if (step.value > 1) step.value = (step.value - 1) as 1 | 2; }
function tryVirtual() { mode.value = "virtual"; step.value = 2; }
function realScreen() { mode.value = "physical"; step.value = 1; }
// The drawing of the chosen screen, which way it hangs and with the name typed so far.
const art = computed(() => {
  const board = chosen.value;
  if (mode.value === "virtual") return { width: previewForm.width, height: previewForm.height, columns: previewForm.columns, rows: previewForm.rows };
  const side = board?.orientations[form.orientation] || board?.orientations.landscape;
  // A board choice that sets the grid (the 4-inch Guition's number of rows, app 0.4.31) draws the grid it gives.
  const chosenNumber = (key: string) => Number(form.choices[key]) || 0;
  return { width: side?.width || board?.width || 480, height: side?.height || board?.height || 480,
    columns: chosenNumber("GRID_COLS") || side?.columns || 2, rows: chosenNumber("GRID_ROWS") || side?.rows || 3 };
});
const boardArt = (board: BoardChoice) => {
  const side = board.orientations.landscape;
  return { width: side?.width || board.width, height: side?.height || board.height, columns: side?.columns || 2, rows: side?.rows || 3 };
};
// The ways in, as cards: USB on the Home Assistant machine first (each port found, or the one to plug into), then this
// computer, a file, or nothing yet.
const ways = computed(() => [
  ...(ports.value.length ? ports.value : ["usb"]).map((port) => ({ value: port, icon: "flash" as const, title: t("editor.installer.ways.ha_title"),
    detail: port === "usb" ? t("editor.installer.ways.ha_waiting") : t("editor.installer.ways.ha_found", { port: portLabel(port).replace(/^USB · /, "") }), live: port !== "usb" })),
  { value: "browser", icon: "monitor-dashboard" as const, title: t("editor.installer.ways.browser_title"), detail: t("editor.installer.ways.browser_detail"), live: false },
  { value: "download", icon: "tray-arrow-down" as const, title: t("editor.installer.ways.download_title"), detail: t("editor.installer.ways.download_detail"), live: false },
  { value: "", icon: "clock-outline" as const, title: t("editor.installer.ways.later_title"), detail: t("editor.installer.ways.later_detail"), live: false },
]);
function pickWay(value: string) { form.target = value; installer.picked = true; installerRefresh(); }

// ---- Another Wi-Fi network (app 0.4.32) ----
// Ready Wi-Fi can still be the wrong one: "Another network" asks for both lines again, written before the build.
const wifiOther = ref(false);
async function saveWifi() {
  await send("firmware/wifi", "PUT", { wifi_ssid: form.wifi_ssid, wifi_password: form.wifi_password });
  form.wifi_password = "";
}

// ---- After the firmware is on it: did the screen reach the Wi-Fi? (app 0.4.32) ----
// Home Assistant finds a screen on the network before anyone pairs it (the inventory's `seen`), so the page can say it
// arrived, or after three minutes without it, that the Wi-Fi is the likely cause and what fixes it. Tessera then adds it
// to Home Assistant itself (app 0.4.73): `failed` when Home Assistant asked something only the person can answer.
const ARRIVE_MS = 3 * 60 * 1000;
const doneAt = ref(0);
const nodeName = computed(() => (installer.file || "").replace(/\.yaml$/, ""));
const waitsForWifi = computed(() => ok.value && !download.value && installer.view === "progress");
watch(waitsForWifi, (waits) => { if (waits && !doneAt.value) doneAt.value = Date.now(); });
const arrival = computed(() => {
  if (!waitsForWifi.value) return null;
  if (state.inventory.screens.some((screen: any) => screen.node === nodeName.value)) return "paired";
  const found = state.inventory.pending?.find((entry) => entry.file === installer.file && entry.seen);
  if (found) return found.pairing === "failed" ? "failed" : "seen";
  return now.value - doneAt.value > ARRIVE_MS ? "missing" : "waiting";
});
let arrivalPoll = 0;
watch(arrival, (value) => {
  clearInterval(arrivalPoll);
  if (value && value !== "paired") arrivalPoll = window.setInterval(() => refresh(false), 5000);
}, { immediate: true });
const fixing = ref(false);
// The right network, then the same installation again: over the same cable, or from this computer after its click.
async function fixWifi(event: Event) {
  if (!(event.target as HTMLFormElement).reportValidity()) return;
  fixing.value = true;
  try {
    await saveWifi();
    doneAt.value = 0;
    await retry();
  } catch (err: any) { toast(err.message); }
  finally { fixing.value = false; }
}

// ---- The installation, step by step ----
const progress = computed(() => installProgress(job.value, logs.value, { browser: installer.browser, mode: download.value ? "download" : "install", flash: flash.state }));
const now = ref(Date.now());
let clock = 0;
const elapsed = computed(() => {
  const started = Number(job.value?.started) * 1000;
  if (!started) return "";
  const end = job.value?.finished ? Number(job.value.finished) * 1000 : now.value;
  const seconds = Math.max(0, Math.round((end - started) / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
});
const artState = computed(() => running.value ? "working" : ok.value ? "done" : installer.view === "progress" ? "failed" : "idle");
const stepLabel = (key: string) => t(key === "done" && download.value ? "editor.installer.steps_done.download" : `editor.installer.steps_done.${key}`);
const logBox = ref<HTMLElement | null>(null);
// The log follows its last line while someone reads the bottom, and stays put once they scroll up.
watch(() => logs.value.length, () => {
  const box = logBox.value;
  if (!box || box.scrollHeight - box.scrollTop - box.clientHeight > 40) return;
  requestAnimationFrame(() => { box.scrollTop = box.scrollHeight; });
});
onMounted(() => { installerRefresh(); poll = window.setInterval(installerRefresh, 3000); clock = window.setInterval(() => { now.value = Date.now(); }, 1000); });
onBeforeUnmount(() => { clearInterval(poll); clearInterval(clock); clearInterval(arrivalPoll); flash.cancel(); });
</script>

<template>
  <div ref="root" class="setup" id="installer" :class="installer.view === 'setup' ? `step-${step}` : 'following'">
    <!-- The bar across the top: where in the setup you are, and the way out. -->
    <header class="setup-head">
      <span class="setup-brand">{{ t("editor.nav.new_screen") }}</span>
      <ol v-if="installer.view === 'setup' && mode === 'physical'" class="setup-steps" :aria-label="t('editor.nav.new_screen')">
        <li v-for="(key, index) in (['board', 'setup', 'install'] as const)" :key="key" :class="{ now: step === index + 1, past: step > index + 1 }">
          <button type="button" :disabled="step <= index + 1" @click="step = (index + 1) as 1 | 2 | 3"><i>{{ step > index + 1 ? "✓" : index + 1 }}</i>{{ t(`editor.installer.steps.${key}`) }}</button>
        </li>
      </ol>
      <span v-else class="setup-steps-spacer"></span>
      <button type="button" class="icon-btn" id="close-install" :aria-label="t('editor.common.close')" :title="t('editor.common.close')" :disabled="flash.busy()" @click="close"><Icon name="close" /></button>
    </header>

    <form v-if="installer.view === 'setup'" id="install-form" class="setup-body" novalidate @submit.prevent="submit">
      <!-- ① Which screen: search, sizes, and every board drawn as it hangs. -->
      <section v-show="step === 1 && mode === 'physical'" class="setup-step pick">
        <h1 id="install-title">{{ t("editor.installer.pick_title") }}</h1>
        <p class="setup-lead">{{ t("editor.installer.pick_intro") }}</p>
        <div class="pick-tools">
          <label class="pick-search"><Icon name="magnify" /><input id="board-search" v-model="query" type="search" :placeholder="t('editor.installer.search')" autocomplete="off" spellcheck="false" /></label>
          <div class="seg pick-sizes" role="group" :aria-label="t('editor.installer.board')">
            <button v-for="key in SIZES" :key="key" type="button" :aria-pressed="size === key" @click="size = key">{{ t(`editor.installer.sizes.${key || "all"}`) }} <small>{{ sizeCount(key) }}</small></button>
          </div>
        </div>
        <fieldset class="boards">
          <legend class="sr-only">{{ t("editor.installer.board") }}</legend>
          <label v-for="family in families" :key="family[0].key" class="board" :class="{ chosen: family.some((b) => b.key === form.board) }" @dblclick="pickFamily(family); next()">
            <input type="radio" name="board" :value="family[0].key" :checked="family.some((b) => b.key === form.board)" @change="pickFamily(family)" />
            <span class="board-art" aria-hidden="true" :style="{ '--inch': family[0].inch }"><DeviceArt v-bind="boardArt(family[0])" /></span>
            <span class="board-words"><b>{{ boardTitle(family[0]) }}</b><small v-for="line in familyLines(family)" :key="line">{{ line }}</small></span>
            <em v-if="familyStatus(family) !== 'stable'" class="board-badge" :class="familyStatus(family)">{{ t(`editor.installer.status.${familyStatus(family)}`) }}</em>
            <span class="board-check" aria-hidden="true"><Icon name="check" /></span>
          </label>
          <p v-if="!shownBoards.length" class="pick-none">{{ t("editor.installer.none_found", { query: query.trim() }) }}</p>
        </fieldset>
        <button type="button" class="btn link try-virtual" id="try-virtual" @click="tryVirtual">{{ t("editor.installer.try_virtual") }}</button>
      </section>

      <!-- ② What it is called and how it hangs, beside the screen itself filling in its name. -->
      <section v-show="step === 2" ref="stepTwo" class="setup-step make">
        <div class="make-art" aria-hidden="true">
          <div class="make-frame" :style="{ '--art-ratio': (art.width + 14 * art.height / 100) / (art.height + 14 * art.height / 100) }">
            <DeviceArt v-bind="art" :name="form.friendly_name.trim()" />
          </div>
          <p v-if="mode === 'physical' && chosen" class="make-caption"><b>{{ boardTitle(chosen) }}</b> · {{ chosen.model }}</p>
        </div>
        <div class="make-fields">
          <h1>{{ t(mode === "virtual" ? "editor.preview.virtual" : "editor.installer.setup_title") }}</h1>
          <p v-if="mode === 'virtual'" class="setup-lead">{{ t("editor.preview.intro") }}</p>
          <template v-if="mode === 'physical'">
          <p v-if="chosen && chosen.status !== 'stable'" class="make-note" id="board-status"><Icon name="information-outline" />{{ t(`editor.installer.status_hint.${chosen.status}`) }}</p>
          <div class="field">
            <label class="f-label" for="friendly_name">{{ t("editor.installer.name") }}</label>
            <input id="friendly_name" name="friendly_name" v-model="form.friendly_name" required maxlength="60" :placeholder="t('editor.installer.name_placeholder')" autocomplete="off" />
            <small>{{ t("editor.installer.name_hint") }}</small>
            <!-- One line, not two: a name that is taken usually makes a device name that is taken as well, and the
                 name is what someone changes. The device name speaks for itself only when it is the one that clashes. -->
            <small v-if="nameTaken" id="name-taken" class="warn">{{ t("editor.installer.name_taken") }}</small>
            <small v-else-if="nodeTaken" id="node-taken" class="warn">{{ t("editor.installer.node_taken") }}</small>
          </div>
          <!-- Which model of this screen: what is printed on the board tells them apart. -->
          <fieldset v-if="siblings.length > 1" id="board-model" class="choice-fields">
            <legend class="f-label">{{ t("editor.installer.model") }}</legend>
            <div class="model-options">
              <label v-for="board in siblings" :key="board.key" class="choice model">
                <input type="radio" name="model" :value="board.key" v-model="form.board" />
                <span><b>{{ board.model }}</b><small>{{ boardDetail(board)[1] }}</small>
                  <em v-if="board.status !== 'stable'" class="board-badge inline" :class="board.status">{{ t(`editor.installer.status.${board.status}`) }}</em></span>
              </label>
            </div>
            <small>{{ t("editor.installer.model_hint") }}</small>
          </fieldset>
          <!-- Which way the screen hangs: the cells of a page differ per way, so each option draws the grid it gives.
               Only glass that is not square is asked about, and only once the add-on has said what the board can do. -->
          <fieldset v-if="orientations.length" id="orientation-fields">
            <legend class="f-label">{{ t("editor.installer.orientation") }}</legend>
            <div class="orients">
              <label v-for="side in orientations" :key="side.key" class="orient">
                <input type="radio" name="orientation" :value="side.key" v-model="form.orientation" />
                <span class="orient-glass" aria-hidden="true"
                      :style="{ '--glass-aspect': `${side.width} / ${side.height}`, '--glass-columns': side.columns, '--glass-rows': side.rows }">
                  <span class="orient-bar"></span>
                  <span class="orient-cells"><i v-for="cell in side.columns * side.rows" :key="cell"></i></span>
                </span>
                <span class="orient-words">
                  <b>{{ t(`editor.installer.orientation_${side.key}`) }}</b>
                  <small>{{ t("editor.installer.orientation_tiles", side.columns * side.rows) }}</small>
                </span>
              </label>
            </div>
            <small id="orientation-hint">{{ t("editor.installer.orientation_hint") }}</small>
          </fieldset>
          <!-- The board's other choices, one per part that differs between boards sold under its name. -->
          <fieldset v-for="choice in choices" :key="choice.key" class="choice-fields" :id="`choice-${choice.key}`">
            <legend class="f-label">{{ t(`editor.installer.choice.${choice.key}`) }}</legend>
            <div class="choice-options">
              <label v-for="(option, index) in choice.options" :key="option" class="choice">
                <input type="radio" :name="`choice-${choice.key}`" :value="option" v-model="form.choices[choice.key]" />
                <span><b>{{ optionName(choice.key, option) }}</b><small v-if="index === 0">{{ firstNote(choice.key) }}</small></span>
              </label>
            </div>
            <small>{{ t(`editor.installer.choice_hint.${choice.key}`) }}</small>
          </fieldset>
          <!-- Wi-Fi, always in sight: ready from ESPHome's secrets, or asked here once for every screen after it. -->
          <fieldset id="wifi-section" class="wifi">
            <legend class="f-label">{{ t("editor.installer.wifi.title") }}</legend>
            <div v-if="askWifi" id="wifi-fields" class="wifi-fields">
              <p class="hint" id="wifi-status">{{ wifiStatus }}</p>
              <div v-if="wifiMissing.includes('wifi_ssid')" class="field" id="wifi-ssid-label"><label class="f-label" for="wifi_ssid">{{ t("editor.installer.wifi.ssid") }}</label><input id="wifi_ssid" name="wifi_ssid" v-model="form.wifi_ssid" required autocomplete="off" /></div>
              <div v-if="wifiMissing.includes('wifi_password')" class="field" id="wifi-password-label"><label class="f-label" for="wifi_password">{{ t("editor.installer.wifi.password") }}</label><input id="wifi_password" name="wifi_password" type="password" v-model="form.wifi_password" autocomplete="new-password" /></div>
            </div>
            <template v-else>
              <p class="wifi-state" :class="wifi?.state"><Icon :name="wifi?.state === 'invalid' ? 'alert-circle-outline' : 'check-circle'" />
                <span>{{ wifiNote || t("editor.installer.wifi.ready") }}</span>
                <button v-if="wifi?.state === 'ready'" type="button" class="btn link mini" id="wifi-other" @click="wifiOther = !wifiOther">{{ t(wifiOther ? "editor.common.cancel" : "editor.installer.wifi.other") }}</button></p>
              <div v-if="wifiOther" id="wifi-fields" class="wifi-fields">
                <p class="hint">{{ t("editor.installer.wifi.other_note") }}</p>
                <div class="field"><label class="f-label" for="wifi_ssid">{{ t("editor.installer.wifi.ssid") }}</label><input id="wifi_ssid" name="wifi_ssid" v-model="form.wifi_ssid" required autocomplete="off" /></div>
                <div class="field"><label class="f-label" for="wifi_password">{{ t("editor.installer.wifi.password") }}</label><input id="wifi_password" name="wifi_password" type="password" v-model="form.wifi_password" autocomplete="new-password" /></div>
              </div>
            </template>
          </fieldset>
          <!-- For whoever wants it, in sight under its own heading: the device name and what the board can and cannot do. -->
          <section class="advanced">
            <h2 class="f-label">{{ t("editor.installer.advanced") }}</h2>
            <div class="field" id="node-label">
              <label class="f-label" for="node-name">{{ t("editor.installer.device_name") }}</label>
              <input id="node-name" name="name" v-model="form.name" pattern="[a-z][a-z0-9\-]{0,29}" maxlength="30" autocomplete="off" @input="installer.nodeEdited = true" />
              <small>{{ t("editor.installer.device_name_hint") }} <code id="node-preview">{{ nodePreview }}</code></small>
            </div>
            <ul v-if="abilities.length" class="abilities" id="board-abilities">
              <li v-for="ability in abilities" :key="ability.key" :class="{ off: !ability.on }">{{ ability.text }}</li>
            </ul>
          </section>
          </template>
          <template v-else>
            <div class="field">
              <label class="f-label" for="virtual-name">{{ t("editor.preview.name") }}</label>
              <input id="virtual-name" v-model="form.friendly_name" required maxlength="60" :placeholder="t('editor.preview.name_placeholder')" autocomplete="off" />
            </div>
            <div class="field">
              <label class="f-label" for="virtual-profile">{{ t("editor.preview.profile") }}</label>
              <select id="virtual-profile" v-model="previewForm.profile">
                <option v-for="profile in previews" :key="profile.key" :value="profile.key">
                  {{ profile.name }} · {{ profile.shape.width }} × {{ profile.shape.height }} · {{ t(`editor.installer.orientation_${profile.orientation}`) }}
                </option>
              </select>
              <small v-if="previewForm.profile === customPreview.key">{{ t("editor.preview.design_only") }}</small>
            </div>
            <details class="advanced">
              <summary>{{ t("editor.preview.override") }}</summary>
              <div v-for="axis in (['width', 'height', 'columns', 'rows'] as const)" :key="axis" class="field">
                <label class="f-label" :for="`virtual-${axis}`">{{ t(`editor.preview.${axis}`) }}</label>
                <input :id="`virtual-${axis}`" type="number" v-model.number="previewForm[axis]" required step="1"
                  :min="axis === 'width' || axis === 'height' ? 160 : 1" :max="axis === 'width' || axis === 'height' ? 2560 : 8" />
              </div>
            </details>
          </template>
        </div>
      </section>

      <!-- ③ How the firmware gets onto it. -->
      <section v-show="step === 3 && mode === 'physical'" class="setup-step ways">
        <h1>{{ t("editor.installer.install_title") }}</h1>
        <fieldset id="install-target" class="way-list">
          <legend class="sr-only">{{ t("editor.installer.install_via") }}</legend>
          <label v-for="way in ways" :key="way.value" class="way" :class="{ chosen: form.target === way.value }">
            <input type="radio" name="target" :value="way.value" :checked="form.target === way.value" @change="pickWay(way.value)" />
            <span class="way-icon"><Icon :name="way.icon" /><i v-if="way.live" class="way-live"></i></span>
            <span class="way-words"><b>{{ way.title }}</b><small>{{ way.detail }}</small></span>
          </label>
        </fieldset>
        <p class="way-hint" id="target-hint">{{ targetHint }}</p>
        <BrowserFlash v-if="form.target === 'browser'" :state="flash.state" />
        <p v-if="note" class="hint" id="install-note">{{ note }}</p>
      </section>

      <footer class="setup-foot">
        <button v-if="step > 1 && !(mode === 'virtual' && step === 2)" type="button" class="btn quiet" id="setup-back" @click="back">{{ t("editor.common.back") }}</button>
        <button v-else-if="mode === 'virtual'" type="button" class="btn quiet" @click="realScreen">{{ t("editor.common.back") }}</button>
        <span class="status-line error" id="install-status" role="status">{{ status }}</span>
        <button v-if="mode === 'virtual'" type="submit" class="btn primary big" id="virtual-create">{{ t("editor.preview.create") }}</button>
        <button v-else-if="step < 3" type="button" class="btn primary big" id="setup-next" :disabled="(step === 1 && !form.board) || (step === 2 && (nameTaken || nodeTaken))" @click="next">{{ t("editor.installer.next") }}<Icon name="arrow-right" /></button>
        <button v-else type="submit" class="btn primary big" id="install-go" :disabled="goDisabled">{{ goLabel }}</button>
      </footer>
    </form>

    <!-- The installation: the screen filling in, the steps it goes through, and ESPHome's own log behind Details. -->
    <div v-else id="install-progress" class="setup-body follow">
      <div class="follow-art" aria-hidden="true">
        <div class="make-frame" :style="{ '--art-ratio': (art.width + 14 * art.height / 100) / (art.height + 14 * art.height / 100) }">
          <DeviceArt v-bind="art" :name="installer.friendly" :lit="installer.view === 'done' ? 0 : progress.percent / 100" :state="artState" />
        </div>
      </div>
      <div class="follow-words">
        <h1 id="progress-title">{{ progressTitle }}</h1>
        <p id="progress-detail">{{ progressDetail }}</p>
      </div>
      <!-- The memory the build has (app 0.4.65): a slower build the person understands, or why it stopped. -->
      <div v-if="memory && !ok" class="memory-note" :class="[memory.reason, { stopped: memory.reason === 'out' || memory.reason === 'limit' }]" id="memory-note" role="status">
        <h2><Icon name="alert-circle-outline" />{{ memory.title }}</h2>
        <p>{{ memory.text }}</p>
      </div>
      <!-- Did it reach the Wi-Fi: waiting, seen by Home Assistant, paired, or after three minutes the way to fix it. -->
      <div v-if="arrival" class="arrive" :class="arrival" id="arrive" role="status">
        <p v-if="arrival !== 'missing'" class="arrive-line">
          <span v-if="arrival === 'waiting' || arrival === 'seen'" class="spin small"></span><Icon v-else :name="arrival === 'failed' ? 'alert-circle-outline' : 'check-circle'" />
          {{ t(`editor.installer.arrive.${arrival}`, { name: installer.friendly }) }}
        </p>
        <template v-else>
          <h2><Icon name="alert-circle-outline" />{{ t("editor.installer.arrive.missing", { name: installer.friendly }) }}</h2>
          <p>{{ t(chosen?.hotspot === false ? "editor.installer.arrive.no_hotspot" : "editor.installer.arrive.hotspot") }}</p>
          <!-- The same line as under Another network: this Wi-Fi goes into secrets.yaml, which every screen builds with. -->
          <p class="hint">{{ t("editor.installer.wifi.other_note") }}</p>
          <form class="arrive-form" id="arrive-wifi" novalidate @submit.prevent="fixWifi">
            <div class="field"><label class="f-label" for="fix_ssid">{{ t("editor.installer.wifi.ssid") }}</label><input id="fix_ssid" v-model="form.wifi_ssid" required autocomplete="off" /></div>
            <div class="field"><label class="f-label" for="fix_password">{{ t("editor.installer.wifi.password") }}</label><input id="fix_password" type="password" v-model="form.wifi_password" autocomplete="new-password" /></div>
            <button type="submit" class="btn primary" :disabled="fixing || flash.busy()"><span v-if="fixing" class="spin small"></span>{{ t("editor.installer.arrive.change") }}</button>
          </form>
        </template>
      </div>
      <!-- While it works, and when it stops short: the bar and the steps. Once it is on the screen, what comes next. -->
      <template v-if="installer.view !== 'done' && !ok">
        <div class="follow-bar" role="progressbar" :aria-valuenow="progress.percent" aria-valuemin="0" aria-valuemax="100" :class="{ bad: progress.failed }">
          <i :style="{ width: `${progress.percent}%` }"></i>
        </div>
        <div class="follow-meta"><span>{{ progress.percent }} %</span><span v-if="elapsed">{{ t("editor.installer.elapsed", { time: elapsed }) }}</span></div>
        <ol class="follow-steps" id="follow-steps">
          <li v-for="item in progress.steps" :key="item.key" :class="item.state">
            <span class="follow-dot"><span v-if="item.state === 'running'" class="spin small"></span><template v-else-if="item.state === 'done'">✓</template><template v-else-if="item.state === 'failed'">✕</template></span>
            <span class="follow-name">{{ stepLabel(item.key) }}</span>
            <span v-if="item.state === 'running' && item.percent !== null" class="follow-pct">{{ item.percent }} %</span>
          </li>
        </ol>
      </template>
      <BrowserFlash v-if="installer.browser" :state="flash.state" />
      <div v-if="ok && download && installer.view !== 'done'" id="install-download" class="follow-card">
        <a class="btn primary big" id="download-firmware" :href="image.href" :download="image.name"><Icon name="tray-arrow-down" />{{ t("editor.firmware.download_file", { name: image.name }) }}</a>
        <ol class="steps" id="download-steps">
          <li><i18n-t keypath="editor.installer.download_steps.plug" scope="global"><template #bold><b>{{ t("editor.installer.download_steps.plug_bold") }}</b></template></i18n-t></li>
          <li><i18n-t keypath="editor.installer.download_steps.open" scope="global">
            <template #bold><b><i18n-t keypath="editor.installer.download_steps.open_bold" scope="global"><template #esphome_web><a :href="ESPHOME_WEB" target="_blank" rel="noopener">ESPHome Web</a></template></i18n-t></b></template>
          </i18n-t></li>
          <li><i18n-t :keypath="installer.calibrate ? 'editor.installer.download_steps.install_calibrate' : 'editor.installer.download_steps.install'" scope="global">
            <template #bold><b>{{ t("editor.installer.download_steps.install_bold") }}</b></template>
            <template #file>{{ image.name }}</template>
          </i18n-t></li>
        </ol>
        <small>{{ t("editor.installer.download_keep") }}</small>
      </div>
      <div v-if="ok" id="install-result" class="follow-card">
        <h2>{{ t("editor.installer.next_title") }}</h2>
        <ol class="steps" id="install-steps">
          <li><i18n-t keypath="editor.installer.pairing.tiles" scope="global"><template #bold><b>{{ t("editor.installer.pairing.tiles_bold") }}</b></template></i18n-t></li>
        </ol>
        <!-- Tessera adds the screen to Home Assistant and allows its actions by itself (app 0.4.73, ha_pairing.py), so
             the way by hand only shows when that did not work out. -->
        <details v-if="arrival === 'failed'" class="key-more" id="key-more" open>
          <summary>{{ t("editor.installer.pair_yourself") }}</summary>
          <ol class="steps" id="pair-steps">
            <li><i18n-t keypath="editor.installer.pairing.ha" scope="global"><template #bold><b>{{ t("editor.installer.pairing.ha_bold") }}</b></template><template #name>{{ installer.friendly }}</template></i18n-t> <button type="button" class="btn quiet mini" @click="openIntegrations">{{ t("editor.common.open_integrations") }}</button></li>
            <li><i18n-t keypath="editor.installer.pairing.key" scope="global"><template #bold><b>{{ t("editor.installer.pairing.key_bold") }}</b></template></i18n-t></li>
            <li><i18n-t keypath="editor.installer.pairing.actions" scope="global"><template #bold><b>{{ t("editor.installer.pairing.actions_bold") }}</b></template></i18n-t></li>
          </ol>
          <div class="key-box">
            <span>{{ t("editor.installer.api_key") }}</span><code id="api-key" ref="keyBox">{{ installer.apiKey || "" }}</code>
            <button type="button" class="btn quiet mini" id="copy-key" @click="copyText(installer.apiKey || '', keyBox)">{{ t("editor.common.copy") }}</button>
          </div>
        </details>
      </div>
      <details v-if="installer.view !== 'done'" id="install-log-wrap" class="follow-log" :open="logOpen" @toggle="logOpen = ($event.target as HTMLDetailsElement).open">
        <summary><Icon name="code-braces" />{{ t(logOpen ? "editor.installer.hide_log" : "editor.installer.show_log") }}<button v-if="logOpen" type="button" class="btn quiet mini" @click.prevent="copyText(logs.join('\n'))">{{ t("editor.common.copy") }}</button></summary>
        <pre id="install-log" ref="logBox" class="log">{{ logs.join("\n") }}</pre>
      </details>
      <footer class="setup-foot">
        <button type="button" class="btn quiet" id="install-close" :disabled="flash.busy()" @click="reset">{{ ok ? t("editor.installer.another") : t("editor.installer.start_over") }}</button>
        <span class="status-line"></span>
        <button v-if="!running && !ok" type="button" class="btn primary big" id="install-retry" @click="retry">{{ t("editor.installer.retry") }}</button>
        <button v-else type="button" class="btn big" :class="ok ? 'primary' : 'quiet'" :disabled="flash.busy()" @click="close">{{ ok ? t("editor.installer.done") : t("editor.common.close") }}</button>
      </footer>
    </div>
  </div>
</template>
