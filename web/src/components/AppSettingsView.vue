<script setup lang="ts">
// Everything around the screens: firmware updates, language and region, alerts, Claude.
import { computed, ref } from "vue";
import { haProfile, matchLanguage, numberText, type NumberMarks, type NumberStyle, STYLE_MARKS, t } from "../i18n";
import { anyUpdating, autoMarks, go, installClaudeSkill, runUpdateAll, saveLanguage, setAutoUpdate, state, updateProgress } from "../store";

const u = computed(() => state.inventory.updates);
const outdated = computed(() => state.inventory.screens.filter((s) => s.update?.available).length);
const running = computed(() => state.inventory.screens.find((s) => s.update?.state === "running" || state.updating.includes(s.id)));
// Each screen is offered its own board's firmware (app 0.3.21): one number only when those screens share it.
const oneTarget = (screens: typeof state.inventory.screens) => {
  const targets = new Set(screens.map((s) => s.update?.target || u.value?.target));
  return targets.size === 1 ? [...targets][0] : null;
};
const updatesHint = computed(() => {
  if (!u.value) return "";
  const screens = state.inventory.screens;
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
const progress = computed(() => (running.value ? updateProgress(running.value) : null));
const logTail = computed(() => (state.firmwareJob?.logs || []).slice(-12).join("\n"));
// What the current firmware brings: the changelog sections that mention it.
const targetNotes = computed(() => {
  const sections = state.inventory.changelog, target = u.value?.target;
  if (!Array.isArray(sections) || !target) return [];
  return sections.filter((s) => s.firmware === target).flatMap((s) => s.lines).slice(0, 10);
});
const skill = computed(() => state.inventory.claude_skill);
const installing = ref(false);
async function install() {
  installing.value = true;
  try { await installClaudeSkill(); } finally { installing.value = false; }
}

// ---- Language & region (app 0.2.90): one place for every screen ----
// The screen language ("auto" is Home Assistant's), the time format and the number format. An add-on without them
// shows no card.
const GUIDE = "https://github.com/MaxGramser/homeassistant_espscreen/blob/main/docs/TRANSLATING.md";
const STYLES: NumberStyle[] = ["point", "comma", "space"];
const lang = computed(() => state.inventory.language);
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
const saving = ref(false);
async function choose(field: "setting" | "clock" | "numbers", event: Event) {
  const select = event.target as HTMLSelectElement;
  saving.value = true;
  const saved = await saveLanguage({ [field]: select.value });
  saving.value = false;
  // A refused change shows the stored choice again.
  if (!saved) select.value = String(lang.value?.[field] ?? "auto");
}
async function useProfile() {
  saving.value = true;
  await saveLanguage(different.value);
  saving.value = false;
}
</script>

<template>
  <div class="panel" id="settings-view">
    <div class="panel-head">
      <div class="tx">
        <span class="eyebrow">{{ t("editor.nav.settings") }}</span>
        <h1 id="settings-title">{{ t("editor.settings.title") }}</h1>
      </div>
      <button type="button" class="btn quiet" id="close-settings" @click="go('')">{{ t("editor.settings.back") }}</button>
    </div>
    <div class="card-grid">
      <section class="card">
        <h2>{{ t("editor.settings.screens.title") }}</h2>
        <p>{{ t("editor.settings.screens.text") }}</p>
        <div class="tools">
          <button type="button" class="tool" @click="go('#new-screen')"><span class="tool-icon">＋</span><span class="tx"><b>{{ t("editor.nav.new_screen") }}</b><small>{{ t("editor.nav.new_screen_detail") }}</small></span></button>
          <button type="button" class="tool" @click="go('#firmware')"><span class="tool-icon">⇪</span><span class="tx"><b>{{ t("editor.nav.firmware") }}</b><small>{{ t("editor.settings.screens.firmware_detail") }}</small></span></button>
        </div>
      </section>
      <section v-if="u" class="card updates" id="updates">
        <h2>{{ t("editor.settings.updates.title") }}</h2>
        <p id="updates-hint">{{ updatesHint }}</p>
        <template v-if="running && progress">
          <div class="progress" role="progressbar" :aria-valuenow="progress.percent" aria-valuemin="0" aria-valuemax="100"><i :style="{ width: progress.percent + '%' }"></i></div>
          <div class="progress-text"><span>{{ running.name }} · {{ progress.percent }} %</span><span>{{ progress.text }}</span></div>
          <pre v-if="logTail" class="log-lines">{{ logTail }}</pre>
        </template>
        <button v-if="u.pending && !u.busy && u.pending >= 2" id="update-all" type="button" class="btn primary" @click="runUpdateAll">{{ t("editor.settings.updates.all", u.pending) }}</button>
        <details v-if="targetNotes.length && !anyUpdating()" class="whatsnew">
          <summary>{{ t("editor.settings.updates.whats_new", { version: u.target }) }}</summary>
          <ul><li v-for="line in targetNotes" :key="line">{{ line }}</li></ul>
        </details>
        <label class="check">
          <input type="checkbox" id="auto-update" :checked="Boolean(u.auto)" @change="setAutoUpdate(($event.target as HTMLInputElement).checked)" />
          <span>{{ t("editor.settings.updates.auto_label") }}<small>{{ t("editor.settings.updates.auto_hint") }}</small></span>
        </label>
      </section>
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
            <option value="auto">{{ t("editor.settings.language.numbers_auto", { example: example(autoMarks) }) }}</option>
            <option v-for="style in STYLES" :key="style" :value="style">{{ example(STYLE_MARKS[style]) }}</option>
          </select>
        </div>
        <div v-if="profileText" class="actions" id="language-profile">
          <small>{{ t("editor.settings.language.profile", { formats: profileText }) }}</small>
          <button type="button" class="btn quiet mini" :disabled="saving" @click="useProfile">{{ t("editor.settings.language.use_profile") }}</button>
        </div>
        <small>{{ t("editor.settings.language.editor_hint") }}</small>
      </section>
      <section class="card">
        <h2>{{ t("editor.nav.alerts") }}</h2>
        <p>{{ t("editor.settings.alerts.text") }}</p>
        <div class="tools">
          <button type="button" class="tool" @click="go('#alerts')"><span class="tool-icon">!</span><span class="tx"><b>{{ t("editor.nav.alerts") }}</b><small>{{ t("editor.settings.alerts.detail") }}</small></span></button>
        </div>
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
