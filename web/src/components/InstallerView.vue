<script setup lang="ts">
// New screen: profile, Wi-Fi, and the first flash in one go.
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { getJson, send } from "../api";
import { copyText, go, openIntegrations, toast } from "../store";

// Download: ESP Screens builds, the owner flashes the file from their own computer. ESPHome Web is ESPHome's own
// browser flasher; this address opens it with its hint for a downloaded project (as ESPHome Device Builder does).
const ESPHOME_WEB = "https://web.esphome.io/?dashboard_install";
const DOWNLOAD_TARGET = "Download · flash from your own computer";
const form = reactive({ board: "cyd", friendly_name: "", name: "", wifi_ssid: "", wifi_password: "", target: "" });
const installer = reactive({
  view: "setup" as "setup" | "progress" | "done", file: null as string | null, friendly: "", board: "cyd", target: "",
  apiKey: null as string | null, nodeEdited: false, jobState: null as string | null, picked: false, action: null as string | null,
});
const nodeVisible = ref(false);
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
const nodePreview = computed(() => form.name || "…");
const ports = computed<string[]>(() => data.value?.ports || []);
const wifi = computed(() => data.value?.wifi);
const askWifi = computed(() => wifi.value?.state === "new" || wifi.value?.state === "missing");
const wifiMissing = computed<string[]>(() => wifi.value?.missing || []);
const wifiStatus = computed(() => wifi.value?.state === "new"
  ? "Fill in once: ESP Screens saves this in ESPHome secrets.yaml, later screens use it automatically."
  : "Your ESPHome secrets.yaml is still missing Wi-Fi details. ESP Screens only fills in the missing lines.");
const wifiNote = computed(() => wifi.value?.state === "ready"
  ? "Wi-Fi comes from your ESPHome secrets.yaml."
  : wifi.value?.state === "invalid"
    ? "secrets.yaml in the ESPHome folder isn't valid YAML. Fix the file first; it won't be overwritten."
    : "");
const targetHint = computed(() => form.target === "usb"
  ? "Connect the screen with a USB data cable to the Home Assistant machine; the list refreshes on its own. Or choose Download to use your own computer."
  : form.target === "download"
    ? "Download the firmware and put it on the screen from your own computer, in Chrome or Edge. After that, updates go over Wi-Fi."
    : !form.target
      ? "The profile goes into the ESPHome folder. You can install later via Firmware & USB, or from ESPHome Device Builder."
      : ports.value.length > 1
        ? "More than one board connected: choose this screen's port."
        : "Once over USB; after that, everything is wireless.");
const goLabel = computed(() => (form.target === "download" ? "Build & download" : form.target ? "Install" : "Save profile"));
const busyElsewhere = computed(() => data.value?.job?.state === "running" && !(installer.file && data.value.job.file === installer.file));
const goDisabled = computed(() => submitting.value || wifi.value?.state === "invalid" || form.target === "usb" ||
  (!!form.target && (busyElsewhere.value || !data.value?.available)));
