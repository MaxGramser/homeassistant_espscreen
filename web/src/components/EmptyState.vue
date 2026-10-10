<script setup lang="ts">
import { t } from "../i18n";
import { useUiStore } from "../stores/ui";
import { useInventoryStore } from "../stores/inventory";

const ui = useUiStore();
const inv = useInventoryStore();
</script>

<template>
  <section v-if="inv.inventory.screens.length" id="choose" class="empty">
    <span class="empty-icon">▦</span>
    <h2>{{ t("editor.empty.choose.title") }}</h2>
    <p>{{ t("editor.empty.choose.text") }}</p>
  </section>
  <section v-else id="empty" class="empty">
    <span class="empty-icon">▦</span>
    <h2>{{ t("editor.empty.start.title") }}</h2>
    <p>{{ t("editor.empty.start.text") }}</p>
    <button id="start" type="button" class="btn primary" @click="ui.go('#new-screen')">{{ t("editor.empty.start.button") }}</button>
  </section>
</template>
