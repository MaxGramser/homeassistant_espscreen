<script setup lang="ts">
// The doorbell's wizard (Events, Doorbell; docs/DOORBELL.md): what rings, its camera, its door, the screens, a name, then a ring now
// to see it and the automation into Home Assistant, "Tessera: Doorbell <name>". One step at a time in UiWizard; what is
// chosen stays while the window is open, and the page lists the automation once it is saved. The last step also offers
// the action alone, for an automation of the person's own (WizardFinish); then what rings may stay empty.
import { computed, reactive, ref, watch } from "vue";
import { useBusy } from "../../composables/useBusy";
import { t } from "../../i18n";
import { screenValue } from "../../model/alert-yaml";
import { actionYaml } from "../../model/automation";
import { doorbellAutomation, doorFields, triggerKind, type DoorChoice, type DoorbellKind, type DoorbellReference } from "../../model/doorbell-yaml";
import { glyph } from "../../model/topbar";
import { useInventoryStore } from "../../stores/inventory";
import { useScreenStore } from "../../stores/screen";
import { useUiStore } from "../../stores/ui";
import CheckRow from "../ui/CheckRow.vue";
import Icon from "../ui/Icon.vue";
import UiChoiceCards from "../ui/UiChoiceCards.vue";
import UiPicker from "../ui/UiPicker.vue";
import UiSelect from "../ui/UiSelect.vue";
import UiWizard from "../ui/UiWizard.vue";
import DoorStep from "./DoorStep.vue";
import TriggerStep, { type Suggestion } from "./TriggerStep.vue";
import WizardFinish, { type Finish } from "./WizardFinish.vue";

const props = defineProps<{ open: boolean; save: (automation: ReturnType<typeof doorbellAutomation>, id?: string | null) => Promise<{ id: string }> }>();
const emit = defineEmits<{ "update:open": [open: boolean] }>();
const inv = useInventoryStore();
const scr = useScreenStore();
const ui = useUiStore();
const reference = computed(() => inv.inventory.doorbell as DoorbellReference | undefined);
const entities = computed(() => inv.inventory.entities || []);
const nameOf = (id: string) => entities.value.find((e) => e.id === id)?.name || id;
const cameras = computed(() => entities.value.filter((e) => e.id.startsWith("camera.")).map((e) => ({ id: e.id, name: e.name || e.id, hint: [e.area, e.id].filter(Boolean).join(" · ") })));
const screens = computed(() => inv.inventory.screens.filter((s) => !s.virtual));
const kindOf = (screen: { doorbell?: DoorbellKind }) => screen.doorbell || "plain";
const suggestions = computed<(Suggestion & { camera: string | null })[]>(() => (reference.value?.suggestions || [])
  .map((s) => ({ ...s, detail: [s.trigger, s.camera].filter(Boolean).join(" · ") })));

const steps = computed(() => ["rings", "camera", "door", "screens", "name", "try", "add"].map((id) => ({
  id, title: t(`editor.doorbell.wizard.steps.${id}.title`), help: t(`editor.doorbell.wizard.steps.${id}.help`) })));
const step = ref(1);
const finish = ref<Finish>("automation");
// At the last step without anything that starts it, the action alone is what fits.
watch(step, (now) => { if (now === steps.value.length && !choice.trigger && !saved.value) finish.value = "action"; });
const noDoor = (): DoorChoice => ({ kind: "none" });
// A missed ring stays in the top bars for a while (the add-on's choices; a new automation gets half an hour).
const keepNew = () => reference.value?.keep?.new ?? 30;
const keepChoices = computed(() => (reference.value?.keep?.choices ?? [10, 30, 60, 240, 0]).map((n) => [n,
  n === 0 ? t("editor.doorbell.wizard.keep.open") : n % 60 === 0 ? t("editor.doorbell.wizard.keep.hours", { n: n / 60 })
    : t("editor.doorbell.wizard.keep.minutes", { n })] as const));
const choice = reactive({ trigger: "", camera: "", screens: [] as string[], title: "", timeout: undefined as number | undefined, door: noDoor(), sound: true, chime: true, keep: keepNew() });
// Sound on or off when it rings is a choice only where a screen it reaches can play it: one that shows the ring live and
// has a speaker (its capability record). Without one the choice is not offered, and the automation leaves it out.
const reached = computed(() => choice.screens.length ? screens.value.filter((s) => choice.screens.includes(screenValue(s))) : screens.value);
const plays = computed(() => reached.value.some((s) => kindOf(s) === "view" && s.caps?.speaker));
function suggest(s: Suggestion) {
  const camera = suggestions.value.find((item) => item.trigger === s.trigger)?.camera;
  if (camera) choice.camera = camera;
}
const cameraCards = computed(() => cameras.value.slice(0, 4).map((c) => ({ value: c.id, title: c.name, detail: c.hint, glyph: glyph("F07AE") })));
const toggle = (value: string) => { choice.screens = choice.screens.includes(value) ? choice.screens.filter((v) => v !== value) : [...choice.screens, value]; };
const automation = computed(() => doorbellAutomation(reference.value, { ...choice, sound: plays.value ? choice.sound : undefined,
  chime: plays.value ? choice.chime : undefined, name: choice.camera ? nameOf(choice.camera) : "" }));
