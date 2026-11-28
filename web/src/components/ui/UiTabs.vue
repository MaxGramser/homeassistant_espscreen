<script setup lang="ts">
// A row of tabs (Reka UI's Tabs, its list and triggers): the parts of one page, one open at a time. The page draws the
// part that is open itself and keeps which one in its address, so this is the row alone. Arrow keys move between them.
import { TabsList, TabsRoot, TabsTrigger } from "reka-ui";
export type Tab = { value: string; label: string; glyph?: string };
defineProps<{ modelValue: string; tabs: Tab[]; label?: string }>();
const emit = defineEmits<{ "update:modelValue": [value: string] }>();
</script>

<template>
  <TabsRoot :model-value="modelValue" activation-mode="manual" @update:model-value="(value) => emit('update:modelValue', String(value))">
    <TabsList class="ui-tabs" :aria-label="label">
      <TabsTrigger v-for="tab in tabs" :key="tab.value" class="ui-tab" :value="tab.value" :data-tab="tab.value">
        <span v-if="tab.glyph" class="mdi" aria-hidden="true">{{ tab.glyph }}</span>
        <span>{{ tab.label }}</span>
      </TabsTrigger>
    </TabsList>
  </TabsRoot>
</template>

<style scoped>
.ui-tabs { display: flex; gap: 4px; padding: 4px; border-radius: 999px; background: var(--surface-2, var(--accent-soft)); width: fit-content; max-width: 100%; overflow-x: auto; }
.ui-tab { display: inline-flex; align-items: center; gap: 7px; padding: 7px 16px; border-radius: 999px; border: 0; background: transparent;
  color: var(--muted); font: inherit; font-size: 13px; font-weight: 500; cursor: pointer; white-space: nowrap; }
.ui-tab .mdi { font-size: 16px; }
.ui-tab[data-state="active"] { background: var(--surface); color: var(--ink); box-shadow: 0 1px 2px rgba(0, 0, 0, .08); }
.ui-tab:focus-visible { outline: none; box-shadow: var(--focus); }
</style>
