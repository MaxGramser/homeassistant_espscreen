<script setup lang="ts">
// A plugin's details in a screen's Plugins tab: the one action for that screen and what stands in its way. A screen with
// its own YAML that is not attached yet gets the one line to paste, once; after that the add-on keeps its plugins file
// and the screen is like any other. Taking it off is asked of the details around it (`remove`).
import { computed } from "vue";
import { editorNumber, t, te } from "../../i18n";
import { attachLine, fileOf, headroomKb, text, type Plugin } from "../../model/plugins";
import { glyph } from "../../model/topbar";
import type { Screen } from "../../types";
import PluginSetup from "../PluginSetup.vue";
import Icon from "../ui/Icon.vue";
import { usePluginsStore } from "../../stores/plugins";

const plugins = usePluginsStore();
const props = defineProps<{ plugin: Plugin; screen: Screen }>();
defineEmits<{ remove: [screens: Screen[]] }>();

const status = computed(() => plugins.statusOn(props.plugin, props.screen));
const installed = computed(() => plugins.installedOn(props.screen, props.plugin.id));
const fit = computed(() => plugins.fits(props.plugin, props.screen));
const attach = computed(() => plugins.needsAttach(props.screen));
// What it needs, what comes along, and the plugins that need it: on this screen, what adding it brings along (the
// add-on's plan), a feature to choose a plugin for, or why it cannot.
const byId = (id: string) => plugins.index.find((p) => p.id === id);
const nameOf = (id: string) => (byId(id) ? text(byId(id)!.name) : id);
const feature = (name: string) => (te(`editor.plugins.features.${name}`) ? t(`editor.plugins.features.${name}`) : name);
const plan = computed(() => (!installed.value && fit.value.ok ? plugins.planOn(props.screen, [props.plugin.id]) : null));
const along = computed(() => plugins.comesAlong(plan.value, [props.plugin.id]));
const needed = computed(() => (installed.value ? plugins.neededBy(props.screen, props.plugin.id) : []));
const cameWith = computed(() => (installed.value?.auto ? needed.value : []));
const other = computed(() => plugins.otherOrigin(props.screen, props.plugin));
const whyAlong = (row: { step: { for: string[] }; plugin: Plugin }) => {
  const brings = (row.plugin.provides || []).filter((f) => row.step.for.some((id) => (byId(id) || props.plugin).requires.features?.includes(f)));
  return brings.length ? t("editor.plugins.along.brings", { what: brings.map(feature).join(", ") })
    : t("editor.plugins.along.needed_by", { name: row.step.for.map(nameOf).join(", ") });
};
// An update that asks for other rights waits for the person's yes, shown above the update key.
const askConsent = computed(() => plugins.realScreens().some((s) => plugins.installedOn(s, props.plugin.id) && plugins.needsConsent(s, props.plugin)));
const agreed = computed(() => !askConsent.value || Boolean(plugins.consented[props.plugin.id]));
// Why a build did not go: the app restarted during it, or the first line of what the build said.
const reasonText = (reason: string) => (reason === "interrupted" ? t("editor.plugins.interrupted") : reason.split("\n")[0]);
</script>

