<script setup lang="ts">
// An on/off switch (Reka UI): a button with role="switch", so a label that points at it, Space and Enter all flip it.
import { SwitchRoot, SwitchThumb } from "reka-ui";
defineProps<{ modelValue: boolean; disabled?: boolean; id?: string }>();
const emit = defineEmits<{ "update:modelValue": [value: boolean] }>();
</script>

<template>
  <SwitchRoot :id="id" class="ui-switch" :model-value="modelValue" :disabled="disabled" @update:model-value="(value: boolean) => emit('update:modelValue', value)">
    <SwitchThumb class="ui-switch-thumb" />
  </SwitchRoot>
</template>
