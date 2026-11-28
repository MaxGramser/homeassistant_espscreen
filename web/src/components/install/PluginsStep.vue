<script setup lang="ts">
// New screen's Plugins step (docs/PLUGINS.md, "Plugins a board starts with"): the plugins the add-on suggests for the
// chosen board's hardware, each on, with what it does. What stays on is built into the screen's first firmware; what is
// turned off is not suggested for that screen again. A board nothing is suggested for has no such step.
import { injectInstaller } from "../../composables/useInstaller";
import { t } from "../../i18n";
import { text } from "../../model/plugins";
import Icon from "../ui/Icon.vue";
import UiSwitch from "../ui/UiSwitch.vue";

const install = injectInstaller();
</script>

<template>
  <section class="ob-step picks" data-step="plugins">
    <span class="ob-badge" aria-hidden="true"><Icon name="puzzle-outline" /></span>
    <h1>{{ t("editor.installer.flow.plugins_title") }}</h1>
    <p class="ob-lead">{{ t("editor.installer.flow.plugins_lead") }}</p>
    <ul class="ob-group" id="install-plugins">
      <li v-for="plugin in install.suggested" :key="plugin.id" class="pick" :class="{ chosen: install.picks[plugin.id] }" :data-plugin="plugin.id">
        <label class="ob-group-words" :for="`plugin-${plugin.id}`">
          <b>{{ text(plugin.name) }}</b>
          <small class="pick-why">{{ t(`editor.plugins.suggest.why.${plugin.why}`) }} {{ text(plugin.summary) }}</small>
        </label>
        <UiSwitch :id="`plugin-${plugin.id}`" :model-value="!!install.picks[plugin.id]" @update:model-value="(on) => (install.picks[plugin.id] = on)" />
      </li>
    </ul>
    <p class="ob-hint">{{ t("editor.installer.flow.plugins_later") }}</p>
  </section>
</template>
