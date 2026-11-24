<script setup lang="ts">
// One choice of a few, all in sight, the chosen one raised (Reka UI's ToggleGroup, one at a time): how a view or a mode
// is switched, such as the library's Tiles and List. Arrow keys move between the choices, Space and Enter take one, and
// a choice never goes off by a second press: there is always one. The look is the editor's `.seg` (styles/app.css),
// which the hand-made segmented rows still use until they move here.
import { ToggleGroupItem, ToggleGroupRoot } from "reka-ui";
import Icon from "./Icon.vue";
import type { IconName } from "../../model/ui-icons";

export type Segment = { value: string; label: string; icon?: IconName; title?: string; disabled?: boolean };
defineProps<{ modelValue: string; segments: Segment[]; label: string }>();
const emit = defineEmits<{ "update:modelValue": [value: string] }>();
</script>

<template>
  <ToggleGroupRoot class="seg ui-segmented" type="single" :aria-label="label" :model-value="modelValue"
    @update:model-value="(value) => value && emit('update:modelValue', value as string)">
    <ToggleGroupItem v-for="segment in segments" :key="segment.value" :value="segment.value" :title="segment.title" :disabled="segment.disabled">
      <Icon v-if="segment.icon" :name="segment.icon" />{{ segment.label }}
    </ToggleGroupItem>
  </ToggleGroupRoot>
</template>
