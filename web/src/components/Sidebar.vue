<script setup lang="ts">
import { ref } from "vue";
import { t } from "../i18n";
import { boardTitle } from "../model/boards";
import { glyph } from "../model/topbar";
import {
  copyText, go, goHome, languageOnly, needsAttention, newLanguageText, openIntegrations, refresh, removeScreen, renameScreen, route, screenLight, screenSubline,
  select, startUpdate, state, updateProgress, updateState, whatsNew,
} from "../store";
import type { Screen } from "../types";
import Icon from "./ui/Icon.vue";
import TesseraMark from "./TesseraMark.vue";

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
const light = screenLight, subline = screenSubline;
const isSelected = (screen: Screen) => screen.id === state.selected && route.value === "";
const isOpen = (screen: Screen) => folded.value?.id === screen.id ? folded.value.open : isSelected(screen) && needsAttention(screen);
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
const notes = (screen: Screen) => [...(screen.update?.language && !languageOnly(screen) ? [newLanguageText()] : []), ...whatsNew(screen)];
function update(screen: Screen) {
  const u = screen.update || {};
  if (u.host && u.profile) startUpdate(screen);
  else if (u.profile) { hostFor.value = screen.id; host.value = ""; }
}
function startWithHost(screen: Screen) {
  const address = host.value.trim();
  if (!address) return;
  hostFor.value = null;
  startUpdate(screen, address);
}
const lastLog = () => {
  const lines = state.firmwareJob?.logs || [];
  return lines.length ? lines[lines.length - 1] : "";
};
const pendingText = (p: { installed?: boolean; downloaded?: boolean; file: string }) => p.installed
  ? t("editor.sidebar.pending.installed")
  : p.downloaded
    ? t("editor.sidebar.pending.downloaded")
    : t("editor.sidebar.pending.not_flashed", { file: p.file });
</script>

