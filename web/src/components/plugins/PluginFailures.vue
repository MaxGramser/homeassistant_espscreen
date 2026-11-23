<script setup lang="ts">
// What did not build on this screen, first thing in its Plugins tab: a new plugin that stayed out, or an update the
// screen went back from. Each kind of failure (plugins.py failure_kind) has its own words and its own way out: a fault
// in the plugin's code goes to its maker, memory that ran short to a build server, a screen that was away installs by
// itself once it is back, a download that did not come is tried again. Always: the build's log to download (kept on
// disk by the add-on, build_logs.py) and the way to try again. It stays until the plugin builds or is taken off.
import { computed } from "vue";
import { t } from "../../i18n";
import { issueUrl, text, type Plugin, type PluginFailure } from "../../model/plugins";
import type { Screen } from "../../types";
import Icon from "../ui/Icon.vue";
import { buildLogHref } from "../../stores/builds";
import { usePluginsStore } from "../../stores/plugins";
import { useUiStore } from "../../stores/ui";

const plugins = usePluginsStore();
const ui = useUiStore();
const props = defineProps<{ screen: Screen }>();
const emit = defineEmits<{ open: [plugin: Plugin] }>();

const failures = computed(() => plugins.failuresOn(props.screen));
// The first line of what the build said, for a failure that has one worth showing.
const reasonLine = (f: PluginFailure) => (f.reason && f.reason !== "interrupted" ? f.reason.split("\n")[0] : "");
const title = (f: PluginFailure) => t(f.kind === "update" ? "editor.plugins.failures.update" : "editor.plugins.failures.added",
  { name: text(f.plugin.name), version: f.version, screen: props.screen.name });
const still = (f: PluginFailure) => (f.kind === "update"
  ? t("editor.plugins.failures.update_note", { current: f.installed.version })
  : t("editor.plugins.failures.added_note"));
// Why, in words, by its kind; a screen that was away says it waits for it (once), not that it failed.
const why = (f: PluginFailure) => t(`editor.plugins.failures.why.${f.waiting ? "offline_wait" : f.why}`, { screen: props.screen.name });
// A build that stopped on the plugin (or on something the log names) can go to its maker: a filled-in issue.
const issue = (f: PluginFailure) => (["plugin", "build"].includes(f.why) ? issueUrl(f, props.screen) : null);
// An update that asks for other rights gets its yes in the plugin's details; everything else goes again from here.
function retry(f: PluginFailure) {
  if (f.kind === "update" && plugins.needsConsent(props.screen, f.plugin) && !plugins.consented[f.plugin.id]) emit("open", f.plugin);
  else void plugins.addPlugin([props.screen], f.plugin);
}
</script>

<template>
  <div v-if="failures.length" class="sp-failures" id="screen-plugin-failures" role="alert">
    <div v-for="f in failures" :key="f.plugin.id" class="sp-failure" :class="[f.why, { waiting: f.waiting }]" :data-plugin="f.plugin.id" :data-why="f.why">
      <Icon :name="f.waiting ? 'information-outline' : 'alert-circle-outline'" />
      <div class="sp-failure-text">
        <b>{{ title(f) }}</b>
        <span>{{ still(f) }} {{ why(f) }}</span>
        <code v-if="reasonLine(f)" class="sp-failure-reason">{{ reasonLine(f) }}</code>
        <small v-if="issue(f)" class="sp-failure-nolog">{{ t("editor.plugins.failures.report_hint") }}</small>
        <small v-if="!f.log" class="sp-failure-nolog">{{ t("editor.plugins.failures.no_log") }}</small>
        <div class="sp-failure-buttons">
          <a v-if="f.log" class="btn primary" :href="buildLogHref(f.log)" :download="`${f.log}.log`" data-action="log"><Icon name="tray-arrow-down" />{{ t("editor.plugins.download_log") }}</a>
          <a v-if="issue(f)" class="btn quiet" :href="issue(f)!" target="_blank" rel="noopener" data-action="issue"><Icon name="arrow-right" />{{ t("editor.plugins.failures.report", { maker: f.plugin.maintainer }) }}</a>
          <button v-if="f.why === 'memory'" type="button" class="btn quiet" data-action="server" @click="ui.openSettings('builds')"><Icon name="arrow-right" />{{ t("editor.plugins.failures.build_server") }}</button>
          <button type="button" class="btn quiet" data-action="retry" @click="retry(f)"><Icon name="refresh" />{{ f.kind === "update" ? t("editor.plugins.update", { version: f.version }) : t("editor.plugins.retry") }}</button>
          <button type="button" class="btn link" data-action="details" @click="emit('open', f.plugin)">{{ t("editor.plugins.failures.details") }}</button>
        </div>
      </div>
    </div>
  </div>
</template>