// A door step is ready without a door, with a lock picked, or with an entity and one of its actions.
const doorReady = computed(() => choice.door.kind === "none" || Object.keys(doorFields(choice.door)).length > 0);
const ready = computed(() => ({ camera: Boolean(choice.camera), door: doorReady.value } as Record<string, boolean>)[steps.value[step.value - 1]?.id] ?? true);
const doorSummary = computed(() => choice.door.kind === "lock" && choice.door.lock ? nameOf(choice.door.lock)
  : choice.door.kind === "action" && choice.door.entity ? `${nameOf(choice.door.entity)} · ${choice.door.action}` : t("editor.doorbell.wizard.door.none"));
const chosenScreens = computed(() => choice.screens.length ? screens.value.filter((s) => choice.screens.includes(screenValue(s))).map((s) => s.name).join(", ") : t("editor.events.wizard.every_screen"));

// A ring now, as the automation would send it.
const { busy: trying, run: whileTrying } = useBusy();
const tried = ref("");
const tryIt = () => whileTrying(async () => {
  tried.value = "";
  try {
    const answer = await scr.sendTestDoorbell("", { camera: choice.camera, title: choice.title, timeout: choice.timeout || undefined,
      ...(choice.screens.length ? { screen: choice.screens } : {}), ...doorFields(choice.door), ...(plays.value && !choice.sound ? { sound: false } : {}),
      ...(plays.value && !choice.chime ? { chime: false } : {}), ...(choice.keep ? { keep_minutes: choice.keep } : {}) });
    tried.value = answer.sent || answer.alerts
      ? [answer.sent ? t("editor.doorbell.try.views", answer.sent) : "", answer.alerts ? t("editor.doorbell.try.alerts", answer.alerts) : ""].filter(Boolean).join(" ")
      : t("editor.doorbell.try.nothing");
  } catch (e: any) {
    tried.value = e.message;
  }
});

// Into Home Assistant: a new automation, or the same one again after a change.
const { busy: saving, run: whileSaving } = useBusy();
const saved = ref<{ id: string } | null>(null);
const error = ref("");
const add = () => whileSaving(async () => {
  error.value = "";
  try { saved.value = await props.save(automation.value, saved.value?.id); } catch (e: any) { error.value = e.message; }
});
// A new wizard starts afresh once the last one was added.
watch(() => props.open, (open) => { if (open && saved.value) { Object.assign(choice, { trigger: "", camera: "", screens: [], title: "", timeout: undefined, door: noDoor(), sound: true, chime: true, keep: keepNew() }); saved.value = null; tried.value = ""; step.value = 1; finish.value = "automation"; } });
</script>

