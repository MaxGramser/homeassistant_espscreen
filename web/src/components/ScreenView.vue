<script setup lang="ts">
// One screen: the head with its status, the Layout and Settings tabs, and the drawer over the right side.
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { t } from "../i18n";
import {
  canAlert, closeInspector, copyLayoutFrom, currentScreen, exportLayout, go, identify, importLayout, needsUpdate, redo, save, screenText, startUpdate, state, undo,
} from "../store";
import LayoutView from "./LayoutView.vue";
import SettingsTab from "./SettingsTab.vue";
import Drawer from "./Drawer.vue";
import FeedbackPanel from "./FeedbackPanel.vue";

const screen = computed(() => currentScreen.value!);
const statusText = computed(() => screen.value.online
  ? `${screen.value.delivery} · ${screen.value.status}`
  : t("editor.screen_view.offline"));
const updateReady = computed(() => needsUpdate(screen.value) && screen.value.online && screen.value.update?.profile && screen.value.update?.host);
const others = computed(() => state.inventory.screens.filter((s) => s.id !== screen.value.id && s.layout?.tiles?.length));
const copyOpen = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);
function closeMenu() { state.menuOpen = false; copyOpen.value = false; }
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
function onDocClick(e: MouseEvent) {
  if (state.menuOpen && !(e.target as HTMLElement).closest(".head-right .menu, #more")) closeMenu();
}
onMounted(() => { document.addEventListener("keydown", onKey); document.addEventListener("click", onDocClick); });
onBeforeUnmount(() => { document.removeEventListener("keydown", onKey); document.removeEventListener("click", onDocClick); });
</script>

<template>
  <header class="main-head">
    <div>
      <span class="eyebrow" id="screen-name">{{ screen.name }}</span>
      <h1>{{ state.layout?.title || screenText("editor.mockup.home") }}</h1>
    </div>
    <span v-if="!screen.in_sync || !screen.online" id="delivery" class="chip" :class="{ off: !screen.online }" :title="statusText"><span class="dot"></span>{{ statusText }}</span>
    <div class="head-right">
      <div class="seg" role="tablist">
        <button type="button" id="tab-layout" role="tab" :aria-pressed="state.tab === 'layout' ? 'true' : 'false'" @click="state.tab = 'layout'">{{ t("editor.screen_view.tabs.layout") }}</button>
        <button type="button" id="tab-settings" role="tab" :aria-pressed="state.tab === 'settings' ? 'true' : 'false'" @click="state.tab = 'settings'; closeInspector()">{{ t("editor.screen_view.tabs.settings") }}</button>
      </div>
      <span v-if="!state.dirty" id="dirty" class="chip" :class="{ sent: state.saved }">{{ state.saved ? t("editor.screen_view.sent") : t("editor.screen_view.all_saved") }}</span>
      <span v-else id="dirty" class="chip dirty">{{ t("editor.common.unsaved") }}</span>
      <button v-if="state.dirty" id="save" type="button" class="btn primary" :disabled="state.busy" title="⌘S" @click="save()">
        <span v-if="state.busy" class="spin small"></span>{{ state.busy ? t("editor.common.saving") : t("editor.common.save_send") }}
      </button>
      <button id="more" type="button" class="icon-btn" :aria-label="t('editor.screen_view.more')" aria-haspopup="menu" :aria-expanded="state.menuOpen ? 'true' : 'false'" @click.stop="state.menuOpen = !state.menuOpen; copyOpen = false">···</button>
      <div v-if="state.menuOpen" class="menu" role="menu">
        <button type="button" role="menuitem" id="identify" :disabled="!canAlert(screen) || !screen.online" :title="canAlert(screen) ? '' : t('editor.screen_view.menu.identify_needs')" @click="closeMenu(); identify(screen)">{{ t("editor.screen_view.menu.identify") }} <small>{{ t("editor.screen_view.menu.identify_hint") }}</small></button>
        <button type="button" role="menuitem" id="inspect" @click="inspectAll">{{ t("editor.common.read_current_data") }} <small>{{ t("editor.screen_view.menu.inspect_hint") }}</small></button>
        <div class="sep"></div>
        <button type="button" role="menuitem" id="copy-layout" :disabled="!others.length" :aria-expanded="copyOpen ? 'true' : 'false'" @click.stop="copyOpen = !copyOpen">{{ t("editor.screen_view.menu.copy") }} <small>{{ others.length ? t("editor.screen_view.menu.copy_screens", others.length) : t("editor.screen_view.menu.copy_none") }}</small></button>
        <div v-if="copyOpen" class="sub">
          <button v-for="other in others" :key="other.id" type="button" role="menuitem" @click="copyFrom(other.id)">{{ other.name }} <small>{{ t("editor.screen_view.menu.copy_tiles", other.layout.tiles.length) }}</small></button>
        </div>
        <button type="button" role="menuitem" id="export-layout" @click="closeMenu(); exportLayout()">{{ t("editor.screen_view.menu.export") }} <small>JSON</small></button>
        <button type="button" role="menuitem" id="import-layout" @click="pickFile">{{ t("editor.screen_view.menu.import") }} <small>JSON</small></button>
        <div class="sep"></div>
        <button type="button" role="menuitem" id="open-override" :disabled="!screen.update?.profile" :title="screen.update?.profile ? '' : t('editor.screen_view.menu.override_none')" @click="openOverride">{{ t("editor.screen_view.menu.override") }} <small>{{ t("editor.screen_view.menu.override_hint") }}</small></button>
        <button type="button" role="menuitem" @click="closeMenu(); go('#firmware')">{{ t("editor.nav.firmware") }}</button>
        <button v-if="updateReady" type="button" role="menuitem" @click="closeMenu(); startUpdate(screen)">{{ t("editor.screen_view.menu.update") }} <small>{{ screen.update?.target }}</small></button>
      </div>
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
