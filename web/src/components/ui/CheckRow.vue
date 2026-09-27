<script setup lang="ts">
// One of several things to pick, with a round check on the left: a page to copy a bar to, an entity for a new bar.
import Icon from "./Icon.vue";
defineProps<{ checked: boolean; disabled?: boolean }>();
const emit = defineEmits<{ toggle: [] }>();
</script>

<template>
  <button type="button" class="check-row" role="checkbox" :aria-checked="checked ? 'true' : 'false'" :disabled="disabled" @click="emit('toggle')">
    <span class="check-dot" :class="{ on: checked }"><Icon v-if="checked" name="check" /></span>
    <slot />
  </button>
</template>
