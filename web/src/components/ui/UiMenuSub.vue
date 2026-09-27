<script setup lang="ts">
// A menu item that opens a second list beside it, such as the other screens to copy a layout from.
import { DropdownMenuPortal, DropdownMenuSub, DropdownMenuSubContent, DropdownMenuSubTrigger } from "reka-ui";
import type { IconName } from "../../model/ui-icons";
import Icon from "./Icon.vue";
defineProps<{ icon?: IconName; label: string; hint?: string; disabled?: boolean; inline?: boolean }>();
</script>

<template>
  <DropdownMenuSub>
    <DropdownMenuSubTrigger class="ui-menu-item" :disabled="disabled" v-bind="$attrs">
      <Icon v-if="icon" :name="icon" class="ui-menu-icon" />
      <span class="ui-menu-text">{{ label }}</span>
      <small v-if="hint" class="ui-menu-end">{{ hint }}</small>
      <Icon name="chevron-right" class="ui-menu-chevron" />
    </DropdownMenuSubTrigger>
    <DropdownMenuPortal :disabled="inline">
      <DropdownMenuSubContent class="ui-popover ui-menu" :side-offset="4" :collision-padding="8"><slot /></DropdownMenuSubContent>
    </DropdownMenuPortal>
  </DropdownMenuSub>
</template>
