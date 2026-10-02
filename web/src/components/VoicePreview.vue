<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { getJson } from "../api";
import { t } from "../i18n";
import { go } from "../store";
import { VoicePreview, type VoicePanel, type VoicePhase, type VoiceSource } from "../model/voice-preview";
import HelpTip from "./HelpTip.vue";
import Icon from "./ui/Icon.vue";

const props = defineProps<{ panel: () => VoicePanel; target?: HTMLElement }>();
const emit = defineEmits<{ action: [] }>();
const enabled = ref(false), configured = ref(false), phase = ref<VoicePhase>("idle");
const provider = ref("openai");
const connected = computed(() => !["idle", "connecting"].includes(phase.value));
const error = ref(""), reply = ref("");
const sources = ref<VoiceSource[]>([]);
let disposed = false;
const hooks = {
  phase: (value: VoicePhase) => { phase.value = value; }, reply: (value: string) => { reply.value = value; },
  error: (value: string) => { error.value = value; }, action: () => emit("action"),
  sources: (value: VoiceSource[]) => { sources.value = value; },
};
let voice: VoicePreview | undefined;
defineExpose({ refreshContext: async () => {
  try { await voice?.refreshContext(); } catch (e) { error.value = e instanceof Error ? e.message : String(e); }
} });
onMounted(async () => {
  try {
    const status = await getJson<{ enabled: boolean; configured: boolean; provider?: string; idle_seconds?: number; reply_speaker?: string }>("voice-preview/status");
    if (!disposed) {
      enabled.value = status.enabled; configured.value = status.configured; provider.value = status.provider ?? "openai";
      voice = new VoicePreview(() => props.panel(), hooks, provider.value, status.idle_seconds ?? 5, !!status.reply_speaker);
    }
  } catch { /* An older manager has no voice experiment. */ }
});
const start = () => { void voice?.start(); };
const stop = () => { void voice?.stop(); };
window.addEventListener("pagehide", stop);
onBeforeUnmount(() => { disposed = true; window.removeEventListener("pagehide", stop); stop(); });
</script>

<template>
  <Teleport v-if="enabled" :to="target || 'body'" :disabled="!target">
    <section class="voice-preview-tools" :aria-label="t('editor.voice.title')">
      <div class="tool-group">
        <button type="button" class="btn" :class="{ primary: connected }" :aria-pressed="connected"
          :disabled="!configured && phase === 'idle'" @click="phase === 'idle' ? start() : stop()">
          <Icon v-if="connected" name="check" />{{ t(phase === 'idle' ? 'editor.voice.start' : 'editor.voice.stop') }}
        </button>
        <HelpTip v-if="configured" :text="t(provider === 'claude' ? 'editor.voice.claude_privacy' : 'editor.voice.privacy')" />
        <span v-if="phase !== 'idle'" role="status">{{ t(`editor.voice.${phase}`) }}</span>
      </div>
      <p v-if="!configured" class="hint">{{ t('editor.voice.setup') }}</p>
      <button v-if="!configured" type="button" class="btn quiet" id="voice-open-settings" @click="go('#settings')">{{ t('editor.voice.configure') }}</button>
      <details v-show="reply || sources.length" class="voice-details">
        <summary>{{ t('editor.voice.details') }}</summary>
        <p v-if="reply" aria-live="polite">{{ reply }}</p>
        <p v-if="sources.length" class="voice-sources">
          {{ t('editor.voice.sources') }}:
          <a v-for="(source, index) in sources" :key="source.url" :href="source.url"
            target="_blank" rel="noopener noreferrer">[{{ index + 1 }}] {{ source.title }}</a>
        </p>
      </details>
      <p v-if="error" role="alert">{{ error }}</p>
    </section>
  </Teleport>
</template>

<style scoped>
.voice-details { font-size: 12px; }
.voice-details summary { cursor: pointer; }
.voice-sources { display: flex; flex-wrap: wrap; gap: 4px 10px; font-size: 12px; overflow-wrap: anywhere; }
</style>
