<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { t } from "../i18n";
import { modelKey, ownYaml, text, type ModelEntry, type Plugin, type PluginBuildSetting } from "../model/plugins";
import { usePluginsStore } from "../stores/plugins";
import type { Screen } from "../types";

const props = defineProps<{ plugin: Plugin; screen: Screen; setting: PluginBuildSetting }>();
const plugins = usePluginsStore();
const url = ref("");
const error = ref("");
const manifest = ref<File>();
const binary = ref<File>();
const manifestInput = ref<HTMLInputElement>();
const binaryInput = ref<HTMLInputElement>();
const uploading = ref(false);
const uploadError = ref("");
let uploadRequest: AbortController | undefined;
const oversize = computed(() => (manifest.value?.size || 0) > 64 * 1024 || (binary.value?.size || 0) > 2 * 1024 * 1024);
function chooseFile(event: Event, kind: "manifest" | "model") {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (kind === "manifest") manifest.value = file;
  else binary.value = file;
  uploadError.value = "";
}
async function upload() {
  if (uploading.value || !manifest.value || !binary.value || oversize.value) return;
  const request = new AbortController();
  uploadRequest = request;
  uploading.value = true;
  uploadError.value = "";
  try {
    await plugins.importModel(props.screen, props.plugin, props.setting, manifest.value, binary.value, request.signal);
    manifest.value = undefined;
    binary.value = undefined;
    if (manifestInput.value) manifestInput.value.value = "";
    if (binaryInput.value) binaryInput.value.value = "";
  } catch (error: unknown) {
    if (!request.signal.aborted) uploadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    uploading.value = false;
    uploadRequest = undefined;
  }
}
function cancel() {
  uploadRequest?.abort();
  plugins.forgetDrafts(props.screen, props.plugin);
  error.value = "";
  uploadError.value = "";
}
watch(() => [props.screen.id, props.plugin.id, props.plugin.origin, props.plugin.source, props.setting.id],
  () => uploadRequest?.abort(), { flush: "sync" });
onBeforeUnmount(() => uploadRequest?.abort());
const desired = computed(() => plugins.modelsOn(props.screen, props.plugin, props.setting));
const have = computed(() => plugins.installedOn(props.screen, props.plugin.id));
const installed = computed(() => have.value?.installed_build_values?.[props.setting.id] || []);
const failed = computed(() => plugins.retryAvailable(props.screen, props.plugin) ? have.value?.failed_update?.build_values?.[props.setting.id] : undefined);
const pending = computed(() => have.value?.state === "building" || (have.value?.build_revision != null
  && have.value.build_revision !== have.value.installed_build_revision));
const label = (model: ModelEntry) => model.label || (model.url
  ? text(props.setting.catalogue.find((entry) => entry.url === model.url)?.label || {}) || model.url
  : t("editor.plugins.models.uploaded"));
function add(source: string) {
  const value = source.trim();
  if (!value) return;
  if (desired.value.some((model) => model.url === value)) { error.value = t("editor.plugins.models.duplicate"); return; }
  if (desired.value.length >= 16) { error.value = t("editor.plugins.models.limit"); return; }
  const preset = props.setting.catalogue.find((entry) => entry.url === value);
  plugins.setModels(props.screen, props.plugin, props.setting, [...desired.value, { ...(preset ? { id: preset.id } : {}), url: value }]);
  error.value = "";
  url.value = "";
}
function remove(source?: ModelEntry) {
  plugins.setModels(props.screen, props.plugin, props.setting, source ? desired.value.filter((model) => modelKey(model) !== modelKey(source)) : []);
  error.value = "";
}
</script>

