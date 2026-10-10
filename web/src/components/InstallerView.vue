<script setup lang="ts">
// New screen (app 0.4.32): three steps in one form, the way a setup assistant asks: which screen (BoardStep), what it is
// called and how it hangs (NameStep), and how it gets its firmware (WayStep). Then one page follows the installation in
// the steps a person knows (Progress). The steps only show and hide; the form, what it sends and when, is the one it
// always was (composables/useInstaller.ts).
import { ref, watch } from "vue";
import { t } from "../i18n";
import { useInstaller } from "../composables/useInstaller";
import BoardStep from "./install/BoardStep.vue";
import NameStep from "./install/NameStep.vue";
import Progress from "./install/Progress.vue";
import WayStep from "./install/WayStep.vue";
import Icon from "./ui/Icon.vue";

const install = useInstaller();
const nameStep = ref<InstanceType<typeof NameStep> | null>(null);
// Step two asks nothing it can't check on the spot: Next goes on only when its fields are filled in as they must be.
function next() {
  if (install.step === 1) { if (install.form.board || install.mode === "virtual") install.step = 2; return; }
  if (install.step === 2) {
    if (!nameStep.value?.check() || install.clash.node || install.clash.name) return;
    install.step = 3;
  }
}
// Each step, and the installation after them, starts at its top.
const root = ref<HTMLElement | null>(null);
watch(() => [install.step, install.installer.view], () => root.value?.scrollTo?.({ top: 0 }));
</script>

<template>
  <div ref="root" class="setup" id="installer" :class="install.installer.view === 'setup' ? `step-${install.step}` : 'following'">
    <!-- The bar across the top: where in the setup you are, and the way out. -->
    <header class="setup-head">
      <span class="setup-brand">{{ t("editor.nav.new_screen") }}</span>
      <ol v-if="install.installer.view === 'setup' && install.mode === 'physical'" class="setup-steps" :aria-label="t('editor.nav.new_screen')">
        <li v-for="(key, index) in (['board', 'setup', 'install'] as const)" :key="key" :class="{ now: install.step === index + 1, past: install.step > index + 1 }">
          <button type="button" :disabled="install.step <= index + 1" @click="install.step = (index + 1) as 1 | 2 | 3"><i>{{ install.step > index + 1 ? "✓" : index + 1 }}</i>{{ t(`editor.installer.steps.${key}`) }}</button>
        </li>
      </ol>
      <span v-else class="setup-steps-spacer"></span>
      <button type="button" class="icon-btn" id="close-install" :aria-label="t('editor.common.close')" :title="t('editor.common.close')" :disabled="install.flash.busy()" @click="install.close"><Icon name="close" /></button>
    </header>

    <form v-if="install.installer.view === 'setup'" id="install-form" class="setup-body" novalidate @submit.prevent="install.submit">
      <BoardStep v-show="install.step === 1 && install.mode === 'physical'" :install="install" @next="next" />
      <NameStep v-show="install.step === 2" ref="nameStep" :install="install" />
      <WayStep v-show="install.step === 3 && install.mode === 'physical'" :install="install" />
      <footer class="setup-foot">
        <button v-if="install.step > 1 && !(install.mode === 'virtual' && install.step === 2)" type="button" class="btn quiet" id="setup-back" @click="install.back">{{ t("editor.common.back") }}</button>
        <button v-else-if="install.mode === 'virtual'" type="button" class="btn quiet" @click="install.realScreen">{{ t("editor.common.back") }}</button>
        <span class="status-line error" id="install-status" role="status">{{ install.status }}</span>
        <button v-if="install.mode === 'virtual'" type="submit" class="btn primary big" id="virtual-create">{{ t("editor.preview.create") }}</button>
        <button v-else-if="install.step < 3" type="button" class="btn primary big" id="setup-next" :disabled="(install.step === 1 && !install.form.board) || (install.step === 2 && (install.clash.name || install.clash.node))" @click="next">{{ t("editor.installer.next") }}<Icon name="arrow-right" /></button>
        <button v-else type="submit" class="btn primary big" id="install-go" :disabled="install.goDisabled">{{ install.goLabel }}</button>
      </footer>
    </form>

    <!-- The installation: the screen filling in, the steps it goes through, and ESPHome's own log behind Details. -->
    <Progress v-else :install="install" />
  </div>
</template>
