<script setup lang="ts">
// The doorbell, a part of Events (EventsView, docs/DOORBELL.md): an automation fires esp_screens_doorbell with the
// doorbell's camera, started by whatever rings at that house, for the screens it names. The page has one way in, the
// wizard that builds that automation with the person's own doorbell, camera and screens and puts it into Home Assistant
// (DoorbellWizard), the doorbell automations of Tessera under it, and, folded away, the event's fields for writing one
// by hand and what comes back after a ring.
import { computed, ref } from "vue";
import { useAutomations } from "../composables/useAutomations";
import { t } from "../i18n";
import { screenValue } from "../model/alert-yaml";
import { dismissYaml, missedYaml, type DoorbellKind, type DoorbellReference } from "../model/doorbell-yaml";
import { glyph } from "../model/topbar";
import { useInventoryStore } from "../stores/inventory";
import { useUiStore } from "../stores/ui";
import AutomationList from "./events/AutomationList.vue";
import DoorbellWizard from "./events/DoorbellWizard.vue";
import Icon from "./ui/Icon.vue";
import theme from "virtual:esp-screens-theme";

const ui = useUiStore();
const inv = useInventoryStore();
const reference = computed(() => inv.inventory.doorbell as DoorbellReference | undefined);
const physicalScreens = computed(() => inv.inventory.screens.filter((s) => !s.virtual));
const kindOf = (screen: { doorbell?: DoorbellKind }) => screen.doorbell || "plain";
const automations = useAutomations("doorbell");
const wizard = ref(false);
// The mock of the view in the firmware's own colours (theme.h): the camera's black page, its ink and note, the doorbell's
// amber, the round key's grey and the accent of the Sound key.
const hex = (role: string) => `#${theme.roles[role].light.toString(16).padStart(6, "0")}`;
const mock = {
  "--db-page": hex("CAMERA_PAGE"), "--db-ink": hex("CAMERA_INK"), "--db-note": hex("CAMERA_NOTE"), "--db-amber": hex("MARK_AMBER"),
  "--db-key": hex("KEY"), "--db-key-ink": hex("INK"), "--db-accent": hex("ACCENT"), "--db-on-accent": hex("ON_ACCENT"), "--db-track": hex("CAMERA_TRACK"),
};
</script>

