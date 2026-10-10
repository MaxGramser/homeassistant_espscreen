<script setup lang="ts">
import { useResizeObserver } from "@vueuse/core";
import { nextTick, onMounted, ref, watch } from "vue";
import { vTooltip } from "floating-vue";
import "floating-vue/dist/style.css";
import { t } from "../i18n";
import { explainsItself, languageOnly, pendingText, rowStatus, screenBoardName, screenIcon, updateNotes } from "../model/screen-status";
import { glyph } from "../model/topbar";
import { summaryText } from "../model/broken-tiles";
import type { Screen } from "../types";
import Icon from "./ui/Icon.vue";
import TesseraMark from "./TesseraMark.vue";
import BuildIndicator from "./BuildIndicator.vue";
import BrokenList from "./BrokenList.vue";
import { PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger } from "reka-ui";
import ProgressRing from "./ui/ProgressRing.vue";
import { SIDE_MAX, SIDE_MIN, useSidebarStore } from "../stores/sidebar";
import { useResizeHandle } from "../composables/useResizeHandle";
import { useUiStore } from "../stores/ui";
import { useBuildsStore } from "../stores/builds";
import { usePluginsStore } from "../stores/plugins";
import { useScreenStore } from "../stores/screen";
import { useSessionStore } from "../stores/session";
import { useInventoryStore } from "../stores/inventory";
import { useDocumentStore } from "../stores/document";
import { useBrokenStore } from "../stores/broken";

const ui = useUiStore();
const sidebar = useSidebarStore();
const builds = useBuildsStore();
const plugins = usePluginsStore();
const scr = useScreenStore();
const session = useSessionStore();
const inv = useInventoryStore();
const doc = useDocumentStore();
const broken = useBrokenStore();

const hostFor = ref<string | null>(null);
const host = ref("");
// The screen that asked to be removed: its details make room for what goes, until it is confirmed or dropped.
const removeFor = ref<string | null>(null);
async function remove(screen: Screen) {
  if (await session.removeScreen(screen)) removeFor.value = null;
}
// Rename (app 0.4.2): a label in this app only, so it takes effect at once, without a flash.
const renameFor = ref<string | null>(null);
const newName = ref("");
function startRename(screen: Screen) {
  renameFor.value = screen.id;
  newName.value = screen.name;
}
async function saveName(screen: Screen) {
  if (await scr.renameScreen(screen, newName.value)) renameFor.value = null;
}
// The details under a screen's name (app 0.4.0): a screen that asks for a look (away, an update, a failure) opens them
// when it is chosen; a healthy one keeps them folded behind the chevron at its right. The chevron's choice holds
// while the screen stays chosen.
const folded = ref<{ id: string; open: boolean } | null>(null);
const subline = scr.screenSubline;
// The row says one thing at most, on its right (app 0.4.32): the update's button, its progress, or why it is quiet.
const status = (screen: Screen) => rowStatus(screen, scr.updateState(screen)?.kind);
const isSelected = (screen: Screen) => screen.id === scr.selected && ui.route === "";
// Only a screen with something to explain opens by itself (model/screen-status.ts explainsItself).
const explains = (screen: Screen) => explainsItself(screen, scr.updateState(screen)?.kind);
// Folded to its icons the sidebar has no room for a screen's details: the row opens them again.
const isOpen = (screen: Screen) => !sidebar.folded && (folded.value?.id === screen.id ? folded.value.open : isSelected(screen) && explains(screen));
const chevronShown = (screen: Screen) => isSelected(screen) || isOpen(screen);
function choose(screen: Screen) {
  if (!isSelected(screen)) folded.value = null;
  removeFor.value = null;
  session.select(screen.id);
}
function toggleDetails(screen: Screen) {
  folded.value = { id: screen.id, open: !isOpen(screen) };
  if (!folded.value.open) removeFor.value = null;
}
// The icon and the board of a screen, and what its update brings (model/screen-status.ts).
const boardIcon = (screen: Screen) => glyph(screenIcon(screen));
const boardName = screenBoardName;
const notes = (screen: Screen) => updateNotes(screen, builds.whatsNew(screen), scr.newLanguageText);
function update(screen: Screen) {
  const u = screen.update || {};
  if (u.host && u.profile) builds.startUpdate(screen);
  else if (u.profile) { hostFor.value = screen.id; host.value = ""; }
}
// The dev channel's own button (docs/RELEASING.md, "Testing dev"): the newest dev keeps the firmware number, so it is
// never an update by itself; this builds and installs it anyway, the way an update does.
const reinstallable = (screen: Screen) => inv.inventory.updates?.channel === "dev" && screen.online
  && Boolean(screen.update?.profile && screen.update?.host) && !inv.inventory.updates?.busy;
