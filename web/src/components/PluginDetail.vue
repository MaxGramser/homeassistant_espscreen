<script setup lang="ts">
// The details of one plugin, in the column on the right: who made it, what to do with it, its README, what it adds,
// what it may do and the room it takes. On the Plugins page (no `screen`) the action is a checkbox per screen, ticked
// where it is on and greyed out with its reason where it does not fit; in a screen's Plugins tab it is the one button
// for that screen. A screen with its own YAML gets the lines to paste instead of a button.
import { computed, reactive, ref, watch } from "vue";
import { editorLanguage, languageMarks, numberText, t, te } from "../i18n";
import { boardTitle } from "../model/boards";
import { fit, flashShare, headroomKb, inEditorLanguage, text, type Plugin } from "../model/plugins";
import { glyph } from "../model/topbar";
import {
  addPlugin, attachLine, buildingOn, isSetAside, setAside, toggleSetAside, copyAttach, fileOf, hasUpdate, installedOn, isTest, labelOf, stageOf, markAttached, needsAttach, partsKb,
  pluginsFile, realScreens, needsConsent, plugins, removePlugin, setupChanged, setupReady, statusOn,
  canLike, chooseProvider, comesAlong, like, neededBy, otherOrigin, planOn, switchPlugin,
} from "../plugin-state";
import { toast } from "../store";
import type { Screen } from "../types";
import PluginReadme from "./PluginReadme.vue";
import PluginSettings from "./PluginSettings.vue";
import PluginSetup from "./PluginSetup.vue";
import Icon from "./ui/Icon.vue";

const props = defineProps<{ plugin: Plugin; screen?: Screen | null }>();
defineEmits<{ close: [] }>();

const label = computed(() => labelOf(props.plugin));
const stage = computed(() => stageOf(props.plugin));
const marks = () => languageMarks(editorLanguage());
const kb = (value: number) => numberText(value, marks());
const percent = (share: number) => `${numberText((share * 100).toFixed(1), marks())} %`;
const works = computed(() => props.plugin.boards === "any"
  ? t(props.plugin.requires.psram ? "editor.plugins.works.any_psram" : "editor.plugins.works.any")
  : (props.plugin.board_names || props.plugin.boards).join(", "));
const domainName = (domain: string) => (te(`editor.domains.${domain}`) ? t(`editor.domains.${domain}`) : domain);
// A plugin whose own words are not in the editor's language shows them in English and says so, once.
const englishOnly = computed(() => !editorLanguage().startsWith("en") && !inEditorLanguage(props.plugin.readme));
const trust = ref(false);
watch(() => props.plugin.id, () => { trust.value = false; });

// ---- One screen (its Plugins tab) ----
const here = computed(() => props.screen || null);
const hereStatus = computed(() => (here.value ? statusOn(props.plugin, here.value) : null));
const hereInstalled = computed(() => (here.value ? installedOn(here.value, props.plugin.id) : undefined));
const hereFit = computed(() => (here.value ? fit(props.plugin, here.value) : { ok: true as const }));
const hereFlash = computed(() => (here.value ? flashShare(props.plugin, here.value, partsKb(here.value, props.plugin)) : null));
const hereAttach = computed(() => Boolean(here.value && needsAttach(here.value)));
// The settings of a plugin this screen runs, grouped by what a change does: at once (its ESPHome entities), for every
// screen (what was filled in once), or a new build of this screen (its own inputs and parts).
const sharedInputs = computed(() => (props.plugin.inputs || []).filter((input) => input.scope === "all"));
const buildInputs = computed(() => (props.plugin.inputs || []).filter((input) => input.scope === "screen").length + (props.plugin.parts || []).length);
const hereSettings = computed(() => Boolean(here.value && hereInstalled.value
  && (props.plugin.settings?.length || sharedInputs.value.length || buildInputs.value)));
