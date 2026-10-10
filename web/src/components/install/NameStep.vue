<script setup lang="ts">
// New screen's second step: what it is called and how it hangs, beside the screen itself filling in its name. Which model
// of the family, the board's other choices, the Wi-Fi, and for whoever wants it the device name, the grid it starts
// with and what the board can and cannot do. A preview screen asks for its name and its glass instead. The step asks
// nothing it can't check on the spot (check).
import { ref } from "vue";
import { boardDetail, boardTitle } from "../../model/boards";
import { canStep } from "../../model/installer";
import { customPreview } from "../../model/preview";
import type { Installer } from "../../composables/useInstaller";
import { t } from "../../i18n";
import DeviceArt from "../DeviceArt.vue";
import Icon from "../ui/Icon.vue";

const props = defineProps<{ install: Installer }>();
const gridAxes = ["columns", "rows"] as const;
function stepGrid(axis: "columns" | "rows", by: number) { if (canStep(props.install.form.grid, props.install.range, axis, by)) props.install.form.grid[axis] += by; }
const root = ref<HTMLElement | null>(null);
/** Whether its fields are filled in as they must be; the first that is not says why. */
function check() {
  const wrong = [...(root.value?.querySelectorAll<HTMLInputElement>("input, select") || [])].find((field) => !field.checkValidity());
  wrong?.reportValidity();
  return !wrong;
}
defineExpose({ check });
</script>

