<script setup lang="ts">
// Everything around the screens: firmware updates, language and region, alerts, Claude.
import { computed, ref } from "vue";
import { useBusy } from "../composables/useBusy";
import { useConfirm } from "../composables/useConfirm";
import { haProfile, matchLanguage, numberText, type NumberMarks, type NumberStyle, STYLE_MARKS, t } from "../i18n";
import BuildLog from "./BuildLog.vue";
import BuildServerCard from "./BuildServerCard.vue";
import Icon from "./ui/Icon.vue";
import { useUiStore } from "../stores/ui";
import { useRegionStore } from "../stores/region";
import { useBuildsStore } from "../stores/builds";
import { useInventoryStore } from "../stores/inventory";
import { usePluginsStore } from "../stores/plugins";

const ui = useUiStore();
const region = useRegionStore();
const builds = useBuildsStore();
const inv = useInventoryStore();
const plugins = usePluginsStore();
// What this app shares about plugins (plugin_likes.py): counting the plugins it runs, and the stars card's asking.
const sharing = computed(() => inv.inventory.plugin_sharing || null);
const sharingBusy = ref(false);
async function share(what: "counting" | "asking", on: boolean) {
  sharingBusy.value = true;
  try {
    if (what === "counting") await plugins.setCounting(on);
    else await plugins.cardAnswer("any", on ? "ask" : "never");
  } catch (error: any) { ui.toast(error.message); } finally { sharingBusy.value = false; }
}

const u = computed(() => inv.inventory.updates);
const outdated = computed(() => inv.inventory.screens.filter((s) => s.update?.available).length);
const running = computed(() => inv.inventory.screens.find((s) => s.id === inv.inventory.updates?.busy));
// Each screen is offered its own board's firmware (app 0.3.21): one number only when those screens share it.
const oneTarget = (screens: typeof inv.inventory.screens) => {
  const targets = new Set(screens.map((s) => s.update?.target || u.value?.target));
  return targets.size === 1 ? [...targets][0] : null;
};
const updatesHint = computed(() => {
  if (!u.value) return "";
  const screens = inv.inventory.screens;
  if (u.value.busy) return t("editor.settings.updates.busy", { version: running.value?.update?.target || u.value.target });
  if (!screens.length) return t("editor.settings.updates.no_screens", { version: u.value.target });
  if (outdated.value) {
    const version = oneTarget(screens.filter((s) => s.update?.available));
    return version ? t("editor.settings.updates.available", { version }, outdated.value)
      : t("editor.settings.updates.available_mixed", {}, outdated.value);
  }
  const version = oneTarget(screens);
  return version ? t("editor.settings.updates.current", { version }) : t("editor.settings.updates.current_mixed");
});
// What the current firmware brings: the changelog sections that mention it.
const targetNotes = computed(() => {
  const sections = inv.inventory.changelog, target = u.value?.target;
  if (!Array.isArray(sections) || !target) return [];
  return sections.filter((s) => s.firmware === target).flatMap((s) => s.lines).slice(0, 10);
});
// Reinstall all from dev asks first: it builds every screen again, which takes a while and restarts each one.
const { confirm } = useConfirm();
async function reinstallAll() {
  const count = u.value?.reinstallable || 0;
  if (await confirm(t("editor.settings.updates.reinstall_all_confirm", count), { confirm: t("editor.settings.updates.reinstall_all_go") })) await builds.runUpdateAll(true);
}
const skill = computed(() => inv.inventory.claude_skill);
const installing = ref(false);
async function install() {
  installing.value = true;
  try { await inv.installClaudeSkill(); } finally { installing.value = false; }
}

// Video in Home Assistant: the tessera_video integration, installed on request, then loaded by a restart of Home
// Assistant; the app adds the screens with Screen camera's part Video to it by itself (screen_video.py).
const video = computed(() => inv.inventory.video);
const videoBusy = ref(false);
const videoWaitsRestart = computed(() => !!video.value?.installed && (!video.value.loaded || video.value.loaded !== video.value.version));
async function installVideo() {
  videoBusy.value = true;
  try { await inv.installVideo(); } finally { videoBusy.value = false; }
}
async function restartForVideo() {
  if (!(await confirm(t("editor.settings.video.restart_confirm"), { confirm: t("editor.settings.video.restart") }))) return;
  videoBusy.value = true;
  try { await inv.restartForVideo(); } finally { videoBusy.value = false; }
}

