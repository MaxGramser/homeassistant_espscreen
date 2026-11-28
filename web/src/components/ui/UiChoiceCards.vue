<script setup lang="ts">
// One choice from a few, each a card with a title and a line under it (Reka UI's RadioGroup): what a wizard offers first,
// such as the doorbells Home Assistant knows. Arrow keys move between them, Space picks.
import { RadioGroupItem, RadioGroupRoot } from "reka-ui";
export type ChoiceCard = { value: string; title: string; detail?: string; glyph?: string };
defineProps<{ modelValue: string; cards: ChoiceCard[]; label?: string }>();
const emit = defineEmits<{ "update:modelValue": [value: string] }>();
</script>

<template>
  <RadioGroupRoot class="choice-cards" :aria-label="label" :model-value="modelValue" @update:model-value="(value) => emit('update:modelValue', String(value ?? ''))">
    <RadioGroupItem v-for="card in cards" :key="card.value" class="choice-card" :value="card.value" :data-value="card.value">
      <span v-if="card.glyph" class="mdi choice-glyph" aria-hidden="true">{{ card.glyph }}</span>
      <span class="choice-text"><strong>{{ card.title }}</strong><small v-if="card.detail">{{ card.detail }}</small></span>
    </RadioGroupItem>
  </RadioGroupRoot>
</template>

<style scoped>
.choice-cards { display: grid; gap: 8px; }
.choice-card { display: flex; align-items: center; gap: 12px; width: 100%; padding: 12px 14px; border-radius: 12px; border: 1px solid var(--line);
  background: var(--surface); color: var(--ink); font: inherit; text-align: left; cursor: pointer; }
.choice-card:hover { border-color: var(--muted); }
.choice-card[data-state="checked"] { border-color: var(--accent); background: var(--accent-soft); }
.choice-card:focus-visible { outline: none; box-shadow: var(--focus); }
.choice-glyph { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 50%; background: var(--surface-2); font-size: 18px; flex: none; }
.choice-card[data-state="checked"] .choice-glyph { background: var(--surface); color: var(--accent); }
.choice-text { display: grid; gap: 2px; min-width: 0; }
.choice-text small { color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }
</style>
