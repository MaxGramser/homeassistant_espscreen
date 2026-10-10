<script setup lang="ts">
// One screen: the head with its status, the Layout and Settings tabs, and the inspector in a column on the right.
import { useEventListener, useFileDialog } from "@vueuse/core";
import { computed } from "vue";
import { t } from "../i18n";
import { needsUpdate } from "../model/screen-status";
import { isEditableTarget } from "../composables/isEditableTarget";
import { useConfirm } from "../composables/useConfirm";
import LayoutView from "./LayoutView.vue";
import SettingsTab from "./SettingsTab.vue";
import ScreenPluginsTab from "./ScreenPluginsTab.vue";
import Drawer from "./Drawer.vue";
import FeedbackPanel from "./FeedbackPanel.vue";
import Icon from "./ui/Icon.vue";
import UiMenu from "./ui/UiMenu.vue";
import UiMenuItem from "./ui/UiMenuItem.vue";
import UiMenuLabel from "./ui/UiMenuLabel.vue";
import UiMenuSeparator from "./ui/UiMenuSeparator.vue";
import UiMenuSub from "./ui/UiMenuSub.vue";
import { useUiStore } from "../stores/ui";
import { useBuildsStore } from "../stores/builds";
import { usePluginsStore } from "../stores/plugins";
import { useScreenStore } from "../stores/screen";
import { useSessionStore } from "../stores/session";
import { useInventoryStore } from "../stores/inventory";
import { removeTile } from "../editor/tiles";
import { useDocumentStore } from "../stores/document";
import { useInspectorStore } from "../stores/inspector";

const ui = useUiStore();
const builds = useBuildsStore();
const plugins = usePluginsStore();
const scr = useScreenStore();
const session = useSessionStore();
const inv = useInventoryStore();
const doc = useDocumentStore();
const insp = useInspectorStore();

const screen = computed(() => scr.currentScreen!);
const statusText = computed(() => screen.value.virtual ? t("editor.preview.virtual") : screen.value.online
  ? `${screen.value.delivery} · ${screen.value.status}`
  : t("editor.screen_view.offline"));
// The head says whether the screen is there in one word; the details of its delivery stay in the chip's tooltip.
const statusKind = computed(() => !screen.value.online ? "off" : screen.value.in_sync ? "good" : "update");
const statusWord = computed(() => !screen.value.online ? t("editor.common.offline") : screen.value.in_sync ? t("editor.common.online") : t("editor.screen_view.sending"));
const updateReady = computed(() => needsUpdate(screen.value) && screen.value.online && screen.value.update?.profile && screen.value.update?.host);
const others = computed(() => inv.inventory.screens.filter((s) => s.id !== screen.value.id && s.layout?.tiles?.length));
function closeMenu() { ui.menuOpen = false; }
function openOverride() {
  closeMenu();
  ui.overrideProfile = screen.value.update?.profile || null;
  ui.overrideFriendly = screen.value.name;
  ui.go("#override");
}
function inspectAll() {
  closeMenu();
  doc.selectedTileId = null;
  insp.inspector = { kind: "inspect" };
}
const { confirm, prompt, question } = useConfirm();
async function copyFrom(id: string) {
  closeMenu();
  if (doc.dirty && !(await confirm(t("editor.screen_view.confirm.copy"), { confirm: t("editor.confirm.replace_layout"), danger: true }))) return;
  doc.copyLayoutFrom(id);
}
// Import: the browser's file chooser for a layout file, the same file again as often as it is chosen.
const chooser = useFileDialog({ accept: "application/json,.json", multiple: false, reset: true });
chooser.onChange(async (files) => {
  const file = files?.[0];
  if (!file) return;
  if (doc.dirty && !(await confirm(t("editor.screen_view.confirm.import"), { confirm: t("editor.confirm.replace_layout"), danger: true }))) return;
  doc.importLayout(await file.text());
});
function pickFile() { closeMenu(); chooser.open(); }
// The phone's menu (app 0.4.40) holds what the toolbar and the tabs hold on a wider page.
function phoneBack() {
  if (ui.tab !== "layout") { ui.tab = "layout"; return; }
  session.goHome();
}
const phoneStatus = computed(() => !screen.value.online ? t("editor.common.offline")
  : doc.dirty ? t("editor.phone.not_sent") : screen.value.in_sync ? t("editor.phone.on_screen") : t("editor.screen_view.sending"));