function startWithHost(screen: Screen) {
  const address = host.value.trim();
  if (!address) return;
  hostFor.value = null;
  builds.startUpdate(screen, address);
}
// Folded to its icons (app 0.4.85) every row says what it is in a tooltip beside it; open, only a row whose name is
// cut short does, with its whole name. Which names are cut is measured when the width or the list changes.
const aside = ref<HTMLElement>();
const cut = ref<Record<string, boolean>>({});
function measure() {
  const found: Record<string, boolean> = {};
  aside.value?.querySelectorAll<HTMLElement>("[data-tip]").forEach((row) => {
    const text = row.querySelector<HTMLElement>(".name, .txt");
    found[row.dataset.tip!] = !!text && text.scrollWidth > text.clientWidth + 1;
  });
  cut.value = found;
}
const remeasure = () => nextTick(measure);
watch(() => [sidebar.width, sidebar.folded, inv.inventory.screens.map((screen) => screen.name).join("\n")], remeasure);
onMounted(remeasure);
// And whenever the sidebar itself changes size (the window, a phone turned).
useResizeObserver(aside, remeasure);
const tip = (key: string, text: string | undefined, always = false) =>
  text && (sidebar.folded || always || cut.value[key]) ? { content: text, placement: "right", distance: 10, delay: { show: 200, hide: 0 } } : null;
const screenTip = (screen: Screen) => [screen.name, subline(screen)?.text].filter(Boolean).join(" · ");
// The edge: dragged, by the arrow keys (Shift for bigger steps) or reset with a double click (stores/sidebar.ts).
let left = 0;
const edge = useResizeHandle({
  onStart: () => { left = aside.value?.getBoundingClientRect().left || 0; sidebar.resizing = true; },
  onMove: (e) => sidebar.drag(e.clientX - left),
  onEnd: () => { sidebar.resizing = false; },
});
function resizeKey(event: KeyboardEvent) {
  const by = event.shiftKey ? 48 : 16;
  if (event.key === "ArrowLeft") sidebar.drag(sidebar.shownWidth - by);
  else if (event.key === "ArrowRight") sidebar.drag(sidebar.folded ? SIDE_MIN : sidebar.shownWidth + by);
  else if (event.key === "Home") sidebar.reset();
  else return;
  event.preventDefault();
}
// Tiles whose entity is gone or away for a while (stores/broken.ts): a quiet dot on a screen's row when it has nothing
// else to say, the tiles in its details, and one row under the screens for all of them, opening their list.
const brokenOn = (screen: Screen) => broken.onScreen(screen);
const brokenOpen = ref(false);
// A plugin build on the way on any screen: the Plugins entry turns.
const pluginBuilds = () => builds.buildingScreens.some((screen) => builds.buildOf(screen)?.by === "plugins");
const lastLog = () => {
  const lines = builds.firmwareJob?.logs || [];
  return lines.length ? lines[lines.length - 1] : "";
};
</script>