<template>
  <aside class="side">
    <button type="button" class="brand" :aria-label="t('editor.sidebar.home')" :title="t('editor.sidebar.home')" :aria-current="!state.selected && route === '' ? 'page' : undefined" @click="goHome">
      <TesseraMark class="mark" />
      <span>Tessera</span>
    </button>
    <span v-if="!state.reachable || !state.connected" id="connection" class="conn" role="status">
      {{ !state.reachable ? t("editor.sidebar.connection.unreachable") : t("editor.sidebar.connection.reconnecting") }}
    </span>
    <button type="button" class="search-btn" id="open-palette" @click="state.palette = true"><Icon name="magnify" />{{ t("editor.sidebar.search") }}<kbd>⌘K</kbd></button>
    <div class="label">{{ t("editor.sidebar.screens") }}</div>
    <div id="screens">
      <div v-for="screen in state.inventory.screens" :key="screen.id" class="screen-item" :class="{ selected: isSelected(screen), open: isOpen(screen), 'has-chevron': chevronShown(screen) }">
        <button type="button" class="nav-item" :aria-current="isSelected(screen) ? 'true' : 'false'" @click="choose(screen)">
          <span class="board-icon">
            <span class="mdi">{{ boardIcon(screen) }}</span>
            <span class="led" :class="light(screen)" role="img" :aria-label="screen.virtual ? t('editor.preview.virtual') : screen.online ? t('editor.common.online') : t('editor.common.offline')"></span>
          </span>
          <span class="txt">
            <span class="name">{{ screen.name }}</span>
            <small v-if="subline(screen)" class="sub" :class="subline(screen)!.kind">{{ subline(screen)!.text }}</small>
          </span>
          <span v-if="screen.id === state.selected && state.dirty" class="unsaved" role="img" :aria-label="t('editor.common.unsaved')" :title="t('editor.common.unsaved')"></span>
          <span v-else-if="updateState(screen)?.kind === 'running'" class="spin small"></span>
        </button>
        <button v-if="chevronShown(screen)" type="button" class="details-toggle" :aria-expanded="isOpen(screen) ? 'true' : 'false'"
          :aria-label="t(isOpen(screen) ? 'editor.sidebar.details.hide' : 'editor.sidebar.details.show', { name: screen.name })"
          :title="t(isOpen(screen) ? 'editor.sidebar.details.hide' : 'editor.sidebar.details.show', { name: screen.name })" @click="toggleDetails(screen)">
          <Icon name="chevron-down" />
        </button>
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
              <div v-else class="screen-actions">
                <button type="button" class="btn mini primary" :disabled="!screen.update?.profile" :title="screen.update?.profile ? '' : t('editor.sidebar.update.no_profile')" @click="update(screen)">{{ t("editor.sidebar.update.button") }}</button>
                <details v-if="notes(screen).length" class="whatsnew">
                  <summary>{{ t("editor.sidebar.update.whats_new") }}</summary>
                  <ul><li v-for="line in notes(screen).slice(0, 8)" :key="line">{{ line }}</li></ul>
                </details>
              </div>
            </template>
            <template v-else-if="updateState(screen)!.kind === 'running' && updateProgress(screen)">
              <div class="progress" role="progressbar" :aria-valuenow="updateProgress(screen)!.percent" aria-valuemin="0" aria-valuemax="100"><i :style="{ width: updateProgress(screen)!.percent + '%' }"></i></div>
              <div class="progress-text"><span>{{ updateProgress(screen)!.percent }} %</span><span :title="lastLog()">{{ updateProgress(screen)!.text }}</span></div>
              <small v-if="lastLog()" :title="lastLog()" style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis">{{ lastLog() }}</small>
              <button type="button" class="btn link mini" style="justify-self: start" @click="go('#firmware')">{{ t("editor.sidebar.update.full_log") }}</button>
            </template>
            <small v-else-if="updateState(screen)!.kind !== 'running'" :class="{ failed: updateState(screen)!.kind === 'failed' }">{{ updateState(screen)!.text }}</small>
          </div>
          <button v-if="screen.api_key" type="button" class="btn link mini copy-key" @click="copyText(screen.api_key!)">{{ t("editor.sidebar.copy_api_key") }}</button>
          <!-- The screen's YAML, Override YAML and the secrets they use, to build it with ESPHome on your own computer. -->
          <a v-if="screen.update?.profile" class="btn link mini screen-files" :href="`api/firmware/profiles/${encodeURIComponent(screen.update.profile)}/files`" download
            :title="t('editor.sidebar.files_hint')">{{ t("editor.sidebar.files") }}</a>
          <form v-if="renameFor === screen.id" class="rename-screen" @submit.prevent="saveName(screen)">
            <input v-model="newName" :placeholder="screen.ha_name" maxlength="40" :aria-label="t('editor.sidebar.rename.label')" autofocus @keydown.esc="renameFor = null" />
            <div class="screen-actions">
              <button type="submit" class="btn mini primary">{{ t("editor.sidebar.rename.save") }}</button>
              <button type="button" class="btn link mini" @click="renameFor = null">{{ t("editor.common.cancel") }}</button>
            </div>
          </form>
          <button v-else type="button" class="btn link mini rename-screen" @click="startRename(screen)">{{ t("editor.sidebar.rename.button") }}</button>
          <button type="button" class="btn link mini danger remove-screen" @click="removeFor = screen.id">{{ t("editor.sidebar.remove.button") }}</button>
        </div>
      </div>
    </div>
    <div id="pending">
      <div v-for="p in state.inventory.pending || []" :key="p.file" class="pending">
        <strong>{{ p.friendly }}</strong>
        <small>{{ pendingText(p) }}</small>
        <div class="pending-actions">
          <button type="button" class="btn mini quiet" @click="openIntegrations">{{ t("editor.common.open_integrations") }}</button>
        </div>
        <details v-if="p.api_key" class="key-more">
          <summary>{{ t("editor.installer.key_more") }}</summary>
          <button type="button" class="btn link mini copy-key" @click="copyText(p.api_key!)">{{ t("editor.sidebar.copy_api_key") }}</button>
        </details>
        <a class="btn link mini screen-files" :href="`api/firmware/profiles/${encodeURIComponent(p.file)}/files`" download :title="t('editor.sidebar.files_hint')">{{ t("editor.sidebar.files") }}</a>
      </div>
    </div>
    <button id="new-screen" type="button" class="nav-item ghost" :aria-current="route === '#new-screen' ? 'true' : 'false'" @click="go('#new-screen')">
      <Icon name="plus" class="plus" /><span class="txt">{{ t("editor.nav.new_screen") }}</span>
    </button>
    <div class="spacer"></div>
    <div class="more">
      <div class="label">{{ t("editor.sidebar.more") }}</div>
      <!-- The firmware tool (build, USB, OTA, download) is for repairs, not for adding a screen, so it lives in Settings,
           the command palette and a screen's menu rather than here, where it read as the way in (app 0.3.27). -->
      <button id="open-alerts" type="button" class="nav-item" :aria-current="route === '#alerts' ? 'true' : 'false'" @click="go('#alerts')"><span class="mdi">{{ glyph("F0594") }}</span><span class="txt">{{ t("editor.nav.alerts") }}</span></button>
      <button id="open-settings" type="button" class="nav-item" :aria-current="route === '#settings' ? 'true' : 'false'" @click="go('#settings')"><span class="mdi">{{ glyph("F0493") }}</span><span class="txt">{{ t("editor.nav.settings") }}</span></button>
      <button id="refresh" type="button" class="nav-item ghost" @click="refresh()"><Icon name="refresh" class="plus" /><span class="txt">{{ t("editor.sidebar.refresh") }}</span></button>
    </div>
  </aside>
</template>
