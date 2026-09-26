<script setup lang="ts">
// A setting that is on or off: what it is and the switch on the right. The label flips it; what it does, where that
// isn't plain from the words, is a tooltip beside the label rather than another line of text.
import { useId } from "vue";
import type { IconName } from "../../model/ui-icons";
import Icon from "./Icon.vue";
import UiSwitch from "./UiSwitch.vue";
import HelpTip from "../HelpTip.vue";
defineProps<{ label: string; description?: string; modelValue: boolean; disabled?: boolean; icon?: IconName }>();
const emit = defineEmits<{ "update:modelValue": [value: boolean] }>();
const id = useId();
</script>

<template>
  <div class="switch-row" :class="{ disabled }">
    <span v-if="icon" class="sr-icon"><Icon :name="icon" /></span>
    <span class="sr-text">
      <span class="sr-label"><label :for="id">{{ label }}</label><HelpTip v-if="description" :text="description" /></span>
      <slot />
    </span>
    <UiSwitch :id="id" :model-value="modelValue" :disabled="disabled"
      @update:model-value="(value: boolean) => emit('update:modelValue', value)" />
  </div>
</template>