<template>
  <aside ref="aside" class="side">
    <div class="side-top">
      <button type="button" class="brand" :aria-label="t('editor.sidebar.home')" :title="sidebar.folded ? undefined : t('editor.sidebar.home')"
        v-tooltip="tip('brand', t('editor.sidebar.home'))" :aria-current="!scr.selected && ui.route === '' ? 'page' : undefined" @click="session.goHome">
        <TesseraMark class="mark" />
        <span class="txt">Tessera</span>
      </button>
      <BuildIndicator />
      <button type="button" id="side-fold" class="icon-btn side-fold" :aria-pressed="sidebar.folded ? 'true' : 'false'"
        :aria-label="t(sidebar.folded ? 'editor.sidebar.unfold' : 'editor.sidebar.fold')" v-tooltip="tip('fold', t(sidebar.folded ? 'editor.sidebar.unfold' : 'editor.sidebar.fold'), true)"
        @click="sidebar.toggle()"><Icon name="dock-left" /></button>
    </div>
    <!-- The add-on out of reach is the line over the page's (ConnectionBar); here only Home Assistant away from the add-on. -->
    <span v-if="inv.reachable && !inv.connected" id="connection" class="conn" role="status" v-tooltip="tip('conn', t('editor.sidebar.connection.reconnecting'))">
      <Icon name="wifi-off" class="conn-icon" /><span class="conn-text">{{ t("editor.sidebar.connection.reconnecting") }}</span>
    </span>
    <button type="button" class="search-btn" id="open-palette" data-tip="search" v-tooltip="tip('search', `${t('editor.sidebar.search')} ⌘K`)" :aria-label="t('editor.sidebar.search')"
      @click="ui.palette = true"><Icon name="magnify" /><span class="txt">{{ t("editor.sidebar.search") }}</span><kbd>⌘K</kbd></button>
    <div class="label label-row">
      <span>{{ t("editor.sidebar.screens") }}</span>
      <button id="refresh" type="button" class="icon-btn" :aria-label="t('editor.sidebar.refresh')" :title="t('editor.sidebar.refresh')" @click="inv.refresh()"><Icon name="refresh" /></button>
      <button id="new-screen" type="button" class="icon-btn" :aria-current="ui.route === '#new-screen' ? 'true' : 'false'" :aria-label="t('editor.nav.new_screen')"
        :title="sidebar.folded ? undefined : t('editor.nav.new_screen')" v-tooltip="tip('new', t('editor.nav.new_screen'))" @click="ui.go('#new-screen')"><Icon name="plus" /></button>
    </div>
    <div id="screens">
      <div v-for="screen in inv.inventory.screens" :key="screen.id" class="screen-item" :class="[{ selected: isSelected(screen), open: isOpen(screen) }, status(screen)]">
        <button type="button" class="nav-item" :data-tip="`screen:${screen.id}`" :aria-current="isSelected(screen) ? 'true' : 'false'"
          :aria-label="screenTip(screen)" :title="tip(`screen:${screen.id}`, screenTip(screen)) ? undefined : subline(screen)?.text"
          v-tooltip="tip(`screen:${screen.id}`, screenTip(screen))" @click="choose(screen)">
          <span class="board-icon mdi" aria-hidden="true">{{ boardIcon(screen) }}</span>
          <!-- Folded, the row keeps its news as a dot on the icon: an update ready, or one that waits. -->
          <span v-if="sidebar.folded && ['update', 'waiting'].includes(status(screen))" class="fold-badge" :class="status(screen)" aria-hidden="true"></span>
          <span class="name">{{ screen.name }}</span>
          <span v-if="screen.id === scr.selected && doc.dirty" class="unsaved" role="img" :aria-label="t('editor.common.unsaved')" :title="t('editor.common.unsaved')"></span>
          <ProgressRing v-if="status(screen) === 'running'" class="row-ring" :percent="builds.buildProgress(screen)?.percent ?? 0" :label="subline(screen)?.text || ''" />
          <Icon v-else-if="status(screen) === 'failed'" name="alert-circle-outline" class="sub-icon failed" />
          <small v-else-if="['down', 'virtual', 'waiting'].includes(status(screen))" class="sub" :class="subline(screen)?.kind">{{ status(screen) === 'waiting' ? t("editor.sidebar.update.short") : subline(screen)?.text }}</small>
          <span v-else-if="brokenOn(screen).length" class="broken-dot" role="img" :aria-label="t('editor.broken.short', brokenOn(screen).length)" :title="t('editor.broken.short', brokenOn(screen).length)"></span>
        </button>
        <span class="row-end">
          <!-- The one button an update needs, always in the list: an icon, so the name keeps its room; its words in the tooltip. -->
          <button v-if="status(screen) === 'update'" type="button" class="update-pill" :title="`${t('editor.sidebar.update.button')} · ${subline(screen)?.text}`" :aria-label="`${t('editor.sidebar.update.button')}: ${screen.name}`" @click="update(screen)"><Icon name="update" /></button>
          <button type="button" class="details-toggle" :aria-expanded="isOpen(screen) ? 'true' : 'false'"
            :aria-label="t(isOpen(screen) ? 'editor.sidebar.details.hide' : 'editor.sidebar.details.show', { name: screen.name })"
            :title="t(isOpen(screen) ? 'editor.sidebar.details.hide' : 'editor.sidebar.details.show', { name: screen.name })" @click="toggleDetails(screen)">
            <Icon name="chevron-down" />
          </button>
        </span>
        <div v-if="isOpen(screen) && removeFor === screen.id" class="screen-details asking">
          <div class="screen-remove">
            <strong>{{ t("editor.sidebar.remove.title", { name: screen.name }) }}</strong>
            <ul>
              <li v-if="!screen.virtual">{{ t("editor.sidebar.remove.ha") }}</li>
              <li v-if="screen.update?.profile">{{ t("editor.sidebar.remove.profile", { file: screen.update.profile }) }}</li>
              <li>{{ t(screen.virtual ? "editor.preview.remove" : "editor.sidebar.remove.layout") }}</li>
            </ul>
            <small v-if="screen.online" class="warn">{{ t("editor.sidebar.remove.online") }}</small>
            <div class="screen-actions">
              <button type="button" class="btn mini danger" :disabled="Boolean(scr.removing)" @click="remove(screen)">
                <span v-if="scr.removing === screen.id" class="spin small"></span>{{ t("editor.sidebar.remove.confirm") }}
              </button>
              <button type="button" class="btn link mini" :disabled="Boolean(scr.removing)" @click="removeFor = null">{{ t("editor.common.cancel") }}</button>
            </div>
          </div>
        </div>
        <div v-else-if="isOpen(screen)" class="screen-details">
          <dl class="facts">
            <template v-if="screen.area"><dt>{{ t("editor.sidebar.details.room") }}</dt><dd>{{ screen.area }}</dd></template>
            <dt>{{ t("editor.sidebar.details.firmware") }}</dt>
            <dd>{{ screen.firmware || t("editor.common.unknown") }}<template v-if="scr.updateState(screen)?.kind === 'available' && !languageOnly(screen)"> → {{ screen.update?.target }}</template></dd>
            <template v-if="boardName(screen)"><dt>{{ t("editor.sidebar.details.board") }}</dt><dd>{{ boardName(screen) }}</dd></template>
          </dl>
          <!-- A screen with 4 MB of flash on ESPHome's partition table (app 0.4.82): update it here, which moves the table. -->
          <details v-if="screen.update_in_tessera" class="whatsnew in-tessera">
            <summary class="act"><Icon name="information-outline" />{{ t("editor.sidebar.update.in_tessera") }}</summary>
            <p>{{ t("editor.sidebar.update.in_tessera_why") }}</p>
          </details>
          <div v-if="scr.updateState(screen)" class="screen-update" :class="scr.updateState(screen)!.kind">
            <template v-if="scr.updateState(screen)!.kind === 'available'">
              <template v-if="hostFor === screen.id">
                <small>{{ t("editor.sidebar.host.hint") }}</small>
                <form class="screen-host" @submit.prevent="startWithHost(screen)">
                  <input v-model="host" :placeholder="t('editor.sidebar.host.placeholder')" required pattern="[A-Za-z0-9][A-Za-z0-9.\-]*" :aria-label="t('editor.sidebar.host.label')" autofocus />
                  <button type="submit" class="btn mini primary">{{ t("editor.sidebar.host.start") }}</button>
                  <button type="button" class="icon-btn" :aria-label="t('editor.common.cancel')" @click="hostFor = null">✕</button>
                </form>
              </template>
              <small v-else-if="!screen.update?.profile" class="warn">{{ t("editor.sidebar.update.no_profile") }}</small>
              <details v-if="notes(screen).length" class="whatsnew">
                <summary class="act"><Icon name="information-outline" />{{ t("editor.sidebar.update.whats_new") }}</summary>
                <ul><li v-for="line in notes(screen).slice(0, 5)" :key="line">{{ line }}</li></ul>
              </details>
            </template>
            <template v-else-if="scr.updateState(screen)!.kind === 'running' && builds.buildProgress(screen)">
              <div class="progress" role="progressbar" :aria-valuenow="builds.buildProgress(screen)!.percent" aria-valuemin="0" aria-valuemax="100"><i :style="{ width: builds.buildProgress(screen)!.percent + '%' }"></i></div>
              <div class="progress-text"><span>{{ builds.buildProgress(screen)!.percent }} %</span><span :title="lastLog()">{{ builds.buildProgress(screen)!.text }}</span></div>
              <small v-if="lastLog()" :title="lastLog()" style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis">{{ lastLog() }}</small>
              <button type="button" class="btn link mini" style="justify-self: start" @click="ui.go('#firmware')">{{ t("editor.sidebar.update.full_log") }}</button>
            </template>
            <small v-else-if="scr.updateState(screen)!.kind !== 'running'" :class="{ failed: scr.updateState(screen)!.kind === 'failed' }">{{ scr.updateState(screen)!.text }}</small>
          </div>
          <div v-if="brokenOn(screen).length" class="screen-broken">
            <small class="screen-broken-head">{{ t("editor.broken.short", brokenOn(screen).length) }}</small>
            <BrokenList :tiles="brokenOn(screen)" :with-screen="false" />
          </div>
          <form v-if="renameFor === screen.id" class="rename-screen" @submit.prevent="saveName(screen)">
            <input v-model="newName" :placeholder="screen.ha_name" maxlength="40" :aria-label="t('editor.sidebar.rename.label')" autofocus @keydown.esc="renameFor = null" />
            <div class="screen-actions">
              <button type="submit" class="btn mini primary">{{ t("editor.sidebar.rename.save") }}</button>
              <button type="button" class="btn link mini" @click="renameFor = null">{{ t("editor.common.cancel") }}</button>
            </div>
          </form>
          <!-- What can be done with the screen, as the rows of a menu: quiet until pointed at, the one that removes in red. -->
          <div class="screen-actions-list">
            <button v-if="reinstallable(screen)" type="button" class="act reinstall-dev" :title="t('editor.sidebar.update.reinstall_why')" @click="builds.startUpdate(screen, undefined, true)"><Icon name="update" />{{ t("editor.sidebar.update.reinstall") }}</button>
            <button v-if="renameFor !== screen.id" type="button" class="act rename-screen" @click="startRename(screen)"><Icon name="pencil-outline" />{{ t("editor.sidebar.rename.button") }}</button>
            <!-- The screen's YAML, Override YAML and the secrets they use, to build it with ESPHome on your own computer. -->
            <a v-if="screen.update?.profile" class="act screen-files" :href="`api/firmware/profiles/${encodeURIComponent(screen.update.profile)}/files`" download
              :title="t('editor.sidebar.files_hint')"><Icon name="tray-arrow-down" />{{ t("editor.sidebar.files") }}</a>
            <button v-if="screen.api_key" type="button" class="act copy-key" @click="ui.copyText(screen.api_key!)"><Icon name="content-copy" />{{ t("editor.sidebar.copy_api_key") }}</button>
            <button type="button" class="act danger remove-screen" @click="removeFor = screen.id"><Icon name="delete-outline" />{{ t("editor.sidebar.remove.button") }}</button>
          </div>
        </div>
      </div>
    </div>
    <div id="pending">
      <!-- Folded, a screen on its way in is its icon; a click opens the sidebar for what can be done with it. -->
      <button v-for="p in sidebar.folded ? inv.inventory.pending || [] : []" :key="`folded:${p.file}`" type="button" class="nav-item pending-folded"
        :aria-label="`${p.friendly} · ${pendingText(p)}`" v-tooltip="tip('pending', `${p.friendly} · ${pendingText(p)}`)" @click="sidebar.toggle()">
        <span v-if="p.seen && p.pairing !== 'failed'" class="spin small"></span><span v-else class="mdi board-icon">{{ glyph("F0ECE") }}</span>
      </button>
      <div v-for="p in sidebar.folded ? [] : inv.inventory.pending || []" :key="p.file" class="pending">
        <strong>{{ p.friendly }}</strong>
        <small><span v-if="p.seen && p.pairing !== 'failed'" class="spin small"></span>{{ pendingText(p) }}</small>
        <div v-if="removeFor === `pending:${p.file}`" class="screen-remove">
          <strong>{{ t("editor.sidebar.remove.title", { name: p.friendly }) }}</strong>
          <ul><li>{{ t("editor.sidebar.remove.profile", { file: p.file }) }}</li></ul>
          <div class="pending-actions">
            <button type="button" class="btn mini danger forget-pending" :disabled="Boolean(scr.removing)" @click="scr.forgetPending(p.file, p.friendly).then((done) => { if (done) removeFor = null; })">
              <span v-if="scr.removing === `pending:${p.file}`" class="spin small"></span>{{ t("editor.sidebar.remove.confirm") }}
            </button>
            <button type="button" class="btn link mini" :disabled="Boolean(scr.removing)" @click="removeFor = null">{{ t("editor.common.cancel") }}</button>
          </div>
        </div>
        <div v-else class="pending-actions">
          <!-- Tessera adds it to Home Assistant by itself (app 0.4.73); the way by hand only when that did not work out. -->
          <button v-if="p.pairing === 'failed'" type="button" class="btn mini quiet" @click="ui.openIntegrations">{{ t("editor.common.open_integrations") }}</button>
          <button type="button" class="btn link mini danger remove-pending" @click="removeFor = `pending:${p.file}`">{{ t("editor.sidebar.remove.button") }}</button>
        </div>
        <details v-if="p.api_key && p.pairing === 'failed'" class="key-more">
          <summary>{{ t("editor.installer.key_more") }}</summary>
          <button type="button" class="btn link mini copy-key" @click="ui.copyText(p.api_key!)">{{ t("editor.sidebar.copy_api_key") }}</button>
        </details>
        <a class="btn link mini screen-files" :href="`api/firmware/profiles/${encodeURIComponent(p.file)}/files`" download :title="t('editor.sidebar.files_hint')">{{ t("editor.sidebar.files") }}</a>
      </div>
    </div>
    <PopoverRoot v-if="broken.summary" v-model:open="brokenOpen">
      <PopoverTrigger as-child>
        <button type="button" id="broken-tiles-open" class="nav-item broken-nav" data-tip="broken" v-tooltip="tip('broken', t('editor.broken.short', broken.summary.tiles))"
          :aria-label="t('editor.broken.short', broken.summary.tiles)">
          <Icon name="alert-circle-outline" /><span class="txt">{{ t("editor.broken.short", broken.summary.tiles) }}</span>
        </button>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent class="ui-popover broken-pop" side="right" align="start" :side-offset="8" :collision-padding="12">
          <h4>{{ summaryText(broken.summary) }}</h4>
          <BrokenList :tiles="broken.tiles" @done="brokenOpen = false" />
        </PopoverContent>
      </PopoverPortal>
    </PopoverRoot>
    <div class="spacer"></div>
    <div class="more">
      <!-- The firmware tool (build, USB, OTA, download) is for repairs, not for adding a screen, so it lives in Settings,
           the command palette and a screen's menu rather than here, where it read as the way in (app 0.3.27). -->
      <button v-if="plugins.pluginsEnabled" id="open-plugins" type="button" class="nav-item" data-tip="plugins" v-tooltip="tip('plugins', t('editor.nav.plugins'))" :aria-current="ui.route === '#plugins' ? 'true' : 'false'" @click="ui.go('#plugins')"><Icon name="puzzle-outline"/><span class="txt">{{ t("editor.nav.plugins") }}</span><span v-if="pluginBuilds()" class="spin small" role="img" :aria-label="t('editor.build.plugins')"></span></button>
      <button id="open-alerts" type="button" class="nav-item" data-tip="alerts" v-tooltip="tip('alerts', t('editor.nav.alerts'))" :aria-current="ui.route === '#alerts' ? 'true' : 'false'" @click="ui.go('#alerts')"><span class="mdi">{{ glyph("F0594") }}</span><span class="txt">{{ t("editor.nav.alerts") }}</span></button>
      <button id="open-settings" type="button" class="nav-item" data-tip="settings" v-tooltip="tip('settings', t('editor.nav.settings'))" :aria-current="ui.route === '#settings' ? 'true' : 'false'" @click="ui.go('#settings')"><span class="mdi">{{ glyph("F0493") }}</span><span class="txt">{{ t("editor.nav.settings") }}</span></button>
    </div>
    <!-- The edge (app 0.4.85): drag it wider or narrower, past the narrowest it folds to the icons; a double click resets it. -->
    <div class="side-resize" role="separator" aria-orientation="vertical" tabindex="0" :aria-label="t('editor.sidebar.resize')"
      :aria-valuenow="sidebar.shownWidth" :aria-valuemin="SIDE_MIN" :aria-valuemax="SIDE_MAX" :title="t('editor.sidebar.resize')"
      @pointerdown="edge.start" @dblclick="sidebar.reset()" @keydown="resizeKey"></div>
  </aside>
</template>
