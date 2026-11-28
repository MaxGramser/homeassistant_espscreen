<script setup lang="ts">
// New screen's question about the way it hangs (app 0.4.103), only for glass that is not square: the screen drawn lying
// down and standing up, each with the page of tiles it gets that way (the board's best grid for it). The editor changes
// both later beside the pages, without a new build.
import { injectInstaller } from "../../composables/useInstaller";
import { t } from "../../i18n";
import DeviceArt from "../DeviceArt.vue";
import Icon from "../ui/Icon.vue";

const install = injectInstaller();
</script>

<template>
  <section class="ob-step hang" data-step="hang">
    <h1>{{ t("editor.installer.flow.hang_title") }}</h1>
    <p class="ob-lead">{{ t("editor.installer.flow.hang_lead") }}</p>
    <fieldset id="orientation-fields" class="ob-cards" style="--cards: 2">
      <legend class="sr-only">{{ t("editor.installer.flow.hang_title") }}</legend>
      <label v-for="way in install.orientations" :key="way.key" class="ob-card" :class="{ chosen: install.form.orientation === way.key }">
        <input type="radio" name="orientation" :value="way.key" v-model="install.form.orientation" />
        <span class="ob-art tall" aria-hidden="true">
          <span class="ob-frame" :style="{ '--art-ratio': way.width / way.height }">
            <DeviceArt :width="way.width" :height="way.height" :columns="way.columns" :rows="way.rows" :name="install.form.friendly_name.trim()" />
          </span>
        </span>
        <span class="ob-card-words"><b>{{ t(`editor.installer.orientation_${way.key}`) }}</b>
          <small>{{ t("editor.installer.flow.tiles_a_page", way.columns * way.rows) }}</small></span>
        <span class="ob-tick" aria-hidden="true"><Icon name="check" /></span>
      </label>
    </fieldset>
  </section>
</template>
