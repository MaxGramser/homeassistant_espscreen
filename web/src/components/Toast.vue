<script setup lang="ts">
// The toast at the bottom, with what it offers to do. Its action runs after the toast went, so a toast the action shows
// itself (Undone, with Redo) stays. A tap on its words sends it away: on a phone it may lie on a key the person wants
// now (with a sheet open it shows at the top, over the page's own keys).
import { useUiStore } from "../stores/ui";

const ui = useUiStore();
function act() {
  const action = ui.notice?.action;
  ui.dismissToast();
  action?.run();
}
</script>

<template>
  <div v-if="ui.notice" id="toast" class="toast" role="status" @click="ui.dismissToast()">
    <span>{{ ui.notice.message }}</span>
    <button v-if="ui.notice.action" type="button" @click.stop="act">{{ ui.notice.action.label }}</button>
  </div>
</template>
