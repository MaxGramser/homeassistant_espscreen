<script setup lang="ts" generic="T extends string | number">
// A choice from a list (Reka UI): the current one in the field, the rest in a list that opens under it with a check at
// the chosen one. An empty value is a real choice here ("not set"), which Reka reserves, so it travels under a stand-in.
import { SelectContent, SelectIcon, SelectItem, SelectItemIndicator, SelectItemText, SelectPortal, SelectRoot, SelectTrigger, SelectValue, SelectViewport } from "reka-ui";
import Icon from "./Icon.vue";

const props = defineProps<{ modelValue: T; options: readonly (readonly [T, string])[]; id?: string; placeholder?: string; disabled?: boolean; inline?: boolean }>();
const emit = defineEmits<{ "update:modelValue": [value: T] }>();
const EMPTY = "\u0000empty";
const encode = (value: T) => (value === "" ? EMPTY : value);
function pick(value: unknown) {
  const found = props.options.find(([key]) => encode(key) === value);
  if (found) emit("update:modelValue", found[0]);
}
</script>

<template>
  <SelectRoot :model-value="encode(modelValue)" :disabled="disabled" @update:model-value="pick">
    <SelectTrigger :id="id" class="ui-select" v-bind="$attrs">
      <SelectValue :placeholder="placeholder" />
      <SelectIcon as-child><Icon name="chevron-down" /></SelectIcon>
    </SelectTrigger>
    <SelectPortal :disabled="inline">
      <SelectContent class="ui-popover ui-select-content" position="popper" :side-offset="4" :collision-padding="8">
        <SelectViewport class="ui-select-viewport">
          <SelectItem v-for="[value, text] in options" :key="String(value)" :value="encode(value)" class="ui-menu-item">
            <SelectItemText>{{ text }}</SelectItemText>
            <SelectItemIndicator class="ui-menu-end"><Icon name="check" /></SelectItemIndicator>
          </SelectItem>
        </SelectViewport>
      </SelectContent>
    </SelectPortal>
  </SelectRoot>
</template>
