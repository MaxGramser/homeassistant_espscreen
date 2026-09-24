<script setup lang="ts">
// Alerts: the cheatsheet for esphome.<node>_show_alert, built from the inventory.
import { computed, reactive, ref } from "vue";
import { andList, t } from "../i18n";
import { versionAtLeast } from "../model/layout";
import { glyph } from "../model/topbar";
import { canAlert, copyText, firmwareVersion, go, sendTestAlert, state } from "../store";

const alerts = computed(() => state.inventory.alerts);
// The bytes a field holds on each look, with the boards that have it ("CYD 48 · Guition and Waveshare 64 bytes"): the
// add-on names the boards from its catalog, so a new board shows up here without a word of this page changing.
function limitText(field: string) {
  const limits: Record<string, Record<string, number>> = alerts.value?.limits || {};
  const boards: Record<string, string[]> = alerts.value?.limit_boards || {};
  const parts = Object.entries(limits).filter(([look, values]) => values[field] && boards[look]?.length)
    .map(([look, values]) => `${andList(boards[look])} ${values[field]}`);
  return parts.length ? t("editor.alerts.fields.bytes", { limits: parts.join(" · ") }) : "";
}
// Try it: the same seven fields an automation sends, to one screen or to all of them. The example is the doorbell, in
// the editor's language; the YAML examples below stay as code.
const tryForm = reactive({
  screen: "all", title: t("editor.alerts.example.title"), subtitle: t("editor.alerts.example.subtitle"), icon: "doorbell", color: "orange",
  button_text: t("editor.alerts.example.button"), timeout: 30, flash: true,
});
const trying = ref(false);
const tryResult = ref("");
const physicalScreens = computed(() => state.inventory.screens.filter(s => !s.virtual));
const readyScreens = computed(() => physicalScreens.value.filter((s) => canAlert(s) && s.online));
async function tryAlert() {
  trying.value = true;
  tryResult.value = "";
  try {
    const { screen, ...data } = tryForm;
    const result = await sendTestAlert(screen, data);
    const name = physicalScreens.value.find((s) => s.id === screen)?.name;
    const sent = screen === "all"
      ? t("editor.alerts.try.sent_all", result.sent)
      : name ? t("editor.alerts.try.sent_to", { name }) : t("editor.alerts.try.sent_one");
    tryResult.value = result.sent
      ? [sent, result.skipped ? t("editor.alerts.try.skipped", result.skipped) : "",
         result.unusable?.length ? t("editor.alerts.try.left_empty", { fields: result.unusable.join(", ") }) : ""].filter(Boolean).join(" ")
      : t("editor.alerts.try.nothing", { version: alerts.value?.min_firmware || "0.2.31" });
  } catch (e: any) {
    tryResult.value = e.message;
  } finally {
    trying.value = false;
  }
}
const icons = computed(() => state.inventory.icons);
const exampleAction = ref("");
const iconQuery = ref("");
const yamlString = (text: unknown) => `"${String(text).replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
const fieldValue = (f: any) => f.type === "string" ? (/^[a-z][a-z0-9-]*$/.test(f.example) ? f.example : yamlString(f.example)) : f.example === true ? "true" : f.example === false ? "false" : String(f.example);
const screensWithAction = computed(() => physicalScreens.value.filter((s) => s.alert_action));
const chosenAction = computed(() => exampleAction.value || screensWithAction.value[0]?.alert_action || "");
const exampleYaml = computed(() => {
  const lines = (alerts.value?.fields || []).map((f: any) => `  ${f.name}: ${fieldValue(f)}`);
  return `action: ${chosenAction.value || "esphome.<device_name>_show_alert"}\ndata:\n${lines.join("\n")}`;
});
// The doorbell example in the editor's language: the fields' own examples, and two lines of its own.
const example = (name: string, fallback: string) => yamlString((alerts.value?.fields || []).find((f: any) => f.name === name)?.example || fallback);
const waitYaml = computed(() => [
  `# ${t("editor.alerts.wait_yaml.comment")}`,
  `actions:`,
  `  - action: ${chosenAction.value || "esphome.<device_name>_show_alert"}`,
  `    data:`,
  `      title: ${example("title", "Someone is at the door")}`,
  `      subtitle: ${example("subtitle", "Door 3, back")}`,
  `      icon: doorbell`,
  `      color: orange`,
  `      button_text: ${example("button_text", "Coming")}`,
  `      timeout: 0`,
  `      flash: true`,
  `  - wait_for_trigger:`,
  `      - trigger: event`,
  `        event_type: ${alerts.value?.event || "esphome.screen_alert"}`,
  `        event_data:`,
  `          action: ok`,
  `    timeout: "00:05:00"`,
  `  - if:`,
  `      - condition: template`,
  `        value_template: "{{ wait.trigger is not none }}"`,
  `    then:`,
  `      - action: notify.notify`,
  `        data:`,
  `          message: ${yamlString(t("editor.alerts.wait_yaml.message"))}`,
].join("\n"));
// One event for every screen (app 0.2.45): an action for "Edit in YAML" of the Event action.
const allYaml = computed(() => {
  const lines = (alerts.value?.fields || []).map((f: any) => `  ${f.name}: ${fieldValue(f)}`);
  const camera = alerts.value?.camera;
  if (camera) lines.push(`  # ${camera.name}: ${camera.example}   # a Guition shows its picture on the card`);
  return `event: ${alerts.value?.broadcast?.show || "esp_screens_show_alert"}\nevent_data:\n${lines.join("\n")}`;
});
// One screen through the same event (app 0.2.133): what goes after `screen:` for each paired screen, and the example for the
// one chosen. The device name is what the screen reports itself and what its actions are named after; a screen that has
// not said it yet goes by the name Home Assistant shows, which the app matches as well.
const screenValue = (screen: { node?: string; name: string }) => screen.node || screen.name;
const yamlName = (text: string) => (/^[a-z][a-z0-9_-]*$/.test(text) ? text : yamlString(text));
const oneScreenId = ref("");
// The example starts at the screen that is open in the editor, else the first in the list.
const oneScreen = computed(() => {
  const [first] = physicalScreens.value;
  return physicalScreens.value.find((s) => s.id === (oneScreenId.value || state.selected)) || first;
});
const oneYaml = computed(() => {
  const screen = oneScreen.value;
  const lines = [`  screen: ${screen ? yamlName(screenValue(screen)) : alerts.value?.screen?.example || "kitchen-screen"}`,
    ...(alerts.value?.fields || []).map((f: any) => `  ${f.name}: ${fieldValue(f)}`)];
  // The picture only where the board draws one; a CYD gets the same alert without it.
  if (alerts.value?.camera && (!screen || screen.pictures)) lines.push(`  ${alerts.value.camera.name}: ${alerts.value.camera.example}`);
  return `event: ${alerts.value?.broadcast?.show || "esp_screens_show_alert"}\nevent_data:\n${lines.join("\n")}`;
});
const iconGroups = computed(() => {
  if (!alerts.value || !icons.value) return [];
  const query = iconQuery.value.trim().toLowerCase();
  const all = [...icons.value.groups, { label: t("editor.alerts.icons.extra"), icons: alerts.value.extra_icons }];
  return all.map((group) => ({ label: group.label, icons: group.icons.filter((i: any) => !query || i.name.includes(query) || (i.label || "").toLowerCase().includes(query)) })).filter((g) => g.icons.length);
});
const doorbell = computed(() => alerts.value?.suggested_icons?.find((i: any) => i.name === "doorbell"));
const orange = computed(() => alerts.value?.colors?.find((c: any) => c.name === "orange"));
// A field's type in words (editor.alerts.fields.types); another type shows as it is.
const typeName = (type: string) => (["string", "int", "bool"].includes(type) ? t(`editor.alerts.fields.types.${type}`) : type);
function jump(id: string) { document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" }); }
// The sections by id; each one's name in the bar is editor.alerts.nav.<the id without "alerts-">.
const sections = ["alerts-try", "alerts-screens", "alerts-howto", "alerts-all", "alerts-one", "alerts-fields", "alerts-icons", "alerts-colors", "alerts-behaviour", "alerts-events", "alerts-tips"];
</script>

<template>
  <div class="panel wide alerts" id="alerts-dialog">
    <div class="panel-head">
      <div class="tx">
        <span class="eyebrow">{{ t("editor.alerts.eyebrow") }}</span>
        <h1>{{ t("editor.alerts.title") }}</h1>
        <i18n-t keypath="editor.alerts.intro" tag="p" scope="global">
          <template #action><code>show_alert</code></template>
        </i18n-t>
      </div>
      <button type="button" class="btn quiet" id="close-alerts" @click="go('')">{{ t("editor.common.back") }}</button>
    </div>
    <p v-if="!alerts" class="hint">{{ t("editor.alerts.loading") }}</p>
    <template v-else>
      <div class="alert-hero">
        <div class="alert-mock" id="alert-mock" aria-hidden="true">
          <div class="alert-mock-card" :style="orange ? { background: orange.color } : undefined">
            <span class="mdi alert-mock-icon" id="alert-mock-icon">{{ doorbell ? glyph(doorbell.cp) : "" }}</span>
            <strong id="alert-mock-title">{{ t("editor.alerts.example.title") }}</strong>
            <span id="alert-mock-subtitle">{{ t("editor.alerts.example.subtitle") }}</span>
            <span class="fake" id="alert-mock-button">{{ t("editor.alerts.example.button") }}</span>
          </div>
        </div>
        <nav class="alerts-nav" :aria-label="t('editor.alerts.sections')">
          <button v-for="id in sections" :key="id" type="button" :data-jump="id" @click="jump(id)">{{ t(`editor.alerts.nav.${id.slice("alerts-".length)}`) }}</button>
        </nav>
      </div>
      <section id="alerts-try" class="card">
        <h2>{{ t("editor.alerts.nav.try") }}</h2>
        <p>{{ t("editor.alerts.try.text") }}</p>
        <form class="try-grid" @submit.prevent="tryAlert">
          <div class="field"><label class="f-label" for="try-screen">{{ t("editor.alerts.try.screen") }}</label>
            <select id="try-screen" v-model="tryForm.screen">
              <option value="all">{{ t("editor.alerts.try.all", { ready: readyScreens.length }) }}</option>
              <option v-for="screen in physicalScreens" :key="screen.id" :value="screen.id" :disabled="!canAlert(screen) || !screen.online">{{ canAlert(screen) && screen.online ? screen.name : t("editor.alerts.try.not_ready", { name: screen.name }) }}</option>
            </select></div>
          <div class="field"><label class="f-label" for="try-title">{{ t("editor.alerts.try.title") }}</label><input id="try-title" v-model="tryForm.title" maxlength="64" /></div>
          <div class="field"><label class="f-label" for="try-subtitle">{{ t("editor.alerts.try.subtitle") }}</label><input id="try-subtitle" v-model="tryForm.subtitle" maxlength="240" /></div>
          <div class="field"><label class="f-label" for="try-icon">{{ t("editor.alerts.try.icon") }}</label><input id="try-icon" v-model="tryForm.icon" list="try-icons" placeholder="doorbell" />
            <datalist id="try-icons"><option v-for="icon in alerts.suggested_icons" :key="icon.name" :value="icon.name">{{ icon.label || icon.name }}</option></datalist></div>
          <div class="field"><label class="f-label" for="try-color">{{ t("editor.alerts.try.color") }}</label>
            <select id="try-color" v-model="tryForm.color"><option value="">{{ t("editor.alerts.white") }}</option><option v-for="colour in alerts.colors" :key="colour.name" :value="colour.name">{{ colour.label }}</option></select></div>
          <div class="field"><label class="f-label" for="try-button">{{ t("editor.alerts.try.button") }}</label><input id="try-button" v-model="tryForm.button_text" maxlength="16" /></div>
          <div class="field"><label class="f-label" for="try-timeout">{{ t("editor.alerts.try.timeout") }}</label><input id="try-timeout" v-model.number="tryForm.timeout" type="number" min="0" max="86400" /></div>
          <label class="check field"><input type="checkbox" id="try-flash" v-model="tryForm.flash" /><span>{{ t("editor.alerts.try.flash") }}<small>{{ t("editor.alerts.try.flash_hint") }}</small></span></label>
          <div class="actions field wide">
            <button type="submit" class="btn primary" id="try-send" :disabled="trying || !readyScreens.length">{{ trying ? t("editor.alerts.try.sending") : t("editor.alerts.try.send") }}</button>
            <span class="status-line" id="try-result" role="status">{{ tryResult }}</span>
          </div>
        </form>
      </section>
      <section id="alerts-screens" class="card">
        <h2>{{ t("editor.alerts.nav.screens") }}</h2>
        <i18n-t keypath="editor.alerts.screens.text" tag="p" scope="global">
          <template #version><code id="alerts-min-firmware">{{ alerts.min_firmware }}</code></template>
        </i18n-t>
        <div id="alerts-screen-list" class="options">
          <p v-if="!physicalScreens.length" class="hint">{{ t("editor.alerts.screens.none") }}</p>
          <div v-for="screen in physicalScreens" :key="screen.id" class="alert-screen">
            <div class="alert-screen-head">
              <strong>{{ screen.name }}</strong>
              <span class="chip" :class="versionAtLeast(firmwareVersion(screen), alerts.min_firmware) && screen.alert_action ? 'good' : 'update'">
                {{ versionAtLeast(firmwareVersion(screen), alerts.min_firmware) && screen.alert_action
                  ? t("editor.alerts.screens.ready", { version: screen.firmware })
                  : screen.alert_action ? t("editor.alerts.screens.update", { version: screen.firmware || t("editor.common.unknown") }) : t("editor.alerts.screens.unknown") }}
              </span>
            </div>
            <div v-for="[label, action] in [[t('editor.alerts.screens.show'), screen.alert_action], [t('editor.alerts.screens.dismiss'), screen.dismiss_action]]" :key="label" class="copy-line">
              <span class="copy-label">{{ label }}</span><code>{{ action || "esphome.<device_name>_show_alert" }}</code>
              <button v-if="action" type="button" class="btn quiet mini" @click="copyText(action!, undefined, 'action_name')">{{ t("editor.common.copy") }}</button>
            </div>
            <div class="copy-line alert-screen-value">
              <span class="copy-label">{{ t("editor.alerts.one.value") }}</span><code>{{ screenValue(screen) }}</code>
              <button type="button" class="btn quiet mini" @click="copyText(screenValue(screen), undefined, 'screen_name')">{{ t("editor.common.copy") }}</button>
            </div>
          </div>
        </div>
      </section>
      <section id="alerts-howto" class="card">
        <h2>{{ t("editor.alerts.nav.howto") }}</h2>
        <ol class="steps">
          <i18n-t keypath="editor.alerts.howto.add" tag="li" scope="global">
            <template #add><b>{{ t("editor.alerts.howto.add_bold") }}</b></template>
            <template #esphome><b>ESPHome</b></template>
            <template #device><i>{{ t("editor.alerts.howto.device") }}</i></template>
          </i18n-t>
          <i18n-t keypath="editor.alerts.howto.fields" tag="li" scope="global">
            <template #bold><b>{{ t("editor.alerts.howto.fields_bold") }}</b></template>
            <template #empty><code>""</code></template>
            <template #zero><code>0</code></template>
          </i18n-t>
          <i18n-t keypath="editor.alerts.howto.yaml" tag="li" scope="global">
            <template #edit><b>{{ t("editor.alerts.edit_yaml") }}</b></template>
          </i18n-t>
        </ol>
        <div class="field">
          <label class="f-label" for="alerts-example-screen">{{ t("editor.alerts.howto.example_for") }}</label>
          <select id="alerts-example-screen" v-model="exampleAction" style="max-width: 360px">
            <option v-for="screen in screensWithAction" :key="screen.id" :value="screen.alert_action">{{ screen.name }}</option>
            <option v-if="!screensWithAction.length" value="">{{ t("editor.alerts.howto.no_screen") }}</option>
          </select>
        </div>
        <div class="copy-line">
          <pre id="alerts-example">{{ exampleYaml }}</pre>
          <button type="button" class="btn quiet mini" id="alerts-example-copy" @click="copyText(exampleYaml, undefined, 'yaml')">{{ t("editor.alerts.copy_yaml") }}</button>
        </div>
      </section>
      <section id="alerts-all" class="card">
        <h2>{{ t("editor.alerts.all.title") }}</h2>
        <i18n-t keypath="editor.alerts.all.text" tag="p" scope="global">
          <template #show><code id="alerts-all-event">{{ alerts.broadcast?.show || "esp_screens_show_alert" }}</code></template>
          <template #dismiss><code id="alerts-all-dismiss">{{ alerts.broadcast?.dismiss || "esp_screens_dismiss_alert" }}</code></template>
          <template #event><b>{{ t("editor.alerts.all.event") }}</b></template>
          <template #edit><b>{{ t("editor.alerts.edit_yaml") }}</b></template>
        </i18n-t>
        <div class="copy-line">
          <pre id="alerts-all-example">{{ allYaml }}</pre>
          <button type="button" class="btn quiet mini" id="alerts-all-copy" @click="copyText(allYaml, undefined, 'yaml')">{{ t("editor.alerts.copy_yaml") }}</button>
        </div>
      </section>
      <section id="alerts-one" class="card">
        <h2>{{ t("editor.alerts.one.title") }}</h2>
        <i18n-t keypath="editor.alerts.one.text" tag="p" scope="global">
          <template #screen><code>screen:</code></template>
          <template #camera><code>camera</code></template>
          <template #action><code>action</code></template>
        </i18n-t>
        <div class="table-scroll">
          <table id="alerts-one-table">
            <tr><th>{{ t("editor.alerts.one.value") }}</th><th>{{ t("editor.alerts.one.name") }}</th><th>{{ t("editor.alerts.one.room") }}</th><th>{{ t("editor.alerts.one.picture") }}</th></tr>
            <tr v-for="screen in physicalScreens" :key="screen.id">
              <td><span class="copy-line"><code>{{ screenValue(screen) }}</code>
                <button type="button" class="btn quiet mini" @click="copyText(screenValue(screen), undefined, 'screen_name')">{{ t("editor.common.copy") }}</button></span></td>
              <td>{{ screen.name }}</td>
              <td>{{ screen.area || "—" }}</td>
              <td>{{ screen.pictures ? t("editor.alerts.one.picture_yes") : t("editor.alerts.one.picture_no") }}</td>
            </tr>
            <tr v-if="!physicalScreens.length"><td colspan="4" class="hint">{{ t("editor.alerts.one.none") }}</td></tr>
          </table>
        </div>
        <i18n-t keypath="editor.alerts.one.more" tag="p" scope="global">
          <template #list><code>screen: [{{ physicalScreens.slice(0, 2).map(screenValue).join(", ") || "kitchen-screen, hallway" }}]</code></template>
        </i18n-t>
        <div v-if="physicalScreens.length" class="field">
          <label class="f-label" for="alerts-one-screen">{{ t("editor.alerts.howto.example_for") }}</label>
          <select id="alerts-one-screen" :value="oneScreen?.id" style="max-width: 360px" @change="oneScreenId = ($event.target as HTMLSelectElement).value">
            <option v-for="screen in physicalScreens" :key="screen.id" :value="screen.id">{{ screen.name }}</option>
          </select>
        </div>
        <div class="copy-line">
          <pre id="alerts-one-example">{{ oneYaml }}</pre>
          <button type="button" class="btn quiet mini" id="alerts-one-copy" @click="copyText(oneYaml, undefined, 'yaml')">{{ t("editor.alerts.copy_yaml") }}</button>
        </div>
      </section>
      <section id="alerts-fields" class="card">
        <h2>{{ t("editor.alerts.nav.fields") }}</h2>
        <p>{{ t("editor.alerts.fields.text") }}</p>
        <div class="table-scroll">
          <table id="alerts-field-table">
            <tr><th>{{ t("editor.alerts.fields.field") }}</th><th>{{ t("editor.alerts.fields.type") }}</th><th>{{ t("editor.alerts.fields.what") }}</th><th>{{ t("editor.alerts.fields.example") }}</th><th>{{ t("editor.alerts.fields.limit") }}</th></tr>
            <tr v-for="field in alerts.fields" :key="field.name">
              <td><code>{{ field.name }}</code><small>{{ field.label }}</small></td>
              <td>{{ typeName(field.type) }}</td>
              <td>{{ field.help }}</td>
              <td><code>{{ typeof field.example === "string" ? field.example : String(field.example) }}</code></td>
              <td>{{ limitText(field.name) || (field.type === "int" ? t("editor.alerts.fields.seconds") : "—") }}</td>
            </tr>
            <tr v-if="alerts.camera">
              <td><code>{{ alerts.camera.name }}</code><small>{{ alerts.camera.label }}</small></td>
              <td>{{ t("editor.alerts.fields.types.entity") }}</td>
              <td>{{ alerts.camera.help }}</td>
              <td><code>{{ alerts.camera.example }}</code></td>
              <td>{{ t("editor.alerts.fields.camera_limit") }}</td>
            </tr>
            <tr v-if="alerts.screen">
              <td><code>{{ alerts.screen.name }}</code><small>{{ alerts.screen.label }}</small></td>
              <td>{{ t("editor.alerts.fields.types.string") }}</td>
              <td>{{ alerts.screen.help }}</td>
              <td><code>{{ oneScreen ? screenValue(oneScreen) : alerts.screen.example }}</code></td>
              <td>{{ t("editor.alerts.fields.screen_limit") }}</td>
            </tr>
          </table>
        </div>
      </section>
      <section id="alerts-icons" class="card">
        <h2>{{ t("editor.alerts.nav.icons") }}</h2>
        <i18n-t keypath="editor.alerts.icons.text" tag="p" scope="global">
          <template #field><code>icon</code></template>
          <template #example><code>doorbell</code></template>
          <template #mdi><code>mdi:doorbell</code></template>
          <template #hex><code>F12E6</code></template>
        </i18n-t>
        <p class="subhead">{{ t("editor.alerts.icons.handy") }}</p>
        <div class="chips" id="alerts-suggested">
          <button v-for="icon in alerts.suggested_icons" :key="icon.name" type="button" class="chip" @click="copyText(icon.name, undefined, 'icon_name')"><span class="mdi">{{ glyph(icon.cp) }}</span><code>{{ icon.name }}</code></button>
        </div>
        <div class="field">
          <label class="f-label" for="alerts-icon-search">{{ t("editor.alerts.icons.search_label") }}</label>
          <input id="alerts-icon-search" v-model="iconQuery" type="search" :placeholder="t('editor.alerts.icons.search')" autocomplete="off" />
        </div>
        <div id="alerts-icon-groups">
          <div v-for="group in iconGroups" :key="group.label" class="field">
            <p class="subhead">{{ group.label }} · {{ group.icons.length }}</p>
            <div class="alert-icon-grid">
              <button v-for="icon in group.icons" :key="icon.name" type="button" class="alert-icon" :title="t('editor.alerts.icons.copy', { name: icon.name })" @click="copyText(icon.name, undefined, 'icon_name')">
                <span class="mdi">{{ glyph(icon.cp) }}</span><code>{{ icon.name }}</code><small v-if="icon.label">{{ icon.label }}</small>
              </button>
            </div>
          </div>
          <p v-if="!iconGroups.length" class="hint">{{ t("editor.alerts.icons.none", { query: iconQuery, fallback: alerts.fallback_icon }) }}</p>
        </div>
      </section>
      <section id="alerts-colors" class="card">
        <h2>{{ t("editor.alerts.nav.colors") }}</h2>
        <i18n-t keypath="editor.alerts.colors.text" tag="p" scope="global">
          <template #field><code>color</code></template>
        </i18n-t>
        <div class="swatches" id="alerts-swatches">
          <button type="button" class="swatch" @click="copyText('', undefined, 'empty_color')"><i style="background: #ffffff"></i><span><code>empty</code><small>{{ t("editor.alerts.white") }}</small></span></button>
          <button v-for="colour in alerts.colors" :key="colour.name" type="button" class="swatch" @click="copyText(colour.name, undefined, 'color_name')"><i :style="{ background: colour.color }"></i><span><code>{{ colour.name }}</code><small>{{ colour.label }} · {{ colour.color }}</small></span></button>
        </div>
      </section>
      <section id="alerts-behaviour" class="card">
        <h2>{{ t("editor.alerts.nav.behaviour") }}</h2>
        <ul class="alerts-list">
          <i18n-t keypath="editor.alerts.behaviour.wakes" tag="li" scope="global">
            <template #bold><b>{{ t("editor.alerts.behaviour.wakes_bold") }}</b></template>
          </i18n-t>
          <i18n-t keypath="editor.alerts.behaviour.on" tag="li" scope="global">
            <template #bold><b>{{ t("editor.alerts.behaviour.on_bold") }}</b></template>
          </i18n-t>
          <i18n-t keypath="editor.alerts.behaviour.timeout" tag="li" scope="global">
            <template #bold><b>{{ t("editor.alerts.behaviour.timeout_bold") }}</b></template>
            <template #zero><code>timeout: 0</code></template>
            <template #minute><code>timeout: 60</code></template>
          </i18n-t>
          <i18n-t keypath="editor.alerts.behaviour.blinking" tag="li" scope="global">
            <template #bold><b>{{ t("editor.alerts.behaviour.blinking_bold") }}</b></template>
            <template #flash><code>flash: true</code></template>
          </i18n-t>
          <i18n-t keypath="editor.alerts.behaviour.replacing" tag="li" scope="global">
            <template #bold><b>{{ t("editor.alerts.behaviour.replacing_bold") }}</b></template>
            <template #replaced><code>replaced</code></template>
          </i18n-t>
          <i18n-t keypath="editor.alerts.behaviour.closing" tag="li" scope="global">
            <template #bold><b>{{ t("editor.alerts.behaviour.closing_bold") }}</b></template>
            <template #dismiss><code>dismiss_alert</code></template>
          </i18n-t>
          <i18n-t keypath="editor.alerts.behaviour.beside" tag="li" scope="global">
            <template #bold><b>{{ t("editor.alerts.behaviour.beside_bold") }}</b></template>
          </i18n-t>
        </ul>
      </section>
      <section id="alerts-events" class="card">
        <h2>{{ t("editor.alerts.nav.events") }}</h2>
        <i18n-t keypath="editor.alerts.events.text" tag="p" scope="global">
          <template #event><code id="alerts-event-name">{{ alerts.event }}</code></template>
          <template #action><code>action</code></template>
          <template #title><code>title</code></template>
          <template #screen><code>screen</code></template>
          <template #device_id><code>device_id</code></template>
        </i18n-t>
        <div class="table-scroll">
          <table id="alerts-ending-table">
            <tr><th>action</th><th>{{ t("editor.alerts.events.when") }}</th></tr>
            <tr v-for="ending in alerts.endings" :key="ending.action"><td><code>{{ ending.action }}</code></td><td>{{ ending.label }}</td></tr>
          </table>
        </div>
        <p class="subhead">{{ t("editor.alerts.events.wait") }}</p>
        <div class="copy-line">
          <pre id="alerts-wait-example">{{ waitYaml }}</pre>
          <button type="button" class="btn quiet mini" id="alerts-wait-copy" @click="copyText(waitYaml, undefined, 'yaml')">{{ t("editor.alerts.copy_yaml") }}</button>
        </div>
      </section>
      <section id="alerts-tips" class="card">
        <h2>{{ t("editor.alerts.nav.tips") }}</h2>
        <ul class="alerts-list">
          <i18n-t keypath="editor.alerts.tips.color" tag="li" scope="global">
            <template #bold><b>{{ t("editor.alerts.tips.color_bold") }}</b></template>
          </i18n-t>
          <i18n-t keypath="editor.alerts.tips.short" tag="li" scope="global">
            <template #bold><b>{{ t("editor.alerts.tips.short_bold") }}</b></template>
          </i18n-t>
          <i18n-t keypath="editor.alerts.tips.button" tag="li" scope="global">
            <template #bold><b>{{ t("editor.alerts.tips.button_bold") }}</b></template>
          </i18n-t>
          <i18n-t keypath="editor.alerts.tips.resolve" tag="li" scope="global">
            <template #dismiss><code>dismiss_alert</code></template>
          </i18n-t>
          <i18n-t keypath="editor.alerts.tips.every" tag="li" scope="global">
            <template #event><code>{{ alerts.broadcast?.show || "esp_screens_show_alert" }}</code></template>
            <template #screen><code>screen</code></template>
          </i18n-t>
          <i18n-t keypath="editor.alerts.tips.claude" tag="li" scope="global">
            <template #bold><b>{{ t("editor.alerts.tips.claude_bold") }}</b></template>
          </i18n-t>
        </ul>
      </section>
    </template>
  </div>
</template>
