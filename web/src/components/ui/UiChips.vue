<script setup lang="ts">
// A row of chips to switch on and off (Reka UI's ToggleGroup, several at once): quick choices that read as what they
// add, where a column of switches reads as settings. Arrow keys move between them, Space and Enter flip one.
import { ToggleGroupItem, ToggleGroupRoot } from "reka-ui";
export type Chip = { value: string; label: string; glyph?: string; disabled?: boolean };
defineProps<{ modelValue: string[]; chips: Chip[]; label?: string }>();
const emit = defineEmits<{ "update:modelValue": [value: string[]] }>();
</script>

<template>
  <ToggleGroupRoot class="ui-chips" type="multiple" :aria-label="label" :model-value="modelValue"
    @update:model-value="(value) => emit('update:modelValue', (value as string[]) || [])">
    <ToggleGroupItem v-for="chip in chips" :key="chip.value" class="ui-chip" :value="chip.value" :disabled="chip.disabled">
      <span v-if="chip.glyph" class="mdi" aria-hidden="true">{{ chip.glyph }}</span>
      <span>{{ chip.label }}</span>
    </ToggleGroupItem>
  </ToggleGroupRoot>
</template>

<style scoped>
.ui-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.ui-chip { display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border-radius: 999px; border: 1px solid var(--line);
  background: var(--surface); color: var(--ink); font: inherit; font-size: 12.5px; cursor: pointer; }
.ui-chip .mdi { font-size: 15px; color: var(--muted); }
.ui-chip[data-state="on"] { background: var(--accent-soft); border-color: transparent; color: var(--accent); }
.ui-chip[data-state="on"] .mdi { color: var(--accent); }
.ui-chip:focus-visible { outline: none; box-shadow: var(--focus); }
.ui-chip[data-disabled] { opacity: .45; cursor: default; }
</style>
