<script setup lang="ts">
// Why "In this computer" would only make a file here (app 0.4.105): this page cannot reach a USB port, because it is not
// in Chrome or Edge on a computer, or because it was opened over plain http. People took the file for how installing
// from a computer always goes, so the reason stands in a red card, with what makes it two clicks instead: Chrome or
// Edge, and a secure address. For a Home Assistant on a local http address Chrome has a setting that treats that one
// address as secure (chrome://flags, "Insecure origins treated as secure"); a page cannot link to chrome://, so the
// card gives the setting's address and this Home Assistant's own to copy, and the steps.
import { ref } from "vue";
import { t } from "../../i18n";
import type { FlashSupport } from "../../flasher/logic";
import { useUiStore } from "../../stores/ui";
import Icon from "../ui/Icon.vue";

defineProps<{ support: Exclude<FlashSupport, "ok"> }>();
const ui = useUiStore();
const FLAG = "chrome://flags/#unsafely-treat-insecure-origin-as-secure";
const origin = window.location.origin;
const flagBox = ref<HTMLElement | null>(null), originBox = ref<HTMLElement | null>(null);
</script>

<template>
  <div class="ob-alert" id="no-usb" :data-support="support" role="note">
    <h2><Icon name="alert-circle-outline" />{{ t(`editor.installer.no_usb.${support}_title`) }}</h2>
    <p>{{ t(`editor.installer.no_usb.${support}`) }}</p>
    <template v-if="support === 'insecure'">
      <p><b>{{ t("editor.installer.no_usb.fix") }}</b></p>
      <ul class="ob-alert-ways">
        <li>{{ t("editor.installer.no_usb.https") }}</li>
        <li>{{ t("editor.installer.no_usb.flag") }}
          <ol class="ob-alert-steps" id="no-usb-flag">
            <li>{{ t("editor.installer.no_usb.flag_open") }}
              <span class="ob-alert-copy"><code ref="flagBox" id="no-usb-flag-link">{{ FLAG }}</code>
                <button type="button" class="btn quiet mini" id="no-usb-copy-flag" @click="ui.copyText(FLAG, flagBox, 'address')">{{ t("editor.common.copy") }}</button></span></li>
            <li>{{ t("editor.installer.no_usb.flag_add") }}
              <span class="ob-alert-copy"><code ref="originBox" id="no-usb-origin">{{ origin }}</code>
                <button type="button" class="btn quiet mini" id="no-usb-copy-origin" @click="ui.copyText(origin, originBox, 'address')">{{ t("editor.common.copy") }}</button></span></li>
            <li>{{ t("editor.installer.no_usb.flag_relaunch") }}</li>
          </ol>
        </li>
      </ul>
    </template>
    <p class="ob-alert-else">{{ t("editor.installer.no_usb.else") }}</p>
  </div>
</template>
