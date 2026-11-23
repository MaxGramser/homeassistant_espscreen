<script setup lang="ts">
// What did not build on this screen, first thing in its Plugins tab: a new plugin that stayed out, or an update the
// screen went back from, with why, the build's log to download (kept on disk by the add-on, build_logs.py, also past a
// restart of the app) and the way to try again. It stays until the plugin builds or is taken off (plugins.failuresOn).
import { computed } from "vue";
import { t } from "../../i18n";
import { text, type Plugin, type PluginFailure } from "../../model/plugins";
import type { Screen } from "../../types";
import Icon from "../ui/Icon.vue";
import { buildLogHref } from "../../stores/builds";
import { usePluginsStore } from "../../stores/plugins";

const plugins = usePluginsStore();
const props = defineProps<{ screen: Screen }>();
const emit = defineEmits<{ open: [plugin: Plugin] }>();

const failures = computed(() => plugins.failuresOn(props.screen));
// Why it did not go: the app restarted during it, or the first line of what the build said.
const reasonText = (reason: string) => (reason === "interrupted" ? t("editor.plugins.interrupted") : reason.split("\n")[0]);
const title = (f: PluginFailure) => t(f.kind === "update" ? "editor.plugins.failures.update" : "editor.plugins.failures.added",
  { name: text(f.plugin.name), version: f.version, screen: props.screen.name });
const note = (f: PluginFailure) => (f.kind === "update"
  ? t("editor.plugins.failures.update_note", { current: f.installed.version })
  : t("editor.plugins.failures.added_note"));
// An update that asks for other rights gets its yes in the plugin's details; everything else goes again from here.
function retry(f: PluginFailure) {
  if (f.kind === "update" && plugins.needsConsent(props.screen, f.plugin) && !plugins.consented[f.plugin.id]) emit("open", f.plugin);
  else void plugins.addPlugin([props.screen], f.plugin);
}
</script>

<template>
  <div v-if="failures.length" class="sp-failures" id="screen-plugin-failures" role="alert">
    <div v-for="f in failures" :key="f.plugin.id" class="sp-failure" :data-plugin="f.plugin.id">
      <Icon name="alert-circle-outline" />
      <div class="sp-failure-text">
        <b>{{ title(f) }}</b>
        <span>{{ note(f) }}</span>
        <code v-if="f.reason" class="sp-failure-reason">{{ reasonText(f.reason) }}</code>
        <small v-if="!f.log" class="sp-failure-nolog">{{ t("editor.plugins.failures.no_log") }}</small>
        <div class="sp-failure-buttons">
          <a v-if="f.log" class="btn primary" :href="buildLogHref(f.log)" :download="`${f.log}.log`" data-action="log"><Icon name="tray-arrow-down" />{{ t("editor.plugins.download_log") }}</a>
          <button type="button" class="btn quiet" data-action="retry" @click="retry(f)"><Icon name="refresh" />{{ f.kind === "update" ? t("editor.plugins.update", { version: f.version }) : t("editor.plugins.retry") }}</button>
          <button type="button" class="btn link" data-action="details" @click="emit('open', f.plugin)">{{ t("editor.plugins.failures.details") }}</button>
        </div>
      </div>
    </div>
  </div>
</template>
