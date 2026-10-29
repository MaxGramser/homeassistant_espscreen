<script setup lang="ts">
import { onKeyStroke } from "@vueuse/core";
import { computed, watch } from "vue";
import { t } from "./i18n";
import Icon from "./components/ui/Icon.vue";
import Sidebar from "./components/Sidebar.vue";
import Toast from "./components/Toast.vue";
import CommandPalette from "./components/CommandPalette.vue";
import ConfirmDialog from "./components/ConfirmDialog.vue";
import ConnectionBar from "./components/ConnectionBar.vue";
import ScreenView from "./components/ScreenView.vue";
import EmptyState from "./components/EmptyState.vue";
import HomeView from "./components/HomeView.vue";
import AppSettingsView from "./components/AppSettingsView.vue";
import InstallerView from "./components/InstallerView.vue";
import FirmwareView from "./components/FirmwareView.vue";
import EventsView from "./components/EventsView.vue";
import OverrideView from "./components/OverrideView.vue";
import ReportPanel from "./components/ReportPanel.vue";
import PluginsView from "./components/PluginsView.vue";
import { question } from "./composables/useConfirm";
import { useSidebarStore } from "./stores/sidebar";
import { useUiStore } from "./stores/ui";
import { usePluginsStore } from "./stores/plugins";
import { useScreenStore } from "./stores/screen";
import { useInventoryStore } from "./stores/inventory";
import { useDragStore } from "./stores/drag";
import { useDocumentStore } from "./stores/document";

const ui = useUiStore();
const sidebar = useSidebarStore();
const plugins = usePluginsStore();
const scr = useScreenStore();
const inv = useInventoryStore();
const dragging = useDragStore();
const doc = useDocumentStore();
const view = computed(() => {
  if (ui.route === "#settings") return AppSettingsView;
  if (ui.route === "#new-screen") return InstallerView;
  if (ui.route === "#firmware") return FirmwareView;
  if (ui.route === "#events") return EventsView;
  if (ui.route === "#override") return OverrideView;
  if (ui.route === "#report") return ReportPanel;
  if (ui.route === "#plugins" && plugins.pluginsEnabled) return PluginsView;
  // Nothing chosen is the overview of every screen (app 0.4.0); a house without screens starts with the first.
  if (scr.currentScreen && doc.layout) return ScreenView;
  return scr.selected || !inv.inventory.screens.length ? EmptyState : HomeView;
});
// The sidebar of a phone closes once something in it is chosen: a screen, the overview or another page.
watch(() => [ui.route, scr.selected, ui.phone], () => { ui.sideOpen = false; });
onKeyStroke("Escape", () => { ui.sideOpen = false; }, { target: document });
// ⌘K (Ctrl+K) opens the search from anywhere, unless a question of the editor's is open.
onKeyStroke((e) => (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k" && !question.value,
  (e) => { e.preventDefault(); ui.palette = !ui.palette; }, { target: document });
</script>

<template>
  <div class="app" :class="{ dragging: dragging.active, phone: ui.phone, 'side-folded': sidebar.folded, 'side-resizing': sidebar.resizing }"
    :style="{ '--side-w': `${sidebar.shownWidth}px` }">
    <!-- On a phone the sidebar is a sheet from the left, everything it holds on a wider page, behind the menu key of
         the overview, of a screen and of every other page. -->
    <Sidebar :class="{ sheet: ui.phone, open: ui.phone && ui.sideOpen }" :inert="ui.phone && !ui.sideOpen" />
    <div v-if="ui.phone && ui.sideOpen" class="sheet-dim side-dim" @click="ui.sideOpen = false"></div>
    <main class="main">
      <ConnectionBar />
      <header v-if="ui.phone && ui.route !== ''" class="phone-nav">
        <button type="button" class="icon-btn phone-menu-key" id="phone-menu" :aria-label="t('editor.phone.menu')" @click="ui.sideOpen = true"><Icon name="menu" /></button>
        <b>Tessera</b>
      </header>
      <component :is="view" />
    </main>
    <Toast />
    <CommandPalette />
    <ConfirmDialog />
  </div>
</template>