<template>
  <UiWizard :open="open" :title="t('editor.doorbell.wizard.title')" :steps="steps" v-model:step="step" :ready="ready" @update:open="(value) => emit('update:open', value)">
    <template #rings>
      <TriggerStep id="doorbell-trigger" v-model="choice.trigger" :suggestions="suggestions" :domains="reference?.trigger_domains" :mark="glyph('F12E6')" @suggest="suggest" />
    </template>
    <template #camera>
      <UiChoiceCards v-if="cameraCards.length" :model-value="choice.camera" :cards="cameraCards" :label="t('editor.doorbell.wizard.steps.camera.title')" @update:model-value="(id) => (choice.camera = id)" />
      <UiPicker v-if="cameras.length > 4 || !cameras.length" id="doorbell-camera" :items="cameras" :placeholder="t('editor.plugin_tile.search')" :empty="t('editor.doorbell.no_camera')" width="var(--reka-popover-trigger-width)" @pick="(id: string) => (choice.camera = id)">
        <template #trigger><button type="button" class="ghost-btn wide-pick"><Icon name="magnify" />{{ choice.camera && !cameraCards.some((c) => c.value === choice.camera) ? nameOf(choice.camera) : t("editor.doorbell.wizard.more_cameras") }}</button></template>
      </UiPicker>
      <p class="hint">{{ t("editor.doorbell.wizard.camera_hint") }}</p>
    </template>
    <template #door>
      <DoorStep v-model="choice.door" />
    </template>
    <template #screens>
      <div class="screen-rows">
        <CheckRow v-for="screen in screens" :key="screen.id" :checked="choice.screens.includes(screenValue(screen))" @toggle="toggle(screenValue(screen))">
          <span class="screen-row"><strong>{{ screen.name }}</strong><small :data-kind="kindOf(screen)">{{ t(`editor.doorbell.screens.${kindOf(screen)}`) }}</small></span>
        </CheckRow>
      </div>
      <p class="hint">{{ t("editor.doorbell.wizard.screens_hint") }}</p>
      <template v-if="plays">
        <CheckRow id="doorbell-chime" :checked="choice.chime" @toggle="choice.chime = !choice.chime">
          <span class="screen-row"><strong>{{ t("editor.doorbell.wizard.chime.label") }}</strong><small>{{ t("editor.doorbell.wizard.chime.hint") }}</small></span>
        </CheckRow>
        <CheckRow id="doorbell-sound" :checked="choice.sound" @toggle="choice.sound = !choice.sound">
          <span class="screen-row"><strong>{{ t("editor.doorbell.wizard.sound.label") }}</strong><small>{{ t("editor.doorbell.wizard.sound.hint") }}</small></span>
        </CheckRow>
      </template>
    </template>
    <template #name>
      <div class="field"><label class="f-label" for="doorbell-title">{{ t("editor.doorbell.fields.title") }}</label>
        <input id="doorbell-title" v-model="choice.title" maxlength="60" :placeholder="choice.camera ? nameOf(choice.camera) : ''" /></div>
      <div class="field"><label class="f-label" for="doorbell-timeout">{{ t("editor.doorbell.fields.timeout") }}</label>
        <input id="doorbell-timeout" v-model.number="choice.timeout" type="number" :min="reference?.timeout?.min ?? 10" :max="reference?.timeout?.max ?? 600" :placeholder="String(reference?.timeout?.default ?? 60)" />
        <small class="hint">{{ t("editor.doorbell.wizard.timeout_hint") }}</small></div>
      <div class="field"><label class="f-label" for="doorbell-keep">{{ t("editor.doorbell.fields.keep") }}</label>
        <UiSelect id="doorbell-keep" v-model="choice.keep" :options="keepChoices" />
        <small class="hint">{{ t("editor.doorbell.wizard.keep.hint") }}</small></div>
    </template>
    <template #try>
      <button type="button" class="btn primary big-action" id="doorbell-try" :disabled="trying" @click="tryIt"><span class="mdi">{{ glyph("F12E6") }}</span>{{ trying ? t("editor.alerts.try.sending") : t("editor.doorbell.try.send") }}</button>
      <p class="status-line" id="doorbell-try-result" role="status">{{ tried }}</p>
      <p class="hint">{{ t("editor.doorbell.wizard.limits") }}</p>
    </template>
    <template #add>
      <WizardFinish v-model="finish" id="doorbell" :automation="automation" :trigger="choice.trigger" :saved="saved" :error="error">
        <template #summary>
          <dl class="summary">
            <template v-if="choice.trigger"><dt>{{ t("editor.events.wizard.summary.starts") }}</dt><dd>{{ nameOf(choice.trigger) }} · {{ t(`editor.events.wizard.kind.${triggerKind(reference, choice.trigger) || 'event'}`) }}</dd></template>
            <dt>{{ t("editor.doorbell.wizard.summary.camera") }}</dt><dd>{{ nameOf(choice.camera) }}</dd>
            <dt>{{ t("editor.doorbell.wizard.summary.door") }}</dt><dd>{{ doorSummary }}</dd>
            <dt>{{ t("editor.events.wizard.summary.screens") }}</dt><dd>{{ chosenScreens }}</dd>
            <dt>{{ t("editor.events.wizard.summary.title") }}</dt><dd>{{ automation.alias }}</dd>
          </dl>
        </template>
      </WizardFinish>
    </template>
    <template #footer="{ last }">
      <template v-if="last">
        <button v-if="saved" type="button" class="btn primary" @click="emit('update:open', false)">{{ t("editor.events.wizard.done") }}</button>
        <button v-else-if="finish === 'action'" type="button" class="btn primary" id="doorbell-copy-action" @click="ui.copyText(actionYaml(automation.actions[0]), undefined, 'yaml')">{{ t("editor.events.wizard.finish.copy") }}</button>
        <button v-else type="button" class="btn primary" id="doorbell-install" :disabled="saving || !choice.trigger" @click="add">{{ saving ? t("editor.events.install.saving") : t("editor.events.install.add") }}</button>
      </template>
    </template>
  </UiWizard>
</template>

<style scoped>
.wide-pick { width: 100%; justify-content: flex-start; }
.screen-rows { display: grid; gap: 6px; }
.screen-row { display: grid; gap: 2px; text-align: left; }
.screen-row small { color: var(--muted); font-size: 12px; }
.screen-row small[data-kind="view"] { color: var(--accent); }
.big-action { justify-self: start; display: inline-flex; align-items: center; gap: 8px; padding: 12px 20px; font-size: 14px; }
.summary { display: grid; grid-template-columns: max-content 1fr; gap: 8px 16px; margin: 0; font-size: 13.5px; }
.summary dt { color: var(--muted); }
.summary dd { margin: 0; overflow-wrap: anywhere; }
</style>
