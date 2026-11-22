<script setup lang="ts">
// The head of one part of a settings page (docs/PAGES.md, "Settings"): the way back to the list of parts, named after
// it, and the part's title (the page's own heading on the app's Settings page, a heading under the tabs on a screen's).
import Icon from "./ui/Icon.vue";

withDefaults(defineProps<{ back: string; title: string; text?: string; as?: "h1" | "h2" }>(), { text: "", as: "h2" });
const emit = defineEmits<{ back: [] }>();
</script>

<template>
  <div class="set-head">
    <button type="button" class="set-back" @click="emit('back')"><Icon name="chevron-left" />{{ back }}</button>
    <component :is="as">{{ title }}</component>
    <p v-if="text">{{ text }}</p>
  </div>
</template>
