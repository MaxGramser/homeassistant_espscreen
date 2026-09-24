<script setup lang="ts">
import { ref } from "vue";
import { t } from "../i18n";
import { boardTitle } from "../model/boards";
import { versionAtLeast } from "../model/layout";
import { glyph } from "../model/topbar";
import {
  copyText, firmwareVersion, go, needsUpdate, newLanguageText, openIntegrations, phaseText, refresh, removeScreen, route, select, startUpdate,
  state, updateProgress, whatsNew,
} from "../store";
import type { Screen } from "../types";

const hostFor = ref<string | null>(null);
const host = ref("");
// The screen that asked to be removed: its details make room for what goes, until it is confirmed or dropped.
const removeFor = ref<string | null>(null);
async function remove(screen: Screen) {
  if (await removeScreen(screen)) removeFor.value = null;
}
// The screen whose details are open under its name; the others show only their name and light.
const open = ref<string | null>(null);
// A screen that only needs the new language (app 0.2.90) says so instead of naming the version it already has.
const languageOnly = (screen: Screen) => {
  const u = screen.update || {};
  return Boolean(u.language) && (!u.target || versionAtLeast(firmwareVersion(screen), u.target));
};
function updateState(screen: Screen) {
  if (screen.virtual) return null;
  const u = screen.update || {};
  if (u.state === "running" || state.updating.includes(screen.id)) return { kind: "running", text: phaseText(u.phase) };
  if (u.state === "queued") return { kind: "queued", text: t("editor.sidebar.update.queued") };
  // A screen ESP Screens did not install has no YAML here to build from, so there is nothing to press: say why
  // instead of offering a button that cannot work (the nightly round already passes such a screen by).
  if (needsUpdate(screen) && screen.online && !u.profile)
    return { kind: "blocked", text: t("addon.errors.updates.no_profile") };
  if (needsUpdate(screen) && screen.online)
    return { kind: "available", text: languageOnly(screen) ? newLanguageText() : t("editor.sidebar.update.available", { version: u.target }) };
  if (u.result && Date.now() / 1000 - u.result.time < 86400) return { kind: u.result.state === "failed" ? "failed" : "done", text: u.result.message };
  return null;
}
// The light beside the icon: green when all is well, amber when an update waits or runs, red when the screen is away.
const light = (screen: Screen) => {
  if (screen.virtual) return "virtual";
  if (!screen.online) return "down";
  const kind = updateState(screen)?.kind;
  return kind === "available" || kind === "blocked" || kind === "running" || kind === "queued" ? "update" : kind === "failed" ? "down" : "ok";
};
// One quiet line under the name, only when there is something to say; a healthy screen shows its name alone.
const subline = (screen: Screen) => {
  if (screen.virtual) return { kind: "virtual", text: t("editor.preview.virtual") };
  if (!screen.online) return { kind: "down", text: t("editor.common.offline") };
  const u = updateState(screen);
  // An update nothing here can build is still an update: the line names it, the details say why it waits.
  if (u?.kind === "blocked") return { kind: "update", text: t("editor.sidebar.update.available", { version: screen.update?.target }) };
  return u && u.kind !== "done" ? u : null;
};
const isSelected = (screen: Screen) => screen.id === state.selected && route.value === "";
const isOpen = (screen: Screen) => open.value === screen.id;
// Choosing a screen opens its details; choosing it again folds them away.
function choose(screen: Screen) {
  open.value = isSelected(screen) && isOpen(screen) ? null : screen.id;
  removeFor.value = null;
  select(screen.id);
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
    <div class="brand"><span class="mark">▦</span><span>ESP Screens</span></div>
    <span v-if="!state.reachable || !state.connected" id="connection" class="conn" role="status">
      {{ !state.reachable ? t("editor.sidebar.connection.unreachable") : t("editor.sidebar.connection.reconnecting") }}
    </span>
    <button type="button" class="search-btn" id="open-palette" @click="state.palette = true">⌕ {{ t("editor.sidebar.search") }}<kbd>⌘K</kbd></button>
    <div class="label">{{ t("editor.sidebar.screens") }}</div>
    <div id="screens">
      <div v-for="screen in state.inventory.screens" :key="screen.id" class="screen-item" :class="{ selected: isSelected(screen), open: isOpen(screen) }">
        <button type="button" class="nav-item" :aria-current="isSelected(screen) ? 'true' : 'false'" :aria-expanded="isOpen(screen) ? 'true' : 'false'" @click="choose(screen)">
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
          <button v-if="p.api_key" type="button" class="btn mini quiet" @click="copyText(p.api_key!)">{{ t("editor.sidebar.copy_api_key") }}</button>
        </div>
      </div>
    </div>
    <button id="new-screen" type="button" class="nav-item ghost" :aria-current="route === '#new-screen' ? 'true' : 'false'" @click="go('#new-screen')">
      <span class="plus">+</span><span class="txt">{{ t("editor.nav.new_screen") }}</span>
    </button>
    <div class="spacer"></div>
    <div class="more">
      <div class="label">{{ t("editor.sidebar.more") }}</div>
      <button id="open-firmware" type="button" class="nav-item" :aria-current="route === '#firmware' ? 'true' : 'false'" @click="go('#firmware')"><span class="mdi">{{ glyph("F0241") }}</span><span class="txt">{{ t("editor.nav.firmware") }}</span></button>
      <button id="open-alerts" type="button" class="nav-item" :aria-current="route === '#alerts' ? 'true' : 'false'" @click="go('#alerts')"><span class="mdi">{{ glyph("F0594") }}</span><span class="txt">{{ t("editor.nav.alerts") }}</span></button>
      <button id="open-settings" type="button" class="nav-item" :aria-current="route === '#settings' ? 'true' : 'false'" @click="go('#settings')"><span class="mdi">{{ glyph("F0493") }}</span><span class="txt">{{ t("editor.nav.settings") }}</span></button>
      <button id="refresh" type="button" class="nav-item ghost" @click="refresh()"><span class="plus">↻</span><span class="txt">{{ t("editor.sidebar.refresh") }}</span></button>
    </div>
  </aside>
</template>
