<script setup lang="ts">
// One screen: the head with its status, the Layout and Settings tabs, and the drawer over the right side.
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { t } from "../i18n";
import {
  canAlert, closeInspector, copyLayoutFrom, currentScreen, exportLayout, go, identify, importLayout, needsUpdate, redo, save, startUpdate, state, undo,
} from "../store";
import LayoutView from "./LayoutView.vue";
import SettingsTab from "./SettingsTab.vue";
import Drawer from "./Drawer.vue";
import FeedbackPanel from "./FeedbackPanel.vue";
import Icon from "./ui/Icon.vue";
import UiMenu from "./ui/UiMenu.vue";
import UiMenuItem from "./ui/UiMenuItem.vue";
import UiMenuLabel from "./ui/UiMenuLabel.vue";
import UiMenuSeparator from "./ui/UiMenuSeparator.vue";
import UiMenuSub from "./ui/UiMenuSub.vue";

const screen = computed(() => currentScreen.value!);
const statusText = computed(() => screen.value.virtual ? t("editor.preview.virtual") : screen.value.online
  ? `${screen.value.delivery} · ${screen.value.status}`
  : t("editor.screen_view.offline"));
// The head says whether the screen is there in one word; the details of its delivery stay in the chip's tooltip.
const statusKind = computed(() => !screen.value.online ? "off" : screen.value.in_sync ? "good" : "update");
const statusWord = computed(() => !screen.value.online ? t("editor.common.offline") : screen.value.in_sync ? t("editor.common.online") : t("editor.screen_view.sending"));
const updateReady = computed(() => needsUpdate(screen.value) && screen.value.online && screen.value.update?.profile && screen.value.update?.host);
const others = computed(() => state.inventory.screens.filter((s) => s.id !== screen.value.id && s.layout?.tiles?.length));
const fileInput = ref<HTMLInputElement | null>(null);
function closeMenu() { state.menuOpen = false; }
function openOverride() {
  closeMenu();
  state.overrideProfile = screen.value.update?.profile || null;
  state.overrideFriendly = screen.value.name;
  go("#override");
}
function inspectAll() {
  closeMenu();
  state.selectedTile = null;
  state.inspector = { kind: "inspect" };
}
function copyFrom(id: string) {
  closeMenu();
  if (state.dirty && !confirm(t("editor.screen_view.confirm.copy"))) return;
  copyLayoutFrom(id);
}
function pickFile() { closeMenu(); fileInput.value?.click(); }
async function onFile(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  if (state.dirty && !confirm(t("editor.screen_view.confirm.import"))) return;
  importLayout(await file.text());
}
function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") {
    if (state.menuOpen) closeMenu();
    else if (state.palette) return;
    else if (state.inspector && !(e.target as HTMLElement)?.closest?.(".picker")) closeInspector();
  } else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
    e.preventDefault();
    if (state.dirty) save();
  } else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z" && !(e.target as HTMLElement)?.closest('input, textarea, [contenteditable]')) {
    e.preventDefault();
    if (e.shiftKey) redo(); else undo();
  }
}
onMounted(() => document.addEventListener("keydown", onKey));
onBeforeUnmount(() => document.removeEventListener("keydown", onKey));
</script>