// ---- Language & region (app 0.2.90): one place for every screen ----
// The screen language ("auto" is Home Assistant's), the time format and the number format. An add-on without them
// shows no card.
const GUIDE = "https://github.com/MaxGramser/homeassistant_espscreen/blob/main/docs/TRANSLATING.md";
const STYLES: NumberStyle[] = ["point", "comma", "space"];
const lang = computed(() => inv.inventory.language);
// Home Assistant's language as the list has it: the same one, else its base language.
const haName = computed(() => {
  const l = lang.value, code = l?.ha ? matchLanguage(l.ha, l.languages.map((own) => own.code)) : undefined;
  return l?.languages.find((own) => own.code === code)?.name;
});
const unchecked = computed(() => lang.value?.languages.find((own) => own.code === lang.value!.effective && !own.checked));
const clockName = (clock: string | undefined) => t(clock === "12" ? "editor.settings.language.clock_12" : "editor.settings.language.clock_24");
const example = (marks: NumberMarks) => numberText("1234.5", marks);
// The user's own Home Assistant profile, where it names a clock or a number format that the screens don't use.
const profile = haProfile();
const different = computed(() => {
  const l = lang.value;
  if (!l) return {};
  return {
    ...(profile.clock && profile.clock !== (l.clock_effective || "24") ? { clock: profile.clock } : {}),
    ...(profile.numbers && profile.numbers !== (l.numbers_effective || "point") ? { numbers: profile.numbers } : {}),
  };
});
const profileText = computed(() => [different.value.clock && clockName(different.value.clock), different.value.numbers && example(STYLE_MARKS[different.value.numbers])]
  .filter(Boolean).join(" · "));
const { busy: saving, run: whileSaving } = useBusy();
async function choose(field: "setting" | "clock" | "numbers", event: Event) {
  const select = event.target as HTMLSelectElement;
  const saved = await whileSaving(() => region.saveLanguage({ [field]: select.value }));
  // A refused change shows the stored choice again.
  if (!saved) select.value = String(lang.value?.[field] ?? "auto");
}
const useProfile = () => whileSaving(() => region.saveLanguage(different.value));
</script>

