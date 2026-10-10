<script setup lang="ts">
// New screen's third step: how the firmware gets onto it. USB on the Home Assistant machine (each port found, or the one
// to plug into), this computer, a file, or nothing yet, and what the chosen way does.
import type { Installer } from "../../composables/useInstaller";
import { t } from "../../i18n";
import BrowserFlash from "../BrowserFlash.vue";
import Icon from "../ui/Icon.vue";

defineProps<{ install: Installer }>();
</script>

<template>
  <section class="setup-step ways">
    <h1>{{ t("editor.installer.install_title") }}</h1>
    <fieldset id="install-target" class="way-list">
      <legend class="sr-only">{{ t("editor.installer.install_via") }}</legend>
      <label v-for="way in install.ways" :key="way.value" class="way" :class="{ chosen: install.form.target === way.value }">
        <input type="radio" name="target" :value="way.value" :checked="install.form.target === way.value" @change="install.pickWay(way.value)" />
        <span class="way-icon"><Icon :name="way.icon" /><i v-if="way.live" class="way-live"></i></span>
        <span class="way-words"><b>{{ way.title }}</b><small>{{ way.detail }}</small></span>
      </label>
    </fieldset>
    <p class="way-hint" id="target-hint">{{ install.wayHint }}</p>
    <BrowserFlash v-if="install.form.target === 'browser'" :state="install.flash.state" />
    <p v-if="install.note" class="hint" id="install-note">{{ install.note }}</p>
  </section>
</template>
