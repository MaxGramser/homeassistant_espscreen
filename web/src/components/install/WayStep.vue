<script setup lang="ts">
// New screen's third step: how the firmware gets onto it. USB on the Home Assistant machine (each port found, or the one
// to plug into), this computer, a file, or nothing yet, and what the chosen way does.
import { injectInstaller } from "../../composables/useInstaller";
import { t } from "../../i18n";
import BrowserFlash from "../BrowserFlash.vue";
import Icon from "../ui/Icon.vue";

const install = injectInstaller();
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
    <!-- The board on the cable is a screen Home Assistant already has (same MAC, app 0.4.96): install that one again,
         or replace it with the screen being made. Nothing is built until one is chosen. -->
    <div v-if="install.installer.known" class="known-board" id="known-board" role="group" :aria-label="t('editor.installer.known.title', { name: install.installer.known.name })">
      <h2><Icon name="alert-circle-outline" />{{ t("editor.installer.known.title", { name: install.installer.known.name }) }}</h2>
      <p>{{ t("editor.installer.known.text", { name: install.installer.known.name, new: install.form.friendly_name.trim() }) }}</p>
      <div class="known-actions">
        <button type="button" class="btn" id="known-keep" @click="install.keepKnown">{{ t("editor.installer.known.reinstall", { name: install.installer.known.name }) }}</button>
        <button type="button" class="btn primary" id="known-replace" :disabled="install.submitting" @click="install.replaceKnown">{{ t("editor.installer.known.replace", { name: install.installer.known.name, new: install.form.friendly_name.trim() }) }}</button>
      </div>
    </div>
    <p v-if="install.note" class="hint" id="install-note">{{ install.note }}</p>
  </section>
</template>

<style scoped>
/* The same box as the wizard's "not on your Wi-Fi yet" (.arrive.missing in styles/app.css). */
.known-board { display: grid; gap: 10px; margin-top: 14px; padding: 18px 20px; border-radius: 14px; background: var(--warn-soft); }
.known-board h2 { margin: 0; font-size: 15px; display: flex; align-items: center; gap: 8px; }
.known-board p { margin: 0; font-size: 13px; color: var(--ink-2); }
.known-actions { display: flex; gap: 10px; flex-wrap: wrap; }
</style>
