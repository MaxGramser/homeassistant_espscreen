<script setup lang="ts">
// Try an alert (Alerts' first card): the same seven fields an automation sends, to one screen or to all of them that can
// show one, and what came of it. The example is the doorbell, in the editor's language.
import { computed, reactive, ref } from "vue";
import { useBusy } from "../../composables/useBusy";
import { t } from "../../i18n";
import { useInventoryStore } from "../../stores/inventory";
import { useScreenStore } from "../../stores/screen";

const inv = useInventoryStore();
const scr = useScreenStore();
const alerts = computed(() => inv.inventory.alerts);
const form = reactive({
  screen: "all", title: t("editor.alerts.example.title"), subtitle: t("editor.alerts.example.subtitle"), icon: "doorbell", color: "orange",
  button_text: t("editor.alerts.example.button"), timeout: 30, flash: true,
});
const { busy: trying, run: whileTrying } = useBusy();
const result = ref("");
const physicalScreens = computed(() => inv.inventory.screens.filter((s) => !s.virtual));
const readyScreens = computed(() => physicalScreens.value.filter((s) => scr.canAlert(s) && s.online));
const send = () => whileTrying(async () => {
  result.value = "";
  try {
    const { screen, ...data } = form;
    const answer = await scr.sendTestAlert(screen, data);
    const name = physicalScreens.value.find((s) => s.id === screen)?.name;
    const sent = screen === "all"
      ? t("editor.alerts.try.sent_all", answer.sent)
      : name ? t("editor.alerts.try.sent_to", { name }) : t("editor.alerts.try.sent_one");
    result.value = answer.sent
      ? [sent, answer.skipped ? t("editor.alerts.try.skipped", answer.skipped) : "",
         answer.unusable?.length ? t("editor.alerts.try.left_empty", { fields: answer.unusable.join(", ") }) : ""].filter(Boolean).join(" ")
      : t("editor.alerts.try.nothing", { version: alerts.value?.min_firmware || "0.2.31" });
  } catch (e: any) {
    result.value = e.message;
  }
});
</script>

<template>
  <section id="alerts-try" class="card">
    <h2>{{ t("editor.alerts.nav.try") }}</h2>
    <p>{{ t("editor.alerts.try.text") }}</p>
    <form class="try-grid" @submit.prevent="send">
      <div class="field"><label class="f-label" for="try-screen">{{ t("editor.alerts.try.screen") }}</label>
        <select id="try-screen" v-model="form.screen">
          <option value="all">{{ t("editor.alerts.try.all", { ready: readyScreens.length }) }}</option>
          <option v-for="screen in physicalScreens" :key="screen.id" :value="screen.id" :disabled="!scr.canAlert(screen) || !screen.online">{{ scr.canAlert(screen) && screen.online ? screen.name : t("editor.alerts.try.not_ready", { name: screen.name }) }}</option>
        </select></div>
      <div class="field"><label class="f-label" for="try-title">{{ t("editor.alerts.try.title") }}</label><input id="try-title" v-model="form.title" maxlength="64" /></div>
      <div class="field"><label class="f-label" for="try-subtitle">{{ t("editor.alerts.try.subtitle") }}</label><input id="try-subtitle" v-model="form.subtitle" maxlength="240" /></div>
      <div class="field"><label class="f-label" for="try-icon">{{ t("editor.alerts.try.icon") }}</label><input id="try-icon" v-model="form.icon" list="try-icons" placeholder="doorbell" />
        <datalist id="try-icons"><option v-for="icon in alerts.suggested_icons" :key="icon.name" :value="icon.name">{{ icon.label || icon.name }}</option></datalist></div>
      <div class="field"><label class="f-label" for="try-color">{{ t("editor.alerts.try.color") }}</label>
        <select id="try-color" v-model="form.color"><option value="">{{ t("editor.alerts.white") }}</option><option v-for="colour in alerts.colors" :key="colour.name" :value="colour.name">{{ colour.label }}</option></select></div>
      <div class="field"><label class="f-label" for="try-button">{{ t("editor.alerts.try.button") }}</label><input id="try-button" v-model="form.button_text" maxlength="16" /></div>
      <div class="field"><label class="f-label" for="try-timeout">{{ t("editor.alerts.try.timeout") }}</label><input id="try-timeout" v-model.number="form.timeout" type="number" min="0" max="86400" /></div>
      <label class="check field"><input type="checkbox" id="try-flash" v-model="form.flash" /><span>{{ t("editor.alerts.try.flash") }}<small>{{ t("editor.alerts.try.flash_hint") }}</small></span></label>
      <div class="actions field wide">
        <button type="submit" class="btn primary" id="try-send" :disabled="trying || !readyScreens.length">{{ trying ? t("editor.alerts.try.sending") : t("editor.alerts.try.send") }}</button>
        <span class="status-line" id="try-result" role="status">{{ result }}</span>
      </div>
    </form>
  </section>
</template>
