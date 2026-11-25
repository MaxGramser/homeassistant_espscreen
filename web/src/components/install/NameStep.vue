<script setup lang="ts">
// New screen's question about the name (app 0.4.103): the screen drawn large with the name typed so far, one field, and
// the rooms of the home as names a tap fills in. More options holds what few people change: the device name, the grid
// it starts with, and what the board can and cannot do. A preview screen asks its name and its glass here instead.
import { nextTick, onMounted, ref, watch } from "vue";
import { boardTitle } from "../../model/boards";
import { canStep } from "../../model/installer";
import { customPreview } from "../../model/preview";
import { injectInstaller } from "../../composables/useInstaller";
import { t } from "../../i18n";
import DeviceArt from "../DeviceArt.vue";
import Icon from "../ui/Icon.vue";

const install = injectInstaller();
const gridAxes = ["columns", "rows"] as const;
function stepGrid(axis: "columns" | "rows", by: number) { if (canStep(install.form.grid, install.range, axis, by)) install.form.grid[axis] += by; }
// The field is ready to type in as the step opens; More options comes into sight when it opens.
const field = ref<HTMLInputElement | null>(null), moreBox = ref<HTMLElement | null>(null);
onMounted(() => field.value?.focus({ preventScroll: true }));
watch(() => install.more, async (open) => { if (open) { await nextTick(); moreBox.value?.scrollIntoView?.({ behavior: "smooth", block: "nearest" }); } });
</script>

<template>
  <section class="ob-step name" data-step="name">
    <div class="ob-hero" aria-hidden="true">
      <div class="ob-frame" :style="{ '--art-ratio': install.art.width / install.art.height }">
        <DeviceArt v-bind="install.art" :name="install.form.friendly_name.trim()" />
      </div>
    </div>

    <template v-if="install.mode === 'physical'">
      <h1>{{ t("editor.installer.flow.name_title") }}</h1>
      <p class="ob-lead">{{ t("editor.installer.flow.name_lead") }}</p>
      <label class="ob-field">
        <span class="sr-only">{{ t("editor.installer.name") }}</span>
        <input id="friendly_name" ref="field" name="friendly_name" v-model="install.form.friendly_name" required maxlength="60"
          :placeholder="t('editor.installer.flow.name_placeholder')" autocomplete="off" @keydown.enter.prevent="install.next" />
      </label>
      <p v-if="install.clash.quote" id="name-quote" class="ob-warn">{{ t("editor.installer.name_quote") }}</p>
      <p v-else-if="install.clash.name" id="name-taken" class="ob-warn">{{ t("editor.installer.name_taken") }}</p>
      <p v-else-if="install.clash.node" id="node-taken" class="ob-warn">{{ t("editor.installer.node_taken") }}</p>
      <div v-if="install.rooms.length" class="ob-chips" id="room-names" :aria-label="t('editor.installer.flow.rooms')">
        <button v-for="room in install.rooms" :key="room" type="button" class="ob-chip" :aria-pressed="install.form.friendly_name.trim() === room" @click="install.form.friendly_name = room">{{ room }}</button>
      </div>
      <p v-if="install.chosen && install.chosen.status !== 'stable'" class="ob-note" id="board-status"><Icon name="information-outline" />{{ t(`editor.installer.status_hint.${install.chosen.status}`) }}</p>

      <!-- More options: what few people change, all of it changeable later without a new build but the device name. -->
      <div v-if="install.more" ref="moreBox" class="ob-more-box" id="more-box">
        <p v-if="install.chosen" class="ob-more-head"><b>{{ boardTitle(install.chosen) }}</b> · {{ install.chosen.model }}</p>
        <div class="field" id="node-label">
          <label class="f-label" for="node-name">{{ t("editor.installer.device_name") }}</label>
          <input id="node-name" name="name" v-model="install.form.name" pattern="[a-z][a-z0-9\-]{0,29}" maxlength="30" autocomplete="off" @input="install.installer.nodeEdited = true" />
          <small>{{ t("editor.installer.device_name_hint") }}</small>
        </div>
        <fieldset id="grid-fields" class="grid-fields">
          <legend class="f-label">{{ t("editor.installer.grid") }}</legend>
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
      </div>
    </template>

    <template v-else>
      <h1>{{ t("editor.preview.virtual") }}</h1>
      <p class="ob-lead">{{ t("editor.preview.intro") }}</p>
      <div class="ob-more-box">
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
      </div>
    </template>
  </section>
</template>