<template>
  <section class="plugin-models" :data-model-setting="setting.id" :data-screen="screen.id">
    <h4>{{ text(setting.label) }}<template v-if="screen.name"> · {{ screen.name }}</template></h4>
    <p v-if="setting.hint" class="pd-room">{{ text(setting.hint) }}</p>
    <p v-if="ownYaml(screen)" class="pd-misfit" role="alert">{{ t("editor.plugins.models.managed_required") }}</p>
    <p class="pd-label">{{ t("editor.plugins.models.available") }}</p>
    <ul class="model-catalogue">
      <li v-for="preset in setting.catalogue" :key="preset.id">
        <span>{{ text(preset.label) }}</span>
        <button type="button" class="btn quiet" :data-add-model="preset.id" :disabled="desired.some((model) => model.url === preset.url)"
          @click="add(preset.url)">{{ desired.some((model) => model.url === preset.url)
            ? t(have?.build_confirmed && installed.some((model) => model.url === preset.url) ? 'editor.plugins.models.installed' : 'editor.plugins.models.added')
            : t('editor.plugins.models.add_to_screen') }}</button>
      </li>
    </ul>
    <div class="field model-url">
      <label class="f-label" :for="`model-url-${screen.id}-${setting.id}`">{{ t("editor.plugins.models.url") }}</label>
      <input :id="`model-url-${screen.id}-${setting.id}`" v-model="url" type="url" autocomplete="off" spellcheck="false" placeholder="https://…/model.json" @keydown.enter.prevent="add(url)" />
      <button type="button" class="btn quiet" data-add-url :disabled="!url.trim()" @click="add(url)">{{ t("editor.plugins.models.add") }}</button>
    </div>
    <div class="model-upload" :aria-busy="uploading">
      <p class="pd-label">{{ t("editor.plugins.models.computer") }}</p>
      <p class="pd-room">{{ t("editor.plugins.models.upload_hint") }}</p>
      <div class="field">
        <label class="f-label" :for="`model-manifest-${screen.id}-${setting.id}`">{{ t("editor.plugins.models.manifest_file") }}</label>
        <input :id="`model-manifest-${screen.id}-${setting.id}`" ref="manifestInput" data-model-manifest type="file" accept=".json,application/json"
          :disabled="uploading" @change="chooseFile($event, 'manifest')" />
      </div>
      <div class="field">
        <label class="f-label" :for="`model-binary-${screen.id}-${setting.id}`">{{ t("editor.plugins.models.binary_file") }}</label>
        <input :id="`model-binary-${screen.id}-${setting.id}`" ref="binaryInput" data-model-binary type="file" accept=".tflite"
          :disabled="uploading" @change="chooseFile($event, 'model')" />
      </div>
      <button type="button" class="btn quiet" data-upload-model
        :disabled="uploading || !manifest || !binary || oversize || desired.length >= 16 || ownYaml(screen) || plugins.submittingOn(screen, plugin.id)"
        @click="upload">{{ t(uploading ? "editor.plugins.models.uploading" : "editor.plugins.models.computer") }}</button>
      <p v-if="oversize || uploadError" class="pd-misfit" role="alert" data-upload-error>{{ oversize ? t("editor.plugins.models.upload_size") : uploadError }}</p>
    </div>
    <p v-if="error" class="pd-misfit" role="alert">{{ error }}</p>
    <p class="pd-label">{{ t("editor.plugins.models.desired") }}</p>
    <ul class="model-desired">
      <li v-for="model in desired" :key="modelKey(model)">
        <span><b>{{ label(model) }}</b><small>{{ model.upload !== undefined ? t("editor.plugins.models.uploaded") : model.url }}</small></span>
        <button type="button" class="btn quiet" :data-remove-model="model.url || model.id" @click="remove(model)">{{ t("editor.plugins.models.remove") }}</button>
      </li>
    </ul>
    <p v-if="!desired.length" class="pd-room" data-manual-only>{{ t("editor.plugins.models.manual_only") }}</p>
    <p v-if="plugins.modelChoiceRequired(screen, plugin, setting)" class="pd-misfit" data-model-required role="alert">{{ t("editor.plugins.models.required") }}</p>
    <p v-if="plugins.setupError(screen, plugin)" class="pd-misfit" role="alert">{{ plugins.setupError(screen, plugin) }}</p>
    <div class="pd-buttons">
      <button v-if="desired.length" type="button" class="btn quiet" data-remove-all @click="remove()">{{ t("editor.plugins.models.remove_all") }}</button>
      <button v-if="uploading || plugins.setupChanged(screen, plugin)" type="button" class="btn quiet" data-cancel-models @click="cancel">{{ t("editor.common.cancel") }}</button>
    </div>
    <p class="pd-room">{{ t("editor.plugins.models.apply_note") }}</p>
    <div v-if="have" class="model-installed" data-installed-models>
      <p class="pd-label">{{ t(have.build_confirmed ? 'editor.plugins.models.installed' : 'editor.plugins.models.unconfirmed') }}</p>
      <p v-if="pending" class="pd-room" data-model-pending>{{ t("editor.plugins.models.pending") }}</p>
      <ul><li v-for="model in installed" :key="modelKey(model)">{{ label(model) }}</li></ul>
      <p v-if="!installed.length" class="pd-room">{{ t("editor.plugins.models.manual_only") }}</p>
    </div>
    <div v-if="failed" class="model-failed" data-failed-models>
      <p class="pd-label">{{ t("editor.plugins.models.failed") }}</p>
      <ul><li v-for="model in failed" :key="modelKey(model)">{{ label(model) }}</li></ul>
      <p v-if="!failed.length" class="pd-room">{{ t("editor.plugins.models.manual_only") }}</p>
    </div>
  </section>
</template>

<style scoped>
.plugin-models { min-width: 0; margin-block: 1rem; overflow-wrap: anywhere; }
h4 { margin-block: 0 .5rem; }
ul { list-style: none; padding: 0; }
.model-catalogue li, .model-desired li { display: flex; gap: .75rem; align-items: center; justify-content: space-between; margin-block: .5rem; }
.model-catalogue span, .model-desired span { flex: 1; min-width: 0; }
.model-catalogue button, .model-desired button { flex: none; }
.model-desired small { display: block; }
.model-url { min-width: 0; grid-template-columns: minmax(0, 1fr); }
.model-url input, .model-upload input { box-sizing: border-box; width: 100%; min-width: 0; max-width: 100%; }
.model-url button { margin-top: .5rem; }
.model-installed, .model-failed { border-top: 1px solid var(--line); margin-top: 1rem; padding-top: .5rem; }
.model-upload, .model-upload .field { min-width: 0; max-width: 100%; }
.model-upload .field { margin-block: .75rem; grid-template-columns: minmax(0, 1fr); }
.model-upload button { white-space: normal; max-width: 100%; }
@media (max-width: 420px) {
  .model-catalogue li, .model-desired li { flex-wrap: wrap; }
  .model-catalogue button, .model-desired button { white-space: normal; max-width: 100%; }
}
</style>