<template>
  <div class="panel" id="settings-view">
    <div class="panel-head">
      <div class="tx">
        <span class="eyebrow">{{ t("editor.nav.settings") }}</span>
        <h1 id="settings-title">{{ t("editor.settings.title") }}</h1>
      </div>
      <button type="button" class="btn quiet" id="close-settings" @click="ui.go('')">{{ t("editor.settings.back") }}</button>
    </div>
    <div class="card-grid">
      <section class="card">
        <h2>{{ t("editor.settings.screens.title") }}</h2>
        <p>{{ t("editor.settings.screens.text") }}</p>
        <div class="tools">
          <button type="button" class="tool" @click="ui.go('#new-screen')"><span class="tool-icon">＋</span><span class="tx"><b>{{ t("editor.nav.new_screen") }}</b><small>{{ t("editor.nav.new_screen_detail") }}</small></span></button>
          <button type="button" class="tool" @click="ui.go('#firmware')"><span class="tool-icon">⇪</span><span class="tx"><b>{{ t("editor.nav.firmware") }}</b><small>{{ t("editor.settings.screens.firmware_detail") }}</small></span></button>
        </div>
      </section>
      <section v-if="u" class="card updates" id="updates">
        <h2>{{ t("editor.settings.updates.title") }}</h2>
        <p id="updates-hint">{{ updatesHint }}</p>
        <!-- Every build on the way, whoever asked: an update, a plugin build, an install (the builds store, stores/builds.ts). -->
        <BuildLog v-for="screen in builds.buildingScreens" :key="screen.id" :screen="screen" name />
        <button v-if="u.pending && u.pending >= 2" id="update-all" type="button" class="btn primary" @click="builds.runUpdateAll()">{{ t("editor.settings.updates.all", u.pending) }}</button>
        <!-- The dev app (docs/RELEASING.md, "Testing dev"): every screen again with the newest dev, one after the other. -->
        <div v-if="builds.devChannel && u.reinstallable" class="dev-tools" id="reinstall-all-wrap">
          <button id="reinstall-all" type="button" class="btn" @click="reinstallAll"><Icon name="update" />{{ t("editor.settings.updates.reinstall_all", u.reinstallable) }}</button>
          <small>{{ t("editor.settings.updates.reinstall_all_hint") }}</small>
        </div>
        <details v-if="targetNotes.length && !builds.anyBuilding" class="whatsnew">
          <summary>{{ t("editor.settings.updates.whats_new", { version: u.target }) }}</summary>
          <ul><li v-for="line in targetNotes" :key="line">{{ line }}</li></ul>
        </details>
        <label class="check">
          <input type="checkbox" id="auto-update" :checked="Boolean(u.auto)" @change="builds.setAutoUpdate(($event.target as HTMLInputElement).checked)" />
          <span>{{ t("editor.settings.updates.auto_label") }}<small>{{ t("editor.settings.updates.auto_hint") }}</small></span>
        </label>
      </section>
      <!-- Build firmware on a faster computer: an ESPHome build server (BuildServerCard, the add-on's build_server.py). -->
      <BuildServerCard v-if="inv.inventory.build_server" />
      <section v-if="lang" class="card" id="language">
        <h2>{{ t("editor.settings.language.title") }}</h2>
        <div class="field">
          <label class="f-label" for="screen-language">{{ t("editor.settings.language.screen_language") }}</label>
          <select id="screen-language" :value="lang.setting" :disabled="saving" @change="choose('setting', $event)">
            <option value="auto">{{ haName ? t("editor.settings.language.auto", { name: haName }) : t("editor.settings.language.auto_plain") }}</option>
            <option v-for="own in lang.languages" :key="own.code" :value="own.code">{{ own.checked ? own.name : t("editor.settings.language.unchecked", { name: own.name }) }}</option>
          </select>
          <small v-if="lang.setting === 'auto' && !haName" id="language-ha-missing">{{ t("editor.settings.language.ha_missing") }}</small>
          <i18n-t v-if="unchecked" keypath="editor.settings.language.help" tag="small" id="language-help" scope="global">
            <template #name>{{ unchecked.name }}</template>
            <template #guide><a :href="GUIDE" target="_blank" rel="noopener">{{ t("editor.settings.language.guide") }}</a></template>
          </i18n-t>
          <small>{{ t("editor.settings.language.update_hint") }}</small>
        </div>
        <div class="field">
          <label class="f-label" for="time-format">{{ t("editor.settings.language.time") }}</label>
          <select id="time-format" :value="lang.clock || 'auto'" :disabled="saving" @change="choose('clock', $event)">
            <option value="auto">{{ t("editor.settings.language.time_auto", { clock: clockName(lang.clock_auto || lang.clock_effective) }) }}</option>
            <option value="24">{{ clockName("24") }}</option>
            <option value="12">{{ clockName("12") }}</option>
          </select>
        </div>
        <div class="field">
          <label class="f-label" for="number-format">{{ t("editor.settings.language.numbers") }}</label>
          <select id="number-format" :value="lang.numbers || 'auto'" :disabled="saving" @change="choose('numbers', $event)">
            <option value="auto">{{ t("editor.settings.language.numbers_auto", { example: example(region.autoMarks) }) }}</option>
            <option v-for="style in STYLES" :key="style" :value="style">{{ example(STYLE_MARKS[style]) }}</option>
          </select>
        </div>
        <div v-if="profileText" class="actions" id="language-profile">
          <small>{{ t("editor.settings.language.profile", { formats: profileText }) }}</small>
          <button type="button" class="btn quiet mini" :disabled="saving" @click="useProfile">{{ t("editor.settings.language.use_profile") }}</button>
        </div>
        <small>{{ t("editor.settings.language.editor_hint") }}</small>
      </section>
      <!-- What this app shares about plugins (plugin_likes.py): counting, and whether the stars card asks. -->
      <section v-if="inv.pluginsEnabled && sharing?.usable" class="card" id="plugin-sharing">
        <h2>{{ t("editor.plugins.sharing.title") }}</h2>
        <p>{{ t("editor.plugins.sharing.text") }}</p>
        <label class="check" for="sharing-counting">
          <input type="checkbox" id="sharing-counting" :checked="sharing.counting" :disabled="sharingBusy" @change="share('counting', ($event.target as HTMLInputElement).checked)" />
          <span>{{ t("editor.plugins.counting.label") }}<small>{{ sharing.counting ? t("editor.plugins.counting.on_hint") : t("editor.plugins.counting.hint") }}</small></span>
        </label>
        <label class="check" for="sharing-asking">
          <input type="checkbox" id="sharing-asking" :checked="sharing.asking" :disabled="sharingBusy" @change="share('asking', ($event.target as HTMLInputElement).checked)" />
          <span>{{ t("editor.plugins.sharing.asking") }}<small>{{ t("editor.plugins.sharing.asking_hint") }}</small></span>
        </label>
        <a class="btn quiet mini" href="https://tessera-maxgramser.on-forge.com/privacy" target="_blank" rel="noopener">{{ t("editor.feedback.privacy") }}</a>
      </section>
      <section class="card">
        <h2>{{ t("editor.nav.events") }}</h2>
        <p>{{ t("editor.settings.alerts.text") }}</p>
        <div class="tools">
          <button type="button" class="tool" @click="ui.go('#events')"><span class="tool-icon">!</span><span class="tx"><b>{{ t("editor.nav.events") }}</b><small>{{ t("editor.settings.alerts.detail") }}</small></span></button>
        </div>
      </section>
      <section v-if="inv.pluginsEnabled" class="card" id="video">
        <h2>{{ t("editor.settings.video.title") }}</h2>
        <p>{{ t("editor.settings.video.text") }}</p>
        <div class="actions">
          <button type="button" id="video-install" class="btn" :class="video?.installed && video.current ? 'quiet' : 'primary'" :disabled="!video || videoBusy" @click="installVideo">
            {{ !video || !video.installed ? t("editor.settings.video.install") : video.current ? t("editor.settings.video.install_again") : t("editor.settings.video.update") }}
          </button>
          <button v-if="videoWaitsRestart" type="button" id="video-restart" class="btn primary" :disabled="videoBusy" @click="restartForVideo">
            {{ t("editor.settings.video.restart") }}
          </button>
          <span id="video-status" class="chip" :class="!video ? '' : !video.installed ? '' : !video.current ? 'update' : videoWaitsRestart ? 'update' : 'good'" role="status">
            {{ !video ? t("editor.common.loading") : !video.installed ? t("editor.settings.claude.not_installed") : !video.current ? t("editor.settings.video.newer") : videoWaitsRestart ? t("editor.settings.video.waits_restart") : t("editor.settings.video.running") }}
          </span>
        </div>
        <small id="video-screens">{{ video?.screens.length ? t("editor.settings.video.screens", { names: video.screens.join(", ") }) : t("editor.settings.video.no_screens") }}</small>
        <i18n-t keypath="editor.settings.video.writes" tag="small" scope="global">
          <template #path><code id="video-path">{{ video?.path || "/homeassistant/custom_components/tessera_video" }}</code></template>
        </i18n-t>
      </section>
      <section class="card" id="claude">
        <h2>Claude</h2>
        <p>{{ t("editor.settings.claude.text") }}</p>
        <div class="actions">
          <button type="button" id="claude-install" class="btn" :class="skill?.installed && skill.current ? 'quiet' : 'primary'" :disabled="!skill || installing" @click="install">
            {{ !skill || !skill.installed ? t("editor.settings.claude.install") : skill.current ? t("editor.settings.claude.install_again") : t("editor.settings.claude.update") }}
          </button>
          <span id="claude-status" class="chip" :class="!skill ? '' : !skill.installed ? '' : skill.current ? 'good' : 'update'" role="status">
            {{ !skill ? t("editor.common.loading") : !skill.installed ? t("editor.settings.claude.not_installed") : skill.current ? t("editor.settings.claude.installed_chip") : t("editor.settings.claude.newer") }}
          </span>
        </div>
        <i18n-t keypath="editor.settings.claude.writes" tag="small" scope="global">
          <template #path><code id="claude-path">{{ skill?.path || "/homeassistant/.claude/skills/esp-screens" }}</code></template>
        </i18n-t>
        <div class="actions">
          <a class="btn quiet" id="claude-download" href="api/claude-skill.zip" download="esp-screens.zip">{{ t("editor.settings.claude.download") }}</a>
          <small>{{ t("editor.settings.claude.upload") }}</small>
        </div>
      </section>
    </div>
  </div>
</template>
