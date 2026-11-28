<script setup lang="ts">
// New screen's question about the Wi-Fi (app 0.4.103), only when ESPHome has none yet: the network's name and password,
// written once into ESPHome's secrets, where every screen after this one finds them too.
import { injectInstaller } from "../../composables/useInstaller";
import { t } from "../../i18n";
import Icon from "../ui/Icon.vue";

const install = injectInstaller();
</script>

<template>
  <section class="ob-step wifi" data-step="wifi" id="wifi-section">
    <span class="ob-badge" aria-hidden="true"><Icon name="wifi-strength-4" /></span>
    <h1>{{ t("editor.installer.flow.wifi_title") }}</h1>
    <p class="ob-lead" id="wifi-status">{{ t("editor.installer.flow.wifi_lead") }}</p>
    <div class="ob-more-box" id="wifi-fields">
      <div v-if="install.wifiMissing.includes('wifi_ssid')" class="field" id="wifi-ssid-label"><label class="f-label" for="wifi_ssid">{{ t("editor.installer.wifi.ssid") }}</label>
        <input id="wifi_ssid" name="wifi_ssid" v-model="install.form.wifi_ssid" required autocomplete="off" /></div>
      <div v-if="install.wifiMissing.includes('wifi_password')" class="field" id="wifi-password-label"><label class="f-label" for="wifi_password">{{ t("editor.installer.wifi.password") }}</label>
        <input id="wifi_password" name="wifi_password" type="password" v-model="install.form.wifi_password" autocomplete="new-password" /></div>
    </div>
    <p class="ob-hint">{{ t("editor.installer.flow.wifi_once") }}</p>
  </section>
</template>