<template>
  <div v-if="attach && !installed" class="pd-action" id="plugin-attach">
    <p class="pd-note pd-attach-note"><Icon name="code-braces" /><span>{{ t("editor.plugins.attach.text", { screen: screen.name }) }}</span></p>
    <pre class="pd-yaml">{{ attachLine(screen) }}</pre>
    <div class="pd-buttons">
      <button type="button" class="btn quiet" id="plugin-copy-line" @click="plugins.copyAttach(screen)"><Icon name="content-copy" />{{ t("editor.plugins.attach.copy") }}</button>
      <button type="button" class="btn primary" id="plugin-attached" @click="plugins.markAttached(screen)">{{ t("editor.plugins.attach.done") }}</button>
    </div>
    <details v-if="plugins.pluginsFile(screen)" class="pd-file">
      <summary><Icon name="chevron-right" />{{ t("editor.plugins.attach.file", { file: fileOf(screen) }) }}</summary>
      <pre class="pd-yaml">{{ plugins.pluginsFile(screen) }}</pre>
    </details>
  </div>

  <div v-else-if="status" class="pd-action" :class="status.kind">
    <p v-if="!fit.ok && !installed" class="pd-misfit" id="plugin-misfit"><Icon name="information-outline" />{{ t(`editor.plugins.misfit.${fit.reason}`, { screen: screen.name, kb: headroomKb(screen) }) }}</p>
    <template v-else-if="installed && plugins.isTakingOff(screen, plugin.id)">
      <p class="pd-note" id="plugin-taking-off"><Icon name="minus" />{{ t("editor.plugins.tray.off_note") }}</p>
      <div class="pd-buttons">
        <button type="button" class="btn quiet" id="plugin-keep" @click="plugins.takeOut(screen, plugin.id)">{{ t("editor.plugins.tray.keep") }}</button>
      </div>
    </template>
    <template v-else-if="status.kind === 'test'">
      <p class="pd-note">{{ t("editor.plugins.test_note") }}</p>
      <div class="pd-buttons">
        <button type="button" class="btn primary" id="plugin-rebuild" @click="plugins.rebuildTest(screen, plugin)">{{ t("editor.plugins.rebuild") }}</button>
        <button type="button" class="btn quiet" @click="$emit('remove', [screen])">{{ t("editor.plugins.remove", { screen: screen.name }) }}</button>
      </div>
    </template>
    <template v-else-if="status.kind === 'failed'">
      <p class="pd-misfit" id="plugin-failed"><Icon name="information-outline" /><span>{{ t("editor.plugins.failed", { screen: screen.name }) }}<small v-if="installed?.reason" class="pd-reason">{{ reasonText(installed.reason) }}</small></span></p>
      <div class="pd-buttons">
        <button type="button" class="btn primary" @click="plugins.addPlugin([screen], plugin)">{{ t("editor.plugins.retry") }}</button>
        <button type="button" class="btn quiet" @click="$emit('remove', [screen])">{{ t("editor.plugins.remove", { screen: screen.name }) }}</button>
      </div>
    </template>
    <p v-else-if="status.kind === 'building'" class="pd-note"><span class="spin" aria-hidden="true"></span>{{ t("editor.plugins.building", { screen: screen.name }) }}</p>
    <template v-else-if="installed">
      <p class="pd-note"><Icon name="check-circle" />{{ t("editor.plugins.installed_on", { screen: screen.name, version: installed.version }) }}</p>
      <p v-if="cameWith.length" class="pd-note pd-along-note" id="plugin-came-with"><Icon name="link-variant" />{{ t("editor.plugins.along.came_with", { names: cameWith.map((p) => text(p.name)).join(", ") }) }}</p>
      <p v-else-if="needed.length" class="pd-note pd-along-note" id="plugin-needed-by"><Icon name="link-variant" />{{ t("editor.plugins.along.needed_now", { names: needed.map((p) => text(p.name)).join(", ") }) }}</p>
      <p v-if="installed.failed_update" class="pd-misfit" id="plugin-failed-update"><Icon name="information-outline" /><span>{{ t("editor.plugins.failed_update", { screen: screen.name, version: installed.failed_update.version, current: installed.version }) }}<small v-if="installed.failed_update.reason" class="pd-reason">{{ reasonText(installed.failed_update.reason) }}</small></span></p>
      <p v-if="installed.blocked" class="pd-misfit" id="plugin-blocked"><Icon name="alert-circle-outline" />{{ t("editor.plugins.blocked_now", { why: installed.blocked }) }}</p>
      <template v-if="other">
        <p class="pd-misfit" id="plugin-other-origin"><Icon name="information-outline" />{{ t("editor.plugins.other_origin", { origin: installed.origin }) }}</p>
        <div class="pd-buttons"><button type="button" class="btn quiet" id="plugin-switch" @click="plugins.switchPlugin(screen, plugin)">{{ t("editor.plugins.switch", { origin: plugin.origin }) }}</button></div>
      </template>
      <label v-if="status.kind === 'update' && askConsent" class="pd-trust" id="plugin-consent">
        <input type="checkbox" :checked="plugins.consented[plugin.id]" @change="plugins.consented[plugin.id] = ($event.target as HTMLInputElement).checked" />
        <span><b>{{ t("editor.plugins.consent.title") }}</b>{{ t("editor.plugins.consent.agree") }}</span>
      </label>
      <div class="pd-buttons">
        <button v-if="status.kind === 'update'" type="button" class="btn primary" id="plugin-update" :disabled="!agreed" @click="plugins.addPlugin([screen], plugin)">{{ t("editor.plugins.update", { version: plugin.version }) }}</button>
        <button type="button" class="btn quiet" id="plugin-remove" @click="$emit('remove', [screen])">{{ t("editor.plugins.remove", { screen: screen.name }) }}</button>
      </div>
    </template>
    <template v-else>
      <PluginSetup :plugin="plugin" :screens="[screen]" />
      <!-- What comes along: a plugin it needs, or the one plugin that brings a feature it needs; set aside with it. -->
      <div v-if="along.length || plan?.choose?.length || plan?.error" class="pd-along" id="plugin-along">
        <p class="pd-label">{{ t("editor.plugins.along.title") }}</p>
        <p v-if="plan?.error" class="pd-misfit"><Icon name="information-outline" />{{ plan.error }}</p>
        <div v-for="row in along" :key="row.plugin.id" class="pd-along-row" :data-plugin="row.plugin.id">
          <span class="plugin-icon" :class="{ tessera: row.plugin.tessera }" aria-hidden="true"><span class="mdi">{{ glyph(row.plugin.icon) }}</span></span>
          <span class="pd-along-words"><b>{{ text(row.plugin.name) }}</b><small>{{ whyAlong(row) }} · {{ row.plugin.tessera ? t("editor.plugins.from_tessera") : t("editor.plugins.by", { maker: row.plugin.maintainer }) }} · {{ editorNumber(row.step.flash_kb) }} KB</small></span>
        </div>
        <label v-for="choice in plan?.choose || []" :key="choice.feature" class="field pd-choose">
          <span class="f-label">{{ t("editor.plugins.along.choose", { what: feature(choice.feature) }) }}</span>
          <select :data-feature="choice.feature" @change="plugins.chooseProvider(screen, choice.feature, ($event.target as HTMLSelectElement).value)">
            <option value="" selected disabled>{{ t("editor.plugin_tile.choose") }}</option>
            <option v-for="id in choice.options" :key="id" :value="id">{{ nameOf(id) }}</option>
          </select>
        </label>
      </div>
      <!-- Set aside, not built: the tray takes it with whatever else is chosen, and builds the screen once. -->
      <button type="button" class="btn pd-install" :class="plugins.isSetAside(screen, plugin.id) ? 'quiet' : 'primary'" id="plugin-install" @click="plugins.toggleSetAside(screen, plugin)">
        <Icon :name="plugins.isSetAside(screen, plugin.id) ? 'check' : 'plus'" />{{ plugins.isSetAside(screen, plugin.id) ? t("editor.plugins.tray.in_tray") : t("editor.plugins.tray.stage", { screen: screen.name }) }}
      </button>
      <p class="pd-build-note">{{ plugins.isSetAside(screen, plugin.id) ? t("editor.plugins.tray.in_tray_note") : t("editor.plugins.build_note") }}</p>
    </template>
  </div>
</template>
