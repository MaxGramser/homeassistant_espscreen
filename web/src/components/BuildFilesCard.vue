<script setup lang="ts">
// The build files (the add-on's build_files.py, docs/BUILDS.md "Build files"): how much room the builds leave in the
// app's data, the clean-up, and the automatic clean-up with what it costs beside it. Every state comes from the live
// inventory (`build_files`); the clean-up itself is the builds store's, which the after-build offer uses too.
import { computed } from "vue";
import { t } from "../i18n";
import { sizeText } from "../model/build-files";
import UiSwitch from "./ui/UiSwitch.vue";
import { useBuildsStore } from "../stores/builds";
import { useInventoryStore } from "../stores/inventory";

const inv = useInventoryStore();
const builds = useBuildsStore();
const view = computed(() => inv.inventory.build_files);
const sizes = computed(() => view.value?.sizes ?? null);
const cleaning = computed(() => !!view.value?.cleaning || builds.cleaningFiles);
// Never while something builds or waits: the add-on refuses it then, so the page doesn't offer it.
const building = computed(() => builds.line.some((build) => build.state === "queued" || build.state === "running"));
const rows = computed(() => sizes.value ? [
  { key: "folders", label: t("editor.settings.build_files.folders"), detail: sizes.value.screens ? t("editor.settings.build_files.folders_detail", { count: sizes.value.screens }, sizes.value.screens) : "", bytes: sizes.value.folders },
  { key: "cache", label: t("editor.settings.build_files.cache"), detail: "", bytes: sizes.value.cache },
  { key: "tools", label: t("editor.settings.build_files.tools"), detail: "", bytes: sizes.value.tools },
] : []);
</script>

<template>
  <section v-if="view" class="card build-files" id="build-files">
    <div class="bf-head">
      <h2>{{ t("editor.settings.build_files.title") }}</h2>
      <span v-if="sizes" class="chip" id="build-files-total">{{ t("editor.settings.build_files.total", { size: sizeText(sizes.total) }) }}</span>
    </div>
    <p>{{ t("editor.settings.build_files.intro") }}</p>
    <p v-if="!sizes" class="hint"><span class="spin small" aria-hidden="true"></span> {{ t("editor.settings.build_files.measuring") }}</p>
    <dl v-else class="bf-sizes">
      <div v-for="row in rows" :key="row.key" :id="`build-files-${row.key}`">
        <dt>{{ row.label }}<small v-if="row.detail"> · {{ row.detail }}</small></dt>
        <dd>{{ sizeText(row.bytes) }}</dd>
      </div>
    </dl>
    <p v-if="view.offer" class="bf-large" id="build-files-large">{{ t("editor.settings.build_files.large", { size: sizeText(sizes!.folders) }) }}</p>
    <p v-if="building" class="hint" id="build-files-busy">{{ t("editor.settings.build_files.busy") }}</p>
    <div class="actions">
      <button type="button" id="build-files-clean" class="btn" :class="{ primary: view.offer }" :disabled="cleaning || building || !sizes?.folders"
        @click="builds.cleanBuildFiles('folders')"><span v-if="cleaning" class="spin small" aria-hidden="true"></span>{{ cleaning ? t("editor.settings.build_files.cleaning") : t("editor.settings.build_files.clean") }}</button>
      <button v-if="view.offer" type="button" id="build-files-not-now" class="btn quiet" :disabled="cleaning" @click="builds.declineBuildFiles()">{{ t("editor.settings.build_files.not_now") }}</button>
    </div>
    <label class="bs-switch" for="build-files-auto">
      <span class="sr-text"><b>{{ t("editor.settings.build_files.auto_label") }}</b><small>{{ t("editor.settings.build_files.auto_hint") }}</small></span>
      <UiSwitch id="build-files-auto" :model-value="view.auto" :disabled="cleaning" @update:model-value="builds.setAutoClean" />
    </label>
    <div class="actions">
      <button type="button" id="build-files-clean-all" class="btn quiet mini" :disabled="cleaning || building || !sizes?.total"
        @click="builds.cleanBuildFiles('all')">{{ t("editor.settings.build_files.clean_all") }}</button>
    </div>
  </section>
</template>
