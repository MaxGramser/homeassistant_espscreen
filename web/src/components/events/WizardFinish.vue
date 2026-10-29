<script setup lang="ts">
// The last step of a wizard of Events (DoorbellWizard, AlertWizard): two ways to finish. "Create the automation" puts the
// whole automation into Home Assistant (the wizard's Add, "Tessera: <name>"); "Use it in an automation of your own" gives
// only its action, the event with its fields, as YAML to paste into an action of an automation the person already has
// (Edit in YAML). The wizard's footer does what the way chosen asks; this shows what it will be.
import { computed } from "vue";
import { automationLink } from "../../composables/useAutomations";
import { t } from "../../i18n";
import { actionYaml, automationYaml, type Automation } from "../../model/automation";
import Icon from "../ui/Icon.vue";
import UiChoiceCards from "../ui/UiChoiceCards.vue";

export type Finish = "automation" | "action";
const props = defineProps<{ modelValue: Finish; automation: Automation; trigger: string; saved: { id: string } | null; error: string; id: string }>();
const emit = defineEmits<{ "update:modelValue": [value: Finish] }>();
const cards = computed(() => [
  { value: "automation", title: t("editor.events.wizard.finish.automation"),
    detail: props.trigger ? t("editor.events.wizard.finish.automation_detail") : t("editor.events.wizard.finish.needs_trigger") },
  { value: "action", title: t("editor.events.wizard.finish.action"), detail: t("editor.events.wizard.finish.action_detail") },
]);
const action = computed(() => actionYaml(props.automation.actions[0] || {}));
const whole = computed(() => automationYaml(props.automation));
</script>

<template>
  <div class="finish">
    <UiChoiceCards v-if="!saved" :model-value="modelValue" :cards="cards" :label="t('editor.events.wizard.finish.label')" @update:model-value="(value) => emit('update:modelValue', value as Finish)" />
    <template v-if="modelValue === 'automation'">
      <slot v-if="!saved" name="summary" />
      <div v-else class="saved" :id="`${id}-saved`">
        <Icon name="check" /><span class="saved-text"><b>{{ t("editor.events.install.saved") }}</b><small>{{ t("editor.events.install.hint", { title: automation.alias }) }}</small></span>
        <a class="btn quiet mini" :href="automationLink(saved.id)" target="_top">{{ t("editor.events.install.open") }}</a>
      </div>
      <details class="yaml-details">
        <summary>{{ t("editor.events.wizard.yaml") }}</summary>
        <pre :id="`${id}-automation-yaml`">{{ whole }}</pre>
      </details>
    </template>
    <template v-else>
      <pre class="action-yaml" :id="`${id}-action-yaml`">{{ action }}</pre>
      <p class="hint">{{ t("editor.events.wizard.finish.paste") }}</p>
    </template>
    <slot name="notes" />
    <p v-if="error" class="status-line error" role="alert">{{ error }}</p>
  </div>
</template>

<style scoped>
.finish { display: grid; gap: 12px; }
.action-yaml { margin: 0; max-height: 220px; overflow: auto; }
.saved { display: flex; align-items: center; gap: 10px; padding: 12px 14px; border-radius: 12px; background: var(--accent-soft); }
.saved-text { display: grid; gap: 2px; flex: 1; min-width: 0; }
.saved small { color: var(--muted); }
.yaml-details summary { cursor: pointer; color: var(--muted); font-size: 13px; }
.yaml-details pre { margin: 8px 0 0; max-height: 220px; overflow: auto; }
.status-line.error { color: var(--danger); }
</style>