const hereChanged = computed(() => Boolean(here.value && setupChanged(here.value, props.plugin)));
// What an update changes: GitHub's compare of the commit this screen runs with the one offered. The only thing a person
// can really judge an update by, since the manifest's rights are the maker's own word (docs/PLUGINS.md).
const changes = computed(() => {
  const have = hereInstalled.value?.ref, next = props.plugin.ref;
  const sha = /^[0-9a-f]{40}$/;
  if (!props.plugin.repo || !have || !next || have === next || !sha.test(have) || !sha.test(next)) return null;
  return `${props.plugin.repo.replace(/\/tree\/.*$/, "")}/compare/${have}...${next}`;
});

// ---- What it needs, what comes along, and the plugins that need it ----
const byId = (id: string) => plugins.index.find((p) => p.id === id);
const nameOf = (id: string) => (byId(id) ? text(byId(id)!.name) : id);
const feature = (name: string) => (te(`editor.plugins.features.${name}`) ? t(`editor.plugins.features.${name}`) : name);
// On this screen: what adding it brings along (the add-on's plan), a feature to choose a plugin for, or why it cannot.
const herePlan = computed(() => (here.value && !hereInstalled.value && hereFit.value.ok ? planOn(here.value, [props.plugin.id]) : null));
const hereAlong = computed(() => comesAlong(herePlan.value, [props.plugin.id]));
const hereNeeded = computed(() => (here.value && hereInstalled.value ? neededBy(here.value, props.plugin.id) : []));
const cameWith = computed(() => (here.value && hereInstalled.value?.auto ? hereNeeded.value : []));
const hereOther = computed(() => Boolean(here.value && otherOrigin(here.value, props.plugin)));
const whyAlong = (row: { step: { for: string[] }; plugin: Plugin }) => {
  const brings = (row.plugin.provides || []).filter((f) => row.step.for.some((id) => (byId(id) || props.plugin).requires.features?.includes(f)));
  return brings.length ? t("editor.plugins.along.brings", { what: brings.map(feature).join(", ") })
    : t("editor.plugins.along.needed_by", { name: row.step.for.map(nameOf).join(", ") });
};
// Taking it off: a plugin that needs it goes with it, and one that only came along with it may go too; the person says.
const confirming = ref<null | { screens: Screen[]; with: string[]; orphans: string[] }>(null);
const alsoOrphans = ref(true);
function askRemove(screens: Screen[]) {
  const needing = [...new Set(screens.flatMap((screen) => neededBy(screen, props.plugin.id).map((p) => p.id)))];
  const orphans = [...new Set(screens.flatMap((screen) => (plugins.installed[screen.id] || []).filter((item) => item.auto
    && item.id !== props.plugin.id && neededBy(screen, item.id).every((p) => p.id === props.plugin.id || needing.includes(p.id)))
    .map((item) => item.id)))];
  if (!needing.length && !orphans.length) return removePlugin(screens, props.plugin);
  alsoOrphans.value = true;
  confirming.value = { screens, with: needing, orphans };
}
function confirmRemove() {
  const ask = confirming.value!;
  confirming.value = null;
  removePlugin(ask.screens, props.plugin, [...ask.with, ...(alsoOrphans.value ? ask.orphans : [])]);
}
watch(() => props.plugin.id, () => { confirming.value = null; });
// A like: the first one asks once whether it may count in a public number (plugin_likes.py).
const askingLike = ref(false);
async function toggleLike(consent = false) {
  if (!props.plugin.liked && !plugins.likeConsent && !consent) { askingLike.value = true; return; }
  askingLike.value = false;
  try { await like(props.plugin, !props.plugin.liked, consent); } catch (error: any) { toast(error.message); }
}

