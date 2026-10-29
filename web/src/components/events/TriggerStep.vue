<script setup lang="ts">
// A wizard's step "what starts it" (Events): the ones Home Assistant says fit best first, as cards (`suggestions`, such
// as its doorbells), and any other entity of the person's own that can start an automation (model/automation.ts
// triggerKind: an event entity, a sensor, switch or helper that turns on, a button) in a searchable list. Under it, in
// words, how the automation will read it, so a boolean, a doorbell's event or a button each say what they do.
import { computed, ref } from "vue";
import { t } from "../../i18n";
import { triggerKind, type TriggerKind } from "../../model/automation";
import { useInventoryStore } from "../../stores/inventory";
import Icon from "../ui/Icon.vue";
import UiChoiceCards from "../ui/UiChoiceCards.vue";
import UiPicker from "../ui/UiPicker.vue";

export type Suggestion = { trigger: string; kind: TriggerKind; name: string; detail?: string };
const OTHER = "__other";
const props = defineProps<{ modelValue: string; suggestions?: Suggestion[]; domains?: Record<string, TriggerKind>; mark?: string; id: string }>();
const emit = defineEmits<{ "update:modelValue": [entity: string]; suggest: [suggestion: Suggestion] }>();
const inv = useInventoryStore();
const known = computed(() => Object.fromEntries((props.suggestions || []).map((s) => [s.trigger, s.kind])));
const entities = computed(() => (inv.inventory.entities || []).filter((e) => triggerKind(e.id, known.value, props.domains))
  .map((e) => ({ id: e.id, name: e.name || e.id, hint: [e.area, e.id].filter(Boolean).join(" · ") })));
const nameOf = (id: string) => (inv.inventory.entities || []).find((e) => e.id === id)?.name || id;
const kind = computed(() => (props.modelValue ? triggerKind(props.modelValue, known.value, props.domains) : null));
// The cards: the suggestions and "something else", which opens the list.
const other = ref(!props.suggestions?.length || Boolean(props.modelValue && !props.suggestions?.some((s) => s.trigger === props.modelValue)));
const cards = computed(() => [
  ...(props.suggestions || []).map((s) => ({ value: s.trigger, title: s.name, detail: s.detail || s.trigger, glyph: props.mark })),
  { value: OTHER, title: t("editor.events.wizard.other"), detail: t("editor.events.wizard.other_detail") },
]);
const picked = computed(() => (other.value ? OTHER : props.modelValue));
function choose(value: string) {
  if (value === OTHER) { other.value = true; return; }
  other.value = false;
  emit("update:modelValue", value);
  const s = props.suggestions?.find((item) => item.trigger === value);
  if (s) emit("suggest", s);
}
// What kind of entity it is, in words, for the line under it: a switch and a helper read "turns on" as a sensor does.
const domain = computed(() => props.modelValue.split(".", 1)[0]);
</script>

<template>
  <div class="trigger-step">
    <UiChoiceCards v-if="suggestions?.length" :model-value="picked" :cards="cards" :label="t('editor.events.wizard.suggested')" @update:model-value="choose" />
    <div v-if="other || !suggestions?.length" class="trigger-row">
      <UiPicker :id="id" :items="entities" :placeholder="t('editor.plugin_tile.search')" :empty="t('editor.events.wizard.none')" width="var(--reka-popover-trigger-width)"
        @pick="(entity: string) => emit('update:modelValue', entity)">
        <template #trigger><button type="button" class="ghost-btn trigger-pick"><Icon name="magnify" />{{ modelValue ? nameOf(modelValue) : t("editor.events.wizard.pick_trigger") }}</button></template>
      </UiPicker>
    </div>
    <div v-if="kind" class="understood" :id="`${id}-kind`" :data-kind="kind">
      <Icon name="check" />
      <span><b>{{ t(`editor.events.wizard.kind.${kind}`) }}</b><small><template v-if="nameOf(modelValue) !== modelValue">{{ nameOf(modelValue) }} · </template><code>{{ modelValue }}</code><template v-if="kind === 'on'"> · {{ t(`editor.events.wizard.domain.${domain}`) }}</template></small></span>
    </div>
  </div>
</template>

<style scoped>
.trigger-step { display: grid; gap: 10px; }
.trigger-pick { width: 100%; justify-content: flex-start; }
.understood { display: flex; gap: 10px; align-items: flex-start; padding: 10px 12px; border-radius: 10px; background: var(--accent-soft); color: var(--ink); }
.understood > span { display: grid; gap: 2px; }
.understood small { color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }
</style>
