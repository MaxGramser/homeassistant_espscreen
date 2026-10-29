<script setup lang="ts">
// One button of an alert in its wizard (AlertWizard): its words, its colour (a key colour of theme.h's KEY_SWATCHES, or
// the button's own paint) and what it does when pressed: nothing but closing the alert, or one of Home Assistant's own
// actions for an entity the person picks (entity-actions, the actions Home Assistant offers for that entity, as a
// tile's Perform action lists them). The app performs it once, from whichever screen it is pressed on.
import { computed, watch } from "vue";
import { t } from "../../i18n";
import type { AlertButtonChoice } from "../../model/alert-yaml";
import { useEntitiesStore } from "../../stores/entities";
import { useInventoryStore } from "../../stores/inventory";
import Icon from "../ui/Icon.vue";
import UiPicker from "../ui/UiPicker.vue";
import theme from "virtual:esp-screens-theme";

const props = defineProps<{ modelValue: AlertButtonChoice; id: string; label: string; maxlength?: number }>();
const emit = defineEmits<{ "update:modelValue": [value: AlertButtonChoice] }>();
const inv = useInventoryStore();
const entities = useEntitiesStore();
const set = (part: Partial<AlertButtonChoice>) => emit("update:modelValue", { ...props.modelValue, ...part });
const hex = (value: number) => `#${value.toString(16).padStart(6, "0")}`;

// Entities that only report (a sensor, a camera, a zone) have nothing to do; everything else is offered.
const READ_ONLY = new Set(["sensor", "binary_sensor", "event", "camera", "image", "zone", "sun", "person", "device_tracker", "weather", "calendar"]);
const items = computed(() => (inv.inventory.entities || []).filter((e) => !READ_ONLY.has(e.id.split(".", 1)[0]))
  .map((e) => ({ id: e.id, name: e.name || e.id, hint: [e.area, e.id].filter(Boolean).join(" · ") })));
const nameOf = (id: string) => (inv.inventory.entities || []).find((e) => e.id === id)?.name || id;
// The entity's own actions that need nothing but the entity (Home Assistant's generic ones and those asking for more left out).
const actions = computed(() => {
  const entity = props.modelValue.entity;
  if (!entity) return [];
  const domain = entity.split(".", 1)[0];
  return (entities.entityActions[entity] || []).filter((a) => a.action.startsWith(`${domain}.`) && !a.fields.some((f) => f.required));
});
watch(() => props.modelValue.entity, (entity) => { if (entity) entities.loadEntityActions(entity); }, { immediate: true });
// The first of its actions until the person picks another.
watch(actions, (list) => { if (list.length && !list.some((a) => a.action === props.modelValue.action)) set({ action: list[0].action }); });
</script>

<template>
  <section class="alert-button" :id="id" :aria-label="label">
    <header class="button-head">{{ label }}</header>
    <div class="field"><label class="f-label" :for="`${id}-text`">{{ t("editor.alerts.try.button") }}</label>
      <input :id="`${id}-text`" :value="modelValue.text" :maxlength="maxlength ?? 16" @input="set({ text: ($event.target as HTMLInputElement).value })" /></div>
    <div class="field"><span class="f-label">{{ t("editor.alerts.wizard.buttons.color") }}</span>
      <div class="keys">
        <button type="button" class="key plain" :aria-pressed="!modelValue.color ? 'true' : 'false'" :title="t('editor.alerts.wizard.buttons.own_color')" @click="set({ color: '' })" />
        <button v-for="k in theme.keys" :key="k.name" type="button" class="key" :style="{ background: hex(k.key) }" :aria-pressed="modelValue.color === k.name ? 'true' : 'false'" :title="k.name" @click="set({ color: k.name })" />
      </div></div>
    <div class="field"><span class="f-label">{{ t("editor.alerts.wizard.buttons.does") }}</span>
      <div class="does">
        <UiPicker :id="`${id}-entity`" :items="items" :placeholder="t('editor.plugin_tile.search')" :empty="t('editor.events.wizard.none')" width="var(--reka-popover-trigger-width)"
          @pick="(entity: string) => set({ entity, action: '' })">
          <template #trigger><button type="button" class="ghost-btn wide-pick"><Icon name="magnify" />{{ modelValue.entity ? nameOf(modelValue.entity) : t("editor.alerts.wizard.buttons.only_close") }}</button></template>
        </UiPicker>
        <button v-if="modelValue.entity" type="button" class="btn quiet mini" :title="t('editor.alerts.wizard.buttons.only_close')" @click="set({ entity: '', action: '' })"><Icon name="close" /></button>
      </div>
      <div v-if="actions.length" class="actions" role="radiogroup">
        <button v-for="a in actions" :key="a.action" type="button" class="action-chip" role="radio" :aria-checked="modelValue.action === a.action ? 'true' : 'false'" :title="a.description" @click="set({ action: a.action })">{{ a.name }}</button>
      </div>
      <small v-else-if="modelValue.entity && entities.entityActions[modelValue.entity]" class="hint">{{ t("editor.alerts.wizard.buttons.no_actions") }}</small>
    </div>
  </section>
</template>

<style scoped>
.alert-button { display: grid; gap: 12px; align-content: start; padding: 14px; border: 1px solid var(--line); border-radius: 12px; background: var(--surface); min-width: 0; }
.button-head { font-size: 13px; font-weight: 600; color: var(--ink); }
.keys { display: flex; flex-wrap: wrap; gap: 6px; }
.key { width: 22px; height: 22px; border-radius: 50%; border: 1px solid var(--line); cursor: pointer; padding: 0; }
.key.plain { background: var(--surface-2); }
.key[aria-pressed="true"] { box-shadow: 0 0 0 2px var(--surface), 0 0 0 4px var(--accent); }
.does { display: flex; align-items: center; gap: 8px; }
.wide-pick { flex: 1; justify-content: flex-start; }
.actions { display: flex; flex-wrap: wrap; gap: 6px; }
.action-chip { border: 1px solid var(--line); background: var(--surface); color: var(--ink); border-radius: 999px; padding: 5px 11px; font: inherit; font-size: 12.5px; cursor: pointer; }
.action-chip[aria-checked="true"] { border-color: var(--accent); background: var(--accent-soft); color: var(--accent); }
</style>
