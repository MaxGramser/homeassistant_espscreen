<script setup lang="ts">
// The alert's wizard (Events, Alerts): what starts it, what it says, its buttons (one or two, each with its words, its
// colour and, if you like, an action of Home Assistant's for an entity), how it looks (with the card as the screen draws
// it), the screens, then one now to see it and the automation into Home Assistant, "Tessera: <its title>". One step at a
// time in UiWizard; the page lists the automation once it is saved. The automation always fires the event for every
// screen, the one way that carries a camera, a button's action and a choice of screens; the last step says what that
// means for the screens chosen (alertRoute). The last step also offers the action alone, for an automation of the
// person's own (WizardFinish); then what starts it may stay empty.
import { computed, reactive, ref, watch } from "vue";
import { useBusy } from "../../composables/useBusy";
import { t } from "../../i18n";
import { alertAutomation, alertRoute, buttonFields, screenValue, type AlertButtonChoice, type AlertReference } from "../../model/alert-yaml";
import { actionYaml, triggerKind } from "../../model/automation";
import { versionAtLeast } from "../../model/layout";
import { firmwareVersion } from "../../model/screen-status";
import { glyph } from "../../model/topbar";
import { useInventoryStore } from "../../stores/inventory";
import { useScreenStore } from "../../stores/screen";
import { useUiStore } from "../../stores/ui";
import CheckRow from "../ui/CheckRow.vue";
import Icon from "../ui/Icon.vue";
import UiChoiceCards from "../ui/UiChoiceCards.vue";
import UiPicker from "../ui/UiPicker.vue";
import UiSwitch from "../ui/UiSwitch.vue";
import UiWizard from "../ui/UiWizard.vue";
import AlertButton from "./AlertButton.vue";
import TriggerStep from "./TriggerStep.vue";
import WizardFinish, { type Finish } from "./WizardFinish.vue";
import theme from "virtual:esp-screens-theme";

type Reference = AlertReference & { suggested_icons?: { name: string; cp: string }[]; colors?: { name: string; label: string; color: string }[]; min_firmware?: string };
const props = defineProps<{ open: boolean; save: (automation: ReturnType<typeof alertAutomation>, id?: string | null) => Promise<{ id: string }> }>();
const emit = defineEmits<{ "update:open": [open: boolean] }>();
const inv = useInventoryStore();
const scr = useScreenStore();
const ui = useUiStore();
const alerts = computed(() => inv.inventory.alerts as Reference | undefined);
const entities = computed(() => inv.inventory.entities || []);
const nameOf = (id: string) => entities.value.find((e) => e.id === id)?.name || id;
const cameras = computed(() => entities.value.filter((e) => e.id.startsWith("camera.") || e.id.startsWith("image."))
  .map((e) => ({ id: e.id, name: e.name || e.id, hint: [e.area, e.id].filter(Boolean).join(" · ") })));
const screens = computed(() => inv.inventory.screens.filter((s) => !s.virtual));

const steps = computed(() => ["trigger", "words", "buttons", "look", "screens", "try", "add"].map((id) => ({
  id, title: t(`editor.alerts.wizard.steps.${id}.title`), help: t(`editor.alerts.wizard.steps.${id}.help`) })));
const step = ref(1);
const finish = ref<Finish>("automation");
// At the last step without anything that starts it, the action alone is what fits.
watch(step, (now) => { if (now === steps.value.length && !choice.trigger && !saved.value) finish.value = "action"; });
const fresh = () => ({ title: t("editor.alerts.example.title"), subtitle: t("editor.alerts.example.subtitle"), icon: "doorbell", color: "orange", timeout: 30, flash: true });
const button = (text: string): AlertButtonChoice => ({ text, color: "", entity: "", action: "" });
const form = reactive(fresh());
const choice = reactive({ trigger: "", camera: "", screens: [] as string[], count: "one",
  first: button(t("editor.alerts.example.button")), second: button(t("editor.alerts.wizard.buttons.second_example")) });
