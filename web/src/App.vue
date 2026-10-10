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
import { currentScreen, state } from "./store";
import { useSidebarStore } from "./stores/sidebar";
import { useUiStore } from "./stores/ui";

const ui = useUiStore();
const sidebar = useSidebarStore();
const view = computed(() => {
  if (ui.route === "#settings") return AppSettingsView;
  if (ui.route === "#new-screen") return InstallerView;
  if (ui.route === "#firmware") return FirmwareView;
  if (ui.route === "#alerts") return AlertsView;
  if (ui.route === "#override") return OverrideView;
  if (ui.route === "#plugins" && pluginsEnabled.value) return PluginsView;
  // Nothing chosen is the overview of every screen (app 0.4.0); a house without screens starts with the first.
  if (currentScreen.value && state.layout) return ScreenView;
  return state.selected || !state.inventory.screens.length ? EmptyState : HomeView;
});
// ⌘K (Ctrl+K) opens the search from anywhere, unless a question of the editor's is open.
onKeyStroke((e) => (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k" && !question.value,
  (e) => { e.preventDefault(); ui.palette = !ui.palette; }, { target: document });
</script>

<template>
  <div class="app" :class="{ dragging: state.drag.active, phone: ui.phone, 'side-folded': sidebar.folded, 'side-resizing': sidebar.resizing }"
    :style="{ '--side-w': `${sidebar.shownWidth}px` }">
    <!-- On a phone the overview and a screen carry their own way around (app 0.4.40): the sidebar's row stays for the rest. -->
    <Sidebar v-if="!(ui.phone && ui.route === '')" />
    <main class="main">
      <component :is="view" />
    </main>
    <Toast />
    <CommandPalette />
    <ConfirmDialog />
  </div>
</template>
