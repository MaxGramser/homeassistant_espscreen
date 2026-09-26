<script setup lang="ts">
// One thing to do in a menu: an icon, what it does, and on the right a short hint (a version, a count, a key).
import { DropdownMenuItem } from "reka-ui";
import type { IconName } from "../../model/ui-icons";
import Icon from "./Icon.vue";
defineProps<{ icon?: IconName; hint?: string; danger?: boolean; disabled?: boolean }>();
const emit = defineEmits<{ select: [] }>();
</script>

<template>
  <DropdownMenuItem class="ui-menu-item" :class="{ danger }" :disabled="disabled" @select="emit('select')">
    <Icon v-if="icon" :name="icon" class="ui-menu-icon" />
    <span class="ui-menu-text"><slot /></span>
    <small v-if="hint" class="ui-menu-end">{{ hint }}</small>
  </DropdownMenuItem>
</template>
