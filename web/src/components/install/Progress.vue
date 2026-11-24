<script setup lang="ts">
// New screen after its last step (app 0.4.103): the whole way until the screen works, not until its firmware is built.
// Four steps a person knows (model/install-progress.ts journey): the software is made, it goes onto the screen (by the
// add-on, this browser, or the person with a file), the screen starts and joins the Wi-Fi, and Tessera adds it to
// Home Assistant's ESPHome integration and allows its actions (ha_pairing.py). Each says what happens and whether
// anything is asked of the person; ESPHome's own log is a click away. Only when Home Assistant has the screen, online
// and allowed to act, does the page say it is ready, with the way on to its pages. When it stops short, it says where
// and what helps: the build's reason, the hotspot when the Wi-Fi is wrong, the way by hand when Home Assistant asks.
import { computed, ref } from "vue";
import { ESPHOME_WEB } from "../../model/firmware-job";
import { injectInstaller } from "../../composables/useInstaller";
import { useStickToBottom } from "../../composables/useStickToBottom";
import { t } from "../../i18n";
import { useSessionStore } from "../../stores/session";
import { useUiStore } from "../../stores/ui";
import BrowserFlash from "../BrowserFlash.vue";
import DeviceArt from "../DeviceArt.vue";
import Icon from "../ui/Icon.vue";

const ui = useUiStore(), session = useSessionStore();
const install = injectInstaller();
const keyBox = ref<HTMLElement | null>(null);
const logBox = ref<HTMLElement | null>(null);
useStickToBottom(logBox, () => install.logs.length, { near: 40 });

const name = computed(() => install.installer.friendly);
const saved = computed(() => install.installer.view === "done" && !install.installer.build);
const ready = computed(() => install.journey.done);
// From this browser the page itself writes the firmware once it is built: until it is on the screen, closing the page
// would let go of the cable's port and nothing would be written, so the page says to keep it open and offers no Close.
const tied = computed(() => install.installer.browser && install.flash.state.phase !== "done");
// The step it is at: the first that is not done.
const now = computed(() => install.journey.steps.find((step) => step.state !== "done")?.key ?? null);
const failed = computed(() => (!install.running && !install.ok) || install.journey.failed);
const waits = computed(() => install.job?.state === "queued");
const title = computed(() => {
  if (saved.value) return t("editor.installer.flow.saved_title", { name: name.value });
  if (ready.value) return t("editor.installer.flow.ready_title", { name: name.value });
  if (!install.running && !install.ok) return t(install.download ? "editor.installer.progress.build_failed" : "editor.installer.progress.install_failed");
  if (install.arrival === "missing") return t("editor.installer.arrive.missing", { name: name.value });
  if (install.arrival === "failed") return t("editor.installer.flow.ha_ask_title", { name: name.value });
  if (waits.value) return t("editor.installer.progress.waiting");
  return t(`editor.installer.flow.now.${now.value === "write" && install.download ? "write_self" : now.value || "build"}`, { name: name.value });
});
const lead = computed(() => {
  if (saved.value) return t("editor.installer.detail.saved");
  if (ready.value) return t("editor.installer.flow.ready_lead");
  if (!install.running && !install.ok) return install.progressDetail;
  if (install.arrival === "missing" || install.arrival === "failed") return "";
  if (waits.value) return install.progressDetail;
  if (now.value === "wifi" && install.installer.calibrate) return t("editor.installer.flow.lead.wifi_calibrate");
  return t(`editor.installer.flow.lead.${now.value === "write" && install.download ? "write_self" : install.installer.browser && now.value === "build" ? "build_browser" : now.value || "build"}`);
});
const stepName = (key: string) => t(`editor.installer.flow.steps.${key === "write" && install.download ? "write_self" : key}`);
// The page's own check stands beside the screen once it is ready, so the drawing itself keeps quiet then.
const artState = computed(() => (ready.value ? "idle" : failed.value ? "failed" : "working"));
// Pages next: the screen's own page in the editor, where its tiles are chosen.
function toPages() { if (install.made) session.select(install.made.id); else ui.go(""); }
</script>