const two = computed(() => choice.count === "two");
const counts = computed(() => [
  { value: "one", title: t("editor.alerts.wizard.buttons.one"), detail: t("editor.alerts.wizard.buttons.one_detail") },
  { value: "two", title: t("editor.alerts.wizard.buttons.two"), detail: t("editor.alerts.wizard.buttons.two_detail") },
]);
const toggle = (value: string) => { choice.screens = choice.screens.includes(value) ? choice.screens.filter((v) => v !== value) : [...choice.screens, value]; };
const fields = computed(() => ({ ...form, ...buttonFields(choice.first, two.value ? choice.second : null) }));
const automation = computed(() => alertAutomation(alerts.value, { ...choice, kind: choice.trigger ? triggerKind(choice.trigger) : null, fields: fields.value }));
const ready = computed(() => ({
  words: Boolean(form.title.trim()),
  buttons: !two.value || Boolean(choice.second.text.trim()),
} as Record<string, boolean>)[steps.value[step.value - 1]?.id] ?? true);
const chosen = computed(() => (choice.screens.length ? screens.value.filter((s) => choice.screens.includes(screenValue(s))) : screens.value.filter((s) => scr.canAlert(s))));
const chosenScreens = computed(() => choice.screens.length ? chosen.value.map((s) => s.name).join(", ") : t("editor.events.wizard.every_screen"));
// What the event means for the screens chosen: two buttons only from show_alert_choice's firmware, a picture only where
// the screen draws one, an action performed by the app.
const choiceFirmware = computed(() => alerts.value?.choice?.min_firmware || "0.3.3");
const actions = computed(() => [choice.first, ...(two.value ? [choice.second] : [])].filter((b) => b.entity && b.action).length);
const route = computed(() => alertRoute({ two: two.value, actions: actions.value, camera: Boolean(choice.camera) },
  chosen.value.map((s) => ({ name: s.name, choice: versionAtLeast(firmwareVersion(s), choiceFirmware.value), pictures: Boolean(s.pictures) }))));
const routeText = (note: { key: string; screens?: string[] }) => t(`editor.alerts.wizard.route.${note.key}`,
  { screens: note.screens?.join(", ") || "", event: alerts.value?.broadcast?.show || "esp_screens_show_alert", version: choiceFirmware.value });

// The card as the screen draws it: its colour, its icon, its words and its buttons, the second left of the first.
const colour = computed(() => alerts.value?.colors?.find((c) => c.name === form.color)?.color);
const iconCp = computed(() => alerts.value?.suggested_icons?.find((i) => i.name === form.icon)?.cp);
const hex = (value: number) => `#${value.toString(16).padStart(6, "0")}`;
// A button without a key colour keeps its own paint: the first the dark key (BUTTON_DARK), the second the light one (KEY).
const paint = (bg: string, ink: string) => ({ background: hex(theme.roles[bg].light), color: hex(theme.roles[ink].light) });
const keyStyle = (color: string, second = false) => {
  const k = theme.keys.find((key) => key.name === color);
  return k ? { background: hex(k.key), color: hex(k.text) } : second ? paint("KEY", "INK") : paint("BUTTON_DARK", "ON_ACCENT");
};

const { busy: trying, run: whileTrying } = useBusy();
const tried = ref("");
const tryIt = () => whileTrying(async () => {
  tried.value = "";
  try {
    const answer = await scr.sendTestAlert("all", { ...fields.value, ...(choice.camera ? { camera: choice.camera } : {}), ...(choice.screens.length ? { screen: choice.screens } : {}) });
    tried.value = answer.sent ? t("editor.alerts.try.sent_all", answer.sent) : t("editor.alerts.try.nothing", { version: alerts.value?.min_firmware || "0.2.31" });
  } catch (e: any) {
    tried.value = e.message;
  }
});

