<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { getJson, send } from "../api";
import { t } from "../i18n";

type Status = { enabled: boolean; configured: boolean; key_configured?: boolean; saved_key: boolean; source: string;
  provider?: string; pipeline?: string; pipelines?: { id: string; name: string; language: string; ready: boolean; stt_ready: boolean; tts_ready: boolean }[];
  speech_ready?: boolean; model?: string; voice?: string; voices?: string[]; idle_seconds?: number;
  reply_speaker?: string; reply_volume?: number; reply_speakers?: { id: string; name: string; available: boolean }[];
  spotify?: { configured: boolean; market: string } };
const status = ref<Status | null>(null), key = ref(""), selectedVoice = ref(""), busy = ref(false), error = ref(""), saved = ref("");
const selectedProvider = ref("openai"), selectedPipeline = ref("");
const idleSeconds = ref(5);
const replySpeaker = ref(""), replyVolume = ref(30);
const replySummary = computed(() => status.value?.reply_speaker
  ? status.value.reply_speakers?.find(item => item.id === status.value?.reply_speaker)?.name || status.value.reply_speaker
  : t('editor.voice.output_local'));
const spotifyId = ref(""), spotifySecret = ref(""), spotifyMarket = ref("");
const credentialsOpen = ref(false), speechOpen = ref(false);
const keyConfigured = computed(() => status.value?.key_configured ?? status.value?.configured ?? false);
const speechSummary = computed(() => status.value?.provider === "claude"
  ? status.value.pipelines?.find(p => p.id === status.value?.pipeline)?.name || t('editor.voice.pipeline_choose')
  : status.value?.voice ? status.value.voice.charAt(0).toUpperCase() + status.value.voice.slice(1) : "");
function openSetup() {
  credentialsOpen.value = !keyConfigured.value;
  speechOpen.value = status.value?.provider === 'claude' && !status.value.speech_ready;
}
function apply(result: Status) {
  status.value = result; selectedVoice.value = result.voice ?? "";
  selectedProvider.value = result.provider ?? "openai"; selectedPipeline.value = result.pipeline ?? "";
  idleSeconds.value = result.idle_seconds ?? 5;
  replySpeaker.value = result.reply_speaker ?? ""; replyVolume.value = result.reply_volume ?? 30;
  spotifyMarket.value = result.spotify?.market ?? "";
}
let disposed = false;
onMounted(async () => {
  try {
    const result = await getJson<Status>("voice-preview/status");
    if (!disposed) { apply(result); openSetup(); }
  } catch { /* Older managers do not have this experiment. */ }
});
onBeforeUnmount(() => { disposed = true; key.value = ""; spotifyId.value = ""; spotifySecret.value = ""; });
async function saveSpotify(remove = false) {
  busy.value = true; error.value = ""; saved.value = "";
  try {
    const result = await send<Status>("voice-preview/spotify", remove ? "DELETE" : "PUT", remove ? undefined : {
      client_id: spotifyId.value.trim(), client_secret: spotifySecret.value.trim(), market: spotifyMarket.value.trim().toUpperCase(),
    });
    if (!disposed) { apply(result); saved.value = remove ? "" : "editor.voice.spotify_saved"; }
  } catch (e) {
    if (!disposed) error.value = e instanceof Error ? e.message : String(e);
  } finally { spotifyId.value = ""; spotifySecret.value = ""; busy.value = false; }
}
async function update(remove = false) {
  busy.value = true; error.value = ""; saved.value = "";
  try {
    const path = status.value?.provider === "claude" ? "voice-preview/config/claude" : "voice-preview/config";
    const result = await send<Status>(path, remove ? "DELETE" : "PUT", remove ? undefined : { api_key: key.value });
    if (!disposed) { apply(result); saved.value = remove ? "" : "editor.voice.key_saved"; }
  } catch (e) {
    if (!disposed) error.value = e instanceof Error ? e.message : String(e);
  } finally {
    key.value = ""; busy.value = false;
  }
}
async function saveRoute(field: "provider" | "pipeline") {
  busy.value = true; error.value = ""; saved.value = ""; key.value = "";
  try {
    const result = await send<Status>("voice-preview/config", "PUT", {
      [field]: field === "provider" ? selectedProvider.value : selectedPipeline.value,
    });
    if (!disposed) { apply(result); if (field === 'provider') openSetup(); }
  } catch (e) {
    if (!disposed) { error.value = e instanceof Error ? e.message : String(e); if (status.value) apply(status.value); }
  } finally { busy.value = false; }
}
async function saveVoice() {
  busy.value = true; error.value = ""; saved.value = "";
  try {
    const result = await send<Status>("voice-preview/config", "PUT", { voice: selectedVoice.value });
    if (!disposed) { status.value = result; selectedVoice.value = result.voice ?? ""; saved.value = "editor.voice.voice_saved"; }
  } catch (e) {
    if (!disposed) error.value = e instanceof Error ? e.message : String(e);
  } finally { busy.value = false; }
}
async function saveIdle() {
  busy.value = true; error.value = ""; saved.value = "";
  try {
    const result = await send<Status>("voice-preview/config", "PUT", { idle_seconds: idleSeconds.value });
    if (!disposed) { apply(result); saved.value = "editor.voice.idle_saved"; }
  } catch (e) {
    if (!disposed) error.value = e instanceof Error ? e.message : String(e);
  } finally { busy.value = false; }
}
async function saveOutput() {
  busy.value = true; error.value = ""; saved.value = "";
  try {
    const result = await send<Status>("voice-preview/config", "PUT", {
      reply_speaker: replySpeaker.value, reply_volume: replyVolume.value,
    });
    if (!disposed) { apply(result); saved.value = "editor.voice.output_saved"; }
  } catch (e) {
    if (!disposed) error.value = e instanceof Error ? e.message : String(e);
  } finally { busy.value = false; }
}
</script>

