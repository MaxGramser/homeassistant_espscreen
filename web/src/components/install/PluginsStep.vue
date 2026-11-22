<script setup lang="ts">
// New screen's Plugins step (docs/PLUGINS.md, "Plugins a board starts with"): the plugins the add-on suggests for the
// chosen board, ticked, each with the reason it is suggested. What stays ticked is built into the screen's first
// firmware; what is unticked is not suggested for that screen again. A board nothing is suggested for has no such step.
import { injectInstaller } from "../../composables/useInstaller";
import { t } from "../../i18n";
import { text } from "../../model/plugins";
import Icon from "../ui/Icon.vue";

const install = injectInstaller();
</script>

<template>
  <section class="setup-step picks">
    <h1>{{ t("editor.installer.plugins_title") }}</h1>
    <p class="picks-intro">{{ t("editor.installer.plugins_intro") }}</p>
    <ul class="pick-list" id="install-plugins">
      <li v-for="plugin in install.suggested" :key="plugin.id">
        <label class="way pick" :class="{ chosen: install.picks[plugin.id] }" :data-plugin="plugin.id">
          <input type="checkbox" :checked="install.picks[plugin.id]" @change="install.picks[plugin.id] = !install.picks[plugin.id]" />
          <span class="pick-check" :class="{ on: install.picks[plugin.id] }"><Icon v-if="install.picks[plugin.id]" name="check" /></span>
          <span class="way-words">
            <b>{{ text(plugin.name) }}</b>
            <small class="pick-why">{{ t(`editor.plugins.suggest.why.${plugin.why}`) }}</small>
            <small>{{ text(plugin.summary) }}</small>
          </span>
        </label>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.picks-intro { margin: -8px 0 0; font-size: 13.5px; color: var(--ink-2); max-width: 560px; }
.pick-list { display: grid; gap: 12px; margin: 0; padding: 0; list-style: none; max-width: 620px; }
.pick { align-items: flex-start; }
.pick-check { flex: none; width: 22px; height: 22px; margin-top: 1px; border-radius: 7px; border: 1.5px solid var(--line-strong); display: grid; place-items: center; font-size: 15px; color: var(--surface); }
.pick-check.on { background: var(--accent); border-color: var(--accent); }
.pick input:focus-visible + .pick-check { outline: 2px solid var(--accent); outline-offset: 2px; }
.pick-why { color: var(--ink-2) !important; font-weight: 550; }
</style>
