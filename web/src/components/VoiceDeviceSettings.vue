<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { getJson, send } from "../api";
import { t } from "../i18n";

type Panel = { id: string; name: string; paired: boolean };
type Pair = { url: string; token: string };
const panels = ref<Panel[]>([]), selected = ref(""), url = ref("");
const credentials = ref<Pair | null>(null), busy = ref(false), error = ref("");
const panel = computed(() => panels.value.find(item => item.id === selected.value));
let disposed = false;
onMounted(async () => {
  try {
    const result = await getJson<{ screens: Panel[]; url: string }>("voice-devices");
    if (!disposed) { panels.value = result.screens; url.value = result.url; selected.value = result.screens[0]?.id ?? ""; }
  } catch (e) { if (!disposed) error.value = e instanceof Error ? e.message : String(e); }
});
onBeforeUnmount(() => { disposed = true; credentials.value = null; });
async function pair(remove = false) {
  busy.value = true; error.value = ""; credentials.value = null;
  try {
    const result = await send<Pair>(`voice-devices/${encodeURIComponent(selected.value)}${remove ? "" : "/pair"}`,
      remove ? "DELETE" : "POST", remove ? undefined : { url: url.value });
    if (!disposed) {
      if (panel.value) panel.value.paired = !remove;
      credentials.value = remove ? null : result;
    }
  } catch (e) { if (!disposed) error.value = e instanceof Error ? e.message : String(e); }
  finally { busy.value = false; }
}
function download() {
  if (!credentials.value) return;
  const pair = credentials.value;
  const yaml = `substitutions:\n  AUDIO_MODE: "voice"\n  VOICE_URL: ${JSON.stringify(pair.url)}\n  VOICE_TOKEN: ${JSON.stringify(pair.token)}\n`;
  const objectURL = URL.createObjectURL(new Blob([yaml], { type: "application/yaml" }));
  const link = document.createElement("a");
  link.href = objectURL; link.download = "panel-voice.yaml"; link.click();
  setTimeout(() => URL.revokeObjectURL(objectURL), 1000);
}
</script>

<template>
  <details class="voice-device-settings">
    <summary>{{ t('editor.voice_device.title') }}</summary>
    <div class="voice-device-body">
      <p>{{ t('editor.voice_device.hint') }}</p>
      <p v-if="!panels.length">{{ t('editor.voice_device.no_panels') }}</p>
      <form v-else @submit.prevent="pair()">
        <div class="field">
          <label for="voice-device">{{ t('editor.voice_device.panel') }}</label>
          <select id="voice-device" v-model="selected" :disabled="busy" @change="credentials = null">
            <option v-for="item in panels" :key="item.id" :value="item.id">{{ item.name }}</option>
          </select>
        </div>
        <div class="field">
          <label for="voice-device-url">{{ t('editor.voice_device.address') }}</label>
          <input id="voice-device-url" v-model="url" type="url" required :disabled="busy" spellcheck="false"
            placeholder="ws://homeassistant.local:8098" />
          <small>{{ t('editor.voice_device.address_hint') }}</small>
        </div>
        <p v-if="panel?.paired">{{ t('editor.voice_device.paired_hint') }}</p>
        <div class="actions">
          <button type="submit" class="btn" :disabled="busy || !url">{{ t(panel?.paired ? 'editor.voice_device.replace' : 'editor.voice_device.pair') }}</button>
          <button v-if="panel?.paired" type="button" class="btn quiet" :disabled="busy" @click="pair(true)">{{ t('editor.voice_device.remove') }}</button>
        </div>
      </form>
      <div v-if="credentials" role="status">
        <p>{{ t('editor.voice_device.install') }}</p>
        <button type="button" class="btn" @click="download">{{ t('editor.voice_device.download') }}</button>
        <p class="muted">{{ t('editor.voice_device.private') }}</p>
      </div>
      <p v-if="error" role="alert">{{ error }}</p>
    </div>
  </details>
</template>

<style scoped>
.voice-device-settings { border-top: 1px solid var(--line); padding-top: 10px; min-width: 0; }
summary { cursor: pointer; font-weight: 600; font-size: 13px; }
.voice-device-body, form { display: grid; gap: 12px; padding-top: 12px; min-width: 0; }
</style>
