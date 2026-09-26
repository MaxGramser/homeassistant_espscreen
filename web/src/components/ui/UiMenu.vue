<script setup lang="ts">
// A menu behind a button (Reka UI): the trigger is the slot, the items are UiMenuItem, UiMenuLabel, UiMenuSeparator
// and UiMenuSub. Arrow keys walk it, Escape and a click beside it close it, and it opens beside the edge it fits.
import { DropdownMenuContent, DropdownMenuPortal, DropdownMenuRoot, DropdownMenuTrigger } from "reka-ui";
withDefaults(defineProps<{ align?: "start" | "center" | "end"; inline?: boolean; width?: string }>(), { align: "end" });
const open = defineModel<boolean>("open", { default: false });
</script>

<template>
  <DropdownMenuRoot v-model:open="open" :modal="false">
    <DropdownMenuTrigger as-child><slot name="trigger" /></DropdownMenuTrigger>
    <DropdownMenuPortal :disabled="inline">
      <DropdownMenuContent class="ui-popover ui-menu" :style="width ? { minWidth: width } : undefined" :align="align" :side-offset="6" :collision-padding="8">
        <slot />
      </DropdownMenuContent>
    </DropdownMenuPortal>
  </DropdownMenuRoot>
</template>
