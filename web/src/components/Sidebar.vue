<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { vTooltip } from "floating-vue";
import "floating-vue/dist/style.css";
import { t } from "../i18n";
import { boardTitle } from "../model/boards";
import { languageOnly } from "../model/screen-status";
import { glyph } from "../model/topbar";
import {
  copyText, forgetPending, go, goHome, newLanguageText, openIntegrations, refresh, removeScreen, renameScreen, route, screenSubline,
  buildOf, buildingScreens, buildProgress, select, startUpdate, state, updateState, whatsNew,
} from "../store";
import type { Screen } from "../types";
import Icon from "./ui/Icon.vue";
import TesseraMark from "./TesseraMark.vue";
import { pluginsEnabled } from "../plugin-state";
import { SIDE_MAX, SIDE_MIN, dragSidebar, resetSidebar, sideWidth, sidebar, toggleSidebar } from "../sidebar-state";
import { useResizeHandle } from "../composables/useResizeHandle";

const hostFor = ref<string | null>(null);
const host = ref("");
// The screen that asked to be removed: its details make room for what goes, until it is confirmed or dropped.
const removeFor = ref<string | null>(null);
async function remove(screen: Screen) {
  if (await removeScreen(screen)) removeFor.value = null;
}
// Rename (app 0.4.2): a label in this app only, so it takes effect at once, without a flash.
const renameFor = ref<string | null>(null);
const newName = ref("");
function startRename(screen: Screen) {
  renameFor.value = screen.id;
  newName.value = screen.name;
}
async function saveName(screen: Screen) {
  if (await renameScreen(screen, newName.value)) renameFor.value = null;
}
// The details under a screen's name (app 0.4.0): a screen that asks for a look (away, an update, a failure) opens them
// when it is chosen; a healthy one keeps them folded behind the chevron at its right. The chevron's choice holds
// while the screen stays chosen.
const folded = ref<{ id: string; open: boolean } | null>(null);
const subline = screenSubline;
// The row says one thing at most, on its right (app 0.4.32): the update's button, its progress, or why it is quiet.
const status = (screen: Screen) => {
  const kind = updateState(screen)?.kind;
  if (screen.virtual) return "virtual";
  if (!screen.online) return "down";
  if (kind === "running" || kind === "queued") return "running";
  if (kind === "available" && screen.update?.profile) return "update";
  if (kind === "failed") return "failed";
  return kind === "blocked" || kind === "available" ? "waiting" : "";
};
const isSelected = (screen: Screen) => screen.id === state.selected && route.value === "";
// Only a screen with something to explain opens by itself (app 0.4.32): an update that failed or waits for a build.
// An update ready to go has its button on the row; a screen that is away says so there.
// So does one that has to be updated here rather than in ESPHome Device Builder (app 0.4.82), while an update waits.
const explains = (screen: Screen) => ["failed", "blocked"].includes(updateState(screen)?.kind || "")
  || Boolean(screen.update_in_tessera && updateState(screen)?.kind === "available");
// Folded to its icons the sidebar has no room for a screen's details: the row opens them again.
const isOpen = (screen: Screen) => !sidebar.folded && (folded.value?.id === screen.id ? folded.value.open : isSelected(screen) && explains(screen));
const chevronShown = (screen: Screen) => isSelected(screen) || isOpen(screen);
function choose(screen: Screen) {
  if (!isSelected(screen)) folded.value = null;
  removeFor.value = null;
  select(screen.id);
}
function toggleDetails(screen: Screen) {
  folded.value = { id: screen.id, open: !isOpen(screen) };
  if (!folded.value.open) removeFor.value = null;
}
// The icon: a panel with tiles on it, a phone for a screen standing up, a monitor for a board this app does not know.
// A board it knows carries its catalog entry in its shape (boards.json, app 0.2.129), which also names it.
const standing = (screen: Screen) => Boolean(screen.shape && screen.shape.height > screen.shape.width);
const known = (screen: Screen) => (screen.board && screen.shape?.catalog?.name ? screen.shape.catalog : null);
const boardIcon = (screen: Screen) => glyph(standing(screen) ? "F011C" : known(screen) ? "F0ECE" : "F0A07");
const boardName = (screen: Screen) => { const board = known(screen); return board ? boardTitle(board) : ""; };
// What the update brings: the new language first, when the version changes as well, then the firmware's notes.
// In the sidebar each note is its first sentence, and what was tested stays in the changelog (app 0.4.32): a column this
// narrow can hold a few headlines, not the release notes.
const headline = (line: string) => line.match(/^.*?[.!?](?=\s|$)/)?.[0] || line;
const notes = (screen: Screen) => [...(screen.update?.language && !languageOnly(screen) ? [newLanguageText()] : []),
  ...whatsNew(screen).filter((line) => !/^(Tested|Getest)\b/i.test(line)).map(headline)];
