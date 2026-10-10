<script setup lang="ts">
// The details of one plugin, in the column on the right: who made it, what to do with it, its README, what it adds,
// what it may do and the room it takes. On the Plugins page (no `screen`) the action is a box per screen, ticked where it
// is on and greyed out with its reason where it does not fit (plugins/PluginOnScreens); in a screen's Plugins tab it is
// the one action for that screen (plugins/PluginOnScreen). Taking it off is said here, once, for either.
import { computed, ref } from "vue";
import { editorLanguage, editorNumber, t, te } from "../i18n";
import { changesBetween, flashShare, inEditorLanguage, text, type Plugin } from "../model/plugins";
import { glyph } from "../model/topbar";
import type { Screen } from "../types";
import PluginReadme from "./PluginReadme.vue";
import PluginSettings from "./PluginSettings.vue";
import PluginSetup from "./PluginSetup.vue";
import PluginOnScreen from "./plugins/PluginOnScreen.vue";
import PluginOnScreens from "./plugins/PluginOnScreens.vue";
import Icon from "./ui/Icon.vue";
import { useUiStore } from "../stores/ui";
import { usePluginsStore } from "../stores/plugins";

const ui = useUiStore();
const plugins = usePluginsStore();

const props = defineProps<{ plugin: Plugin; screen?: Screen | null }>();
defineEmits<{ close: [] }>();

const label = computed(() => plugins.labelOf(props.plugin));
const stage = computed(() => plugins.stageOf(props.plugin));
const kb = (value: number) => editorNumber(value);
const percent = (share: number) => `${editorNumber((share * 100).toFixed(1))} %`;
const works = computed(() => props.plugin.boards === "any"
  ? t(props.plugin.requires.psram ? "editor.plugins.works.any_psram" : "editor.plugins.works.any")
  : (props.plugin.board_names || props.plugin.boards).join(", "));
const domainName = (domain: string) => (te(`editor.domains.${domain}`) ? t(`editor.domains.${domain}`) : domain);
// A plugin whose own words are not in the editor's language shows them in English and says so, once.
const englishOnly = computed(() => !editorLanguage().startsWith("en") && !inEditorLanguage(props.plugin.readme));

// ---- One screen (its Plugins tab) ----
const here = computed(() => props.screen || null);
const hereStatus = computed(() => (here.value ? plugins.statusOn(props.plugin, here.value) : null));
const hereInstalled = computed(() => (here.value ? plugins.installedOn(here.value, props.plugin.id) : undefined));
const hereFlash = computed(() => (here.value ? flashShare(props.plugin, here.value, plugins.partsKb(here.value, props.plugin)) : null));
// The settings of a plugin this screen runs, grouped by what a change does: at once (its ESPHome entities), for every
// screen (what was filled in once), or a new build of this screen (its own inputs and parts).
const sharedInputs = computed(() => (props.plugin.inputs || []).filter((input) => input.scope === "all"));
const buildInputs = computed(() => (props.plugin.inputs || []).filter((input) => input.scope === "screen").length + (props.plugin.parts || []).length);
const hereSettings = computed(() => Boolean(here.value && hereInstalled.value
  && (props.plugin.settings?.length || sharedInputs.value.length || buildInputs.value)));
const hereChanged = computed(() => Boolean(here.value && plugins.setupChanged(here.value, props.plugin)));

// ---- What it needs and what it brings ----
const byId = (id: string) => plugins.index.find((p) => p.id === id);
const nameOf = (id: string) => (byId(id) ? text(byId(id)!.name) : id);
const feature = (name: string) => (te(`editor.plugins.features.${name}`) ? t(`editor.plugins.features.${name}`) : name);
// Taking it off: a plugin that needs it goes with it, and one that only came along with it may go too; the person says.
const confirming = ref<null | { screens: Screen[]; with: string[]; orphans: string[] }>(null);
const alsoOrphans = ref(true);
function askRemove(screens: Screen[]) {
  const plan = plugins.removalPlan(screens, props.plugin);
  if (!plan.with.length && !plan.orphans.length) return plugins.removePlugin(screens, props.plugin);
  alsoOrphans.value = true;
  confirming.value = { screens, ...plan };
}
function confirmRemove() {
  const ask = confirming.value!;
  confirming.value = null;
  plugins.removePlugin(ask.screens, props.plugin, [...ask.with, ...(alsoOrphans.value ? ask.orphans : [])]);
}
// A like: the first one asks once whether it may count in a public number (plugin_likes.py).
const askingLike = ref(false);
async function toggleLike(consent = false) {
  if (!props.plugin.liked && !plugins.likeConsent && !consent) { askingLike.value = true; return; }
  askingLike.value = false;
  try { await plugins.like(props.plugin, !props.plugin.liked, consent); } catch (error: any) { ui.toast(error.message); }
}