<template>
  <div class="doorbell" id="doorbell-part">
    <section class="card event-create" id="doorbell-create">
      <div class="event-create-text">
        <h2>{{ t("editor.doorbell.hero.title") }}</h2>
        <p>{{ t("editor.doorbell.hero.text") }}</p>
        <button type="button" class="btn primary event-create-button" id="doorbell-wizard-open" @click="wizard = true">
          <Icon name="plus" />{{ t("editor.doorbell.hero.create") }}
        </button>
      </div>
      <div class="doorbell-mock" aria-hidden="true" :style="mock">
        <div class="doorbell-mock-head"><span class="mdi doorbell-mock-disc">{{ glyph("F12E6") }}</span>
          <span><strong>{{ t("editor.doorbell.example.title") }}</strong><small>{{ t("editor.doorbell.example.when") }}</small></span>
          <span class="mdi doorbell-mock-close">{{ glyph("F0156") }}</span></div>
        <div class="doorbell-mock-body"><span class="doorbell-mock-picture" /><span class="doorbell-mock-key"><span class="mdi">{{ glyph("F057E") }}</span>{{ t("editor.doorbell.example.sound") }}</span></div>
      </div>
    </section>

    <section class="card" id="doorbell-automations">
      <h2>{{ t("editor.events.install.listed") }}</h2>
      <AutomationList :listed="automations.listed.value" :empty="t('editor.doorbell.hero.empty')" :refresh="automations.refresh" :remove="automations.remove" />
    </section>

    <details class="card event-more" id="doorbell-by-hand">
      <summary>{{ t("editor.doorbell.by_hand.title") }}</summary>
      <p>{{ t("editor.doorbell.intro") }}</p>
      <table class="fields-table">
        <tr v-for="field in reference?.fields || []" :key="field.name"><td><code>{{ field.name }}</code></td><td>{{ field.help }}</td></tr>
      </table>
      <div id="doorbell-screens" class="options">
        <p v-if="!physicalScreens.length" class="hint">{{ t("editor.alerts.screens.none") }}</p>
        <div v-for="screen in physicalScreens" :key="screen.id" class="alert-screen">
          <div class="alert-screen-head">
            <strong>{{ screen.name }}</strong>
            <span class="chip" :class="kindOf(screen) === 'view' ? 'good' : ''" :data-kind="kindOf(screen)">{{ t(`editor.doorbell.screens.${kindOf(screen)}`) }}</span>
          </div>
          <div class="copy-line alert-screen-value">
            <span class="copy-label">{{ t("editor.alerts.one.value") }}</span><code>{{ screenValue(screen) }}</code>
            <button type="button" class="btn quiet mini" @click="ui.copyText(screenValue(screen), undefined, 'screen_name')">{{ t("editor.common.copy") }}</button>
          </div>
        </div>
      </div>
    </details>

    <details class="card event-more" id="doorbell-after">
      <summary>{{ t("editor.doorbell.after.title") }}</summary>
      <i18n-t keypath="editor.doorbell.after.text" tag="p" scope="global">
        <template #answered><code>{{ reference?.answered || "esp_screens_doorbell_answered" }}</code></template>
        <template #missed><code>{{ reference?.missed || "esp_screens_doorbell_missed" }}</code></template>
      </i18n-t>
      <div class="copy-line">
        <pre id="doorbell-missed-yaml">{{ missedYaml(reference) }}</pre>
        <button type="button" class="btn quiet mini" @click="ui.copyText(missedYaml(reference), undefined, 'yaml')">{{ t("editor.alerts.copy_yaml") }}</button>
      </div>
      <p>{{ t("editor.doorbell.after.dismiss") }}</p>
      <div class="copy-line">
        <pre id="doorbell-dismiss-yaml">{{ dismissYaml(reference) }}</pre>
        <button type="button" class="btn quiet mini" @click="ui.copyText(dismissYaml(reference), undefined, 'yaml')">{{ t("editor.alerts.copy_yaml") }}</button>
      </div>
    </details>

    <DoorbellWizard v-model:open="wizard" :save="automations.save" />
  </div>
</template>

<style scoped>
.doorbell { display: grid; gap: 14px; }
.doorbell h2 { font-size: 15px; margin: 0 0 10px; }
.doorbell-mock { width: 300px; max-width: 100%; aspect-ratio: 16 / 10; border-radius: 14px; background: var(--db-page); color: var(--db-ink); padding: 10px; display: grid; grid-template-rows: auto 1fr; gap: 8px; }
.doorbell-mock-head { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.doorbell-mock-head > span:nth-child(2) { display: grid; flex: 1; line-height: 1.2; }
.doorbell-mock-head small { color: var(--db-note); font-size: 10px; }
.doorbell-mock-disc { width: 26px; height: 26px; border-radius: 50%; background: var(--db-amber); color: var(--db-page); display: grid; place-items: center; font-size: 15px; }
.doorbell-mock-close { width: 24px; height: 24px; border-radius: 50%; background: var(--db-key); color: var(--db-key-ink); display: grid; place-items: center; font-size: 14px; }
.doorbell-mock-body { display: grid; grid-template-columns: 1fr 34%; gap: 8px; align-items: end; }
.doorbell-mock-picture { align-self: stretch; border-radius: 8px; background: var(--db-track); }
.doorbell-mock-key { display: inline-flex; align-items: center; gap: 4px; padding: 6px 8px; border-radius: 999px; background: var(--db-accent); color: var(--db-on-accent); font-size: 10px; }
.fields-table { border-collapse: collapse; width: 100%; font-size: 13px; }
.fields-table td { padding: 6px 8px; border-top: 1px solid var(--line); vertical-align: top; }
.fields-table td:first-child { white-space: nowrap; width: 1%; }
</style>
