<script setup lang="ts">
// One screen: the head with its status, the Layout and Settings tabs, and the inspector in a column on the right.
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { t } from "../i18n";
import { needsUpdate } from "../model/screen-status";
import {
  buildOf, canAlert, closeInspector, copyLayoutFrom, currentScreen, currentTile, removeTile, exportLayout, go, goHome, identify, importLayout, narrowPhone, openBar,
  phone, redo, renameScreen, save, setFullEditor, startUpdate, state, tileLimit, undo,
} from "../store";
import LayoutView from "./LayoutView.vue";
import SettingsTab from "./SettingsTab.vue";
import ScreenPluginsTab from "./ScreenPluginsTab.vue";
import { pluginsEnabled } from "../plugin-state";
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
// The phone's menu (app 0.4.40) holds what the toolbar and the tabs hold on a wider page.
function phoneBack() {
  if (state.tab !== "layout") { state.tab = "layout"; return; }
  goHome();
}
const phoneStatus = computed(() => !screen.value.online ? t("editor.common.offline")
  : state.dirty ? t("editor.phone.not_sent") : screen.value.in_sync ? t("editor.phone.on_screen") : t("editor.screen_view.sending"));
function phoneSettings() { closeMenu(); closeInspector(); state.tab = "settings"; }
function phoneRename() {
  closeMenu();
  const name = prompt(t("editor.sidebar.rename.label"), screen.value.name);
  if (name && name.trim() && name.trim() !== screen.value.name) renameScreen(screen.value, name.trim());
}
const full = computed(() => (state.layout?.tiles.length || 0) >= tileLimit.value);
function phoneAdd() { state.insertAt = -1; closeInspector(); state.addSheet = true; }
async function onFile(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  if (state.dirty && !confirm(t("editor.screen_view.confirm.import"))) return;
  importLayout(await file.text());
}
// Escape belongs to the innermost thing open (app 0.4.32): a list of choices or a menu closes and the inspector under it
// stays. Whether one was open is read before it closes, in the capture phase, since it is gone by the time the key
// reaches this handler.
let popoverEscape = false;
function beforeKey(e: KeyboardEvent) {
  popoverEscape = e.key === "Escape" && Boolean(document.querySelector(".ui-popover"));
}
function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") {
    if (popoverEscape) return;
    if (state.menuOpen) closeMenu();
    else if (state.palette) return;
    else if (state.inspector && !(e.target as HTMLElement)?.closest?.(".picker")) closeInspector();
  } else if ((e.key === "Delete" || e.key === "Backspace") && !e.defaultPrevented && state.inspector?.kind === "tile" && currentTile.value
    && !(e.target as HTMLElement)?.closest?.("input, textarea, select, [contenteditable], [role='menu'], dialog")) {
    // The selected tile goes, as a selected object does in Keynote (app 0.4.32); Undo brings it back.
    e.preventDefault();
    removeTile(currentTile.value);
  } else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
    e.preventDefault();
    if (state.dirty) save();
  } else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z" && !(e.target as HTMLElement)?.closest('input, textarea, [contenteditable]')) {
    e.preventDefault();
    if (e.shiftKey) redo(); else undo();
  }
}
onMounted(() => { document.addEventListener("keydown", beforeKey, true); document.addEventListener("keydown", onKey); });
onBeforeUnmount(() => { document.removeEventListener("keydown", beforeKey, true); document.removeEventListener("keydown", onKey); });
</script>

