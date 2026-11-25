<script setup lang="ts">
// New screen's question about the cable (app 0.4.103): before any port or way, where the screen's USB cable is. In this
// computer, the one this page is open on, or in the machine Home Assistant runs on. People took "USB" for this
// computer's port when it was the Home Assistant machine's, so the two are drawn and named apart, and the port comes
// only after (ConnectStep).
import { computed } from "vue";
import { injectInstaller } from "../../composables/useInstaller";
import { t } from "../../i18n";
import type { Cable } from "../../model/installer";
import CableArt from "./CableArt.vue";
import Icon from "../ui/Icon.vue";

const install = injectInstaller();
// This computer first where this browser can write a board, else the Home Assistant machine first.
const order = computed<Cable[]>(() => (install.support === "ok" ? ["here", "ha"] : ["ha", "here"]));
</script>

<template>
  <section class="ob-step cable" data-step="cable">
    <h1>{{ t("editor.installer.flow.cable_title") }}</h1>
    <p class="ob-lead">{{ t("editor.installer.flow.cable_lead") }}</p>
    <fieldset id="install-cable" class="ob-cards" style="--cards: 2">
      <legend class="sr-only">{{ t("editor.installer.flow.cable_title") }}</legend>
      <label v-for="where in order" :key="where" class="ob-card cable-card" :class="{ chosen: install.cable === where }" :data-cable="where" @dblclick="install.cable = where; install.next()">
        <input type="radio" name="cable" :value="where" v-model="install.cable" />
        <span class="ob-art" aria-hidden="true"><CableArt :kind="where" :width="install.art.width" :height="install.art.height" :chosen="install.cable === where" /></span>
        <span class="ob-card-words"><b>{{ t(`editor.installer.flow.cable_${where}`) }}</b><small>{{ t(`editor.installer.flow.cable_${where}_detail`) }}</small></span>
        <span class="ob-tick" aria-hidden="true"><Icon name="check" /></span>
      </label>
    </fieldset>
    <p v-if="install.cable === 'here' && install.support !== 'ok'" class="ob-note" id="cable-browser"><Icon name="information-outline" />{{ t(`editor.webflash.unavailable.${install.support}`) }}</p>
  </section>
</template>