<template>
  <header class="main-head">
    <div class="head-title">
      <h1 id="screen-name">{{ screen.name }}</h1>
      <span id="delivery" class="chip status" :class="statusKind" :title="statusText"><span class="dot"></span>{{ statusWord }}</span>
    </div>
    <div class="seg tabs" role="tablist" :aria-label="screen.name">
      <button type="button" id="tab-layout" role="tab" :aria-pressed="state.tab === 'layout' ? 'true' : 'false'" :aria-selected="state.tab === 'layout'" @click="state.tab = 'layout'">
        <Icon name="view-dashboard-outline" />{{ t("editor.screen_view.tabs.layout") }}
      </button>
      <button v-if="!screen.virtual" type="button" id="tab-settings" role="tab" :aria-pressed="state.tab === 'settings' ? 'true' : 'false'" :aria-selected="state.tab === 'settings'" @click="state.tab = 'settings'; closeInspector()">
        <Icon name="cog-outline" />{{ t("editor.screen_view.tabs.settings") }}
      </button>
    </div>
    <div class="head-right">
      <span v-if="!state.dirty" id="dirty" class="saved-note" :class="{ sent: state.saved }"><Icon name="check" />{{ state.saved ? t(screen.virtual ? "editor.preview.saved" : "editor.screen_view.sent") : t("editor.screen_view.all_saved") }}</span>
      <span v-else id="dirty" class="chip dirty">{{ t("editor.common.unsaved") }}</span>
      <button v-if="state.dirty" id="save" type="button" class="btn primary" :disabled="state.busy" title="⌘S" @click="save()">
        <span v-if="state.busy" class="spin small"></span>{{ state.busy ? t("editor.common.saving") : t(screen.virtual ? "editor.preview.save" : "editor.common.save_send") }}
      </button>
      <UiMenu v-model:open="state.menuOpen" width="264px">
        <template #trigger>
          <button id="more" type="button" class="icon-btn" :aria-label="t('editor.screen_view.more')"><Icon name="dots-horizontal" /></button>
        </template>
        <UiMenuLabel>{{ t("editor.screen_view.menu.group_screen") }}</UiMenuLabel>
        <UiMenuItem id="identify" icon="monitor-eye" :hint="t('editor.screen_view.menu.identify_hint')" :disabled="!canAlert(screen) || !screen.online"
          :title="canAlert(screen) ? '' : t('editor.screen_view.menu.identify_needs')" @select="identify(screen)">{{ t("editor.screen_view.menu.identify") }}</UiMenuItem>
        <UiMenuItem id="inspect" icon="database-search-outline" @select="inspectAll">{{ t("editor.common.read_current_data") }}</UiMenuItem>
        <UiMenuItem v-if="updateReady" id="update-screen" icon="update" :hint="screen.update?.target" @select="startUpdate(screen)">{{ t("editor.screen_view.menu.update") }}</UiMenuItem>
        <UiMenuSeparator />
        <UiMenuLabel>{{ t("editor.screen_view.menu.group_layout") }}</UiMenuLabel>
        <UiMenuSub id="copy-layout" icon="content-copy" :label="t('editor.screen_view.menu.copy')" :disabled="!others.length"
          :hint="others.length ? t('editor.screen_view.menu.copy_screens', others.length) : t('editor.screen_view.menu.copy_none')">
          <UiMenuItem v-for="other in others" :key="other.id" icon="monitor-dashboard" :hint="t('editor.screen_view.menu.copy_tiles', other.layout.tiles.length)" @select="copyFrom(other.id)">{{ other.name }}</UiMenuItem>
        </UiMenuSub>
        <UiMenuItem id="export-layout" icon="tray-arrow-down" hint="JSON" @select="exportLayout()">{{ t("editor.screen_view.menu.export") }}</UiMenuItem>
        <UiMenuItem id="import-layout" icon="tray-arrow-up" hint="JSON" @select="pickFile">{{ t("editor.screen_view.menu.import") }}</UiMenuItem>
        <UiMenuSeparator />
        <UiMenuLabel>{{ t("editor.screen_view.menu.group_advanced") }}</UiMenuLabel>
        <UiMenuItem id="open-override" icon="code-braces" :disabled="!screen.update?.profile" :title="screen.update?.profile ? '' : t('editor.screen_view.menu.override_none')" @select="openOverride">{{ t("editor.screen_view.menu.override") }}</UiMenuItem>
        <UiMenuItem icon="flash" @select="go('#firmware')">{{ t("editor.nav.firmware") }}</UiMenuItem>
      </UiMenu>
      <input ref="fileInput" type="file" accept="application/json,.json" hidden @change="onFile" />
    </div>
  </header>
  <FeedbackPanel v-if="screen.feedback?.available" :key="`card-${screen.id}`" :screen="screen" mode="card" />
  <div class="body" id="body">
    <LayoutView v-if="state.tab === 'layout'" />
    <SettingsTab v-else />
    <Drawer />
  </div>
</template>