<template>
  <header class="main-head">
    <button v-if="phone" type="button" class="phone-back" @click="phoneBack">
      <Icon name="chevron-left" />{{ state.tab !== "layout" ? t("editor.screen_view.tabs.layout") : t("editor.phone.screens") }}
    </button>
    <div class="head-title">
      <h1 id="screen-name">{{ screen.name }}</h1>
      <span v-if="!phone" id="delivery" class="chip status" :class="statusKind" :title="statusText"><span class="dot"></span>{{ statusWord }}</span>
      <p v-else class="phone-status" :class="{ dirty: state.dirty }" :title="statusText"><span class="dot" :class="statusKind"></span>{{ phoneStatus }}</p>
    </div>
    <div v-if="!phone" class="seg tabs" role="tablist" :aria-label="screen.name">
      <button type="button" id="tab-layout" role="tab" :aria-pressed="state.tab === 'layout' ? 'true' : 'false'" :aria-selected="state.tab === 'layout'" @click="state.tab = 'layout'">
        <Icon name="view-dashboard-outline" />{{ t("editor.screen_view.tabs.layout") }}
      </button>
      <button v-if="!screen.virtual" type="button" id="tab-settings" role="tab" :aria-pressed="state.tab === 'settings' ? 'true' : 'false'" :aria-selected="state.tab === 'settings'" @click="state.tab = 'settings'; closeInspector()">
        <Icon name="cog-outline" />{{ t("editor.screen_view.tabs.settings") }}
      </button>
      <button v-if="!screen.virtual && pluginsEnabled" type="button" id="tab-plugins" role="tab" :aria-pressed="state.tab === 'plugins' ? 'true' : 'false'" :aria-selected="state.tab === 'plugins'" @click="state.tab = 'plugins'; closeInspector()">
        <Icon name="puzzle-outline" />{{ t("editor.screen_view.tabs.plugins") }}
        <span v-if="buildOf(screen)?.by === 'plugins'" class="spin small" role="img" :aria-label="t('editor.build.plugins')"></span>
      </button>
    </div>
    <div class="head-right">
      <template v-if="!phone">
      <span v-if="!state.dirty" id="dirty" class="saved-note" :class="{ sent: state.saved }"><Icon name="check" />{{ state.saved ? t(screen.virtual ? "editor.preview.saved" : "editor.screen_view.sent") : t("editor.screen_view.all_saved") }}</span>
      <span v-else id="dirty" class="chip dirty">{{ t("editor.common.unsaved") }}</span>
      </template>
      <button v-if="state.dirty && !phone" id="save" type="button" class="btn primary" :disabled="state.busy" title="⌘S" @click="save()">
        <span v-if="state.busy" class="spin small"></span>{{ state.busy ? t("editor.common.saving") : t(screen.virtual ? "editor.preview.save" : "editor.common.save_send") }}
      </button>
      <UiMenu v-model:open="state.menuOpen" width="264px">
        <template #trigger>
          <button id="more" type="button" class="icon-btn" :aria-label="t('editor.screen_view.more')"><Icon name="dots-horizontal" /></button>
        </template>
        <template v-if="phone && state.layout">
          <div class="phone-menu-row" role="group">
            <button type="button" role="menuitem" @click="closeMenu(); state.tab = 'layout'; state.previewOpen = true"><Icon name="play" />{{ t("editor.pages.preview") }}</button>
            <button type="button" role="menuitem" :disabled="!state.undoCount" @click="undo"><Icon name="undo" />{{ t("editor.common.undo") }}</button>
            <button type="button" role="menuitem" :disabled="!state.redoCount" @click="redo"><Icon name="redo" />{{ t("editor.pages.redo") }}</button>
          </div>
          <UiMenuItem icon="file-plus-outline" @select="state.tab = 'layout'; state.pageWizardOpen = true">{{ t("editor.layout.add_page") }}</UiMenuItem>
          <UiMenuItem icon="view-column-outline" @select="state.tab = 'layout'; state.pagesSheet = true">{{ t("editor.phone.pages_order") }}</UiMenuItem>
          <UiMenuItem icon="page-layout-header" @select="state.tab = 'layout'; openBar(0, state.barPage)">{{ t("editor.page.edit_bar") }}</UiMenuItem>
          <UiMenuSeparator />
          <UiMenuItem v-if="!screen.virtual" icon="cog-outline" @select="phoneSettings">{{ t("editor.screen_view.tabs.settings") }}</UiMenuItem>
          <UiMenuItem v-if="!screen.virtual && pluginsEnabled" icon="puzzle-outline" @select="closeMenu(); closeInspector(); state.tab = 'plugins'">{{ t("editor.screen_view.tabs.plugins") }}</UiMenuItem>
          <UiMenuItem v-if="!screen.virtual" icon="pencil-outline" @select="phoneRename">{{ t("editor.sidebar.rename.button") }}</UiMenuItem>
          <UiMenuSeparator />
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
        <template v-if="narrowPhone">
          <UiMenuSeparator />
          <UiMenuItem v-if="phone" icon="monitor-dashboard" @select="setFullEditor(true)">{{ t("editor.phone.full_editor") }}</UiMenuItem>
          <UiMenuItem v-else icon="cellphone" @select="setFullEditor(false)">{{ t("editor.phone.simple_editor") }}</UiMenuItem>
        </template>
      </UiMenu>
      <input ref="fileInput" type="file" accept="application/json,.json" hidden @change="onFile" />
    </div>
  </header>
  <FeedbackPanel v-if="screen.feedback?.available" :key="`card-${screen.id}`" :screen="screen" mode="card" />
  <div class="body" id="body">
    <div class="work">
      <LayoutView v-if="state.tab === 'layout'" />
      <SettingsTab v-else-if="state.tab === 'settings'" />
      <ScreenPluginsTab v-else />
    </div>
    <Drawer />
  </div>
  <!-- The phone's one button (app 0.4.40): add a tile, and once something changed, send it to the screen. -->
  <div v-if="phone && state.tab === 'layout' && state.layout" class="phone-dock">
    <button type="button" id="phone-add" class="btn" :class="state.dirty ? 'soft square' : 'primary'" :disabled="full"
      :aria-label="t('editor.phone.add_tile')" :title="full ? t('editor.library.full', tileLimit) : ''" @click="phoneAdd">
      <Icon name="plus" /><span v-if="!state.dirty">{{ t("editor.phone.add_tile") }}</span>
    </button>
    <button v-if="state.dirty" type="button" id="save" class="btn primary" :disabled="state.busy" @click="save()">
      <span v-if="state.busy" class="spin small"></span><Icon v-else name="tray-arrow-up" />{{ state.busy ? t("editor.common.saving") : t(screen.virtual ? "editor.preview.save" : "editor.common.save_send") }}
    </button>
  </div>
</template>