function phoneSettings() { closeMenu(); insp.closeInspector(); ui.tab = "settings"; }
async function phoneRename() {
  closeMenu();
  const name = await prompt(t("editor.sidebar.rename.label"), screen.value.name, { confirm: t("editor.sidebar.rename.button") });
  if (name && name.trim() && name.trim() !== screen.value.name) scr.renameScreen(screen.value, name.trim());
}
const full = computed(() => (doc.layout?.tiles.length || 0) >= doc.tileLimit);
function phoneAdd() { insp.forgetCell(); insp.closeInspector(); ui.addSheet = true; }
// Escape belongs to the innermost thing open (app 0.4.32): a list of choices or a menu closes and the inspector under it
// stays. Whether one was open is read before it closes, in the capture phase, since it is gone by the time the key
// reaches this handler.
let popoverEscape = false;
function beforeKey(e: KeyboardEvent) {
  popoverEscape = e.key === "Escape" && Boolean(document.querySelector(".ui-popover"));
}
function onKey(e: KeyboardEvent) {
  // A question of the editor's (ConfirmDialog) keeps every key to itself until it is answered.
  if (question.value) return;
  if (e.key === "Escape") {
    if (popoverEscape) return;
    if (ui.menuOpen) closeMenu();
    else if (ui.palette) return;
    else if (insp.inspector && !(e.target as HTMLElement)?.closest?.(".picker")) insp.closeInspector();
  } else if ((e.key === "Delete" || e.key === "Backspace") && !e.defaultPrevented && insp.inspector?.kind === "tile" && doc.currentTile
    && !isEditableTarget(e.target) && !(e.target as HTMLElement)?.closest?.("select, [role='menu'], dialog")) {
    // The selected tile goes, as a selected object does in Keynote (app 0.4.32); Undo brings it back.
    e.preventDefault();
    removeTile(doc.currentTile);
  } else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
    e.preventDefault();
    if (doc.dirty) doc.save();
  } else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z" && !isEditableTarget(e.target)) {
    e.preventDefault();
    if (e.shiftKey) doc.redo(); else doc.undo();
  }
}
useEventListener(document, "keydown", beforeKey, { capture: true });
useEventListener(document, "keydown", onKey);
</script>

