<script setup lang="ts">
// Shared firmware workspace; always a concrete profile and upload target.
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useFirmwareJob, useLineBuild } from "../composables/useFirmwareJob";
import { t } from "../i18n";
import { afterBrowserBuild, ESPHOME_WEB, firmwareImage, memoryText as memoryOf, usbTarget } from "../model/firmware-job";
import { serverStep } from "../model/screen-status";
import type { ServerSide } from "../types";
import BrowserFlash from "./BrowserFlash.vue";
import Icon from "./ui/Icon.vue";
import { flashSupport } from "../flasher/logic";
import { useBrowserFlash } from "../flasher/session";
import { buildLogHref, useBuildsStore } from "../stores/builds";
import { useUiStore } from "../stores/ui";

const ui = useUiStore();
const builds = useBuildsStore();

const data = ref<any>(null);
const file = ref("");
const target = ref("ota");
// The address of a paired screen's profile, as its Update has it (api/firmware), until the person types another: what
// they typed stays with that profile while the page is open, a field they emptied too, through every poll.
const typedHosts = reactive<Record<string, string>>({});
const host = computed({
  get: () => typedHosts[file.value] ?? data.value?.profiles?.find((p: { file: string; host?: string }) => p.file === file.value)?.host ?? "",
  set: (value: string) => { typedHosts[file.value] = value; },
});
// This computer (browser): reinstall or rescue a screen plugged into the computer this page runs on, for instance one
// that restarts over and over and so never comes online for Wi-Fi / OTA. The add-on builds, this page writes the image
// without erasing first, so the screen keeps its touch calibration and settings (as ESPHome's reinstall does).
const flash = useBrowserFlash();
const support = flashSupport();
// The build this page asked for last, by its id in the add-on's build line (useLineBuild): it may wait its turn behind
// another screen's build. `browser`: this page writes its image once it is built.
const asked = ref<{ id: number; file: string; browser: boolean } | null>(null);
const followed = useLineBuild(() => asked.value?.id);
// The job, followed every few seconds while the page is in sight (composables/useFirmwareJob.ts): every answer, this
// page's own or another's, lands here. The first one picks the first profile.
let first = true;
function take(next: any) {
  data.value = next;
  if (first || !file.value) file.value = next.profiles[0]?.file || "";
  first = false;
  // USB stays chosen while the board is replugged; a port that went away falls back to the first one.
  target.value = usbTarget(target.value, next.ports || []);
}
const firmware = useFirmwareJob({ onAnswer: take, onError: (e) => ui.toast(e.message) });
async function refreshFirmware() {
  try { await firmware.refresh(); } catch (e: any) { ui.toast(e.message); }
}
// Something builds or waits in the add-on's line. A new job is never refused for it: it waits its turn.
const running = computed(() => data.value?.job?.state === "running" || followed.onItsWay.value);
const disabled = computed(() => !data.value || !data.value.available || !data.value.profiles?.length);
const installDisabled = computed(() => disabled.value || target.value === "usb" ||
  (target.value === "browser" && (support !== "ok" || flash.busy() || flash.state.phase === "waiting")));