function update(screen: Screen) {
  const u = screen.update || {};
  if (u.host && u.profile) startUpdate(screen);
  else if (u.profile) { hostFor.value = screen.id; host.value = ""; }
}
// The dev channel's own button (docs/RELEASING.md, "Testing dev"): the newest dev keeps the firmware number, so it is
// never an update by itself; this builds and installs it anyway, the way an update does.
const reinstallable = (screen: Screen) => state.inventory.updates?.channel === "dev" && screen.online
  && Boolean(screen.update?.profile && screen.update?.host) && !state.inventory.updates?.busy;
function startWithHost(screen: Screen) {
  const address = host.value.trim();
  if (!address) return;
  hostFor.value = null;
  startUpdate(screen, address);
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
watch(() => [sidebar.width, sidebar.folded, state.inventory.screens.map((screen) => screen.name).join("\n")], remeasure);
onMounted(() => { remeasure(); window.addEventListener("resize", remeasure); });
onBeforeUnmount(() => window.removeEventListener("resize", remeasure));
const tip = (key: string, text: string | undefined, always = false) =>
  text && (sidebar.folded || always || cut.value[key]) ? { content: text, placement: "right", distance: 10, delay: { show: 200, hide: 0 } } : null;
const screenTip = (screen: Screen) => [screen.name, subline(screen)?.text].filter(Boolean).join(" · ");
// The edge: dragged, by the arrow keys (Shift for bigger steps) or reset with a double click (sidebar-state.ts).
let left = 0;
const edge = useResizeHandle({
  onStart: () => { left = aside.value?.getBoundingClientRect().left || 0; sidebar.resizing = true; },
  onMove: (e) => dragSidebar(e.clientX - left),
  onEnd: () => { sidebar.resizing = false; },
});
function resizeKey(event: KeyboardEvent) {
  const by = event.shiftKey ? 48 : 16;
  if (event.key === "ArrowLeft") dragSidebar(sideWidth() - by);
  else if (event.key === "ArrowRight") dragSidebar(sidebar.folded ? SIDE_MIN : sideWidth() + by);
  else if (event.key === "Home") resetSidebar();
  else return;
  event.preventDefault();
}
// A plugin build on the way on any screen: the Plugins entry turns.
const pluginBuilds = () => buildingScreens().some((screen) => buildOf(screen)?.by === "plugins");
const lastLog = () => {
  const lines = state.firmwareJob?.logs || [];
  return lines.length ? lines[lines.length - 1] : "";
};
// Tessera adds a screen Home Assistant found by itself (app 0.4.73): it says so while it does, and that it is up to the
// person when Home Assistant asks something only they can answer.
const pendingText = (p: { installed?: boolean; downloaded?: boolean; file: string; seen?: boolean; pairing?: string | null }) => p.pairing === "failed"
  ? t("editor.sidebar.pending.failed")
  : p.seen
    ? t("editor.sidebar.pending.adding")
    : p.installed
      ? t("editor.sidebar.pending.installed")
      : p.downloaded
        ? t("editor.sidebar.pending.downloaded")
        : t("editor.sidebar.pending.not_flashed", { file: p.file });
</script>

<template>
  <aside ref="aside" class="side">
    <div class="side-top">
      <button type="button" class="brand" :aria-label="t('editor.sidebar.home')" :title="sidebar.folded ? undefined : t('editor.sidebar.home')"
        v-tooltip="tip('brand', t('editor.sidebar.home'))" :aria-current="!state.selected && route === '' ? 'page' : undefined" @click="goHome">
        <TesseraMark class="mark" />
        <span class="txt">Tessera</span>
      </button>
      <button type="button" id="side-fold" class="icon-btn side-fold" :aria-pressed="sidebar.folded ? 'true' : 'false'"
        :aria-label="t(sidebar.folded ? 'editor.sidebar.unfold' : 'editor.sidebar.fold')" v-tooltip="tip('fold', t(sidebar.folded ? 'editor.sidebar.unfold' : 'editor.sidebar.fold'), true)"
        @click="toggleSidebar"><Icon name="dock-left" /></button>
    </div>
    <span v-if="!state.reachable || !state.connected" id="connection" class="conn" role="status"
      v-tooltip="tip('conn', !state.reachable ? t('editor.sidebar.connection.unreachable') : t('editor.sidebar.connection.reconnecting'))">
      <Icon name="wifi-off" class="conn-icon" /><span class="conn-text">{{ !state.reachable ? t("editor.sidebar.connection.unreachable") : t("editor.sidebar.connection.reconnecting") }}</span>
    </span>
    <button type="button" class="search-btn" id="open-palette" data-tip="search" v-tooltip="tip('search', `${t('editor.sidebar.search')} ⌘K`)" :aria-label="t('editor.sidebar.search')"
      @click="state.palette = true"><Icon name="magnify" /><span class="txt">{{ t("editor.sidebar.search") }}</span><kbd>⌘K</kbd></button>
    <div class="label label-row">
      <span>{{ t("editor.sidebar.screens") }}</span>
      <button id="refresh" type="button" class="icon-btn" :aria-label="t('editor.sidebar.refresh')" :title="t('editor.sidebar.refresh')" @click="refresh()"><Icon name="refresh" /></button>
      <button id="new-screen" type="button" class="icon-btn" :aria-current="route === '#new-screen' ? 'true' : 'false'" :aria-label="t('editor.nav.new_screen')"
        :title="sidebar.folded ? undefined : t('editor.nav.new_screen')" v-tooltip="tip('new', t('editor.nav.new_screen'))" @click="go('#new-screen')"><Icon name="plus" /></button>
    </div>
    <div id="screens">
      <div v-for="screen in state.inventory.screens" :key="screen.id" class="screen-item" :class="[{ selected: isSelected(screen), open: isOpen(screen) }, status(screen)]">
        <button type="button" class="nav-item" :data-tip="`screen:${screen.id}`" :aria-current="isSelected(screen) ? 'true' : 'false'"
          :aria-label="screenTip(screen)" :title="tip(`screen:${screen.id}`, screenTip(screen)) ? undefined : subline(screen)?.text"
          v-tooltip="tip(`screen:${screen.id}`, screenTip(screen))" @click="choose(screen)">
          <span class="board-icon mdi" aria-hidden="true">{{ boardIcon(screen) }}</span>
          <!-- Folded, the row keeps its news as a dot on the icon: an update ready, or one that waits. -->
          <span v-if="sidebar.folded && ['update', 'waiting'].includes(status(screen))" class="fold-badge" :class="status(screen)" aria-hidden="true"></span>
          <span class="name">{{ screen.name }}</span>
          <span v-if="screen.id === state.selected && state.dirty" class="unsaved" role="img" :aria-label="t('editor.common.unsaved')" :title="t('editor.common.unsaved')"></span>
          <span v-if="status(screen) === 'running'" class="spin small" role="img" :aria-label="subline(screen)?.text"></span>
          <Icon v-else-if="status(screen) === 'failed'" name="alert-circle-outline" class="sub-icon failed" />
          <small v-else-if="['down', 'virtual', 'waiting'].includes(status(screen))" class="sub" :class="subline(screen)?.kind">{{ status(screen) === 'waiting' ? t("editor.sidebar.update.short") : subline(screen)?.text }}</small>
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
              <button type="button" class="btn mini danger" :disabled="Boolean(state.removing)" @click="remove(screen)">
                <span v-if="state.removing === screen.id" class="spin small"></span>{{ t("editor.sidebar.remove.confirm") }}
              </button>
              <button type="button" class="btn link mini" :disabled="Boolean(state.removing)" @click="removeFor = null">{{ t("editor.common.cancel") }}</button>
            </div>
          </div>
        </div>
        <div v-else-if="isOpen(screen)" class="screen-details">
          <dl class="facts">
            <template v-if="screen.area"><dt>{{ t("editor.sidebar.details.room") }}</dt><dd>{{ screen.area }}</dd></template>
            <dt>{{ t("editor.sidebar.details.firmware") }}</dt>
            <dd>{{ screen.firmware || t("editor.common.unknown") }}<template v-if="updateState(screen)?.kind === 'available' && !languageOnly(screen)"> → {{ screen.update?.target }}</template></dd>
            <template v-if="boardName(screen)"><dt>{{ t("editor.sidebar.details.board") }}</dt><dd>{{ boardName(screen) }}</dd></template>
          </dl>
          <!-- A screen with 4 MB of flash on ESPHome's partition table (app 0.4.82): update it here, which moves the table. -->
          <details v-if="screen.update_in_tessera" class="whatsnew in-tessera">
            <summary class="act"><Icon name="information-outline" />{{ t("editor.sidebar.update.in_tessera") }}</summary>
            <p>{{ t("editor.sidebar.update.in_tessera_why") }}</p>
          </details>
          <div v-if="updateState(screen)" class="screen-update" :class="updateState(screen)!.kind">
            <template v-if="updateState(screen)!.kind === 'available'">
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
            <template v-else-if="updateState(screen)!.kind === 'running' && buildProgress(screen)">
              <div class="progress" role="progressbar" :aria-valuenow="buildProgress(screen)!.percent" aria-valuemin="0" aria-valuemax="100"><i :style="{ width: buildProgress(screen)!.percent + '%' }"></i></div>
              <div class="progress-text"><span>{{ buildProgress(screen)!.percent }} %</span><span :title="lastLog()">{{ buildProgress(screen)!.text }}</span></div>
              <small v-if="lastLog()" :title="lastLog()" style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis">{{ lastLog() }}</small>
              <button type="button" class="btn link mini" style="justify-self: start" @click="go('#firmware')">{{ t("editor.sidebar.update.full_log") }}</button>
            </template>
            <small v-else-if="updateState(screen)!.kind !== 'running'" :class="{ failed: updateState(screen)!.kind === 'failed' }">{{ updateState(screen)!.text }}</small>
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
            <button v-if="reinstallable(screen)" type="button" class="act reinstall-dev" :title="t('editor.sidebar.update.reinstall_why')" @click="startUpdate(screen, undefined, true)"><Icon name="update" />{{ t("editor.sidebar.update.reinstall") }}</button>
            <button v-if="renameFor !== screen.id" type="button" class="act rename-screen" @click="startRename(screen)"><Icon name="pencil-outline" />{{ t("editor.sidebar.rename.button") }}</button>
            <!-- The screen's YAML, Override YAML and the secrets they use, to build it with ESPHome on your own computer. -->
            <a v-if="screen.update?.profile" class="act screen-files" :href="`api/firmware/profiles/${encodeURIComponent(screen.update.profile)}/files`" download
              :title="t('editor.sidebar.files_hint')"><Icon name="tray-arrow-down" />{{ t("editor.sidebar.files") }}</a>
            <button v-if="screen.api_key" type="button" class="act copy-key" @click="copyText(screen.api_key!)"><Icon name="content-copy" />{{ t("editor.sidebar.copy_api_key") }}</button>
            <button type="button" class="act danger remove-screen" @click="removeFor = screen.id"><Icon name="delete-outline" />{{ t("editor.sidebar.remove.button") }}</button>
          </div>
        </div>
      </div>
    </div>
    <div id="pending">
      <!-- Folded, a screen on its way in is its icon; a click opens the sidebar for what can be done with it. -->
      <button v-for="p in sidebar.folded ? state.inventory.pending || [] : []" :key="`folded:${p.file}`" type="button" class="nav-item pending-folded"
        :aria-label="`${p.friendly} · ${pendingText(p)}`" v-tooltip="tip('pending', `${p.friendly} · ${pendingText(p)}`)" @click="toggleSidebar">
        <span v-if="p.seen && p.pairing !== 'failed'" class="spin small"></span><span v-else class="mdi board-icon">{{ glyph("F0ECE") }}</span>
      </button>
      <div v-for="p in sidebar.folded ? [] : state.inventory.pending || []" :key="p.file" class="pending">
        <strong>{{ p.friendly }}</strong>
        <small><span v-if="p.seen && p.pairing !== 'failed'" class="spin small"></span>{{ pendingText(p) }}</small>
        <div v-if="removeFor === `pending:${p.file}`" class="screen-remove">
          <strong>{{ t("editor.sidebar.remove.title", { name: p.friendly }) }}</strong>
          <ul><li>{{ t("editor.sidebar.remove.profile", { file: p.file }) }}</li></ul>
          <div class="pending-actions">
            <button type="button" class="btn mini danger forget-pending" :disabled="Boolean(state.removing)" @click="forgetPending(p.file, p.friendly).then((done) => { if (done) removeFor = null; })">
              <span v-if="state.removing === `pending:${p.file}`" class="spin small"></span>{{ t("editor.sidebar.remove.confirm") }}
            </button>
            <button type="button" class="btn link mini" :disabled="Boolean(state.removing)" @click="removeFor = null">{{ t("editor.common.cancel") }}</button>
          </div>
        </div>
        <div v-else class="pending-actions">
          <!-- Tessera adds it to Home Assistant by itself (app 0.4.73); the way by hand only when that did not work out. -->
          <button v-if="p.pairing === 'failed'" type="button" class="btn mini quiet" @click="openIntegrations">{{ t("editor.common.open_integrations") }}</button>
          <button type="button" class="btn link mini danger remove-pending" @click="removeFor = `pending:${p.file}`">{{ t("editor.sidebar.remove.button") }}</button>
        </div>
        <details v-if="p.api_key && p.pairing === 'failed'" class="key-more">
          <summary>{{ t("editor.installer.key_more") }}</summary>
          <button type="button" class="btn link mini copy-key" @click="copyText(p.api_key!)">{{ t("editor.sidebar.copy_api_key") }}</button>
        </details>
        <a class="btn link mini screen-files" :href="`api/firmware/profiles/${encodeURIComponent(p.file)}/files`" download :title="t('editor.sidebar.files_hint')">{{ t("editor.sidebar.files") }}</a>
      </div>
    </div>
    <div class="spacer"></div>
    <div class="more">
      <!-- The firmware tool (build, USB, OTA, download) is for repairs, not for adding a screen, so it lives in Settings,
           the command palette and a screen's menu rather than here, where it read as the way in (app 0.3.27). -->
      <button v-if="pluginsEnabled" id="open-plugins" type="button" class="nav-item" data-tip="plugins" v-tooltip="tip('plugins', t('editor.nav.plugins'))" :aria-current="route === '#plugins' ? 'true' : 'false'" @click="go('#plugins')"><Icon name="puzzle-outline"/><span class="txt">{{ t("editor.nav.plugins") }}</span><span v-if="pluginBuilds()" class="spin small" role="img" :aria-label="t('editor.build.plugins')"></span></button>
      <button id="open-alerts" type="button" class="nav-item" data-tip="alerts" v-tooltip="tip('alerts', t('editor.nav.alerts'))" :aria-current="route === '#alerts' ? 'true' : 'false'" @click="go('#alerts')"><span class="mdi">{{ glyph("F0594") }}</span><span class="txt">{{ t("editor.nav.alerts") }}</span></button>
      <button id="open-settings" type="button" class="nav-item" data-tip="settings" v-tooltip="tip('settings', t('editor.nav.settings'))" :aria-current="route === '#settings' ? 'true' : 'false'" @click="go('#settings')"><span class="mdi">{{ glyph("F0493") }}</span><span class="txt">{{ t("editor.nav.settings") }}</span></button>
    </div>
    <!-- The edge (app 0.4.85): drag it wider or narrower, past the narrowest it folds to the icons; a double click resets it. -->
    <div class="side-resize" role="separator" aria-orientation="vertical" tabindex="0" :aria-label="t('editor.sidebar.resize')"
      :aria-valuenow="sideWidth()" :aria-valuemin="SIDE_MIN" :aria-valuemax="SIDE_MAX" :title="t('editor.sidebar.resize')"
      @pointerdown="edge.start" @dblclick="resetSidebar" @keydown="resizeKey"></div>
  </aside>
</template>
