<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from "vue";
import Sidebar from "./components/Sidebar.vue";
import Toast from "./components/Toast.vue";
import CommandPalette from "./components/CommandPalette.vue";
import ScreenView from "./components/ScreenView.vue";
import EmptyState from "./components/EmptyState.vue";
import HomeView from "./components/HomeView.vue";
import AppSettingsView from "./components/AppSettingsView.vue";
import InstallerView from "./components/InstallerView.vue";
import FirmwareView from "./components/FirmwareView.vue";
import AlertsView from "./components/AlertsView.vue";
import OverrideView from "./components/OverrideView.vue";
import { currentScreen, route, state } from "./store";

const view = computed(() => {
  if (route.value === "#settings") return AppSettingsView;
  if (route.value === "#new-screen") return InstallerView;
  if (route.value === "#firmware") return FirmwareView;
  if (route.value === "#alerts") return AlertsView;
  if (route.value === "#override") return OverrideView;
  // Nothing chosen is the overview of every screen (app 0.4.0); a house without screens starts with the first.
  if (currentScreen.value && state.layout) return ScreenView;
  return state.selected || !state.inventory.screens.length ? EmptyState : HomeView;
});
// ⌘K (Ctrl+K) opens the search from anywhere.
function onKey(e: KeyboardEvent) {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); state.palette = !state.palette; }
}
onMounted(() => document.addEventListener("keydown", onKey));
onBeforeUnmount(() => document.removeEventListener("keydown", onKey));
</script>

<template>
  <div class="app" :class="{ dragging: state.drag.active }">
    <Sidebar />
    <main class="main">
      <component :is="view" />
    </main>
    <Toast />
    <CommandPalette />
  </div>
</template>
