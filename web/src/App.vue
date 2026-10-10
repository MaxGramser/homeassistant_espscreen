<script setup lang="ts">
import { onKeyStroke } from "@vueuse/core";
import { computed } from "vue";
import Sidebar from "./components/Sidebar.vue";
import Toast from "./components/Toast.vue";
import CommandPalette from "./components/CommandPalette.vue";
import ConfirmDialog from "./components/ConfirmDialog.vue";
import ScreenView from "./components/ScreenView.vue";
import EmptyState from "./components/EmptyState.vue";
import HomeView from "./components/HomeView.vue";
import AppSettingsView from "./components/AppSettingsView.vue";
import InstallerView from "./components/InstallerView.vue";
import FirmwareView from "./components/FirmwareView.vue";
import AlertsView from "./components/AlertsView.vue";
import OverrideView from "./components/OverrideView.vue";
import PluginsView from "./components/PluginsView.vue";
import { pluginsEnabled } from "./plugin-state";
import { question } from "./composables/useConfirm";
import { currentScreen, phone, route, state } from "./store";
import { sideWidth, sidebar } from "./sidebar-state";

const view = computed(() => {
  if (route.value === "#settings") return AppSettingsView;
  if (route.value === "#new-screen") return InstallerView;
  if (route.value === "#firmware") return FirmwareView;
  if (route.value === "#alerts") return AlertsView;
  if (route.value === "#override") return OverrideView;
  if (route.value === "#plugins" && pluginsEnabled.value) return PluginsView;
  // Nothing chosen is the overview of every screen (app 0.4.0); a house without screens starts with the first.
  if (currentScreen.value && state.layout) return ScreenView;
  return state.selected || !state.inventory.screens.length ? EmptyState : HomeView;
});
// ⌘K (Ctrl+K) opens the search from anywhere, unless a question of the editor's is open.
onKeyStroke((e) => (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k" && !question.value,
  (e) => { e.preventDefault(); state.palette = !state.palette; }, { target: document });
</script>

<template>
  <div class="app" :class="{ dragging: state.drag.active, phone, 'side-folded': sidebar.folded, 'side-resizing': sidebar.resizing }"
    :style="{ '--side-w': `${sideWidth()}px` }">
    <!-- On a phone the overview and a screen carry their own way around (app 0.4.40): the sidebar's row stays for the rest. -->
    <Sidebar v-if="!(phone && route === '')" />
    <main class="main">
      <component :is="view" />
    </main>
    <Toast />
    <CommandPalette />
    <ConfirmDialog />
  </div>
</template>
