<script setup lang="ts">
// Ready to install: the plugins set aside, in a card that floats in the corner of the Plugins page and a screen's
// Plugins tab. Adding a plugin puts it here instead of building at once, so a person can pick several and build each
// screen once. A plugin that still needs something (a stop code, trust in its maker) says so and opens its details.
import { computed, ref } from "vue";
import { editorLanguage, languageMarks, numberText, t } from "../i18n";
import { headroomKb, text, type Plugin } from "../model/plugins";
import { glyph } from "../model/topbar";
import { chooseProvider, installTray, labelOf, plugins, setupReady, setAsideKb, tray, trayAlong, trayGroups, trayPlan, trayReady, takeOut } from "../plugin-state";
import type { Screen } from "../types";
import Icon from "./ui/Icon.vue";

defineEmits<{ open: [plugin: Plugin, screen: Screen] }>();

const groups = trayGroups;
const count = computed(() => groups.value.reduce((sum, g) => sum + g.plugins.length, 0));
const stack = computed(() => groups.value.flatMap((g) => g.plugins).slice(-3));
const kb = (value: number) => numberText(value, languageMarks(editorLanguage()));
// A 4 MB screen's slot: what is set aside together has to fit under the line, not each plugin alone.
const small = (screen: Screen) => Boolean(screen.firmware_image ? screen.firmware_image.slot <= 2_100_000 : ["cyd", "cyd9342", "hosyond40"].includes(screen.board || ""));
const over = (screen: Screen, list: Plugin[]) => small(screen) && setAsideKb(screen, list) > headroomKb(screen);
const unready = (screen: Screen, plugin: Plugin) => !setupReady(plugin, [screen]);
// What comes along counts for trust as well: one yes for everything that goes on.
const community = computed(() => [...new Set(groups.value.flatMap((g) => [...g.plugins, ...trayAlong(g).map((row) => row.plugin)])
  .filter((p) => labelOf(p) === "community"))]);
const nameOf = (id: string) => { const p = plugins.index.find((x) => x.id === id); return p ? text(p.name) : id; };
const trust = ref(false);
const blocked = computed(() => tray.sending || groups.value.some((g) => !trayReady(g) || over(g.screen, g.plugins) || g.plugins.some((p) => unready(g.screen, p))
  || trayAlong(g).some((row) => unready(g.screen, row.plugin)))
  || (community.value.length > 0 && !trust.value));
const builds = computed(() => groups.value.length === 1
  ? t("editor.plugins.tray.one_build", { screen: groups.value[0].screen.name })
  : t("editor.plugins.tray.builds", { n: groups.value.length }));
async function install() { await installTray(); trust.value = false; }
</script>

