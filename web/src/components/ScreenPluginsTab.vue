<script setup lang="ts">
// A screen's Plugins tab, beside Layout and Screen settings: what this screen runs, what it can add, and, folded away,
// what does not fit its board. The same cards and details as the Plugins page, with one button for this screen.
import { computed, ref, watch } from "vue";
import { t } from "../i18n";
import { text, type Plugin } from "../model/plugins";
import PluginCard from "./PluginCard.vue";
import PluginDetail from "./PluginDetail.vue";
import PluginLink from "./PluginLink.vue";
import PluginTray from "./PluginTray.vue";
import BuildLog from "./BuildLog.vue";
import Icon from "./ui/Icon.vue";
import { useUiStore } from "../stores/ui";
import { usePluginsStore } from "../stores/plugins";
import { useScreenStore } from "../stores/screen";

const ui = useUiStore();
const plugins = usePluginsStore();
const scr = useScreenStore();

plugins.loadPlugins();
const screen = computed(() => scr.currentScreen!);
const here = computed(() => [...plugins.index.filter((p) => plugins.installedOn(screen.value, p.id) || plugins.buildingOn(screen.value, p.id)), ...plugins.testsOn(screen.value)]);
const addable = computed(() => plugins.index.filter((p) => !here.value.includes(p) && plugins.fits(p, screen.value).ok));
const misfits = computed(() => plugins.index.filter((p) => !here.value.includes(p) && !plugins.fits(p, screen.value).ok));
// Update all on this screen: every plugin with an update in one build. Updates that ask for other rights are named, and
// go only with one yes for all of them, which counts as the yes each one asks for in its details.
const updates = computed(() => plugins.updatesOn(screen.value));
const asking = computed(() => updates.value.filter((p) => plugins.needsConsent(screen.value, p)));
const agreed = computed(() => asking.value.every((p) => plugins.consented[p.id]));
const names = (list: Plugin[]) => list.map((p) => text(p.name)).join(", ");
function agree(on: boolean) { for (const p of asking.value) plugins.consented[p.id] = on; }

const panel = ref<"plugin" | "link" | null>(null);
const openId = ref<string | null>(null);
const open = computed(() => [...plugins.index, ...plugins.testsOn(screen.value)].find((p) => p.id === openId.value) || null);
// The tray folds to its head while details are open, and opens again when they close.
function show(plugin: Plugin) { openId.value = plugin.id; panel.value = "plugin"; plugins.tray.open = false; }
function close() { panel.value = null; openId.value = null; plugins.tray.open = true; }
// Screen settings sends a person to a plugin's settings: open its details once the tab shows.
watch(() => plugins.focus, (id) => {
  const plugin = id ? [...plugins.index, ...plugins.testsOn(screen.value)].find((p) => p.id === id) : null;
  if (plugin) show(plugin);
  if (id) plugins.focus = null;
}, { immediate: true });
</script>

<template>
  <div class="screen-plugins" id="screen-plugins" :class="{ 'with-detail': panel }">
    <div class="sp-list">
      <div class="sp-head">
        <p class="sp-intro">{{ t("editor.plugins.tab.intro", { screen: screen.name }) }}</p>
        <div class="sp-actions">
          <button type="button" class="btn quiet" id="screen-plugin-link" :aria-pressed="panel === 'link'" @click="panel = 'link'; openId = null"><Icon name="link-variant" />{{ t("editor.plugins.add_link") }}</button>
          <button type="button" class="btn link" id="screen-plugin-all" @click="ui.go('#plugins')">{{ t("editor.plugins.tab.all") }}<Icon name="arrow-right" /></button>
        </div>
      </div>

      <!-- This screen's build, whoever asked for it, with its log; a failed one stays until the next build. -->
      <BuildLog :screen="screen" />

      <div v-if="updates.length" class="sp-updates" id="screen-plugin-updates">
        <p><b>{{ t("editor.plugins.tab.updates", { n: updates.length }, updates.length) }}</b>{{ t("editor.plugins.tab.updates_note", { names: names(updates), screen: screen.name }) }}</p>
        <label v-if="asking.length" class="pd-trust" id="screen-plugin-consent">
          <input type="checkbox" :checked="agreed" @change="agree(($event.target as HTMLInputElement).checked)" />
          <span><b>{{ t("editor.plugins.tab.updates_rights", { names: names(asking) }, asking.length) }}</b>{{ t("editor.plugins.consent.agree") }}</span>
        </label>
        <button type="button" class="btn primary" id="screen-plugin-update-all" :disabled="!agreed" @click="plugins.updateAll(screen, updates)">{{ t("editor.plugins.tab.update_all") }}</button>
      </div>

      <section class="sp-group">
        <h3>{{ t("editor.plugins.tab.here") }}</h3>
        <div class="plugin-grid" role="list">
          <PluginCard v-for="plugin in here" :key="plugin.id" :plugin="plugin" :status="plugins.statusOn(plugin, screen)" :chosen="openId === plugin.id" @open="show(plugin)" />
          <p v-if="!here.length" class="sp-empty">{{ t("editor.plugins.none_installed") }}</p>
        </div>
      </section>

      <section v-if="addable.length" class="sp-group">
        <h3>{{ t("editor.plugins.tab.add") }}</h3>
        <div class="plugin-grid" role="list">
          <PluginCard v-for="plugin in addable" :key="plugin.id" :plugin="plugin" :status="plugins.statusOn(plugin, screen)" :chosen="openId === plugin.id"
            :staged="plugins.isSetAside(screen, plugin.id)" @open="show(plugin)" @add="plugins.toggleSetAside(screen, plugin)" />
        </div>
      </section>

      <details v-if="misfits.length" class="sp-group sp-misfits" id="screen-plugin-misfits">
        <summary><Icon name="chevron-right" />{{ t("editor.plugins.tab.misfits", { n: misfits.length }, misfits.length) }}</summary>
        <div class="plugin-grid" role="list">
          <PluginCard v-for="plugin in misfits" :key="plugin.id" :plugin="plugin" :status="plugins.statusOn(plugin, screen)" :chosen="openId === plugin.id" @open="show(plugin)" />
        </div>
      </details>

      <PluginTray @open="show" />
    </div>

    <Transition name="drawer">
      <aside v-if="panel" class="plugin-detail" id="plugin-detail" @click.stop>
        <div class="plugin-detail-inner">
          <PluginDetail v-if="panel === 'plugin' && open" :key="open.id" :plugin="open" :screen="screen" @close="close" />
          <PluginLink v-else-if="panel === 'link'" :screen="screen" @close="close" @found="show" />
        </div>
      </aside>
    </Transition>
  </div>
</template>
