<script setup lang="ts">
// The doorbell wizard's door (DoorbellWizard; docs/DOORBELL.md, "Open the door"): no door key, a lock, or another action.
// A lock is unlocked after a second tap on the ring's view; another action is one of Home Assistant's own for an entity
// the person picks (entity-actions, as an alert's button offers them), such as a script or a gate's button. The app
// performs either; a lock that asks for a code gets its key only with a default code in Home Assistant, and this says so.
import { computed, watch } from "vue";
import { t } from "../../i18n";
import type { DoorChoice } from "../../model/doorbell-yaml";
import { glyph } from "../../model/topbar";
import { useEntitiesStore } from "../../stores/entities";
import { useInventoryStore } from "../../stores/inventory";
import Icon from "../ui/Icon.vue";
import UiChoiceCards from "../ui/UiChoiceCards.vue";
import UiPicker from "../ui/UiPicker.vue";

const props = defineProps<{ modelValue: DoorChoice }>();
const emit = defineEmits<{ "update:modelValue": [value: DoorChoice] }>();
const inv = useInventoryStore();
const entities = useEntitiesStore();
const set = (part: Partial<DoorChoice>) => emit("update:modelValue", { ...props.modelValue, ...part });
const all = computed(() => inv.inventory.entities || []);
const nameOf = (id: string) => all.value.find((e) => e.id === id)?.name || id;
const item = (e: { id: string; name?: string; area?: string }) => ({ id: e.id, name: e.name || e.id, hint: [e.area, e.id].filter(Boolean).join(" · ") });

const cards = computed(() => [
  { value: "none", title: t("editor.doorbell.wizard.door.none"), glyph: glyph("F0156") },
  { value: "lock", title: t("editor.doorbell.wizard.door.lock"), glyph: glyph("F033E") },
  { value: "action", title: t("editor.doorbell.wizard.door.action"), glyph: glyph("F081C") },
]);
const locks = computed(() => all.value.filter((e) => e.id.startsWith("lock.")).map(item));
// A lock that asks for a code (its code_format) without a default code: the view has no keypad, so no key.
const asksCode = computed(() => {
  const lock = props.modelValue.lock;
  return Boolean(lock && entities.liveStates[lock]?.a?.code_format);
});
watch(() => props.modelValue.lock, (lock) => { if (lock) entities.loadStates([lock]); }, { immediate: true });
// Entities that only report have nothing to do (as an alert's button); everything else is offered.
const READ_ONLY = new Set(["sensor", "binary_sensor", "event", "camera", "image", "zone", "sun", "person", "device_tracker", "weather", "calendar", "lock"]);
const others = computed(() => all.value.filter((e) => !READ_ONLY.has(e.id.split(".", 1)[0])).map(item));
const actions = computed(() => {
  const entity = props.modelValue.entity;
  if (!entity) return [];
  const domain = entity.split(".", 1)[0];
  return (entities.entityActions[entity] || []).filter((a) => a.action.startsWith(`${domain}.`) && !a.fields.some((f) => f.required));
});
watch(() => props.modelValue.entity, (entity) => { if (entity) entities.loadEntityActions(entity); }, { immediate: true });
watch(actions, (list) => { if (list.length && !list.some((a) => a.action === props.modelValue.action)) set({ action: list[0].action }); });
</script>

<template>
  <UiChoiceCards :model-value="modelValue.kind" :cards="cards" :label="t('editor.doorbell.wizard.steps.door.title')"
    @update:model-value="(kind) => set({ kind: kind as DoorChoice['kind'] })" />
  <template v-if="modelValue.kind === 'lock'">
    <UiPicker id="doorbell-lock" :items="locks" :placeholder="t('editor.plugin_tile.search')" :empty="t('editor.events.wizard.none')" width="var(--reka-popover-trigger-width)"
      @pick="(lock: string) => set({ lock })">
      <template #trigger><button type="button" class="ghost-btn wide-pick"><Icon name="magnify" />{{ modelValue.lock ? nameOf(modelValue.lock) : t("editor.doorbell.wizard.door.pick_lock") }}</button></template>
    </UiPicker>
    <p v-if="asksCode" class="hint warn" id="doorbell-lock-code">{{ t("editor.doorbell.wizard.door.code") }}</p>
  </template>
  <template v-else-if="modelValue.kind === 'action'">
    <UiPicker id="doorbell-door-entity" :items="others" :placeholder="t('editor.plugin_tile.search')" :empty="t('editor.events.wizard.none')" width="var(--reka-popover-trigger-width)"
      @pick="(entity: string) => set({ entity, action: '' })">
      <template #trigger><button type="button" class="ghost-btn wide-pick"><Icon name="magnify" />{{ modelValue.entity ? nameOf(modelValue.entity) : t("editor.doorbell.wizard.door.pick_action") }}</button></template>
    </UiPicker>
    <div v-if="actions.length" class="actions" role="radiogroup">
      <button v-for="a in actions" :key="a.action" type="button" class="action-chip" role="radio" :aria-checked="modelValue.action === a.action ? 'true' : 'false'" :title="a.description" @click="set({ action: a.action })">{{ a.name }}</button>
    </div>
    <small v-else-if="modelValue.entity && entities.entityActions[modelValue.entity]" class="hint">{{ t("editor.alerts.wizard.buttons.no_actions") }}</small>
  </template>
</template>

<style scoped>
.wide-pick { width: 100%; justify-content: flex-start; }
.actions { display: flex; flex-wrap: wrap; gap: 6px; }
.action-chip { border: 1px solid var(--line); background: var(--surface); color: var(--ink); border-radius: 999px; padding: 5px 11px; font: inherit; font-size: 12.5px; cursor: pointer; }
.action-chip[aria-checked="true"] { border-color: var(--accent); background: var(--accent-soft); color: var(--accent); }
.warn { color: var(--warn, var(--muted)); }
</style>