<template>
  <Transition name="tray">
    <aside v-if="count" class="plugin-tray" id="plugin-tray" :class="{ folded: !tray.open }" :aria-label="t('editor.plugins.tray.title')">
      <button type="button" class="pt-head" :aria-expanded="tray.open" @click="tray.open = !tray.open">
        <span class="pt-stack" aria-hidden="true">
          <TransitionGroup name="pt-chip">
            <span v-for="plugin in stack" :key="plugin.id" class="plugin-icon" :class="{ tessera: plugin.tessera }"><span class="mdi">{{ glyph(plugin.icon) }}</span></span>
          </TransitionGroup>
        </span>
        <span class="pt-title">
          <b>{{ t("editor.plugins.tray.title") }}</b>
          <small>{{ t("editor.plugins.tray.count", { n: count }, count) }}</small>
        </span>
        <Icon :name="tray.open ? 'chevron-down' : 'chevron-up'" />
      </button>

      <div class="pt-body">
        <div class="pt-body-inner">
          <div class="pt-scroll">
          <section v-for="group in groups" :key="group.screen.id" class="pt-group">
            <p class="pt-screen"><Icon name="tablet-dashboard" />{{ group.screen.name }}</p>
            <TransitionGroup tag="ul" name="pt-row" class="pt-rows">
              <li v-for="plugin in group.plugins" :key="plugin.id" class="pt-row" :class="{ unready: unready(group.screen, plugin) }">
                <button type="button" class="pt-row-main" @click="$emit('open', plugin, group.screen)">
                  <span class="plugin-icon" :class="{ tessera: plugin.tessera }" aria-hidden="true"><span class="mdi">{{ glyph(plugin.icon) }}</span></span>
                  <span class="pt-words">
                    <b>{{ text(plugin.name) }}</b>
                  </span>
                  <small v-if="unready(group.screen, plugin)" class="pt-todo">{{ t("editor.plugins.tray.setup") }}<Icon name="chevron-right" /></small>
                </button>
                <button type="button" class="pt-remove" :aria-label="t('editor.plugins.tray.remove', { name: text(plugin.name) })" @click="takeOut(group.screen, plugin.id)"><Icon name="close" /></button>
              </li>
            </TransitionGroup>
            <!-- What comes along with them on this screen (the add-on's plan), under what was chosen; it goes with them. -->
            <ul v-if="trayAlong(group).length" class="pt-rows pt-along">
              <li v-for="row in trayAlong(group)" :key="row.plugin.id" class="pt-row along" :class="{ unready: unready(group.screen, row.plugin) }" :data-plugin="row.plugin.id">
                <button type="button" class="pt-row-main" @click="$emit('open', row.plugin, group.screen)">
                  <span class="plugin-icon" :class="{ tessera: row.plugin.tessera }" aria-hidden="true"><span class="mdi">{{ glyph(row.plugin.icon) }}</span></span>
                  <span class="pt-words"><b>{{ text(row.plugin.name) }}</b><small>{{ t("editor.plugins.tray.along", { names: row.step.for.map(nameOf).join(", ") }) }}</small></span>
                  <small v-if="unready(group.screen, row.plugin)" class="pt-todo">{{ t("editor.plugins.tray.setup") }}<Icon name="chevron-right" /></small>
                </button>
              </li>
            </ul>
            <label v-for="choice in trayPlan(group)?.choose || []" :key="choice.feature" class="field pt-choose">
              <span class="f-label">{{ t("editor.plugins.along.choose", { what: t(`editor.plugins.features.${choice.feature}`) }) }}</span>
              <select :data-feature="choice.feature" @change="chooseProvider(group.screen, choice.feature, ($event.target as HTMLSelectElement).value)">
                <option value="" selected disabled>{{ t("editor.plugin_tile.choose") }}</option>
                <option v-for="id in choice.options" :key="id" :value="id">{{ nameOf(id) }}</option>
              </select>
            </label>
            <p v-if="trayPlan(group)?.error" class="pt-room over">{{ trayPlan(group)!.error }}</p>
            <template v-if="small(group.screen)">
              <div class="pd-meter pt-meter" :class="{ tight: over(group.screen, group.plugins) }" role="meter" aria-valuemin="0" :aria-valuemax="headroomKb(group.screen)" :aria-valuenow="setAsideKb(group.screen, group.plugins)">
                <i class="added" :style="{ left: 0, width: Math.min(100, (setAsideKb(group.screen, group.plugins) / Math.max(1, headroomKb(group.screen))) * 100) + '%' }"></i>
              </div>
              <p class="pt-room" :class="{ over: over(group.screen, group.plugins) }">{{ over(group.screen, group.plugins)
                ? t("editor.plugins.tray.too_much", { kb: kb(setAsideKb(group.screen, group.plugins)), room: kb(headroomKb(group.screen)) })
                : t("editor.plugins.tray.room", { kb: kb(setAsideKb(group.screen, group.plugins)), room: kb(headroomKb(group.screen)) }) }}</p>
            </template>
          </section>

          </div>
          <label v-if="community.length" class="pd-trust pt-trust">
            <input type="checkbox" v-model="trust" />
            <span><b>{{ t("editor.plugins.trust.title") }}</b>{{ t("editor.plugins.tray.trust", { names: community.map((p) => text(p.name)).join(", ") }, community.length) }}</span>
          </label>

          <div class="pt-foot">
            <button type="button" class="btn primary pt-install" id="plugin-tray-install" :disabled="blocked" @click="install">
              <span v-if="tray.sending" class="spin" aria-hidden="true"></span>{{ t("editor.plugins.tray.install", { n: count }, count) }}
            </button>
            <p class="pt-note">{{ builds }}</p>
          </div>
        </div>
      </div>
    </aside>
  </Transition>
</template>