// USB on the Home Assistant machine is always listed first, also before a board is plugged in, so nobody
// concludes it isn't possible; "usb" stands for that port until one shows up.
function syncTarget() {
  const current = form.target;
  const kept = current === "download" || current === "" ? installer.picked : ports.value.includes(current);
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
      ? `A build or installation is already running (${current.file}). Wait for it to finish.`
      : !next.available && form.target
        ? "The ESPHome CLI is missing from this installation; only saving the profile is possible."
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
const running = computed(() => job.value?.state === "running");
const ok = computed(() => installer.view === "done" || job.value?.state === "success");
const download = computed(() => installer.action === "download");
const title = computed(() => installer.view === "done" ? "Profile saved." : running.value ? "One moment…" : ok.value ? (download.value ? "Ready to download." : "Done.") : "That didn't work.");
const progressTitle = computed(() => installer.view === "done"
  ? `${installer.file} is in the ESPHome folder`
  : running.value
    ? job.value?.stage === "upload" ? `Writing firmware to ${installer.friendly}…` : "Building firmware…"
    : ok.value
      ? download.value ? `Firmware for ${installer.friendly} is ready` : `Firmware is on ${installer.friendly}`
      : download.value ? "Build failed" : "Install failed");
const progressDetail = computed(() => installer.view === "done"
  ? "Install it later from Firmware & USB: choose this profile, then the USB port of the Home Assistant machine, or Download to put the firmware on the screen from your own computer. Save the API key for pairing:"
  : running.value
    ? job.value?.stage === "upload"
      ? "Don't disconnect the USB cable yet."
      : `A first build takes a few minutes on a Raspberry Pi. You can leave this page: the ${download.value ? "build" : "installation"} keeps running and you'll find it again under New screen.`
    : ok.value
      ? download.value
        ? "Put it on the screen from your own computer, then pair the screen with Home Assistant."
        : `The screen boots up and connects to your Wi-Fi.${installer.board === "cyd" ? " The CYD first asks for a touch calibration: tap the crosshairs." : ""} Pair it with Home Assistant now:`
      : logs.value.filter((l) => /error/i.test(l)).pop() || logs.value.filter((l) => /failed/i.test(l)).pop() || "See the log below.");
const image = computed(() => ({ href: `api/firmware/profiles/${encodeURIComponent(installer.file || "")}/download`, name: (installer.file || "").replace(/\.yaml$/, "") + ".factory.bin" }));
const pairingSteps = computed(() => [
  ["Go to Home Assistant → Settings → Devices & services.", ` This happens outside ESP Screens. Home Assistant discovers ${installer.friendly} as an ESPHome device; click Add. Not discovered? Add ESPHome manually with the screen's IP address. `],
  ["Paste the API key", " above when Home Assistant asks for an encryption key."],
  ["Allow HA actions:", " ESPHome integration → Configure → “Allow the device to perform Home Assistant actions”. Without this, the screen sees everything but controls nothing."],
  ["Choose your tiles.", " Back in ESP Screens, the screen appears in the list on the left within about thirty seconds; until then it's shown there as “not yet in Home Assistant”."],
]);
async function submit(event: Event) {
  const element = event.target as HTMLFormElement;
  if (!installer.nodeEdited) form.name = slug(form.friendly_name);
  if (!element.reportValidity()) return;
  submitting.value = true;
  status.value = "";
  try {
    const payload: Record<string, string> = { board: form.board, friendly_name: form.friendly_name, name: form.name, target: form.target };
    if (askWifi.value) { if (wifiMissing.value.includes("wifi_ssid")) payload.wifi_ssid = form.wifi_ssid; if (wifiMissing.value.includes("wifi_password")) payload.wifi_password = form.wifi_password; }
    const result = await send("firmware/profiles", "POST", payload);
    Object.assign(installer, { file: result.file, apiKey: result.api_key, friendly: form.friendly_name.trim(), board: form.board, target: form.target });
    form.wifi_password = "";
    if (result.job) showProgress(result.job, []);
    else installer.view = "done";
  } catch (err: any) {
    status.value = err.message;
  } finally {
    submitting.value = false;
  }
}
async function retry() {
  try {
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
  Object.assign(installer, { view: "setup", file: null, apiKey: null, nodeEdited: false, jobState: null, target: "", picked: false, action: null });
  Object.assign(form, { board: "cyd", friendly_name: "", name: "", wifi_ssid: "", wifi_password: "", target: "" });
  nodeVisible.value = false; job.value = null; logs.value = []; status.value = ""; note.value = ""; logOpen.value = false;
  installerRefresh();
}
function close() {
  if (installer.view === "progress" && installer.jobState !== "running") installer.view = "done";
  go("");
}
onMounted(() => { installerRefresh(); poll = window.setInterval(installerRefresh, 3000); });
onBeforeUnmount(() => clearInterval(poll));
</script>

<template>
  <div class="panel" id="installer">
    <div class="panel-head">
      <div class="tx">
        <span class="eyebrow">New screen</span>
        <h1 id="install-title">{{ installer.view === "setup" ? "Connect and install." : title }}</h1>
        <p v-if="installer.view === 'setup'">ESP Screens creates the screen's own profile with unique keys and builds the firmware. Connect the screen with a USB data cable to the machine running Home Assistant, or download the firmware and put it on the screen from your own computer.</p>
      </div>
      <button type="button" class="btn quiet" id="close-install" aria-label="Close" @click="close">← Back</button>
    </div>
    <form v-if="installer.view === 'setup'" id="install-form" class="card" @submit.prevent="submit">
      <fieldset>
        <legend>Which screen do you have?</legend>
        <div class="boards">
          <label class="board"><input type="radio" name="board" value="cyd" v-model="form.board" /><span><b>CYD · 2.8 inch</b><small>ESP32-2432S028 · 320 × 240</small></span></label>
          <label class="board"><input type="radio" name="board" value="guition" v-model="form.board" /><span><b>Guition · 4 inch</b><small>ESP32-S3-4848S040 · 480 × 480 · GT911</small></span></label>
          <label class="board"><input type="radio" name="board" value="jc8012p4a1" v-model="form.board" /><span><b>Guition · 10.1 inch</b><small>JC8012P4A1 · 1280 × 800 · MIPI-DSI · GSL3680</small></span></label>
        </div>
      </fieldset>
      <div class="field">
        <label class="f-label" for="friendly_name">Name</label>
        <input id="friendly_name" name="friendly_name" v-model="form.friendly_name" required maxlength="60" placeholder="Living room screen" autocomplete="off" />
        <small class="node-line">Device name <code id="node-preview">{{ nodePreview }}</code><button type="button" class="btn link mini" id="edit-node" @click="installer.nodeEdited = true; nodeVisible = true">customize</button></small>
        <small>Every screen gets its own profile with its own keys. Four screens? Go through this four times with a different name.</small>
      </div>
      <div v-if="nodeVisible" class="field" id="node-label">
        <label class="f-label" for="node-name">Device name</label>
        <input id="node-name" name="name" v-model="form.name" pattern="[a-z][a-z0-9\-]{0,29}" maxlength="30" autocomplete="off" @input="installer.nodeEdited = true" />
        <small>Lowercase letters, digits, and dashes. A different name for each screen.</small>
      </div>
      <fieldset v-if="askWifi" id="wifi-fields" class="wifi">
        <legend>Wi-Fi</legend>
        <p class="hint" id="wifi-status">{{ wifiStatus }}</p>
        <div v-if="wifiMissing.includes('wifi_ssid')" class="field" id="wifi-ssid-label"><label class="f-label" for="wifi_ssid">Wi-Fi name (2.4 GHz)</label><input id="wifi_ssid" name="wifi_ssid" v-model="form.wifi_ssid" autocomplete="off" /></div>
        <div v-if="wifiMissing.includes('wifi_password')" class="field" id="wifi-password-label"><label class="f-label" for="wifi_password">Wi-Fi password</label><input id="wifi_password" name="wifi_password" type="password" v-model="form.wifi_password" autocomplete="new-password" /></div>
      </fieldset>
      <div class="field">
        <label class="f-label" for="install-target">Install via</label>
        <select id="install-target" name="target" v-model="form.target" @change="installer.picked = true; installerRefresh()">
          <option v-if="!ports.length" value="usb">USB · no board found on the Home Assistant machine yet</option>
          <option v-for="p in ports" :key="p" :value="p">{{ portLabel(p) }}</option>
          <option value="download">{{ DOWNLOAD_TARGET }}</option>
          <option value="">Later · save profile only</option>
        </select>
        <small id="target-hint">{{ targetHint }}</small>
      </div>
      <p v-if="note" class="hint" id="install-note">{{ note }}</p>
      <div class="actions">
        <button type="submit" class="btn primary" id="install-go" :disabled="goDisabled">{{ goLabel }}</button>
        <span id="install-status" class="status-line error" role="status">{{ status }}</span>
      </div>
    </form>
    <div v-else id="install-progress" class="card">
      <div class="progress-head">
        <span v-if="running" class="spin" id="progress-spin"></span>
        <span v-else class="outcome" :class="ok ? 'ok' : 'bad'" id="progress-mark">{{ ok ? "✓" : "✕" }}</span>
        <strong id="progress-title">{{ progressTitle }}</strong>
      </div>
      <p id="progress-detail">{{ progressDetail }}</p>
      <div v-if="ok && download && installer.view !== 'done'" id="install-download" class="card" style="background: var(--surface-2)">
        <a class="btn primary" id="download-firmware" :href="image.href" :download="image.name">Download {{ image.name }}</a>
        <ol class="steps" id="download-steps">
          <li><b>Plug the screen into your computer</b> with a USB data cable.</li>
          <li><b>Open <a :href="ESPHOME_WEB" target="_blank" rel="noopener">ESPHome Web</a></b> in Chrome or Edge, click Connect and choose the screen's USB port.</li>
          <li><b>Click Install</b> and select {{ image.name }}. The screen restarts and joins your Wi-Fi.{{ installer.board === "cyd" ? " The CYD first asks for a touch calibration: tap the crosshairs." : "" }}</li>
        </ol>
        <small>The file holds your Wi-Fi password and the screen's keys: keep it to yourself.</small>
      </div>
      <div v-if="ok" id="install-result" class="field">
        <div class="key-box">
          <span>API key</span><code id="api-key" ref="keyBox">{{ installer.apiKey || "" }}</code>
          <button type="button" class="btn quiet mini" id="copy-key" @click="copyText(installer.apiKey || '', keyBox)">Copy</button>
        </div>
        <ol class="steps" id="install-steps">
          <li v-for="([b, t], i) in pairingSteps" :key="i"><b>{{ b }}</b>{{ t }}<button v-if="i === 0" type="button" class="btn quiet mini" @click="openIntegrations">Open Devices &amp; services</button></li>
        </ol>
      </div>
      <details v-if="installer.view !== 'done'" id="install-log-wrap" class="log-wrap" :open="logOpen" @toggle="logOpen = ($event.target as HTMLDetailsElement).open">
        <summary>ESPHome log</summary>
        <pre id="install-log" class="log">{{ logs.join("\n") }}</pre>
      </details>
      <div class="actions">
        <button v-if="!running && !ok" type="button" class="btn primary" id="install-retry" @click="retry">Retry</button>
        <button type="button" class="btn quiet" id="install-close" @click="reset">{{ ok ? "Install another screen" : "Start over" }}</button>
        <button type="button" class="btn" :class="ok ? 'primary' : 'quiet'" @click="close">{{ ok ? "Done" : "Close" }}</button>
      </div>
    </div>
  </div>
</template>