<template>
  <header class="main-head">
    <button v-if="ui.phone" type="button" class="phone-back" @click="phoneBack">
      <Icon name="chevron-left" />{{ ui.tab !== "layout" ? t("editor.screen_view.tabs.layout") : t("editor.phone.screens") }}
    </button>
    <div class="head-title">
      <h1 id="screen-name">{{ screen.name }}</h1>
      <span v-if="!ui.phone" id="delivery" class="chip status" :class="statusKind" :title="statusText"><span class="dot"></span>{{ statusWord }}</span>
      <p v-else class="phone-status" :class="{ dirty: doc.dirty }" :title="statusText"><span class="dot" :class="statusKind"></span>{{ phoneStatus }}</p>
    </div>
    <div v-if="!ui.phone" class="seg tabs" role="tablist" :aria-label="screen.name">
      <button type="button" id="tab-layout" role="tab" :aria-pressed="ui.tab === 'layout' ? 'true' : 'false'" :aria-selected="ui.tab === 'layout'" @click="ui.tab = 'layout'">
        <Icon name="view-dashboard-outline" />{{ t("editor.screen_view.tabs.layout") }}
      </button>
      <button v-if="!screen.virtual" type="button" id="tab-settings" role="tab" :aria-pressed="ui.tab === 'settings' ? 'true' : 'false'" :aria-selected="ui.tab === 'settings'" @click="ui.tab = 'settings'; insp.closeInspector()">
        <Icon name="cog-outline" />{{ t("editor.screen_view.tabs.settings") }}
      </button>
      <button v-if="!screen.virtual && plugins.pluginsEnabled" type="button" id="tab-plugins" role="tab" :aria-pressed="ui.tab === 'plugins' ? 'true' : 'false'" :aria-selected="ui.tab === 'plugins'" @click="ui.tab = 'plugins'; insp.closeInspector()">
        <Icon name="puzzle-outline" />{{ t("editor.screen_view.tabs.plugins") }}
        <span v-if="builds.buildOf(screen)?.by === 'plugins'" class="spin small" role="img" :aria-label="t('editor.build.plugins')"></span>
      </button>
    </div>
    <div class="head-right">
      <template v-if="!ui.phone">
      <span v-if="!doc.dirty" id="dirty" class="saved-note" :class="{ sent: doc.saved }"><Icon name="check" />{{ doc.saved ? t(screen.virtual ? "editor.preview.saved" : "editor.screen_view.sent") : t("editor.screen_view.all_saved") }}</span>
      <span v-else id="dirty" class="chip dirty">{{ t("editor.common.unsaved") }}</span>
      </template>
      <button v-if="doc.dirty && !ui.phone" id="save" type="button" class="btn primary" :disabled="doc.busy" title="⌘S" @click="doc.save()">
        <span v-if="doc.busy" class="spin small"></span>{{ doc.busy ? t("editor.common.saving") : t(screen.virtual ? "editor.preview.save" : "editor.common.save_send") }}
      </button>
      <UiMenu v-model:open="ui.menuOpen" width="264px">
        <template #trigger>
          <button id="more" type="button" class="icon-btn" :aria-label="t('editor.screen_view.more')"><Icon name="dots-horizontal" /></button>
        </template>
        <template v-if="ui.phone && doc.layout">
          <div class="phone-menu-row" role="group">
            <button type="button" role="menuitem" @click="closeMenu(); ui.tab = 'layout'; ui.previewOpen = true"><Icon name="play" />{{ t("editor.pages.preview") }}</button>
            <button type="button" role="menuitem" :disabled="!doc.undoCount" @click="doc.undo"><Icon name="undo" />{{ t("editor.common.undo") }}</button>
            <button type="button" role="menuitem" :disabled="!doc.redoCount" @click="doc.redo"><Icon name="redo" />{{ t("editor.pages.redo") }}</button>
          </div>
          <UiMenuItem icon="file-plus-outline" @select="ui.tab = 'layout'; ui.pageWizardOpen = true">{{ t("editor.layout.add_page") }}</UiMenuItem>
          <UiMenuItem icon="view-column-outline" @select="ui.tab = 'layout'; ui.pagesSheet = true">{{ t("editor.phone.pages_order") }}</UiMenuItem>
          <UiMenuItem icon="page-layout-header" @select="ui.tab = 'layout'; insp.openBar(0, doc.barPage)">{{ t("editor.page.edit_bar") }}</UiMenuItem>
          <UiMenuSeparator />
          <UiMenuItem v-if="!screen.virtual" icon="cog-outline" @select="phoneSettings">{{ t("editor.screen_view.tabs.settings") }}</UiMenuItem>
          <UiMenuItem v-if="!screen.virtual && plugins.pluginsEnabled" icon="puzzle-outline" @select="closeMenu(); insp.closeInspector(); ui.tab = 'plugins'">{{ t("editor.screen_view.tabs.plugins") }}</UiMenuItem>
          <UiMenuItem v-if="!screen.virtual" icon="pencil-outline" @select="phoneRename">{{ t("editor.sidebar.rename.button") }}</UiMenuItem>
          <UiMenuSeparator />
        </template>
        <UiMenuLabel>{{ t("editor.screen_view.menu.group_screen") }}</UiMenuLabel>
        <UiMenuItem id="identify" icon="monitor-eye" :hint="t('editor.screen_view.menu.identify_hint')" :disabled="!scr.canAlert(screen) || !screen.online"
          :title="scr.canAlert(screen) ? '' : t('editor.screen_view.menu.identify_needs')" @select="scr.identify(screen)">{{ t("editor.screen_view.menu.identify") }}</UiMenuItem>
        <UiMenuItem id="inspect" icon="database-search-outline" @select="inspectAll">{{ t("editor.common.read_current_data") }}</UiMenuItem>
        <UiMenuItem v-if="updateReady" id="update-screen" icon="update" :hint="screen.update?.target" @select="builds.startUpdate(screen)">{{ t("editor.screen_view.menu.update") }}</UiMenuItem>
        <UiMenuSeparator />
        <UiMenuLabel>{{ t("editor.screen_view.menu.group_layout") }}</UiMenuLabel>
        <UiMenuSub id="copy-layout" icon="content-copy" :label="t('editor.screen_view.menu.copy')" :disabled="!others.length"
          :hint="others.length ? t('editor.screen_view.menu.copy_screens', others.length) : t('editor.screen_view.menu.copy_none')">
          <UiMenuItem v-for="other in others" :key="other.id" icon="monitor-dashboard" :hint="t('editor.screen_view.menu.copy_tiles', other.layout.tiles.length)" @select="copyFrom(other.id)">{{ other.name }}</UiMenuItem>
        </UiMenuSub>
        <UiMenuItem id="export-layout" icon="tray-arrow-down" hint="JSON" @select="doc.exportLayout()">{{ t("editor.screen_view.menu.export") }}</UiMenuItem>
        <UiMenuItem id="import-layout" icon="tray-arrow-up" hint="JSON" @select="pickFile">{{ t("editor.screen_view.menu.import") }}</UiMenuItem>
        <UiMenuSeparator />
        <UiMenuLabel>{{ t("editor.screen_view.menu.group_advanced") }}</UiMenuLabel>
        <UiMenuItem id="open-override" icon="code-braces" :disabled="!screen.update?.profile" :title="screen.update?.profile ? '' : t('editor.screen_view.menu.override_none')" @select="openOverride">{{ t("editor.screen_view.menu.override") }}</UiMenuItem>
        <UiMenuItem icon="flash" @select="ui.go('#firmware')">{{ t("editor.nav.firmware") }}</UiMenuItem>
        <template v-if="ui.narrowPhone">
          <UiMenuSeparator />
          <UiMenuItem v-if="ui.phone" icon="monitor-dashboard" @select="ui.setFullEditor(true)">{{ t("editor.phone.full_editor") }}</UiMenuItem>
          <UiMenuItem v-else icon="cellphone" @select="ui.setFullEditor(false)">{{ t("editor.phone.simple_editor") }}</UiMenuItem>
        </template>
      </UiMenu>
    </div>
  </header>
  <FeedbackPanel v-if="screen.feedback?.available" :key="`card-${screen.id}`" :screen="screen" mode="card" />
  <div class="body" id="body">
    <div class="work">
      <LayoutView v-if="ui.tab === 'layout'" />
      <SettingsTab v-else-if="ui.tab === 'settings'" />
      <ScreenPluginsTab v-else />
    </div>
    <Drawer />
  </div>
  <!-- The phone's one button (app 0.4.40): add a tile, and once something changed, send it to the screen. -->
  <div v-if="ui.phone && ui.tab === 'layout' && doc.layout" class="phone-dock">
    <button type="button" id="phone-add" class="btn" :class="doc.dirty ? 'soft square' : 'primary'" :disabled="full"
      :aria-label="t('editor.phone.add_tile')" :title="full ? t('editor.library.full', doc.tileLimit) : ''" @click="phoneAdd">
      <Icon name="plus" /><span v-if="!doc.dirty">{{ t("editor.phone.add_tile") }}</span>
    </button>
    <button v-if="doc.dirty" type="button" id="save" class="btn primary" :disabled="doc.busy" @click="doc.save()">
      <span v-if="doc.busy" class="spin small"></span><Icon v-else name="tray-arrow-up" />{{ doc.busy ? t("editor.common.saving") : t(screen.virtual ? "editor.preview.save" : "editor.common.save_send") }}
    </button>
  </div>
</template>