<template>
  <section v-if="status?.enabled" class="card" id="voice-settings">
    <h2>{{ t('editor.voice.settings_title') }}</h2>
    <div class="field">
      <label class="f-label" for="voice-provider">{{ t('editor.voice.provider') }}</label>
      <select id="voice-provider" v-model="selectedProvider" :disabled="busy" @change="saveRoute('provider')">
        <option value="openai">OpenAI</option><option value="claude">Claude</option>
      </select>
    </div>
    <details id="voice-credentials" class="voice-section" :open="credentialsOpen" @toggle="credentialsOpen = ($event.target as HTMLDetailsElement).open">
      <summary>
        <span>{{ t('editor.voice.credentials_title') }}<small>{{ t(keyConfigured ? (status.source === 'server' ? 'editor.voice.key_server' : 'editor.voice.key_configured') : 'editor.voice.key_missing') }}</small></span>
      </summary>
      <div class="voice-section-body">
        <p>{{ t(status.provider === 'claude' ? 'editor.voice.claude_route' : 'editor.voice.openai_route') }}</p>
        <form @submit.prevent="update()">
          <div class="field">
            <label class="f-label" for="voice-api-key">{{ t(status.provider === 'claude' ? 'editor.voice.claude_key' : 'editor.voice.api_key') }}</label>
            <input id="voice-api-key" v-model="key" type="password" autocomplete="new-password" spellcheck="false" autocapitalize="none"
              :disabled="busy" required minlength="20" maxlength="1024" :placeholder="t(keyConfigured ? 'editor.voice.key_replace' : 'editor.voice.key_enter')" />
            <small>{{ t('editor.voice.key_private') }}</small>
          </div>
          <div class="actions">
            <button type="submit" class="btn primary" :disabled="busy || !key.trim()">{{ t('editor.voice.key_save') }}</button>
            <button v-if="status.saved_key" type="button" class="btn quiet" :disabled="busy" @click="update(true)">{{ t('editor.voice.key_remove') }}</button>
          </div>
        </form>
      </div>
    </details>
    <details id="voice-speech" class="voice-section" :open="speechOpen" @toggle="speechOpen = ($event.target as HTMLDetailsElement).open">
      <summary><span>{{ t('editor.voice.speech_title') }}<small>{{ speechSummary }}{{ speechSummary ? ' · ' : '' }}{{ t('editor.voice.idle_summary', { seconds: status.idle_seconds ?? 5 }) }}</small></span></summary>
      <div class="voice-section-body">
        <form v-if="status.provider === 'claude'" id="voice-pipeline-form" @submit.prevent="saveRoute('pipeline')">
          <div class="field">
            <label class="f-label" for="voice-pipeline">{{ t('editor.voice.pipeline') }}</label>
            <select id="voice-pipeline" v-model="selectedPipeline" :disabled="busy">
              <option value="" disabled>{{ t('editor.voice.pipeline_choose') }}</option>
              <option v-for="pipeline in status.pipelines" :key="pipeline.id" :value="pipeline.id" :disabled="!pipeline.ready">
                {{ pipeline.name }} ({{ pipeline.language }}){{ pipeline.ready ? '' : ': ' + t('editor.voice.pipeline_incomplete') + ' (' + [!pipeline.stt_ready && 'STT', !pipeline.tts_ready && 'TTS'].filter(Boolean).join(', ') + ')' }}
              </option>
            </select>
            <small>{{ t('editor.voice.pipeline_hint') }}</small>
          </div>
          <p v-if="!status.pipelines?.some(p => p.ready)" class="hint">{{ t('editor.voice.pipeline_missing') }}</p>
          <div class="actions">
            <button class="btn" type="submit" :disabled="busy || !selectedPipeline || selectedPipeline === status.pipeline">{{ t('editor.voice.pipeline_save') }}</button>
          </div>
        </form>
        <form v-if="status.voices?.length" id="voice-choice-form" @submit.prevent="saveVoice">
          <div class="field">
            <label class="f-label" for="voice-choice">{{ t('editor.voice.voice_label') }}</label>
            <select id="voice-choice" v-model="selectedVoice" :disabled="busy">
              <option v-for="voice in status.voices" :key="voice" :value="voice">{{ voice.charAt(0).toUpperCase() + voice.slice(1) }}</option>
            </select>
            <small>{{ t('editor.voice.voice_hint') }}</small>
          </div>
          <div class="actions">
            <button type="submit" class="btn" :disabled="busy || selectedVoice === status.voice">{{ t('editor.voice.voice_save') }}</button>
          </div>
        </form>
        <form id="voice-idle-form" @submit.prevent="saveIdle">
          <div class="field">
            <label class="f-label" for="voice-idle-seconds">{{ t('editor.voice.idle_label') }}</label>
            <input id="voice-idle-seconds" v-model.number="idleSeconds" type="number" min="1" max="300" step="1" required :disabled="busy" />
            <small>{{ t('editor.voice.idle_hint') }}</small>
          </div>
          <div class="actions">
            <button type="submit" class="btn" :disabled="busy || idleSeconds === (status.idle_seconds ?? 5)">{{ t('editor.voice.idle_save') }}</button>
          </div>
        </form>
      </div>
    </details>
    <details id="voice-output" class="voice-section">
      <summary><span>{{ t('editor.voice.output_title') }}<small>{{ replySummary }}</small></span></summary>
      <form id="voice-output-form" class="voice-section-body" @submit.prevent="saveOutput">
        <div class="field">
          <label class="f-label" for="voice-reply-speaker">{{ t('editor.voice.output_title') }}</label>
          <select id="voice-reply-speaker" v-model="replySpeaker" :disabled="busy">
            <option value="">{{ t('editor.voice.output_local') }}</option>
            <option v-for="speaker in status.reply_speakers" :key="speaker.id" :value="speaker.id" :disabled="!speaker.available">
              {{ speaker.name }}{{ speaker.available ? '' : ' · ' + t('editor.voice.output_unavailable') }}
            </option>
            <option v-if="replySpeaker && !status.reply_speakers?.some(item => item.id === replySpeaker)" :value="replySpeaker" disabled>
              {{ replySpeaker }} · {{ t('editor.voice.output_unavailable') }}
            </option>
          </select>
          <small>{{ t('editor.voice.output_hint') }}</small>
        </div>
        <div v-if="replySpeaker" class="field">
          <label class="f-label" for="voice-reply-volume">{{ t('editor.voice.output_volume') }} · {{ replyVolume }}%</label>
          <input id="voice-reply-volume" v-model.number="replyVolume" type="range" min="1" max="100" step="1" :disabled="busy" />
        </div>
        <div class="actions">
          <button type="submit" class="btn" :disabled="busy || (replySpeaker === (status.reply_speaker ?? '') && replyVolume === (status.reply_volume ?? 30))">{{ t('editor.voice.output_save') }}</button>
        </div>
      </form>
    </details>
    <details id="voice-spotify" class="voice-section">
      <summary><span>{{ t('editor.voice.spotify_title') }}<small>{{ t(status.spotify?.configured ? 'editor.voice.spotify_status_saved' : 'editor.voice.spotify_status_optional') }}{{ status.spotify?.configured && status.spotify.market ? ' · ' + status.spotify.market : '' }}</small></span></summary>
      <form id="voice-spotify-form" class="voice-section-body" @submit.prevent="saveSpotify()">
        <p>{{ t('editor.voice.spotify_hint') }}</p>
        <p role="status">{{ t(status.spotify?.configured ? 'editor.voice.spotify_replace_hint' : 'editor.voice.spotify_missing') }}</p>
        <a href="https://developer.spotify.com/dashboard" target="_blank" rel="noopener noreferrer">Spotify Developer Dashboard</a>
        <div class="field">
          <label class="f-label" for="voice-spotify-id">Spotify Client ID</label>
          <input id="voice-spotify-id" v-model="spotifyId" type="password" autocomplete="new-password" spellcheck="false" autocapitalize="none"
            :disabled="busy" required minlength="16" maxlength="128" :placeholder="t(status.spotify?.configured ? 'editor.voice.spotify_id_replace' : 'editor.voice.spotify_id_enter')" />
        </div>
        <div class="field">
          <label class="f-label" for="voice-spotify-secret">Spotify Client Secret</label>
          <input id="voice-spotify-secret" v-model="spotifySecret" type="password" autocomplete="new-password" spellcheck="false" autocapitalize="none"
            :disabled="busy" required minlength="16" maxlength="128" :placeholder="t(status.spotify?.configured ? 'editor.voice.spotify_secret_replace' : 'editor.voice.spotify_secret_enter')" />
          <small>{{ t('editor.voice.key_private') }}</small>
        </div>
        <div class="field">
          <label class="f-label" for="voice-spotify-market">{{ t('editor.voice.spotify_market') }}</label>
          <input id="voice-spotify-market" v-model="spotifyMarket" type="text" pattern="[A-Za-z]{2}" minlength="2" maxlength="2"
            :disabled="busy" required placeholder="NL" autocapitalize="characters" />
          <small>{{ t('editor.voice.spotify_market_hint') }}</small>
        </div>
        <div class="actions">
          <button class="btn" type="submit" :disabled="busy || !spotifyId.trim() || !spotifySecret.trim() || spotifyMarket.trim().length !== 2">{{ t('editor.voice.spotify_save') }}</button>
          <button v-if="status.spotify?.configured" class="btn quiet" type="button" :disabled="busy" @click="saveSpotify(true)">{{ t('editor.voice.spotify_remove') }}</button>
        </div>
      </form>
    </details>
    <p v-if="saved" role="status">{{ t(saved) }}</p>
    <p v-if="error" role="alert">{{ error }}</p>
  </section>
</template>

<style scoped>
#voice-settings { align-self: start; min-width: 0; }
.voice-section { border-top: 1px solid var(--line); padding-top: 10px; min-width: 0; }
.voice-section > summary { display: flex; align-items: baseline; gap: 8px; cursor: pointer; list-style: none; font-weight: 600; font-size: 13px; }
.voice-section > summary::-webkit-details-marker { display: none; }
.voice-section > summary::before { content: "\25B8"; flex: none; color: var(--muted); }
.voice-section[open] > summary::before { transform: rotate(90deg); }
.voice-section > summary > span { min-width: 0; }
.voice-section > summary small { display: block; color: var(--muted); font-weight: 400; font-size: 12px; overflow-wrap: anywhere; }
.voice-section-body { display: grid; gap: 12px; padding-top: 12px; }
.voice-section-body form { display: grid; gap: 12px; min-width: 0; }
</style>
