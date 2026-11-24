<script setup lang="ts">
// New screen's last step (app 0.4.103), the way for where the cable is (CableStep). In this computer: what happens after
// Install, step by step, since the browser's own port picker is what follows; a browser that cannot write a board makes
// a file instead. In the Home Assistant machine: the page watches its ports and says when the screen is there, picks it
// when it is the only one, asks which when there are more, and keeps the radios and meters that are certainly not a
// screen (a Zigbee stick) out of the way. The Wi-Fi it joins is a line under it, with another network a click away.
import { computed } from "vue";
import { portName } from "../../model/installer";
import { injectInstaller } from "../../composables/useInstaller";
import { t } from "../../i18n";
import BrowserFlash from "../BrowserFlash.vue";
import CableArt from "./CableArt.vue";
import Icon from "../ui/Icon.vue";

const install = injectInstaller();
const here = computed(() => install.cable === "here");
const screens = computed(() => install.haPorts.screens);
const others = computed(() => install.haPorts.others);
const title = computed(() => {
  if (here.value) return t(install.support === "ok" ? "editor.installer.flow.here_title" : "editor.installer.flow.file_title");
  return t(screens.value.length > 1 ? "editor.installer.flow.ha_which" : "editor.installer.flow.ha_title");
});
</script>

<template>
  <section class="ob-step connect" :data-step="here ? 'connect-here' : 'connect-ha'">
    <div class="ob-hero small" aria-hidden="true"><CableArt :kind="here ? 'here' : 'ha'" :width="install.art.width" :height="install.art.height" chosen /></div>
    <h1>{{ title }}</h1>

    <template v-if="here">
      <template v-if="install.support === 'ok'">
        <ol class="ob-howto" id="here-steps">
          <li>{{ t("editor.installer.flow.here_plug") }}</li>
          <li>{{ t("editor.installer.flow.here_click") }}</li>
          <li>{{ t("editor.installer.flow.here_pick") }}</li>
        </ol>
        <BrowserFlash :state="install.flash.state" />
      </template>
      <p v-else class="ob-lead" id="target-hint">{{ t("editor.installer.flow.file_lead") }}</p>
      <!-- The board on the cable is a screen Home Assistant already has (same MAC, app 0.4.96): install that one again,
           or replace it with the screen being made. Nothing is built until one is chosen. -->
      <div v-if="install.installer.known" class="ob-ask" id="known-board" role="group" :aria-label="t('editor.installer.known.title', { name: install.installer.known.name })">
        <h2><Icon name="alert-circle-outline" />{{ t("editor.installer.known.title", { name: install.installer.known.name }) }}</h2>
        <p>{{ t("editor.installer.known.text", { name: install.installer.known.name, new: install.form.friendly_name.trim() }) }}</p>
        <div class="ob-ask-keys">
          <button type="button" class="btn" id="known-keep" :disabled="install.submitting" @click="install.againKnown">{{ t("editor.installer.known.reinstall", { name: install.installer.known.name }) }}</button>
          <button type="button" class="btn primary" id="known-replace" :disabled="install.submitting" @click="install.replaceKnown">{{ t("editor.installer.known.replace", { name: install.installer.known.name, new: install.form.friendly_name.trim() }) }}</button>
        </div>
      </div>
    </template>

    <template v-else>
      <p class="ob-lead">{{ t(screens.length > 1 ? "editor.installer.flow.ha_which_lead" : "editor.installer.flow.ha_lead") }}</p>
      <div v-if="!screens.length" class="ob-status waiting" id="ha-waiting" role="status"><span class="spin"></span>
        <span><b>{{ t("editor.installer.flow.ha_waiting") }}</b><small>{{ t("editor.installer.flow.ha_waiting_detail") }}</small></span></div>
      <div v-else-if="screens.length === 1" class="ob-status found" id="ha-found" role="status"><span class="ob-status-mark"><Icon name="check" /></span>
        <span><b>{{ t("editor.installer.flow.ha_found") }}</b><small>{{ portName(screens[0]) }}</small></span></div>
      <fieldset v-else class="ob-rows" id="ha-ports">
        <legend class="sr-only">{{ t("editor.installer.flow.ha_which") }}</legend>
        <label v-for="port in screens" :key="port" class="ob-row" :class="{ chosen: install.form.target === port }">
          <input type="radio" name="target" :value="port" :checked="install.form.target === port" @change="install.pickWay(port)" />
          <span class="ob-row-words"><b>{{ portName(port) }}</b></span>
          <span class="ob-tick" aria-hidden="true"><Icon name="check" /></span>
        </label>
      </fieldset>
      <details v-if="others.length" class="ob-others" id="ha-others">
        <summary>{{ t("editor.installer.flow.ha_others", others.length) }}<Icon name="chevron-down" /></summary>
        <div class="ob-rows">
          <label v-for="port in others" :key="port" class="ob-row" :class="{ chosen: install.form.target === port }">
            <input type="radio" name="target" :value="port" :checked="install.form.target === port" @change="install.pickWay(port)" />
            <span class="ob-row-words"><b>{{ portName(port) }}</b><small>{{ t("editor.installer.flow.ha_not_screen") }}</small></span>
            <span class="ob-tick" aria-hidden="true"><Icon name="check" /></span>
          </label>
        </div>
      </details>
    </template>

    <!-- The Wi-Fi it joins: from ESPHome's secrets, another network a click away (written before the build). -->
    <div class="ob-wifi" id="wifi-section">
      <p v-if="install.wifi?.state === 'invalid'" class="ob-note warn" id="wifi-invalid"><Icon name="alert-circle-outline" />{{ t("editor.installer.wifi.invalid") }}</p>
      <p v-else-if="!install.askWifi" class="ob-wifi-line"><Icon name="wifi-strength-4" />{{ t("editor.installer.flow.wifi_ready") }}
        <button type="button" class="ob-link" id="wifi-other" @click="install.wifiOther = !install.wifiOther">{{ t(install.wifiOther ? "editor.common.cancel" : "editor.installer.wifi.other") }}</button></p>
      <div v-if="install.wifiOther" id="wifi-fields" class="ob-more-box">
        <p class="hint">{{ t("editor.installer.wifi.other_note") }}</p>
        <div class="field"><label class="f-label" for="wifi_ssid">{{ t("editor.installer.wifi.ssid") }}</label><input id="wifi_ssid" name="wifi_ssid" v-model="install.form.wifi_ssid" required autocomplete="off" /></div>
        <div class="field"><label class="f-label" for="wifi_password">{{ t("editor.installer.wifi.password") }}</label><input id="wifi_password" name="wifi_password" type="password" v-model="install.form.wifi_password" autocomplete="new-password" /></div>
      </div>
    </div>
    <p v-if="install.note" class="ob-hint" id="install-note">{{ install.note }}</p>
  </section>
</template>
