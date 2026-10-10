<script setup lang="ts">
// The toast at the bottom, with what it offers to do. Its action runs after the toast went, so a toast the action shows
// itself (Undone, with Redo) stays.
import { useUiStore } from "../stores/ui";

const ui = useUiStore();
function act() {
  const action = ui.notice?.action;
  ui.dismissToast();
  action?.run();
}
</script>

<template>
  <div v-if="ui.notice" id="toast" class="toast" role="status">
    <span>{{ ui.notice.message }}</span>
    <button v-if="ui.notice.action" type="button" @click="act">{{ ui.notice.action.label }}</button>
  </div>
</template>
