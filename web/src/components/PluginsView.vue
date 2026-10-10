<script setup lang="ts">
// Plugins (design for the plugins proposal): every plugin there is, and on which of your screens it is. A plugin lives
// in a screen's firmware, so this page does not install anything for "the app": its details tick the screens it goes
// on, greyed out where it does not fit. A screen's own Plugins tab does the same for that one screen. The list is the
// add-on's: the plugin index, and the plugins someone is making in a folder of Home Assistant's config (a test).
import { computed, ref, watch } from "vue";
import { t } from "../i18n";
import { fit, PLUGIN_TOPICS, PLUGIN_TYPES, text, type Plugin } from "../model/plugins";
import { matchesWords, queryWords } from "../model/search";
import { allTests, installedOn, isSetAside, loadPlugins, plugins, realScreens, statusOverall, toggleSetAside, tray } from "../plugin-state";
// The folder as Home Assistant shows it (config/...), not as the app's container mounts it (/homeassistant/...).
const folderShown = (path: string) => path.replace(/^\/(homeassistant|config)\//, "config/");
import BuildLog from "./BuildLog.vue";
import PluginCard from "./PluginCard.vue";
import PluginDetail from "./PluginDetail.vue";
import PluginLink from "./PluginLink.vue";
import PluginMaker from "./PluginMaker.vue";
import PluginTray from "./PluginTray.vue";
import Icon from "./ui/Icon.vue";
import UiMenu from "./ui/UiMenu.vue";
import UiMenuItem from "./ui/UiMenuItem.vue";
import UiMenuLabel from "./ui/UiMenuLabel.vue";
import UiMenuSeparator from "./ui/UiMenuSeparator.vue";
import { DropdownMenuCheckboxItem, DropdownMenuItemIndicator, DropdownMenuRadioGroup, DropdownMenuRadioItem } from "reka-ui";
import { useUiStore } from "../stores/ui";
import { useBuildsStore } from "../stores/builds";

const ui = useUiStore();
const builds = useBuildsStore();

loadPlugins();
// Three tabs by what a plugin adds (read from its manifest), so a countdown is never found among a board's audio parts,
// and what is on a screen now; under them the topics its makers gave, as chips; a search looks through every tab.
const TABS = [...PLUGIN_TYPES, "in_use"] as const;
type Tab = (typeof TABS)[number];
const tab = ref<Tab>("tiles");
const chosenTopics = ref<string[]>([]);
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
  const words = queryWords(query.value);
  const topics = (plugin.topics || []).map((name) => t(`editor.plugins.topics.${name}`)).join(" ");
  return matchesWords(words, text(plugin.name), text(plugin.summary), plugin.maintainer, plugin.id, topics);
};
const found = computed(() => everything.value.filter(matches));
const count = (key: Tab) => found.value.filter((plugin) => inTab(plugin, key)).length;
// The topics of the plugins in this tab, each with how many: only those there are.
const topics = computed(() => {
  const counts = new Map<string, number>();
  for (const plugin of found.value.filter((p) => inTab(p, tab.value))) for (const name of plugin.topics || []) counts.set(name, (counts.get(name) || 0) + 1);
  return PLUGIN_TOPICS.filter((name) => counts.has(name)).map((name) => ({ name, n: counts.get(name)! }));
});
watch(tab, () => { chosenTopics.value = []; });
watch(topics, (list) => { chosenTopics.value = chosenTopics.value.filter((name) => list.some((item) => item.name === name)); });
const toggleTopic = (name: string, on: boolean) => {
  chosenTopics.value = on ? [...new Set([...chosenTopics.value, name])] : chosenTopics.value.filter((n) => n !== name);
};
// What narrows the list now, as pills in the bar, each with its own way out; the Filter key counts them.
const pills = computed(() => [
  ...chosenTopics.value.map((name) => ({ key: `topic-${name}`, label: t(`editor.plugins.topics.${name}`), clear: () => toggleTopic(name, false) })),
  ...(maker.value !== "all" ? [{ key: "maker", label: t(`editor.plugins.made_by.${maker.value}`), clear: () => { maker.value = "all"; } }] : []),
  ...(!fittingOnly.value ? [{ key: "fitting", label: t("editor.plugins.fitting_all"), clear: () => { fittingOnly.value = true; } }] : []),
]);
const clearAll = () => { chosenTopics.value = []; maker.value = "all"; fittingOnly.value = true; };
// Recommended first (Tessera's featured.yaml), then the most liked, then by name; or the most liked, or the newest.
const byName = (a: Plugin, b: Plugin) => text(a.name).localeCompare(text(b.name));
const order = (a: Plugin, b: Plugin) => sort.value === "name" ? byName(a, b)
  : sort.value === "new" ? String(b.date || "").localeCompare(String(a.date || "")) || byName(a, b)
  : (b.likes || 0) - (a.likes || 0) || Number(Boolean(b.featured)) - Number(Boolean(a.featured)) || byName(a, b);