const { busy: saving, run: whileSaving } = useBusy();
const saved = ref<{ id: string } | null>(null);
const error = ref("");
const add = () => whileSaving(async () => {
  error.value = "";
  try { saved.value = await props.save(automation.value, saved.value?.id); } catch (e: any) { error.value = e.message; }
});
watch(() => props.open, (open) => {
  if (!open || !saved.value) return;
  Object.assign(form, fresh());
  Object.assign(choice, { trigger: "", camera: "", screens: [], count: "one", first: button(t("editor.alerts.example.button")), second: button(t("editor.alerts.wizard.buttons.second_example")) });
  saved.value = null; tried.value = ""; step.value = 1; finish.value = "automation";
});
</script>

<template>
  <UiWizard :open="open" :title="t('editor.alerts.wizard.title')" :steps="steps" v-model:step="step" :ready="ready" @update:open="(value) => emit('update:open', value)">
    <template #trigger>
      <TriggerStep id="alert-trigger" v-model="choice.trigger" />
    </template>
    <template #words>
      <div class="with-preview">
        <div class="fields">
          <div class="field"><label class="f-label" for="alert-title">{{ t("editor.alerts.try.title") }}</label><input id="alert-title" v-model="form.title" maxlength="64" /></div>
          <div class="field"><label class="f-label" for="alert-subtitle">{{ t("editor.alerts.try.subtitle") }}</label><input id="alert-subtitle" v-model="form.subtitle" maxlength="240" /></div>
        </div>
        <div class="alert-mock" aria-hidden="true"><div class="alert-mock-card" :style="colour ? { background: colour } : undefined">
          <span class="mdi alert-mock-icon">{{ iconCp ? glyph(iconCp) : "" }}</span><strong>{{ form.title }}</strong><span>{{ form.subtitle }}</span>
          <span class="mock-keys"><span v-if="two" class="mock-key" :style="keyStyle(choice.second.color, true)">{{ choice.second.text }}</span><span class="mock-key" :style="keyStyle(choice.first.color)">{{ choice.first.text || "OK" }}</span></span></div></div>
      </div>
    </template>
    <template #buttons>
      <div class="with-preview">
        <UiChoiceCards v-model="choice.count" :cards="counts" :label="t('editor.alerts.wizard.steps.buttons.title')" />
        <div class="alert-mock" aria-hidden="true"><div class="alert-mock-card" :style="colour ? { background: colour } : undefined">
          <span class="mdi alert-mock-icon">{{ iconCp ? glyph(iconCp) : "" }}</span><strong>{{ form.title }}</strong><span>{{ form.subtitle }}</span>
          <span class="mock-keys"><span v-if="two" class="mock-key" :style="keyStyle(choice.second.color, true)">{{ choice.second.text }}</span><span class="mock-key" :style="keyStyle(choice.first.color)">{{ choice.first.text || "OK" }}</span></span></div></div>
      </div>
      <div class="button-columns" :class="{ two }">
        <AlertButton v-if="two" v-model="choice.second" id="alert-button2" :label="t('editor.alerts.wizard.buttons.second')" />
        <AlertButton v-model="choice.first" id="alert-button" :label="two ? t('editor.alerts.wizard.buttons.first') : t('editor.alerts.wizard.buttons.only')" />
      </div>
    </template>
    <template #look>
      <div class="with-preview">
        <div class="fields">
          <span class="f-label">{{ t("editor.alerts.try.icon") }}</span>
          <div class="icon-grid">
            <button v-for="icon in (alerts?.suggested_icons || []).slice(0, 14)" :key="icon.name" type="button" class="icon-pick mdi" :aria-pressed="form.icon === icon.name ? 'true' : 'false'" :title="icon.name" @click="form.icon = icon.name">{{ glyph(icon.cp) }}</button>
          </div>
          <span class="f-label">{{ t("editor.alerts.try.color") }}</span>
          <div class="swatches">
            <button type="button" class="swatch white" :aria-pressed="!form.color ? 'true' : 'false'" :title="t('editor.alerts.white')" @click="form.color = ''" />
            <button v-for="c in alerts?.colors || []" :key="c.name" type="button" class="swatch" :style="{ background: c.color }" :aria-pressed="form.color === c.name ? 'true' : 'false'" :title="c.label" @click="form.color = c.name" />
          </div>
          <span class="f-label">{{ t("editor.alerts.wizard.camera") }}</span>
          <div class="pick-row">
            <UiPicker id="alert-camera" :items="cameras" :placeholder="t('editor.plugin_tile.search')" :empty="t('editor.doorbell.no_camera')" width="var(--reka-popover-trigger-width)" @pick="(id: string) => (choice.camera = id)">
              <template #trigger><button type="button" class="ghost-btn wide-pick"><Icon name="magnify" />{{ choice.camera ? nameOf(choice.camera) : t("editor.alerts.wizard.no_camera") }}</button></template>
            </UiPicker>
            <button v-if="choice.camera" type="button" class="btn quiet mini" @click="choice.camera = ''"><Icon name="close" /></button>
          </div>
          <label class="switch-row" for="alert-flash"><UiSwitch id="alert-flash" v-model="form.flash" /><span>{{ t("editor.alerts.try.flash") }}<small>{{ t("editor.alerts.try.flash_hint") }}</small></span></label>
        </div>
        <div class="alert-mock" aria-hidden="true"><div class="alert-mock-card" :style="colour ? { background: colour } : undefined">
          <span class="mdi alert-mock-icon">{{ iconCp ? glyph(iconCp) : "" }}</span><strong>{{ form.title }}</strong><span>{{ form.subtitle }}</span>
          <span class="mock-keys"><span v-if="two" class="mock-key" :style="keyStyle(choice.second.color, true)">{{ choice.second.text }}</span><span class="mock-key" :style="keyStyle(choice.first.color)">{{ choice.first.text || "OK" }}</span></span></div></div>
      </div>
    </template>
    <template #screens>
      <div class="screen-rows">
        <CheckRow v-for="screen in screens" :key="screen.id" :checked="choice.screens.includes(screenValue(screen))" :disabled="!scr.canAlert(screen)" @toggle="toggle(screenValue(screen))">
          <span class="screen-row"><strong>{{ screen.name }}</strong><small>{{ scr.canAlert(screen) ? (screen.pictures ? t("editor.alerts.wizard.with_picture") : t("editor.alerts.wizard.without_picture")) : t("editor.alerts.screens.unknown") }}</small></span>
        </CheckRow>
      </div>
      <p class="hint">{{ t("editor.alerts.wizard.screens_hint") }}</p>
      <div class="field"><label class="f-label" for="alert-timeout">{{ t("editor.alerts.try.timeout") }}</label><input id="alert-timeout" v-model.number="form.timeout" type="number" min="0" max="86400" /></div>
    </template>
    <template #try>
      <button type="button" class="btn primary big-action" id="alert-try" :disabled="trying" @click="tryIt"><span class="mdi">{{ iconCp ? glyph(iconCp) : "" }}</span>{{ trying ? t("editor.alerts.try.sending") : t("editor.alerts.try.send") }}</button>
      <p class="status-line" id="alert-try-result" role="status">{{ tried }}</p>
      <p v-if="actions" class="hint" id="alert-try-action">{{ t("editor.alerts.wizard.try_action") }}</p>
    </template>
    <template #add>
      <WizardFinish v-model="finish" id="alerts" :automation="automation" :trigger="choice.trigger" :saved="saved" :error="error">
        <template #summary>
          <dl class="summary">
            <template v-if="choice.trigger"><dt>{{ t("editor.events.wizard.summary.starts") }}</dt><dd>{{ nameOf(choice.trigger) }} · {{ t(`editor.events.wizard.kind.${triggerKind(choice.trigger) || 'event'}`) }}</dd></template>
            <dt>{{ t("editor.alerts.wizard.summary.says") }}</dt><dd>{{ form.title }}<template v-if="form.subtitle"> · {{ form.subtitle }}</template></dd>
            <dt>{{ t("editor.alerts.wizard.summary.buttons") }}</dt>
            <dd><span v-for="(b, i) in two ? [choice.second, choice.first] : [choice.first]" :key="i">{{ b.text || "OK" }}: {{ b.entity && b.action ? `${b.action} · ${nameOf(b.entity)}` : t("editor.alerts.wizard.buttons.closes") }}</span></dd>
            <dt>{{ t("editor.events.wizard.summary.screens") }}</dt><dd>{{ chosenScreens }}</dd>
            <dt>{{ t("editor.events.wizard.summary.title") }}</dt><dd>{{ automation.alias }}</dd>
          </dl>
        </template>
        <template #notes>
          <ul class="route" id="alert-route">
            <li v-for="note in route" :key="note.key" :data-note="note.key">{{ routeText(note) }}</li>
          </ul>
        </template>
      </WizardFinish>
    </template>
    <template #footer="{ last }">
      <template v-if="last">
        <button v-if="saved" type="button" class="btn primary" @click="emit('update:open', false)">{{ t("editor.events.wizard.done") }}</button>
        <button v-else-if="finish === 'action'" type="button" class="btn primary" id="alert-copy-action" @click="ui.copyText(actionYaml(automation.actions[0]), undefined, 'yaml')">{{ t("editor.events.wizard.finish.copy") }}</button>
        <button v-else type="button" class="btn primary" id="alert-install" :disabled="saving || !choice.trigger" @click="add">{{ saving ? t("editor.events.install.saving") : t("editor.events.install.add") }}</button>
      </template>
    </template>
  </UiWizard>
