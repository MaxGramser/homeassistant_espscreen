<script setup lang="ts">
// Plugins (design for the plugins proposal): every plugin there is, and on which of your screens it is. A plugin lives
// in a screen's firmware, so this page does not install anything for "the app": its details tick the screens it goes
// on, greyed out where it does not fit. A screen's own Plugins tab does the same for that one screen. The list is the
// add-on's: the plugin index, and the plugins someone is making in a folder of Home Assistant's config (a test).
import { computed, ref, watch } from "vue";
import { t } from "../i18n";
import { fit, PLUGIN_TOPICS, PLUGIN_TYPES, text, type Plugin } from "../model/plugins";
import { allTests, installedOn, isSetAside, loadPlugins, plugins, realScreens, statusOverall, toggleSetAside, tray } from "../plugin-state";
// The folder as Home Assistant shows it (config/...), not as the app's container mounts it (/homeassistant/...).
const folderShown = (path: string) => path.replace(/^\/(homeassistant|config)\//, "config/");
import { buildingScreens, buildOf, go } from "../store";
import BuildLog from "./BuildLog.vue";
import PluginCard from "./PluginCard.vue";
import PluginDetail from "./PluginDetail.vue";
import PluginLink from "./PluginLink.vue";
import PluginMaker from "./PluginMaker.vue";
import PluginTray from "./PluginTray.vue";
import Icon from "./ui/Icon.vue";

loadPlugins();
// Three tabs by what a plugin adds (read from its manifest), so a countdown is never found among a board's audio parts,
// and what is on a screen now; under them the topics its makers gave, as chips; a search looks through every tab.
const TABS = [...PLUGIN_TYPES, "in_use"] as const;
type Tab = (typeof TABS)[number];
const tab = ref<Tab>("tiles");
const topic = ref<string | null>(null);
// Most liked first by default; or the newest, or by name. Tessera's recommendation (featured.yaml) breaks a tie.
const SORTS = ["popular", "new", "name"] as const;
const sort = ref<(typeof SORTS)[number]>("popular");
// Who made it: anyone, Tessera, or the community.
const MAKERS = ["all", "tessera", "community"] as const;
const maker = ref<(typeof MAKERS)[number]>("all");
// Only what fits one of the screens: on by default, the rest folds away under the list.
const fittingOnly = ref(true);
const query = ref("");
const everything = computed(() => [...plugins.index, ...allTests()]);
const inUse = (plugin: Plugin) => realScreens().some((screen) => installedOn(screen, plugin.id));
const inTab = (plugin: Plugin, key: Tab) => (key === "in_use" ? inUse(plugin) : (plugin.type || "functions") === key);
const matches = (plugin: Plugin) => {
  const words = query.value.toLocaleLowerCase().split(/\s+/).filter(Boolean);
  const topics = (plugin.topics || []).map((name) => t(`editor.plugins.topics.${name}`)).join(" ");
  return words.every((word) => `${text(plugin.name)} ${text(plugin.summary)} ${plugin.maintainer} ${plugin.id} ${topics}`
    .toLocaleLowerCase().includes(word));
};
const found = computed(() => everything.value.filter(matches));
const count = (key: Tab) => found.value.filter((plugin) => inTab(plugin, key)).length;
// The topics of the plugins in this tab, each with how many: only those there are.
const topics = computed(() => {
  const counts = new Map<string, number>();
  for (const plugin of found.value.filter((p) => inTab(p, tab.value))) for (const name of plugin.topics || []) counts.set(name, (counts.get(name) || 0) + 1);
  return PLUGIN_TOPICS.filter((name) => counts.has(name)).map((name) => ({ name, n: counts.get(name)! }));
});
watch(tab, () => { topic.value = null; });
watch(topics, (list) => { if (topic.value && !list.some((item) => item.name === topic.value)) topic.value = null; });
// Recommended first (Tessera's featured.yaml), then the most liked, then by name; or the most liked, or the newest.
const byName = (a: Plugin, b: Plugin) => text(a.name).localeCompare(text(b.name));
const order = (a: Plugin, b: Plugin) => sort.value === "name" ? byName(a, b)
  : sort.value === "new" ? String(b.date || "").localeCompare(String(a.date || "")) || byName(a, b)
  : (b.likes || 0) - (a.likes || 0) || Number(Boolean(b.featured)) - Number(Boolean(a.featured)) || byName(a, b);
const byMaker = (plugin: Plugin) => maker.value === "all" || (maker.value === "tessera" ? plugin.tessera : !plugin.tessera);
const listed = computed(() => found.value.filter((plugin) => inTab(plugin, tab.value) && byMaker(plugin)
  && (!topic.value || (plugin.topics || []).includes(topic.value))).sort(order));
// What fits none of this app's screens folds away under the list, with its reason on the card: it is still there to look
// at, never hidden the way a store hides what a phone cannot run.
const fitsSome = (plugin: Plugin) => !realScreens().length || inUse(plugin) || realScreens().some((screen) => fit(plugin, screen).ok);
const shown = computed(() => listed.value.filter((plugin) => !fittingOnly.value || fitsSome(plugin)));
const misfits = computed(() => (fittingOnly.value ? listed.value.filter((plugin) => !fitsSome(plugin)) : []));
const misfitsOpen = ref(false);

const panel = ref<"plugin" | "link" | null>(null);
const openId = ref<string | null>(null);
const open = computed(() => everything.value.find((plugin) => plugin.id === openId.value) || null);
// The tray folds to its head while details are open, and opens again when they close.
function show(plugin: Plugin) { openId.value = plugin.id; panel.value = "plugin"; tray.open = false; }
function close() { panel.value = null; openId.value = null; tray.open = true; }
// Add on a card goes straight to the tray when there is one screen it can go on; with more, its details ask which.
const onlyScreen = (plugin: Plugin) => {
  const fits = realScreens().filter((screen) => !installedOn(screen, plugin.id) && fit(plugin, screen).ok);
  return fits.length === 1 && realScreens().length === 1 ? fits[0] : null;
};
const pluginBuilds = computed(() => buildingScreens().filter((screen) => buildOf(screen)?.by === "plugins"));
</script>

<template>
  <div class="setup plugins" id="plugins" :class="{ 'with-detail': panel }">
    <header class="setup-head">
      <span class="setup-brand">{{ t("editor.plugins.title") }}</span>
      <span class="setup-steps-spacer"></span>
      <div class="plugins-head-actions">
        <button type="button" class="btn quiet" id="plugin-add-link" :aria-pressed="panel === 'link'" @click="panel = 'link'; openId = null"><Icon name="link-variant" />{{ t("editor.plugins.add_link") }}</button>
        <button type="button" class="icon-btn" id="close-plugins" :aria-label="t('editor.common.close')" :title="t('editor.common.close')" @click="go('')"><Icon name="close" /></button>
      </div>
    </header>

    <div class="plugins-frame">
      <section class="plugins-list">
        <h1>{{ t("editor.plugins.title") }}</h1>
        <p class="setup-lead">{{ t("editor.plugins.intro") }}</p>
        <!-- The screens building their plugins now, each with its progress and log (the store's builds). -->
        <div v-if="pluginBuilds.length" class="plugin-builds" id="plugin-builds">
          <BuildLog v-for="screen in pluginBuilds" :key="screen.id" :screen="screen" name />
        </div>
        <div class="pick-tools">
          <label class="pick-search"><Icon name="magnify" /><input id="plugin-search" v-model="query" type="search" :placeholder="t('editor.plugins.search')" autocomplete="off" spellcheck="false" /></label>
          <div class="seg" role="tablist" id="plugin-tabs" :aria-label="t('editor.plugins.filter')">
            <button v-for="key in TABS" :key="key" type="button" role="tab" :aria-selected="tab === key" :aria-pressed="tab === key" :data-tab="key" @click="tab = key">{{ t(`editor.plugins.tabs.${key}`) }} <small>{{ count(key) }}</small></button>
          </div>
        </div>
        <div v-if="topics.length" class="plugin-topics" id="plugin-topics">
          <div class="plugin-topic-chips" role="group" :aria-label="t('editor.plugins.topic_filter')">
            <button v-if="topics.length" type="button" class="topic-chip" :aria-pressed="!topic" @click="topic = null">{{ t("editor.plugins.topics_all") }}</button>
            <button v-for="item in topics" :key="item.name" type="button" class="topic-chip" :aria-pressed="topic === item.name" :data-topic="item.name"
              @click="topic = topic === item.name ? null : item.name">{{ t(`editor.plugins.topics.${item.name}`) }} <small>{{ item.n }}</small></button>
          </div>
        </div>
        <div class="plugin-order" id="plugin-order">
          <label class="plugin-pick"><span>{{ t("editor.plugins.sort.label") }}</span>
            <select id="plugin-sort" v-model="sort"><option v-for="key in SORTS" :key="key" :value="key">{{ t(`editor.plugins.sort.${key}`) }}</option></select>
          </label>
          <label class="plugin-pick"><span>{{ t("editor.plugins.made_by.label") }}</span>
            <select id="plugin-maker" v-model="maker"><option v-for="key in MAKERS" :key="key" :value="key">{{ t(`editor.plugins.made_by.${key}`) }}</option></select>
          </label>
          <label v-if="realScreens().length" class="plugin-fitting"><input id="plugin-fitting" v-model="fittingOnly" type="checkbox" />{{ t("editor.plugins.fitting_only") }}</label>
        </div>
        <div class="plugin-grid" role="list">
          <PluginCard v-for="plugin in shown" :key="plugin.id" :plugin="plugin" :status="statusOverall(plugin)" :chosen="openId === plugin.id"
            :staged="onlyScreen(plugin) ? isSetAside(onlyScreen(plugin)!, plugin.id) : null" @open="show(plugin)" @add="toggleSetAside(onlyScreen(plugin)!, plugin)" />
          <p v-if="!shown.length" class="pick-none">{{ query.trim() ? t("editor.plugins.none_found", { query: query.trim() })
            : tab === "in_use" ? t("editor.plugins.none_in_use") : t(`editor.plugins.none_in_tab.${tab}`) }}</p>
        </div>
        <!-- What fits none of the screens: still there to look at, folded under the rest with the reason on each card. -->
        <div v-if="misfits.length" class="plugin-misfits" id="plugin-misfits">
          <button type="button" class="plugin-misfits-head" :aria-expanded="misfitsOpen" @click="misfitsOpen = !misfitsOpen">
            <Icon :name="misfitsOpen ? 'chevron-down' : 'chevron-right'" />{{ t("editor.plugins.fits_none_group", { n: misfits.length }, misfits.length) }}
          </button>
          <div v-if="misfitsOpen" class="plugin-grid" role="list">
            <PluginCard v-for="plugin in misfits" :key="plugin.id" :plugin="plugin" :status="statusOverall(plugin)" :chosen="openId === plugin.id" @open="show(plugin)" />
          </div>
        </div>
        <PluginMaker :folder="plugins.folders.path ? folderShown(plugins.folders.path) : ''" @link="panel = 'link'; openId = null" />
        <p v-for="(why, folder) in plugins.folders.errors" :key="folder" class="pd-misfit plugins-folder-error"><Icon name="information-outline" />{{ t("editor.plugins.folder_error", { folder, why }) }}</p>
        <PluginTray @open="show" />
      </section>

      <Transition name="drawer">
        <aside v-if="panel" class="plugin-detail" id="plugin-detail" @click.stop>
          <div class="plugin-detail-inner">
            <PluginDetail v-if="panel === 'plugin' && open" :plugin="open" @close="close" />
            <PluginLink v-else-if="panel === 'link'" @close="close" @found="show" />
          </div>
        </aside>
      </Transition>
    </div>
  </div>
</template>
