<script setup lang="ts">
import { useUiStore } from "../stores/ui";

const ui = useUiStore();
</script>

<template>
  <div v-if="ui.notice" id="toast" class="toast" role="status">
    <span>{{ ui.notice.message }}</span>
    <button v-if="ui.notice.action" type="button" @click="ui.notice.action.run(); ui.dismissToast()">{{ ui.notice.action.label }}</button>
  </div>
</template>