const chipOf = (name: string): string | null => data.value?.profiles?.find((p: { file: string; chip?: string }) => p.file === name)?.chip || null;
const browserHint = computed(() => t(support === "ok" ? "editor.webflash.firmware_hint" : `editor.webflash.unavailable.${support}`));
// The build this page writes from the browser: once it ended, write its image, or let go of the port.
watch(() => [followed.build.value?.state, flash.state.phase] as const, ([state, phase]) => {
  const wanted = asked.value;
  if (!wanted?.browser || !builds.lineEnded(followed.build.value)) return;
  asked.value = { ...wanted, browser: false };
  if (afterBrowserBuild(state, phase) === "write") flash.install(wanted.file, false);
  else flash.cancel();
});
const ports = computed<string[]>(() => data.value?.ports || []);
// The build this page asked for while it is known, else the add-on's last job: its profile, action and where it stands,
// and while it waits, its turn.
const statusText = computed(() => {
  if (!data.value) return t("editor.common.loading");
  if (!data.value.available) return t("editor.firmware.no_cli");
  const own = followed.build.value;
  // Where its compile runs: on the build server, at its step, or here after all, with the reason (build_server.py).
  const where = (build: ServerSide | null | undefined) => { const step = serverStep(build); return step ? ` · ${step.text}` : ""; };
  if (own) return `${own.file} · ${own.action} · ${own.state === "queued" ? t("editor.firmware.waiting", own.place || 1) : own.state}${own.state === "running" ? where(own) : ""}${own.reason ? ` · ${own.reason}` : ""}`;
  const job = data.value.job;
  return job ? `${job.file} · ${job.action} · ${job.state}${job.state === "running" ? where(job) : ""}` : t("editor.firmware.choose");
});
// Every build's log the add-on keeps on disk (build_logs.py), also past a restart: asked when the page opens and again
// whenever a build ends.
const keptLogs = computed(() => builds.keptLogs);
const endedIds = computed(() => builds.line.filter((b) => builds.lineEnded(b)).map((b) => b.id).join(","));
watch(endedIds, () => void builds.loadKeptLogs(), { immediate: true });
const keptWhen = (at?: number) => (at ? new Date(at * 1000).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" }) : "");
const keptState = (state: string) => t(`editor.firmware.kept_state.${["success", "failed", "interrupted", "running"].includes(state) ? state : "other"}`);
// What the add-on says about the memory the build has (build_memory.py, app 0.4.65), under the status line.
const memoryText = computed(() => memoryOf(followed.build.value ?? data.value?.job)?.text || "");
// The log of the build this page asked for once it is known, else whatever builds now.
const logLines = computed(() => (followed.build.value && followed.build.value.state !== "queued" ? followed.logs.value : data.value?.logs || []));
const downloadReady = computed(() => target.value === "download" && !!file.value && !!data.value?.downloads?.includes(file.value));
const image = computed(() => firmwareImage(file.value));
async function run(action: "validate" | "build" | "install") {
  if (action === "install" && target.value === "browser") return runBrowser();
  try {
    const build = await builds.askBuild({
      file: file.value,
      action: action === "validate" ? "validate" : action === "build" ? "build" : target.value === "download" ? "download" : "install",
      target: action !== "install" ? "" : target.value === "ota" ? host.value.trim() : target.value === "download" ? "" : target.value,
    });
    asked.value = { id: build.id, file: file.value, browser: false };
  } catch (e: any) {
    ui.toast(e.message);
  }
}
// The port picker first, from this click; then the build, whose image the watch above writes.
async function runBrowser() {
  const name = file.value;
  if (!(await flash.connect(chipOf(name)))) return;
  try {
    const build = await builds.askBuild({ file: name, action: "download", target: "" });
    asked.value = { id: build.id, file: name, browser: true };
  } catch (e: any) {
    flash.cancel();
    ui.toast(e.message);
  }
}
onMounted(refreshFirmware);
onBeforeUnmount(() => flash.cancel());
</script>

<template>
  <div class="panel" id="firmware-dialog">
    <div class="panel-head">
      <div class="tx">
        <span class="eyebrow">{{ t("editor.nav.firmware") }}</span>
        <h1>{{ t("editor.firmware.title") }}</h1>
        <i18n-t keypath="editor.firmware.intro" tag="p" scope="global">
          <template #ota><b>{{ t("editor.firmware.ota") }}</b></template>
          <template #download><b>{{ t("editor.firmware.download") }}</b></template>
          <template #check><b>{{ t("editor.firmware.check") }}</b></template>
          <template #build><b>{{ t("editor.firmware.build") }}</b></template>
          <template #install><b>{{ t("editor.firmware.install") }}</b></template>
        </i18n-t>
      </div>
      <button type="button" class="btn quiet" id="close-firmware" :disabled="flash.busy()" @click="ui.go('')">{{ t("editor.common.back") }}</button>
    </div>
    <div class="card">
      <div class="card-grid">
        <div class="field">
          <label class="f-label" for="firmware-file">{{ t("editor.firmware.profile") }}</label>
          <select id="firmware-file" v-model="file">
            <option v-for="p in data?.profiles || []" :key="p.file" :value="p.file">{{ p.file }}</option>
          </select>
        </div>
        <div class="field">
          <label class="f-label" for="firmware-port">{{ t("editor.firmware.install_to") }}</label>
          <select id="firmware-port" v-model="target">
            <optgroup :label="t('editor.webflash.group_wifi')">
              <option value="ota">{{ t("editor.firmware.ota") }}</option>
            </optgroup>
            <optgroup :label="t('editor.webflash.group_ha')">
              <option v-if="!ports.length" value="usb">{{ t("editor.firmware.no_board") }}</option>
              <option v-for="p in ports" :key="p" :value="p">{{ p }}</option>
            </optgroup>
            <optgroup :label="t('editor.webflash.group_here')">
              <option value="browser">{{ t("editor.webflash.target") }}</option>
              <option value="download">{{ t("editor.firmware.download_target") }}</option>
            </optgroup>
          </select>
        </div>
        <div v-if="target === 'ota'" class="field" id="firmware-host-label">
          <label class="f-label" for="firmware-host">{{ t("editor.firmware.host") }}</label>
          <input id="firmware-host" v-model="host" :placeholder="file ? file.replace(/\.yaml$/, '.local') : 'screen-livingroom.local'" />
        </div>
      </div>
      <div class="actions">
        <button type="button" class="btn quiet" id="firmware-validate" :disabled="disabled" @click="run('validate')">{{ t("editor.firmware.check") }}</button>
        <button type="button" class="btn quiet" id="firmware-build" :disabled="disabled" @click="run('build')">{{ t("editor.firmware.build") }}</button>
        <button type="button" class="btn primary" id="firmware-install" :disabled="installDisabled" @click="run('install')">{{ target === "download" ? t("editor.firmware.build_download") : target === "browser" ? t("editor.webflash.go") : t("editor.firmware.install") }}</button>
        <span v-if="running" class="spin"></span>
      </div>
      <p id="firmware-status" class="status-line" role="status">{{ statusText }}</p>
      <p v-if="memoryText" id="firmware-memory" class="notice warn">{{ memoryText }}</p>
      <template v-if="target === 'browser'">
        <small id="firmware-browser-hint">{{ browserHint }}</small>
        <BrowserFlash :state="flash.state" />
      </template>
      <div v-if="downloadReady" id="firmware-download" class="card" style="background: var(--surface-2)">
        <a class="btn primary" id="firmware-download-link" :href="image.href" :download="image.name">{{ t("editor.firmware.download_file", { name: image.name }) }}</a>
        <i18n-t keypath="editor.firmware.download_how" tag="small" scope="global">
          <template #esphome_web><a :href="ESPHOME_WEB" target="_blank" rel="noopener">ESPHome Web</a></template>
        </i18n-t>
      </div>
    </div>
    <pre id="firmware-log" class="log">{{ logLines.join("\n") }}</pre>
    <section class="kept-logs" id="firmware-kept-logs">
      <h3>{{ t("editor.firmware.kept_title") }}</h3>
      <p class="kept-note">{{ t("editor.firmware.kept_note") }}</p>
      <p v-if="!keptLogs.length" class="kept-note">{{ t("editor.firmware.kept_none") }}</p>
      <ul v-else class="kept-list">
        <li v-for="log in keptLogs" :key="log.key" :class="log.state" :data-key="log.key">
          <span class="kept-words"><b>{{ log.file || log.key }}</b><small>{{ keptWhen(log.started) }} · {{ log.by }} · <span class="kept-state">{{ keptState(log.state) }}</span><template v-if="log.reason"> · {{ log.reason }}</template></small></span>
          <a class="btn quiet mini" :href="buildLogHref(log.key)" :download="`${log.key}.log`"><Icon name="tray-arrow-down" />{{ t("editor.firmware.kept_download") }}</a>
        </li>
      </ul>
    </section>
  </div>
</template>
