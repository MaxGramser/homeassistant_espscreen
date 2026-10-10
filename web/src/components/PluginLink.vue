<script setup lang="ts">
// Add with a link: a release of any repo, a branch to test, or a folder on the Home Assistant machine. A release opens
// the plugin's details once Tessera has read its description; a test goes on one screen straight away, so on the
// Plugins page it asks which.
import { computed, reactive } from "vue";
import { t } from "../i18n";
import type { Plugin, PluginSource } from "../model/plugins";
import { addPlugin, plugins, realScreens, reloadPlugins } from "../plugin-state";
import { send } from "../api";
import type { Screen } from "../types";
import Icon from "./ui/Icon.vue";
import { useUiStore } from "../stores/ui";

const ui = useUiStore();

const props = defineProps<{ screen?: Screen | null }>();
const emit = defineEmits<{ close: []; found: [plugin: Plugin] }>();

const link = reactive({ source: "link" as Exclude<PluginSource, "index">, url: "", branch: "main", folder: "/config/tessera-plugins/", screen: props.screen?.id || realScreens()[0]?.id || "" });
const target = computed(() => props.screen || realScreens().find((s) => s.id === link.screen) || null);
const ready = computed(() => link.source === "folder" ? link.folder.trim().length > "/config/".length : /^https:\/\/github\.com\/[^/]+\/[^/]+/.test(link.url.trim()));
const reading = reactive({ busy: false });
// The add-on reads the plugin's description first (api/plugins/link): a release opens its details, a test goes on the
// chosen screen at once, as a test with no updates.
async function read() {
  reading.busy = true;
  try {
    const body = link.source === "folder" ? { folder: link.folder.trim() }
      : { url: link.url.trim(), ...(link.source === "branch" ? { branch: link.branch.trim() } : {}) };
    const plugin = await send<Plugin>("plugins/link", "POST", body);
    await reloadPlugins();
    if (link.source !== "link" && target.value) await addPlugin([target.value], plugins.index.find((p) => p.id === plugin.id) || plugin);
    emit("found", plugins.index.find((p) => p.id === plugin.id) || plugin);
  } catch (error: any) {
    ui.toast(error.message || t("editor.plugins.link.not_found"));
  } finally {
    reading.busy = false;
  }
}
</script>

<template>
  <div class="pd-top">
    <span class="plugin-icon large" aria-hidden="true"><Icon name="link-variant" /></span>
    <button type="button" class="icon-btn" :aria-label="t('editor.common.close')" @click="emit('close')"><Icon name="close" /></button>
  </div>
  <div class="pd-title"><h2>{{ t("editor.plugins.link.title") }}</h2></div>
  <p class="pd-description">{{ t("editor.plugins.link.intro") }}</p>
  <form class="pd-link" @submit.prevent="read">
    <div class="seg" role="group" :aria-label="t('editor.plugins.link.title')">
      <button v-for="source in (['link', 'branch', 'folder'] as const)" :key="source" type="button" :aria-pressed="link.source === source" @click="link.source = source">{{ t(`editor.plugins.link.sources.${source}`) }}</button>
    </div>
    <div v-if="link.source !== 'folder'" class="field">
      <label class="f-label" for="plugin-url">{{ t("editor.plugins.link.url") }}</label>
      <input id="plugin-url" v-model="link.url" type="url" placeholder="https://github.com/…/…" autocomplete="off" spellcheck="false" />
    </div>
    <div v-if="link.source === 'branch'" class="field">
      <label class="f-label" for="plugin-branch">{{ t("editor.plugins.link.branch") }}</label>
      <input id="plugin-branch" v-model="link.branch" autocomplete="off" spellcheck="false" />
    </div>
    <div v-if="link.source === 'folder'" class="field">
      <label class="f-label" for="plugin-folder">{{ t("editor.plugins.link.folder") }}</label>
      <input id="plugin-folder" v-model="link.folder" autocomplete="off" spellcheck="false" />
    </div>
    <div v-if="link.source !== 'link' && !screen" class="field">
      <label class="f-label" for="plugin-test-screen">{{ t("editor.plugins.link.on_screen") }}</label>
      <select id="plugin-test-screen" v-model="link.screen"><option v-for="s in realScreens()" :key="s.id" :value="s.id">{{ s.name }}</option></select>
    </div>
    <p class="pd-note">{{ t(`editor.plugins.link.hints.${link.source}`) }}</p>
    <button type="submit" class="btn primary" id="plugin-fetch" :disabled="!ready || reading.busy || (link.source !== 'link' && !target)">{{ link.source === "link" ? t("editor.plugins.link.fetch") : t("editor.plugins.link.test", { screen: target?.name || "" }) }}</button>
  </form>
  <p class="pd-warning">{{ t("editor.plugins.warning") }}</p>
</template>
