<script setup lang="ts">
// New screen while it installs: the screen drawn filling in, the steps it goes through, ESPHome's own log a click away,
// and once it is on, whether it reached the Wi-Fi (useArrival) and what comes next. The log follows its last line while
// someone reads the bottom, and stays put once they scroll up.
import { ref } from "vue";
import { ESPHOME_WEB } from "../../model/firmware-job";
import { stepLabel } from "../../model/install-progress";
import type { Installer } from "../../composables/useInstaller";
import { useStickToBottom } from "../../composables/useStickToBottom";
import { t } from "../../i18n";
import { useUiStore } from "../../stores/ui";
import BrowserFlash from "../BrowserFlash.vue";
import DeviceArt from "../DeviceArt.vue";
import Icon from "../ui/Icon.vue";

const ui = useUiStore();
const props = defineProps<{ install: Installer }>();
const keyBox = ref<HTMLElement | null>(null);
const logBox = ref<HTMLElement | null>(null);
useStickToBottom(logBox, () => props.install.logs.length, { near: 40 });
</script>

<template>
  <div id="install-progress" class="setup-body follow">
    <div class="follow-art" aria-hidden="true">
      <div class="make-frame" :style="{ '--art-ratio': (install.art.width + 14 * install.art.height / 100) / (install.art.height + 14 * install.art.height / 100) }">
        <DeviceArt v-bind="install.art" :name="install.installer.friendly" :lit="install.installer.view === 'done' ? 0 : install.progress.percent / 100" :state="install.artState" />
      </div>
    </div>
    <div class="follow-words">
      <h1 id="progress-title">{{ install.progressTitle }}</h1>
      <p id="progress-detail">{{ install.progressDetail }}</p>
    </div>
    <!-- The memory the build has (app 0.4.65): a slower build the person understands, or why it stopped. -->
    <div v-if="install.memory && !install.ok" class="memory-note" :class="[install.memory.reason, { stopped: install.memory.reason === 'out' || install.memory.reason === 'limit' }]" id="memory-note" role="status">
      <h2><Icon name="alert-circle-outline" />{{ install.memory.title }}</h2>
      <p>{{ install.memory.text }}</p>
    </div>
    <!-- Did it reach the Wi-Fi: waiting, seen by Home Assistant, paired, or after three minutes the way to fix it. -->
    <div v-if="install.arrival" class="arrive" :class="install.arrival" id="arrive" role="status">
      <p v-if="install.arrival !== 'missing'" class="arrive-line">
        <span v-if="install.arrival === 'waiting' || install.arrival === 'seen'" class="spin small"></span><Icon v-else :name="install.arrival === 'failed' ? 'alert-circle-outline' : 'check-circle'" />
        {{ t(`editor.installer.arrive.${install.arrival}`, { name: install.installer.friendly }) }}
      </p>
      <template v-else>
        <h2><Icon name="alert-circle-outline" />{{ t("editor.installer.arrive.missing", { name: install.installer.friendly }) }}</h2>
        <p>{{ t(install.chosen?.hotspot === false ? "editor.installer.arrive.no_hotspot" : "editor.installer.arrive.hotspot") }}</p>
        <!-- The same line as under Another network: this Wi-Fi goes into secrets.yaml, which every screen builds with. -->
        <p class="hint">{{ t("editor.installer.wifi.other_note") }}</p>
        <form class="arrive-form" id="arrive-wifi" novalidate @submit.prevent="install.fixWifi">
          <div class="field"><label class="f-label" for="fix_ssid">{{ t("editor.installer.wifi.ssid") }}</label><input id="fix_ssid" v-model="install.form.wifi_ssid" required autocomplete="off" /></div>
          <div class="field"><label class="f-label" for="fix_password">{{ t("editor.installer.wifi.password") }}</label><input id="fix_password" type="password" v-model="install.form.wifi_password" autocomplete="new-password" /></div>
          <button type="submit" class="btn primary" :disabled="install.fixing || install.flash.busy()"><span v-if="install.fixing" class="spin small"></span>{{ t("editor.installer.arrive.change") }}</button>
        </form>
      </template>
    </div>
    <!-- While it works, and when it stops short: the bar and the steps. Once it is on the screen, what comes next. -->
    <template v-if="install.installer.view !== 'done' && !install.ok">
      <div class="follow-bar" role="progressbar" :aria-valuenow="install.progress.percent" aria-valuemin="0" aria-valuemax="100" :class="{ bad: install.progress.failed }">
        <i :style="{ width: `${install.progress.percent}%` }"></i>
      </div>
      <div class="follow-meta"><span>{{ install.progress.percent }} %</span><span v-if="install.elapsed">{{ t("editor.installer.elapsed", { time: install.elapsed }) }}</span></div>
      <ol class="follow-steps" id="follow-steps">
        <li v-for="item in install.progress.steps" :key="item.key" :class="item.state">
          <span class="follow-dot"><span v-if="item.state === 'running'" class="spin small"></span><template v-else-if="item.state === 'done'">✓</template><template v-else-if="item.state === 'failed'">✕</template></span>
          <span class="follow-name">{{ stepLabel(item.key, install.download) }}</span>
          <span v-if="item.state === 'running' && item.percent !== null" class="follow-pct">{{ item.percent }} %</span>
        </li>
      </ol>
    </template>
    <BrowserFlash v-if="install.installer.browser" :state="install.flash.state" />
    <div v-if="install.ok && install.download && install.installer.view !== 'done'" id="install-download" class="follow-card">
      <a class="btn primary big" id="download-firmware" :href="install.image.href" :download="install.image.name"><Icon name="tray-arrow-down" />{{ t("editor.firmware.download_file", { name: install.image.name }) }}</a>
      <ol class="steps" id="download-steps">
        <li><i18n-t keypath="editor.installer.download_steps.plug" scope="global"><template #bold><b>{{ t("editor.installer.download_steps.plug_bold") }}</b></template></i18n-t></li>
        <li><i18n-t keypath="editor.installer.download_steps.open" scope="global">
          <template #bold><b><i18n-t keypath="editor.installer.download_steps.open_bold" scope="global"><template #esphome_web><a :href="ESPHOME_WEB" target="_blank" rel="noopener">ESPHome Web</a></template></i18n-t></b></template>
        </i18n-t></li>
        <li><i18n-t :keypath="install.installer.calibrate ? 'editor.installer.download_steps.install_calibrate' : 'editor.installer.download_steps.install'" scope="global">
          <template #bold><b>{{ t("editor.installer.download_steps.install_bold") }}</b></template>
          <template #file>{{ install.image.name }}</template>
        </i18n-t></li>
      </ol>
      <small>{{ t("editor.installer.download_keep") }}</small>
    </div>
    <div v-if="install.ok" id="install-result" class="follow-card">
      <h2>{{ t("editor.installer.next_title") }}</h2>
      <ol class="steps" id="install-steps">
        <li><i18n-t keypath="editor.installer.pairing.tiles" scope="global"><template #bold><b>{{ t("editor.installer.pairing.tiles_bold") }}</b></template></i18n-t></li>
      </ol>
      <!-- Tessera adds the screen to Home Assistant and allows its actions by itself (app 0.4.73, ha_pairing.py), so
           the way by hand only shows when that did not work out. -->
      <details v-if="install.arrival === 'failed'" class="key-more" id="key-more" open>
        <summary>{{ t("editor.installer.pair_yourself") }}</summary>
        <ol class="steps" id="pair-steps">
          <li><i18n-t keypath="editor.installer.pairing.ha" scope="global"><template #bold><b>{{ t("editor.installer.pairing.ha_bold") }}</b></template><template #name>{{ install.installer.friendly }}</template></i18n-t> <button type="button" class="btn quiet mini" @click="ui.openIntegrations">{{ t("editor.common.open_integrations") }}</button></li>
          <li><i18n-t keypath="editor.installer.pairing.key" scope="global"><template #bold><b>{{ t("editor.installer.pairing.key_bold") }}</b></template></i18n-t></li>
          <li><i18n-t keypath="editor.installer.pairing.actions" scope="global"><template #bold><b>{{ t("editor.installer.pairing.actions_bold") }}</b></template></i18n-t></li>
        </ol>
        <div class="key-box">
          <span>{{ t("editor.installer.api_key") }}</span><code id="api-key" ref="keyBox">{{ install.installer.apiKey || "" }}</code>
          <button type="button" class="btn quiet mini" id="copy-key" @click="ui.copyText(install.installer.apiKey || '', keyBox)">{{ t("editor.common.copy") }}</button>
        </div>
      </details>
    </div>
    <details v-if="install.installer.view !== 'done'" id="install-log-wrap" class="follow-log" :open="install.logOpen" @toggle="install.logOpen = ($event.target as HTMLDetailsElement).open">
      <summary><Icon name="code-braces" />{{ t(install.logOpen ? "editor.installer.hide_log" : "editor.installer.show_log") }}<button v-if="install.logOpen" type="button" class="btn quiet mini" @click.prevent="ui.copyText(install.logs.join('\n'), null, 'log')">{{ t("editor.common.copy") }}</button></summary>
      <pre id="install-log" ref="logBox" class="log">{{ install.logs.join("\n") }}</pre>
    </details>
    <footer class="setup-foot">
      <button type="button" class="btn quiet" id="install-close" :disabled="install.flash.busy()" @click="install.reset">{{ install.ok ? t("editor.installer.another") : t("editor.installer.start_over") }}</button>
      <span class="status-line"></span>
      <button v-if="!install.running && !install.ok" type="button" class="btn primary big" id="install-retry" @click="install.retry">{{ t("editor.installer.retry") }}</button>
      <button v-else type="button" class="btn big" :class="install.ok ? 'primary' : 'quiet'" :disabled="install.flash.busy()" @click="install.close">{{ install.ok ? t("editor.installer.done") : t("editor.common.close") }}</button>
    </footer>
  </div>
</template>