</template>

<style scoped>
.with-preview { display: grid; grid-template-columns: minmax(0, 1fr) 240px; gap: 16px; align-items: start; }
.fields { display: grid; gap: 10px; }
.button-columns { display: grid; gap: 18px; }
.button-columns.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.alert-mock-card > .mock-keys { position: absolute; right: 10px; bottom: 10px; display: flex; gap: 6px; font-size: 12px; }
.mock-key { padding: 6px 14px; border-radius: 999px; }
.icon-grid { display: flex; flex-wrap: wrap; gap: 6px; }
.icon-pick { width: 36px; height: 36px; border-radius: 10px; border: 1px solid var(--line); background: var(--surface); color: var(--ink); font-size: 18px; cursor: pointer; }
.icon-pick[aria-pressed="true"] { border-color: var(--accent); background: var(--accent-soft); color: var(--accent); }
.swatches { display: flex; flex-wrap: wrap; gap: 8px; }
.swatch { width: 28px; height: 28px; border-radius: 50%; border: 1px solid var(--line); cursor: pointer; }
.swatch.white { background: var(--surface); }
.swatch[aria-pressed="true"] { box-shadow: 0 0 0 2px var(--surface), 0 0 0 4px var(--accent); }
.pick-row { display: flex; align-items: center; gap: 8px; }
.wide-pick { flex: 1; justify-content: flex-start; }
.switch-row { display: flex; align-items: center; gap: 10px; cursor: pointer; }
.switch-row > span { display: grid; }
.switch-row small { color: var(--muted); font-size: 12px; }
.screen-rows { display: grid; gap: 6px; }
.screen-row { display: grid; gap: 2px; text-align: left; }
.screen-row small { color: var(--muted); font-size: 12px; }
.big-action { justify-self: start; display: inline-flex; align-items: center; gap: 8px; padding: 12px 20px; font-size: 14px; }
.summary { display: grid; grid-template-columns: max-content 1fr; gap: 8px 16px; margin: 0; font-size: 13.5px; }
.summary dt { color: var(--muted); }
.summary dd { margin: 0; overflow-wrap: anywhere; display: grid; gap: 2px; }
.route { margin: 0; padding-left: 18px; display: grid; gap: 4px; color: var(--muted); font-size: 12.5px; line-height: 1.5; }
@media (max-width: 640px) { .with-preview, .button-columns.two { grid-template-columns: minmax(0, 1fr); } }
</style>