<template>
  <div id="install-progress" class="ob-body follow" :class="{ ready, failed }">
    <div class="ob-hero" aria-hidden="true">
      <div class="ob-frame" :style="{ '--art-ratio': install.art.width / install.art.height }">
        <DeviceArt v-bind="install.art" :name="name" :lit="saved ? 0 : install.journey.percent / 100" :state="artState" />
        <span v-if="ready" class="ob-done-mark"><Icon name="check" /></span>
      </div>
    </div>
    <div class="ob-step-words">
      <h1 id="progress-title">{{ title }}</h1>
      <p v-if="lead" id="progress-detail" class="ob-lead">{{ lead }}</p>
    </div>
    <!-- Ready: what is now true of it, each checked by Home Assistant, not assumed. -->
    <ul v-if="ready" class="ob-recap" id="ready-recap">
      <li v-for="key in ['wifi', 'ha', 'actions']" :key="key"><Icon name="check" />{{ t(`editor.installer.flow.recap.${key}`) }}</li>
    </ul>

    <!-- A file the person puts on the screen: the file and the three steps, until Home Assistant sees the screen. -->
    <div v-if="install.ok && install.download && now === 'write'" id="install-download" class="ob-ask plain">
      <a class="ob-go" id="download-firmware" :href="install.image.href" :download="install.image.name"><Icon name="tray-arrow-down" />{{ t("editor.firmware.download_file", { name: install.image.name }) }}</a>
      <ol class="ob-howto" id="download-steps">
        <li><span><i18n-t keypath="editor.installer.download_steps.plug" scope="global"><template #bold><b>{{ t("editor.installer.download_steps.plug_bold") }}</b></template></i18n-t></span></li>
        <li><span><i18n-t keypath="editor.installer.download_steps.open" scope="global">
          <template #bold><b><i18n-t keypath="editor.installer.download_steps.open_bold" scope="global"><template #esphome_web><a :href="ESPHOME_WEB" target="_blank" rel="noopener">ESPHome Web</a></template></i18n-t></b></template>
        </i18n-t></span></li>
        <li><span><i18n-t :keypath="install.installer.calibrate ? 'editor.installer.download_steps.install_calibrate' : 'editor.installer.download_steps.install'" scope="global">
          <template #bold><b>{{ t("editor.installer.download_steps.install_bold") }}</b></template>
          <template #file>{{ install.image.name }}</template>
        </i18n-t></span></li>
      </ol>
      <small>{{ t("editor.installer.download_keep") }}</small>
    </div>
    <!-- On its way: one bar, and the four steps with the one it is at. -->
    <template v-if="!saved && !ready">
      <div class="ob-bar" role="progressbar" :aria-valuenow="install.journey.percent" aria-valuemin="0" aria-valuemax="100" :class="{ bad: failed }">
        <i :style="{ width: `${install.journey.percent}%` }"></i>
      </div>
      <ol class="ob-journey" id="follow-steps">
        <li v-for="step in install.journey.steps" :key="step.key" :class="step.state" :data-step="step.key">
          <span class="ob-journey-dot"><span v-if="step.state === 'running'" class="spin small"></span><Icon v-else-if="step.state === 'done'" name="check" /><Icon v-else-if="step.state === 'failed'" name="close" /></span>
          <span class="ob-journey-name">{{ stepName(step.key) }}</span>
          <span v-if="step.state === 'running' && step.percent !== null" class="ob-journey-pct">{{ step.percent }} %</span>
        </li>
      </ol>
      <p v-if="install.elapsed && install.running" class="ob-meta">{{ t("editor.installer.elapsed", { time: install.elapsed }) }} · {{ t(tied ? "editor.installer.flow.keep_open" : "editor.installer.flow.may_close") }}</p>
    </template>

    <!-- The memory the build has (app 0.4.65): a slower build the person understands, or why it stopped. -->
    <div v-if="install.memory && !install.ok" class="ob-ask" :class="[install.memory.reason, { stopped: install.memory.reason === 'out' || install.memory.reason === 'limit' }]" id="memory-note" role="status">
      <h2><Icon name="alert-circle-outline" />{{ install.memory.title }}</h2>
      <p>{{ install.memory.text }}</p>
    </div>
    <BrowserFlash v-if="install.installer.browser && !ready" :state="install.flash.state" />


    <!-- Not on the Wi-Fi after three minutes: the likely cause and the fix, with the installation again. -->
    <div v-if="install.arrival === 'missing'" class="ob-ask missing" id="arrive" role="status">
      <p>{{ t(install.chosen?.hotspot === false ? "editor.installer.arrive.no_hotspot" : "editor.installer.arrive.hotspot") }}</p>
      <p class="hint">{{ t("editor.installer.wifi.other_note") }}</p>
      <form class="arrive-form" id="arrive-wifi" novalidate @submit.prevent="install.fixWifi">
        <div class="field"><label class="f-label" for="fix_ssid">{{ t("editor.installer.wifi.ssid") }}</label><input id="fix_ssid" v-model="install.form.wifi_ssid" required autocomplete="off" /></div>
        <div class="field"><label class="f-label" for="fix_password">{{ t("editor.installer.wifi.password") }}</label><input id="fix_password" type="password" v-model="install.form.wifi_password" autocomplete="new-password" /></div>
        <button type="submit" class="btn primary" :disabled="install.fixing || install.flash.busy()"><span v-if="install.fixing" class="spin small"></span>{{ t("editor.installer.arrive.change") }}</button>
      </form>
    </div>
    <span v-else-if="install.arrival" class="sr-only" id="arrive" :class="install.arrival">{{ install.arrival }}</span>

    <!-- Home Assistant asked something only the person can answer: the steps by hand, with the screen's key. -->
    <div v-if="install.arrival === 'failed' || saved" class="ob-ask plain" id="key-more">
      <ol v-if="install.arrival === 'failed'" class="ob-howto" id="pair-steps">
        <li><span><i18n-t keypath="editor.installer.pairing.ha" scope="global"><template #bold><b>{{ t("editor.installer.pairing.ha_bold") }}</b></template><template #name>{{ name }}</template></i18n-t> <button type="button" class="btn quiet mini" @click="ui.openIntegrations">{{ t("editor.common.open_integrations") }}</button></span></li>
        <li><span><i18n-t keypath="editor.installer.pairing.key" scope="global"><template #bold><b>{{ t("editor.installer.pairing.key_bold") }}</b></template></i18n-t></span></li>
        <li><span><i18n-t keypath="editor.installer.pairing.actions" scope="global"><template #bold><b>{{ t("editor.installer.pairing.actions_bold") }}</b></template></i18n-t></span></li>
      </ol>
      <div class="key-box">
        <span>{{ t("editor.installer.api_key") }}</span><code id="api-key" ref="keyBox">{{ install.installer.apiKey || "" }}</code>
        <button type="button" class="btn quiet mini" id="copy-key" @click="ui.copyText(install.installer.apiKey || '', keyBox)">{{ t("editor.common.copy") }}</button>
      </div>
    </div>

    <details v-if="!saved && !ready" id="install-log-wrap" class="ob-log" :open="install.logOpen" @toggle="install.logOpen = ($event.target as HTMLDetailsElement).open">
      <summary><Icon name="code-braces" />{{ t(install.logOpen ? "editor.installer.hide_log" : "editor.installer.flow.show_log") }}<button v-if="install.logOpen" type="button" class="btn quiet mini" @click.prevent="ui.copyText(install.logs.join('\n'), null, 'log')">{{ t("editor.common.copy") }}</button></summary>
      <pre id="install-log" ref="logBox" class="log">{{ install.logs.join("\n") }}</pre>
    </details>

    <footer class="ob-foot">
      <template v-if="ready">
        <button type="button" class="ob-go" id="install-pages" @click="toPages">{{ t("editor.installer.flow.to_pages") }}</button>
        <button type="button" class="ob-quiet" id="install-close" @click="install.reset">{{ t("editor.installer.flow.another") }}</button>
      </template>
      <template v-else-if="!install.running && !install.ok">
        <button type="button" class="ob-go" id="install-retry" @click="install.retry">{{ t("editor.installer.retry") }}</button>
        <button type="button" class="ob-quiet" id="install-close" :disabled="install.flash.busy()" @click="install.reset">{{ t("editor.installer.start_over") }}</button>
      </template>
      <template v-else-if="saved">
        <button type="button" class="ob-go" @click="install.close">{{ t("editor.installer.done") }}</button>
        <button type="button" class="ob-quiet" id="install-close" @click="install.reset">{{ t("editor.installer.flow.another") }}</button>
      </template>
      <button v-else-if="!tied" type="button" class="ob-quiet" id="install-close" @click="install.close">{{ t("editor.installer.flow.close_follow") }}</button>
    </footer>
  </div>
</template>