// What an update brings: the plugin's changelog from the version the screen runs (on the Plugins page: the oldest of the
// screens with the update) up to the one on offer, and GitHub's compare as the full story. Every release, folded, for a
// plugin with a changelog and no update waiting.
const newsFrom = computed(() => plugins.newsFrom(props.plugin, here.value));
const news = computed(() => (newsFrom.value ? changesBetween(text(props.plugin.changelog || {}), newsFrom.value, props.plugin.version) : ""));
const newsCompare = computed(() => plugins.compareFor(props.plugin, here.value));
const history = computed(() => (!newsFrom.value ? changesBetween(text(props.plugin.changelog || {})) : ""));
</script>

<template>
  <div class="pd-top">
    <span class="plugin-icon large" :class="{ tessera: plugin.tessera }" aria-hidden="true"><span class="mdi">{{ glyph(plugin.icon) }}</span></span>
    <span class="pd-top-end">
      <!-- A heart for a plugin that runs on one of the screens; before that it only shows how many like it. -->
      <button v-if="plugin.source === 'index'" type="button" class="pd-like" id="plugin-like" :class="{ on: plugin.liked }" :aria-pressed="Boolean(plugin.liked)"
        :disabled="!plugins.canLike(plugin) && !plugin.liked" :title="plugins.canLike(plugin) || plugin.liked ? t(plugin.liked ? 'editor.plugins.likes.unlike' : 'editor.plugins.likes.like') : t('editor.plugins.likes.install_first')"
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

  <!-- In a screen's tab: the action for this screen; on the Plugins page: a box per screen. -->
  <PluginOnScreen v-if="here" :plugin="plugin" :screen="here" @remove="askRemove" />
  <PluginOnScreens v-else :plugin="plugin" @remove="askRemove" />

  <!-- What an update brings, before the person presses it: the changelog's lines from the version they run. -->
  <section v-if="newsFrom" class="pd-section pd-news" id="plugin-news">
    <h3>{{ t("editor.plugins.news.title", { version: plugin.version }) }}</h3>
    <PluginReadme v-if="news" :source="news" :repo="plugin.repo" />
    <p v-else class="pd-room">{{ t("editor.plugins.news.none") }}</p>
    <a v-if="newsCompare" class="pd-news-link" :href="newsCompare" target="_blank" rel="noopener">{{ t("editor.plugins.changes") }}</a>
  </section>

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
      :disabled="!hereChanged || hereStatus?.kind === 'building'" @click="plugins.addPlugin([here], plugin)">{{ t("editor.plugins.settings.save_build") }}</button>
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
      <p class="pd-room">{{ t("editor.plugins.room.small", { kb: kb(plugin.flash_kb + (here ? plugins.partsKb(here, plugin) : 0)), before: percent(hereFlash.before), after: percent(hereFlash.after) }) }}</p>
    </template>
    <p v-else-if="here" class="pd-room">{{ t("editor.plugins.room.large", { kb: kb(plugin.flash_kb + plugins.partsKb(here, plugin)) }) }}</p>
    <p v-else class="pd-room">{{ t("editor.plugins.room.per_screen", { kb: kb(plugin.flash_kb) }) }}</p>
    <p class="pd-room"><span class="pd-works">{{ t("editor.plugins.works.title") }}</span> {{ works }}</p>
  </section>

  <details v-if="history" class="pd-section pd-history" id="plugin-history">
    <summary><h3>{{ t("editor.plugins.news.history") }}</h3><Icon name="chevron-down" /></summary>
    <PluginReadme :source="history" :repo="plugin.repo" />
  </details>

  <p class="pd-links">
    <a v-if="plugin.repo" :href="plugin.repo" target="_blank" rel="noopener">{{ t("editor.plugins.source_code") }}</a>
    <a v-if="plugin.repo && !plugin.tessera" :href="`${plugin.repo}/issues`" target="_blank" rel="noopener">{{ t("editor.plugins.issues") }}</a>
    <a v-if="plugin.privacy" :href="plugin.privacy" target="_blank" rel="noopener">{{ t("editor.plugins.privacy") }}</a>
  </p>
</template>