// ---- Every screen (the Plugins page): a box per screen, applied together ----
const screens = computed(() => realScreens());
const wanted = reactive<Record<string, boolean>>({});
function reset() {
  for (const key of Object.keys(wanted)) delete wanted[key];
  for (const screen of screens.value) wanted[screen.id] = Boolean(installedOn(screen, props.plugin.id));
}
watch([() => props.plugin.id, () => screens.value.map((s) => s.id).join()], reset, { immediate: true });
const has = (screen: Screen) => Boolean(installedOn(screen, props.plugin.id));
const canTick = (screen: Screen) => !buildingOn(screen, props.plugin.id) && !needsAttach(screen) && (has(screen) || fit(props.plugin, screen).ok);
function rowLine(screen: Screen) {
  const have = installedOn(screen, props.plugin.id);
  if (buildingOn(screen, props.plugin.id)) return t("editor.plugins.state.building");
  if (wanted[screen.id] && !have) return t("editor.plugins.pending.add");
  if (!wanted[screen.id] && have) return t("editor.plugins.pending.remove");
  if (isTest(have)) return t(`editor.plugins.source.${have!.source}`);
  if (hasUpdate(screen, props.plugin)) return t("editor.plugins.screen_update", { from: have!.version, to: props.plugin.version });
  if (have) return t("editor.plugins.screen_version", { version: have.version });
  const result = fit(props.plugin, screen);
  if (!result.ok) return t(`editor.plugins.misfit_short.${result.reason}`);
  if (needsAttach(screen)) return t("editor.plugins.attach.row");
  return screen.shape?.catalog ? boardTitle(screen.shape.catalog) : "";
}
const adding = computed(() => screens.value.filter((s) => wanted[s.id] && !has(s)));
const removing = computed(() => screens.value.filter((s) => !wanted[s.id] && has(s)));
// An update that asks for other rights waits for the person's yes, shown above the update keys.
const askConsent = computed(() => screens.value.some((s) => installedOn(s, props.plugin.id) && needsConsent(s, props.plugin)));
const agreed = computed(() => !askConsent.value || Boolean(plugins.consented[props.plugin.id]));
const updatable = computed(() => screens.value.filter((s) => hasUpdate(s, props.plugin)));
const applyText = computed(() => {
  const add = adding.value.length, drop = removing.value.length;
  if (add && drop) return t("editor.plugins.apply.both", { n: add + drop }, add + drop);
  if (drop) return t("editor.plugins.apply.remove", { n: drop }, drop);
  if (!add) return t("editor.plugins.apply.none");
  return t("editor.plugins.apply.add", { n: add }, add);
});
function apply() {
  // Adding sets the plugin aside on each ticked screen (the tray builds them); taking it off a screen goes at once.
  for (const screen of adding.value) setAside(screen, props.plugin);
  if (removing.value.length) askRemove(removing.value);
  trust.value = false;
}
watch(() => screens.value.map((s) => `${s.id}:${installedOn(s, props.plugin.id)?.version || ""}`).join(), reset);
</script>