const byMaker = (plugin: Plugin) => maker.value === "all" || (maker.value === "tessera" ? plugin.tessera : !plugin.tessera);
const listed = computed(() => found.value.filter((plugin) => inTab(plugin, tab.value) && byMaker(plugin)
  && (!chosenTopics.value.length || (plugin.topics || []).some((name) => chosenTopics.value.includes(name)))).sort(order));
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
const pluginBuilds = computed(() => builds.buildingScreens.filter((screen) => builds.buildOf(screen)?.by === "plugins"));
</script>

<template>
  <div class="setup plugins" id="plugins" :class="{ 'with-detail': panel }">
    <header class="setup-head">
      <span class="setup-brand">{{ t("editor.plugins.title") }}</span>
      <span class="setup-steps-spacer"></span>
      <div class="plugins-head-actions">
        <button type="button" class="btn quiet" id="plugin-add-link" :aria-pressed="panel === 'link'" @click="panel = 'link'; openId = null"><Icon name="link-variant" />{{ t("editor.plugins.add_link") }}</button>
        <button type="button" class="icon-btn" id="close-plugins" :aria-label="t('editor.common.close')" :title="t('editor.common.close')" @click="ui.go('')"><Icon name="close" /></button>
      </div>
    </header>

    <div class="plugins-frame">
      <section class="plugins-list">
        <h1>{{ t("editor.plugins.title") }}</h1>
        <p class="setup-lead">{{ t("editor.plugins.intro") }}</p>
        <!-- The screens building their plugins now, each with its progress and log (the builds store, stores/builds.ts). -->
        <div v-if="pluginBuilds.length" class="plugin-builds" id="plugin-builds">
          <BuildLog v-for="screen in pluginBuilds" :key="screen.id" :screen="screen" name />
        </div>
        <!-- One bar for finding a plugin: the search (what narrows the list shows in it as pills), the tabs by what a
             plugin adds, a Filter menu (topics, maker, only what fits) and the order. -->
        <div class="plugin-bar" id="plugin-bar" role="search">
          <label class="pb-search">
            <Icon name="magnify" />
            <span v-for="pill in pills" :key="pill.key" class="pb-pill" :data-pill="pill.key">{{ pill.label }}
              <button type="button" :aria-label="t('editor.plugins.filter_remove', { what: pill.label })" @click.prevent="pill.clear()"><Icon name="close" /></button>
            </span>
            <input id="plugin-search" v-model="query" type="search" :placeholder="pills.length ? '' : t('editor.plugins.search')" autocomplete="off" spellcheck="false"
              @keydown.backspace="!query && pills.length && pills[pills.length - 1].clear()" />
          </label>
          <div class="seg pb-tabs" role="tablist" id="plugin-tabs" :aria-label="t('editor.plugins.filter')">
            <button v-for="key in TABS" :key="key" type="button" role="tab" :aria-selected="tab === key" :aria-pressed="tab === key" :data-tab="key" @click="tab = key">{{ t(`editor.plugins.tabs.${key}`) }} <small>{{ count(key) }}</small></button>
          </div>
          <UiMenu align="end" width="260px">
            <template #trigger>
              <button type="button" class="pb-btn" id="plugin-filter" :class="{ on: pills.length }"><Icon name="filter-variant" />{{ t("editor.plugins.filter_button") }}<b v-if="pills.length" class="pb-count">{{ pills.length }}</b></button>
            </template>
            <template v-if="topics.length">
              <UiMenuLabel>{{ t("editor.plugins.topic_filter") }}</UiMenuLabel>
              <DropdownMenuCheckboxItem v-for="item in topics" :key="item.name" class="ui-menu-item pb-check" :data-topic="item.name"
                :model-value="chosenTopics.includes(item.name)" @update:model-value="(on: boolean) => toggleTopic(item.name, on)" @select="(e: Event) => e.preventDefault()">
                <span class="pb-tick"><DropdownMenuItemIndicator><Icon name="check" /></DropdownMenuItemIndicator></span>
                <span class="ui-menu-text">{{ t(`editor.plugins.topics.${item.name}`) }}</span><small class="ui-menu-end">{{ item.n }}</small>
              </DropdownMenuCheckboxItem>
              <UiMenuSeparator />
            </template>
            <UiMenuLabel>{{ t("editor.plugins.made_by.label") }}</UiMenuLabel>
            <DropdownMenuRadioGroup v-model="maker">
              <DropdownMenuRadioItem v-for="key in MAKERS" :key="key" :value="key" class="ui-menu-item pb-check" :data-maker="key" @select="(e: Event) => e.preventDefault()">
                <span class="pb-tick"><DropdownMenuItemIndicator><Icon name="check" /></DropdownMenuItemIndicator></span>
                <span class="ui-menu-text">{{ t(`editor.plugins.made_by.${key}`) }}</span>
              </DropdownMenuRadioItem>
            </DropdownMenuRadioGroup>
            <template v-if="realScreens().length">
              <UiMenuSeparator />
              <DropdownMenuCheckboxItem v-model="fittingOnly" class="ui-menu-item pb-check" id="plugin-fitting" @select="(e: Event) => e.preventDefault()">
                <span class="pb-tick"><DropdownMenuItemIndicator><Icon name="check" /></DropdownMenuItemIndicator></span>
                <span class="ui-menu-text">{{ t("editor.plugins.fitting_only") }}</span>
              </DropdownMenuCheckboxItem>
            </template>
            <template v-if="pills.length">
              <UiMenuSeparator />
              <UiMenuItem icon="close" @select="clearAll">{{ t("editor.plugins.filter_clear") }}</UiMenuItem>
            </template>
          </UiMenu>
          <UiMenu align="end" width="200px">
            <template #trigger>
              <button type="button" class="pb-btn" id="plugin-sort"><Icon name="sort-variant" />{{ t(`editor.plugins.sort.${sort}`) }}</button>
            </template>
            <UiMenuLabel>{{ t("editor.plugins.sort.label") }}</UiMenuLabel>
            <DropdownMenuRadioGroup v-model="sort">
              <DropdownMenuRadioItem v-for="key in SORTS" :key="key" :value="key" class="ui-menu-item pb-check" :data-sort="key">
                <span class="pb-tick"><DropdownMenuItemIndicator><Icon name="check" /></DropdownMenuItemIndicator></span>
                <span class="ui-menu-text">{{ t(`editor.plugins.sort.${key}`) }}</span>
              </DropdownMenuRadioItem>
            </DropdownMenuRadioGroup>
          </UiMenu>
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
            <PluginDetail v-if="panel === 'plugin' && open" :key="open.id" :plugin="open" @close="close" />
            <PluginLink v-else-if="panel === 'link'" @close="close" @found="show" />
          </div>
        </aside>
      </Transition>
    </div>
  </div>
</template>