<template>
  <section ref="root" class="setup-step make">
    <div class="make-art" aria-hidden="true">
      <div class="make-frame" :style="{ '--art-ratio': (install.art.width + 14 * install.art.height / 100) / (install.art.height + 14 * install.art.height / 100) }">
        <DeviceArt v-bind="install.art" :name="install.form.friendly_name.trim()" />
      </div>
      <p v-if="install.mode === 'physical' && install.chosen" class="make-caption"><b>{{ boardTitle(install.chosen) }}</b> · {{ install.chosen.model }}</p>
    </div>
    <div class="make-fields">
      <h1>{{ t(install.mode === "virtual" ? "editor.preview.virtual" : "editor.installer.setup_title") }}</h1>
      <p v-if="install.mode === 'virtual'" class="setup-lead">{{ t("editor.preview.intro") }}</p>
      <template v-if="install.mode === 'physical'">
      <p v-if="install.chosen && install.chosen.status !== 'stable'" class="make-note" id="board-status"><Icon name="information-outline" />{{ t(`editor.installer.status_hint.${install.chosen.status}`) }}</p>
      <div class="field">
        <label class="f-label" for="friendly_name">{{ t("editor.installer.name") }}</label>
        <input id="friendly_name" name="friendly_name" v-model="install.form.friendly_name" required maxlength="60" :placeholder="t('editor.installer.name_placeholder')" autocomplete="off" />
        <small>{{ t("editor.installer.name_hint") }}</small>
        <!-- One line, not two: a name that is taken usually makes a device name that is taken as well, and the
             name is what someone changes. The device name speaks for itself only when it is the one that clashes. -->
        <small v-if="install.clash.name" id="name-taken" class="warn">{{ t("editor.installer.name_taken") }}</small>
        <small v-else-if="install.clash.node" id="node-taken" class="warn">{{ t("editor.installer.node_taken") }}</small>
      </div>
      <!-- Which model of this screen: what is printed on the board tells them apart. -->
      <fieldset v-if="install.siblings.length > 1" id="board-model" class="choice-fields">
        <legend class="f-label">{{ t("editor.installer.model") }}</legend>
        <div class="model-options">
          <label v-for="board in install.siblings" :key="board.key" class="choice model">
            <input type="radio" name="model" :value="board.key" v-model="install.form.board" />
            <span><b>{{ board.model }}</b><small>{{ boardDetail(board)[1] }}</small>
              <em v-if="board.status !== 'stable'" class="board-badge inline" :class="board.status">{{ t(`editor.installer.status.${board.status}`) }}</em></span>
          </label>
        </div>
        <small>{{ t("editor.installer.model_hint") }}</small>
      </fieldset>
      <!-- The board's other choices, one per part that differs between boards sold under its name. -->
      <fieldset v-for="choice in install.choices" :key="choice.key" class="choice-fields" :id="`choice-${choice.key}`">
        <legend class="f-label">{{ t(`editor.installer.choice.${choice.key}`) }}</legend>
        <div class="choice-options">
          <label v-for="(option, index) in choice.options" :key="option" class="choice">
            <input type="radio" :name="`choice-${choice.key}`" :value="option" v-model="install.form.choices[choice.key]" />
            <span><b>{{ option }}</b><small v-if="index === 0">{{ t("editor.installer.choice_usual") }}</small></span>
          </label>
        </div>
        <small>{{ t(`editor.installer.choice_hint.${choice.key}`) }}</small>
      </fieldset>
      <!-- Wi-Fi, always in sight: ready from ESPHome's secrets, or asked here once for every screen after it. -->
      <fieldset id="wifi-section" class="wifi">
        <legend class="f-label">{{ t("editor.installer.wifi.title") }}</legend>
        <div v-if="install.askWifi" id="wifi-fields" class="wifi-fields">
          <p class="hint" id="wifi-status">{{ t(install.wifi?.state === "new" ? "editor.installer.wifi.new" : "editor.installer.wifi.missing") }}</p>
          <div v-if="install.wifiMissing.includes('wifi_ssid')" class="field" id="wifi-ssid-label"><label class="f-label" for="wifi_ssid">{{ t("editor.installer.wifi.ssid") }}</label><input id="wifi_ssid" name="wifi_ssid" v-model="install.form.wifi_ssid" required autocomplete="off" /></div>
          <div v-if="install.wifiMissing.includes('wifi_password')" class="field" id="wifi-password-label"><label class="f-label" for="wifi_password">{{ t("editor.installer.wifi.password") }}</label><input id="wifi_password" name="wifi_password" type="password" v-model="install.form.wifi_password" autocomplete="new-password" /></div>
        </div>
        <template v-else>
          <p class="wifi-state" :class="install.wifi?.state"><Icon :name="install.wifi?.state === 'invalid' ? 'alert-circle-outline' : 'check-circle'" />
            <span>{{ install.wifiNote || t("editor.installer.wifi.ready") }}</span>
            <button v-if="install.wifi?.state === 'ready'" type="button" class="btn link mini" id="wifi-other" @click="install.wifiOther = !install.wifiOther">{{ t(install.wifiOther ? "editor.common.cancel" : "editor.installer.wifi.other") }}</button></p>
          <div v-if="install.wifiOther" id="wifi-fields" class="wifi-fields">
            <p class="hint">{{ t("editor.installer.wifi.other_note") }}</p>
            <div class="field"><label class="f-label" for="wifi_ssid">{{ t("editor.installer.wifi.ssid") }}</label><input id="wifi_ssid" name="wifi_ssid" v-model="install.form.wifi_ssid" required autocomplete="off" /></div>
            <div class="field"><label class="f-label" for="wifi_password">{{ t("editor.installer.wifi.password") }}</label><input id="wifi_password" name="wifi_password" type="password" v-model="install.form.wifi_password" autocomplete="new-password" /></div>
          </div>
        </template>
      </fieldset>
      <!-- For whoever wants it, in sight under its own heading: the device name and what the board can and cannot do. -->
      <section class="advanced">
        <h2 class="f-label">{{ t("editor.installer.advanced") }}</h2>
        <div class="field" id="node-label">
          <label class="f-label" for="node-name">{{ t("editor.installer.device_name") }}</label>
          <input id="node-name" name="name" v-model="install.form.name" pattern="[a-z][a-z0-9\-]{0,29}" maxlength="30" autocomplete="off" @input="install.installer.nodeEdited = true" />
          <small>{{ t("editor.installer.device_name_hint") }} <code id="node-preview">{{ install.form.name || "…" }}</code></small>
        </div>
        <!-- The grid it starts with, and which way it hangs (app 0.4.85): the board's best unless chosen here; the editor
             changes either later beside the pages, without a new build. Only glass that is not square has two ways. -->
        <fieldset id="grid-fields" class="choice-fields">
          <legend class="f-label">{{ t("editor.installer.grid") }}</legend>
          <div v-if="install.orientations.length" class="orients" id="orientation-fields">
            <label v-for="way in install.orientations" :key="way.key" class="orient">
              <input type="radio" name="orientation" :value="way.key" v-model="install.form.orientation" />
              <span class="orient-glass" aria-hidden="true"
                    :style="{ '--glass-aspect': `${way.width} / ${way.height}`, '--glass-columns': way.columns, '--glass-rows': way.rows }">
                <span class="orient-bar"></span>
                <span class="orient-cells"><i v-for="cell in way.columns * way.rows" :key="cell"></i></span>
              </span>
              <span class="orient-words"><b>{{ t(`editor.installer.orientation_${way.key}`) }}</b></span>
            </label>
          </div>
          <div class="grid-steps">
            <div v-for="axis in gridAxes" :key="axis" class="grid-step">
              <span>{{ t(`editor.grid.${axis}`) }}</span>
              <button type="button" class="icon-btn" :id="`install-${axis}-less`" :disabled="!canStep(install.form.grid, install.range, axis, -1)"
                :aria-label="t(`editor.grid.${axis}_less`)" @click="stepGrid(axis, -1)"><Icon name="minus" /></button>
              <b>{{ install.form.grid[axis] }}</b>
              <button type="button" class="icon-btn" :id="`install-${axis}-more`" :disabled="!canStep(install.form.grid, install.range, axis, 1)"
                :aria-label="t(`editor.grid.${axis}_more`)" @click="stepGrid(axis, 1)"><Icon name="plus" /></button>
            </div>
            <button v-if="install.gridChosen" type="button" class="btn link mini" id="install-grid-best" @click="install.bestGrid">{{ t("editor.installer.grid_best") }}</button>
          </div>
          <small>{{ t("editor.installer.grid_hint") }}</small>
        </fieldset>
        <ul v-if="install.abilities.length" class="abilities" id="board-abilities">
          <li v-for="ability in install.abilities" :key="ability.key" :class="{ off: !ability.on }">{{ ability.text }}</li>
        </ul>
      </section>
      </template>
      <template v-else>
        <div class="field">
          <label class="f-label" for="virtual-name">{{ t("editor.preview.name") }}</label>
          <input id="virtual-name" v-model="install.form.friendly_name" required maxlength="60" :placeholder="t('editor.preview.name_placeholder')" autocomplete="off" />
        </div>
        <div class="field">
          <label class="f-label" for="virtual-profile">{{ t("editor.preview.profile") }}</label>
          <select id="virtual-profile" v-model="install.previewForm.profile">
            <option v-for="profile in install.previews" :key="profile.key" :value="profile.key">
              {{ profile.name }} · {{ profile.shape.width }} × {{ profile.shape.height }} · {{ t(`editor.installer.orientation_${profile.orientation}`) }}
            </option>
          </select>
          <small v-if="install.previewForm.profile === customPreview.key">{{ t("editor.preview.design_only") }}</small>
        </div>
        <details class="advanced">
          <summary>{{ t("editor.preview.override") }}</summary>
          <div v-for="axis in (['width', 'height', 'columns', 'rows'] as const)" :key="axis" class="field">
            <label class="f-label" :for="`virtual-${axis}`">{{ t(`editor.preview.${axis}`) }}</label>
            <input :id="`virtual-${axis}`" type="number" v-model.number="install.previewForm[axis]" required step="1"
              :min="axis === 'width' || axis === 'height' ? 160 : 1" :max="axis === 'width' || axis === 'height' ? 2560 : 8" />
          </div>
        </details>
      </template>
    </div>
  </section>
</template>