<template>
  <div class="pd-top">
    <span class="plugin-icon large" :class="{ tessera: plugin.tessera }" aria-hidden="true"><span class="mdi">{{ glyph(plugin.icon) }}</span></span>
    <span class="pd-top-end">
      <!-- A heart for a plugin that runs on one of the screens; before that it only shows how many like it. -->
      <button v-if="plugin.source === 'index'" type="button" class="pd-like" id="plugin-like" :class="{ on: plugin.liked }" :aria-pressed="Boolean(plugin.liked)"
        :disabled="!canLike(plugin) && !plugin.liked" :title="canLike(plugin) || plugin.liked ? t(plugin.liked ? 'editor.plugins.likes.unlike' : 'editor.plugins.likes.like') : t('editor.plugins.likes.install_first')"
        @click="toggleLike()"><Icon :name="plugin.liked ? 'heart' : 'heart-outline'" /><span>{{ plugin.likes || 0 }}</span></button>
      <button type="button" class="icon-btn" :aria-label="t('editor.common.close')" @click="$emit('close')"><Icon name="close" /></button>
    </span>
  </div>
  <div v-if="askingLike" class="pd-confirm" id="plugin-like-ask">
    <p>{{ t("editor.plugins.likes.ask") }} <a href="https://tessera-maxgramser.on-forge.com/privacy" target="_blank" rel="noopener">{{ t("editor.plugins.privacy") }}</a></p>
    <div class="pd-buttons">
      <button type="button" class="btn primary" id="plugin-like-yes" @click="toggleLike(true)"><Icon name="heart" />{{ t("editor.plugins.likes.like") }}</button>
      <button type="button" class="btn quiet" @click="askingLike = false">{{ t("editor.common.cancel") }}</button>
    </div>
  </div>
  <div class="pd-title">
    <h2 id="plugin-name">{{ text(plugin.name) }}</h2>
    <p class="pd-by">
      {{ plugin.tessera ? t("editor.plugins.from_tessera") : t("editor.plugins.by", { maker: plugin.maintainer }) }}
      <template v-if="label !== 'test'"> · {{ t("editor.plugins.version", { version: plugin.version }) }}</template>
      <template v-if="plugin.license"> · {{ plugin.license }}</template>
    </p>
    <p class="pd-chips">
      <em class="plugin-chip" :class="label">{{ t(`editor.plugins.label.${label}`) }}</em>
      <em v-if="stage" class="plugin-chip" :class="stage" id="plugin-stage">{{ t(`editor.plugins.stage.${stage}`) }}</em>
      <em v-if="plugin.type" class="plugin-chip" id="plugin-type">{{ t(`editor.plugins.types.${plugin.type}`) }}</em>
      <em v-for="name in plugin.topics || []" :key="name" class="plugin-chip topic">{{ t(`editor.plugins.topics.${name}`) }}</em>
      <em v-for="mark in plugin.attributes" :key="mark" class="plugin-chip attribute">{{ t(`editor.plugins.attribute.${mark}`) }}</em>
      <em v-if="englishOnly" class="plugin-chip attribute" id="plugin-english-only">{{ t("editor.plugins.english_only") }}</em>
    </p>
  </div>
  <p v-if="text(plugin.summary)" class="pd-description">{{ text(plugin.summary) }}</p>
  <p v-if="stage" class="pd-stage" id="plugin-stage-hint">{{ t(`editor.plugins.stage_hint.${stage}`) }}</p>

  <!-- Taking it off when another plugin needs it, or one only came along with it: said once, decided here. -->
  <div v-if="confirming" class="pd-confirm" id="plugin-remove-ask">
    <p v-if="confirming.with.length">{{ t("editor.plugins.remove_ask.needed", { names: confirming.with.map(nameOf).join(", "), name: text(plugin.name) }) }}</p>
    <label v-if="confirming.orphans.length" class="pd-part">
      <input type="checkbox" v-model="alsoOrphans" id="plugin-remove-orphans" />
      <span><b>{{ t("editor.plugins.remove_ask.orphans", { names: confirming.orphans.map(nameOf).join(", ") }) }}</b><small>{{ t("editor.plugins.remove_ask.orphans_note", { name: text(plugin.name) }) }}</small></span>
    </label>
    <div class="pd-buttons">
      <button type="button" class="btn primary" id="plugin-remove-yes" @click="confirmRemove">{{ confirming.with.length ? t("editor.plugins.remove_ask.both") : t("editor.plugins.remove_ask.go") }}</button>
      <button type="button" class="btn quiet" @click="confirming = null">{{ t("editor.common.cancel") }}</button>
    </div>
  </div>

  <!-- In a screen's tab, for a screen with its own YAML that is not attached yet: one line, once. After that the add-on
       keeps its plugins file and the screen is like any other; ESPHome Device Builder builds it as always. -->
  <div v-if="here && hereAttach && !hereInstalled" class="pd-action" id="plugin-attach">
    <p class="pd-note pd-attach-note"><Icon name="code-braces" /><span>{{ t("editor.plugins.attach.text", { screen: here.name }) }}</span></p>
    <pre class="pd-yaml">{{ attachLine(here) }}</pre>
    <div class="pd-buttons">
      <button type="button" class="btn quiet" id="plugin-copy-line" @click="copyAttach(here)"><Icon name="content-copy" />{{ t("editor.plugins.attach.copy") }}</button>
      <button type="button" class="btn primary" id="plugin-attached" @click="markAttached(here)">{{ t("editor.plugins.attach.done") }}</button>
    </div>
    <details v-if="pluginsFile(here)" class="pd-file">
      <summary><Icon name="chevron-right" />{{ t("editor.plugins.attach.file", { file: fileOf(here) }) }}</summary>
      <pre class="pd-yaml">{{ pluginsFile(here) }}</pre>
    </details>
  </div>

  <!-- In a screen's tab: the action for this screen, and what stands in its way. -->
  <div v-else-if="here && hereStatus" class="pd-action" :class="hereStatus.kind">
    <p v-if="!hereFit.ok && !hereInstalled" class="pd-misfit" id="plugin-misfit"><Icon name="information-outline" />{{ t(`editor.plugins.misfit.${hereFit.reason}`, { screen: here.name, kb: headroomKb(here) }) }}</p>
    <template v-else-if="hereStatus.kind === 'test'">
      <p class="pd-note">{{ t("editor.plugins.test_note") }}</p>
      <div class="pd-buttons">
        <button type="button" class="btn primary" id="plugin-rebuild" @click="addPlugin([here], plugin)">{{ t("editor.plugins.rebuild") }}</button>
        <button type="button" class="btn quiet" @click="askRemove([here])">{{ t("editor.plugins.remove", { screen: here.name }) }}</button>
      </div>
    </template>
    <template v-else-if="hereStatus.kind === 'failed'">
      <p class="pd-misfit" id="plugin-failed"><Icon name="information-outline" />{{ t("editor.plugins.failed", { screen: here.name }) }}</p>
      <div class="pd-buttons">
        <button type="button" class="btn primary" @click="addPlugin([here], plugin)">{{ t("editor.plugins.retry") }}</button>
        <button type="button" class="btn quiet" @click="askRemove([here])">{{ t("editor.plugins.remove", { screen: here.name }) }}</button>
      </div>
    </template>
    <p v-else-if="hereStatus.kind === 'building'" class="pd-note"><span class="spin" aria-hidden="true"></span>{{ t("editor.plugins.building", { screen: here.name }) }}</p>
    <template v-else-if="hereInstalled">
      <p class="pd-note"><Icon name="check-circle" />{{ t("editor.plugins.installed_on", { screen: here.name, version: hereInstalled.version }) }}</p>
      <p v-if="cameWith.length" class="pd-note pd-along-note" id="plugin-came-with"><Icon name="link-variant" />{{ t("editor.plugins.along.came_with", { names: cameWith.map((p) => text(p.name)).join(", ") }) }}</p>
      <p v-else-if="hereNeeded.length" class="pd-note pd-along-note" id="plugin-needed-by"><Icon name="link-variant" />{{ t("editor.plugins.along.needed_now", { names: hereNeeded.map((p) => text(p.name)).join(", ") }) }}</p>
      <p v-if="hereInstalled.blocked" class="pd-misfit" id="plugin-blocked"><Icon name="alert-circle-outline" />{{ t("editor.plugins.blocked_now", { why: hereInstalled.blocked }) }}</p>
      <template v-if="hereOther">
        <p class="pd-misfit" id="plugin-other-origin"><Icon name="information-outline" />{{ t("editor.plugins.other_origin", { origin: hereInstalled.origin }) }}</p>
        <div class="pd-buttons"><button type="button" class="btn quiet" id="plugin-switch" @click="switchPlugin(here, plugin)">{{ t("editor.plugins.switch", { origin: plugin.origin }) }}</button></div>
      </template>
      <label v-if="hereStatus.kind === 'update' && askConsent" class="pd-trust" id="plugin-consent">
        <input type="checkbox" :checked="plugins.consented[plugin.id]" @change="plugins.consented[plugin.id] = ($event.target as HTMLInputElement).checked" />
        <span><b>{{ t("editor.plugins.consent.title") }}</b>{{ t("editor.plugins.consent.agree") }}</span>
      </label>
      <div class="pd-buttons">
        <button v-if="hereStatus.kind === 'update'" type="button" class="btn primary" id="plugin-update" :disabled="!agreed" @click="addPlugin([here], plugin)">{{ t("editor.plugins.update", { version: plugin.version }) }}</button>
        <a v-if="hereStatus.kind === 'update' && changes" class="btn quiet" id="plugin-changes" :href="changes" target="_blank" rel="noopener">{{ t("editor.plugins.changes") }}</a>
        <button type="button" class="btn quiet" id="plugin-remove" @click="askRemove([here])">{{ t("editor.plugins.remove", { screen: here.name }) }}</button>
      </div>
    </template>
    <template v-else>
      <PluginSetup :plugin="plugin" :screens="[here]" />
      <!-- What comes along: a plugin it needs, or the one plugin that brings a feature it needs; set aside with it. -->
      <div v-if="hereAlong.length || herePlan?.choose?.length || herePlan?.error" class="pd-along" id="plugin-along">
        <p class="pd-label">{{ t("editor.plugins.along.title") }}</p>
        <p v-if="herePlan?.error" class="pd-misfit"><Icon name="information-outline" />{{ herePlan.error }}</p>
        <div v-for="row in hereAlong" :key="row.plugin.id" class="pd-along-row" :data-plugin="row.plugin.id">
          <span class="plugin-icon" :class="{ tessera: row.plugin.tessera }" aria-hidden="true"><span class="mdi">{{ glyph(row.plugin.icon) }}</span></span>
          <span class="pd-along-words"><b>{{ text(row.plugin.name) }}</b><small>{{ whyAlong(row) }} · {{ row.plugin.tessera ? t("editor.plugins.from_tessera") : t("editor.plugins.by", { maker: row.plugin.maintainer }) }} · {{ kb(row.step.flash_kb) }} KB</small></span>
        </div>
        <label v-for="choice in herePlan?.choose || []" :key="choice.feature" class="field pd-choose">
          <span class="f-label">{{ t("editor.plugins.along.choose", { what: feature(choice.feature) }) }}</span>
          <select :data-feature="choice.feature" @change="chooseProvider(here!, choice.feature, ($event.target as HTMLSelectElement).value)">
            <option value="" selected disabled>{{ t("editor.plugin_tile.choose") }}</option>
            <option v-for="id in choice.options" :key="id" :value="id">{{ nameOf(id) }}</option>
          </select>
        </label>
      </div>
      <!-- Set aside, not built: the tray takes it with whatever else is chosen, and builds the screen once. -->
      <button type="button" class="btn pd-install" :class="isSetAside(here, plugin.id) ? 'quiet' : 'primary'" id="plugin-install" @click="toggleSetAside(here, plugin)">
        <Icon :name="isSetAside(here, plugin.id) ? 'check' : 'plus'" />{{ isSetAside(here, plugin.id) ? t("editor.plugins.tray.in_tray") : t("editor.plugins.tray.stage", { screen: here.name }) }}
      </button>
      <p class="pd-build-note">{{ isSetAside(here, plugin.id) ? t("editor.plugins.tray.in_tray_note") : t("editor.plugins.build_note") }}</p>
    </template>
  </div>

  <!-- On the Plugins page: a box per screen; what does not fit stays in the list, greyed out, with its reason. -->
  <div v-else-if="!here" class="pd-action pd-screens-box">
    <p class="pd-label">{{ t("editor.plugins.on_screens") }}</p>
    <ul class="pd-screens" id="plugin-screens">
      <li v-for="s in screens" :key="s.id" :class="{ off: !canTick(s) }">
        <label>
          <input type="checkbox" :checked="wanted[s.id]" :disabled="!canTick(s)" :data-screen="s.name" @change="wanted[s.id] = ($event.target as HTMLInputElement).checked" />
          <span class="pd-screen-words"><b>{{ s.name }}</b><small :class="{ 'pd-pending': Boolean(wanted[s.id]) !== has(s) }">{{ rowLine(s) }}</small></span>
        </label>
        <span v-if="buildingOn(s, plugin.id)" class="spin small" aria-hidden="true"></span>
      </li>
    </ul>
    <PluginSetup :plugin="plugin" :screens="adding" />
    <div class="pd-buttons">
      <button type="button" class="btn primary" id="plugin-apply" :disabled="!(adding.length || removing.length) || !setupReady(plugin, adding)" @click="apply">{{ applyText }}</button>
      <label v-if="updatable.length && askConsent" class="pd-trust" id="plugin-consent-all">
        <input type="checkbox" :checked="plugins.consented[plugin.id]" @change="plugins.consented[plugin.id] = ($event.target as HTMLInputElement).checked" />
        <span><b>{{ t("editor.plugins.consent.title") }}</b>{{ t("editor.plugins.consent.agree") }}</span>
      </label>
      <button v-if="updatable.length" type="button" class="btn quiet" id="plugin-update-all" :disabled="!agreed" @click="addPlugin(updatable, plugin)">{{ t("editor.plugins.update_all", { n: updatable.length, version: plugin.version }, updatable.length) }}</button>
    </div>
  </div>

  <!-- A plugin this screen runs: all of its settings in one place, in three groups by what a change does. -->
  <section v-if="here && hereSettings" class="pd-section pd-settings" id="plugin-settings">
    <h3>{{ t("editor.plugins.settings.title") }}</h3>
    <div v-if="plugin.settings?.length" class="pd-group" id="plugin-settings-live">
      <p class="pd-group-head"><b>{{ t("editor.plugins.settings.live") }}</b><small>{{ t("editor.plugins.settings.live_note") }}</small></p>
      <PluginSettings :plugin="plugin.id" />
    </div>
    <div v-if="sharedInputs.length" class="pd-group" id="plugin-settings-shared">
      <p class="pd-group-head"><b>{{ t("editor.plugins.settings.shared") }}</b><small>{{ t("editor.plugins.settings.shared_note") }}</small></p>
      <PluginSetup :plugin="plugin" :screens="[here]" only="shared" />
    </div>
    <div v-if="buildInputs" class="pd-group" id="plugin-settings-build">
      <p class="pd-group-head"><b>{{ t("editor.plugins.settings.build") }}</b><small>{{ t("editor.plugins.settings.build_note", { screen: here.name }) }}</small></p>
      <PluginSetup :plugin="plugin" :screens="[here]" only="screen" />
    </div>
    <button v-if="sharedInputs.length || buildInputs" type="button" class="btn primary pd-save" id="plugin-settings-save"
      :disabled="!hereChanged || hereStatus?.kind === 'building'" @click="addPlugin([here], plugin)">{{ t("editor.plugins.settings.save_build") }}</button>
  </section>

  <!-- The plugin's README: what to do in Home Assistant, where a key comes from. Its own words, safely shown. -->
  <section v-if="text(plugin.readme)" class="pd-section" id="plugin-readme">
    <h3>{{ t("editor.plugins.readme.title") }}</h3>
    <PluginReadme :source="text(plugin.readme)" :repo="plugin.repo" />
  </section>

  <section v-if="label !== 'test'" class="pd-section">
    <h3>{{ t("editor.plugins.adds.title") }}</h3>
    <ul class="pd-list">
      <li v-for="tile in plugin.tiles || []" :key="`tile-${tile.id}`"><Icon name="view-dashboard-outline" /><span><b>{{ t("editor.plugins.adds.tile", { name: text(tile.name) }) }}</b><small>{{ t("editor.plugins.adds.tile_sizes", { min: tile.min, max: tile.max }) }}</small></span></li>
      <li v-for="card in plugin.cards || []" :key="`card-${card.id}`"><Icon name="monitor-eye" /><span><b>{{ t("editor.plugins.adds.card", { name: text(card.name) }) }}</b></span></li>
      <li v-for="action in plugin.tap_actions || []" :key="`tap-${action.id}`"><Icon name="gesture-tap" /><span><b>{{ t("editor.plugins.adds.tap", { name: text(action.label) }) }}</b><small>{{ t("editor.plugins.adds.tap_on", { domains: action.domains.map(domainName).join(", ") }) }}</small></span></li>
      <li v-for="bar in plugin.bar_items || []" :key="`bar-${bar.id}`"><Icon name="page-layout-header" /><span><b>{{ t("editor.plugins.adds.bar", { name: text(bar.label) }) }}</b></span></li>
      <li v-if="plugin.settings?.length"><Icon name="cog-outline" /><span><b>{{ t("editor.plugins.adds.settings") }}</b><small>{{ t("editor.plugins.adds.settings_where") }}</small></span></li>
    </ul>
  </section>

  <section v-if="plugin.requires.plugins?.length || plugin.requires.features?.length || plugin.provides?.length" class="pd-section" id="plugin-needs">
    <h3>{{ t("editor.plugins.needs.title") }}</h3>
    <ul class="pd-list">
      <li v-for="id in plugin.requires.plugins || []" :key="`p-${id}`"><Icon name="puzzle-outline" /><span><b>{{ nameOf(id) }}</b><small>{{ t("editor.plugins.needs.plugin") }}</small></span></li>
      <li v-for="name in plugin.requires.features || []" :key="`f-${name}`"><Icon name="speaker" /><span><b>{{ t("editor.plugins.needs.feature", { what: feature(name) }) }}</b><small>{{ t("editor.plugins.needs.feature_note") }}</small></span></li>
      <li v-for="name in plugin.provides || []" :key="`b-${name}`"><Icon name="puzzle-outline" /><span><b>{{ t("editor.plugins.needs.brings", { what: feature(name) }) }}</b><small>{{ t("editor.plugins.needs.brings_note") }}</small></span></li>
    </ul>
  </section>

  <section class="pd-section">
    <h3>{{ t("editor.plugins.may.title") }}</h3>
    <ul class="pd-list">
      <li><Icon name="home-outline" /><span>
        <b>{{ plugin.permissions.home_assistant.length ? t("editor.plugins.may.ha") : t("editor.plugins.may.ha_none") }}</b>
        <small v-if="plugin.permissions.home_assistant.length"><code v-for="kind in plugin.permissions.home_assistant" :key="kind">{{ kind }}</code></small>
      </span></li>
      <li v-if="plugin.permissions.read_entities?.length"><Icon name="eye-outline" /><span><b>{{ t("editor.plugins.may.read") }}</b><small><code v-for="entity in plugin.permissions.read_entities" :key="entity">{{ entity }}</code></small></span></li>
      <li><Icon name="wifi-strength-off-outline" /><span><b>{{ plugin.permissions.network.length ? t("editor.plugins.may.network", { hosts: plugin.permissions.network.join(", ") }) : t("editor.plugins.may.network_none") }}</b></span></li>
    </ul>
    <p v-if="!plugin.tessera" class="pd-warning" id="plugin-warning">{{ t("editor.plugins.warning") }}</p>
  </section>

  <section v-if="label !== 'test'" class="pd-section">
    <h3>{{ here ? t("editor.plugins.room.title", { screen: here.name }) : t("editor.plugins.room.title_all") }}</h3>
    <template v-if="hereFlash">
      <div class="pd-meter" :class="{ tight: hereFlash.after > 0.9 }" role="meter" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="Math.round(hereFlash.after * 100)">
        <i class="before" :style="{ width: hereFlash.before * 100 + '%' }"></i>
        <i class="added" :style="{ left: hereFlash.before * 100 + '%', width: Math.max(0.6, (hereFlash.after - hereFlash.before) * 100) + '%' }"></i>
      </div>
      <p class="pd-room">{{ t("editor.plugins.room.small", { kb: kb(plugin.flash_kb + (here ? partsKb(here, plugin) : 0)), before: percent(hereFlash.before), after: percent(hereFlash.after) }) }}</p>
    </template>
    <p v-else-if="here" class="pd-room">{{ t("editor.plugins.room.large", { kb: kb(plugin.flash_kb + partsKb(here, plugin)) }) }}</p>
    <p v-else class="pd-room">{{ t("editor.plugins.room.per_screen", { kb: kb(plugin.flash_kb) }) }}</p>
    <p class="pd-room"><span class="pd-works">{{ t("editor.plugins.works.title") }}</span> {{ works }}</p>
  </section>

  <p class="pd-links">
    <a v-if="plugin.repo" :href="plugin.repo" target="_blank" rel="noopener">{{ t("editor.plugins.source_code") }}</a>
    <a v-if="plugin.repo && !plugin.tessera" :href="`${plugin.repo}/issues`" target="_blank" rel="noopener">{{ t("editor.plugins.issues") }}</a>
    <a v-if="plugin.privacy" :href="plugin.privacy" target="_blank" rel="noopener">{{ t("editor.plugins.privacy") }}</a>
  </p>
</template>
