<script setup lang="ts">
// New screen (app 0.4.103): a setup assistant that asks one thing at a time, the way a phone is set up. Which screen
// (BoardStep), which version of it (ModelStep, only when there are more), its name (NameStep), which way it hangs
// (HangStep, only glass that is not square), the plugins for its hardware (PluginsStep, only when suggested), the Wi-Fi
// (WifiStep, only when ESPHome has none), where its USB cable is (CableStep) and that way (ConnectStep). Then one page
// follows the screen until it works in Home Assistant (Progress). The form, what it sends and when, is
// composables/useInstaller.ts; which steps there are is model/installer.ts installStages.
import "../styles/new-screen.css";
import { computed, provide, ref, watch } from "vue";
import { t } from "../i18n";
import { INSTALLER, useInstaller } from "../composables/useInstaller";
import BoardStep from "./install/BoardStep.vue";
import CableStep from "./install/CableStep.vue";
import ConnectStep from "./install/ConnectStep.vue";
import HangStep from "./install/HangStep.vue";
import ModelStep from "./install/ModelStep.vue";
import NameStep from "./install/NameStep.vue";
import PluginsStep from "./install/PluginsStep.vue";
import Progress from "./install/Progress.vue";
import WifiStep from "./install/WifiStep.vue";
import Icon from "./ui/Icon.vue";

const install = useInstaller();
provide(INSTALLER, install);
const setup = computed(() => install.installer.view === "setup");
const physical = computed(() => install.mode === "physical");
const showBack = computed(() => setup.value && (!physical.value || install.step > 1 || install.browse));
function back() { if (physical.value) install.back(); else install.realScreen(); }
// The key at the bottom: Continue, or on the last step what it does with this way.
const goLabel = computed(() => t(install.form.target === "download" ? "editor.installer.flow.go_download" : "editor.installer.flow.go_install"));
// Each step, and the page that follows the installation, starts at its top.
const root = ref<HTMLElement | null>(null);
watch(() => [install.step, install.browse, install.installer.view], () => root.value?.scrollTo?.({ top: 0 }));
</script>

<template>
  <div ref="root" class="ob" id="installer" :class="setup ? `at-${install.stage}` : 'following'">
    <header class="ob-head">
      <button v-if="showBack" type="button" class="ob-back" id="setup-back" @click="back"><Icon name="chevron-left" />{{ t("editor.installer.flow.back") }}</button>
      <span v-else></span>
      <ol v-if="setup && physical" class="ob-dots" :aria-label="t('editor.installer.flow.step_of', { step: install.step, steps: install.stages.length })">
        <li v-for="(key, index) in install.stages" :key="key" :class="{ on: index < install.step }" :data-stage="key"></li>
      </ol>
      <span v-else></span>
      <button type="button" class="ob-close" id="close-install" :aria-label="t('editor.common.close')" :title="t('editor.common.close')" :disabled="install.flash.busy()" @click="install.close"><Icon name="close" /></button>
    </header>

    <form v-if="setup" id="install-form" class="ob-body" novalidate @submit.prevent="install.submit">
      <Transition name="ob-step" mode="out-in">
        <NameStep v-if="!physical" key="virtual" />
        <BoardStep v-else-if="install.stage === 'board'" key="board" />
        <ModelStep v-else-if="install.stage === 'model'" key="model" />
        <NameStep v-else-if="install.stage === 'name'" key="name" />
        <HangStep v-else-if="install.stage === 'hang'" key="hang" />
        <PluginsStep v-else-if="install.stage === 'plugins'" key="plugins" />
        <WifiStep v-else-if="install.stage === 'wifi'" key="wifi" />
        <CableStep v-else-if="install.stage === 'cable'" key="cable" />
        <ConnectStep v-else key="connect" />
      </Transition>
      <footer class="ob-foot">
        <p v-if="install.status" class="ob-error" id="install-status" role="status">{{ install.status }}</p>
        <button v-if="!physical" type="submit" class="ob-go" id="virtual-create">{{ t("editor.preview.create") }}</button>
        <button v-else-if="install.stage !== 'connect'" type="button" class="ob-go" id="setup-next" :disabled="!install.canGoOn" @click="install.next">{{ t("editor.installer.flow.continue") }}</button>
        <button v-else type="submit" class="ob-go" id="install-go" :disabled="install.goDisabled">
          <span v-if="install.submitting" class="spin small"></span>{{ goLabel }}</button>
        <!-- One quiet way out per step, under the key. -->
        <button v-if="physical && install.stage === 'board' && !install.browse" type="button" class="ob-quiet" id="try-virtual" @click="install.tryVirtual">{{ t("editor.installer.try_virtual") }}</button>
        <button v-else-if="physical && install.stage === 'name'" type="button" class="ob-quiet" id="more-options" :aria-expanded="install.more" @click="install.more = !install.more">{{ t(install.more ? "editor.installer.flow.fewer_options" : "editor.installer.flow.more_options") }}</button>
        <button v-else-if="physical && install.stage === 'cable'" type="button" class="ob-quiet" id="install-later" :disabled="install.submitting" @click="install.later">{{ t("editor.installer.flow.later") }}</button>
        <button v-else-if="physical && install.stage === 'connect' && install.form.target !== 'download'" type="button" class="ob-quiet" id="install-download" :disabled="install.submitting || !!install.clash.name || !!install.clash.node" @click="install.downloadInstead">{{ t("editor.installer.flow.download_instead") }}</button>
      </footer>
    </form>

    <Progress v-else />
  </div>
</template>
