<script setup lang="ts">
// The overview's word on broken tiles (stores/broken.ts): one calm line, "3 tiles on 2 screens show an entity that no
// longer exists", that opens the list of them; nothing while every tile shows what it should.
import { ref } from "vue";
import { t } from "../i18n";
import { summaryText } from "../model/broken-tiles";
import BrokenList from "./BrokenList.vue";
import Icon from "./ui/Icon.vue";
import { useBrokenStore } from "../stores/broken";

const broken = useBrokenStore();
const open = ref(false);
</script>

<template>
  <section v-if="broken.summary" id="broken" class="broken-note" :class="{ open }">
    <button type="button" class="broken-head" :aria-expanded="open ? 'true' : 'false'" aria-controls="broken-tiles" @click="open = !open">
      <Icon name="alert-circle-outline" class="broken-icon" />
      <span class="broken-text">{{ summaryText(broken.summary) }}</span>
      <span class="broken-toggle">{{ t(open ? "editor.broken.hide" : "editor.broken.review") }}<Icon name="chevron-down" /></span>
    </button>
    <BrokenList v-if="open" id="broken-tiles" :tiles="broken.tiles" />
  </section>
</template>
