<script setup lang="ts">
// Per-screen local YAML override: a small file of the owner's, loaded after the shared screen package.
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { getJson, send } from "../api";
import { t } from "../i18n";
import { glyph } from "../model/topbar";
import { fetchFirmware, go, state, toast } from "../store";

const OVERRIDE_EXAMPLE = `# Hardware-specific changes for this screen.
# This file is kept when the shared firmware package updates.
# Do not add esphome:, api:, ota:, wifi: or packages: here.

# Example: a CYD with the ST7789V display controller.
# "!extend" changes the display the shared package already defines;
# a bare id would add a second, incomplete display and fail the build.
display:
  - id: !extend my_display
    model: ST7789V
`;
const profile = computed(() => state.overrideProfile);
const content = ref("");
const file = ref("");
const attached = ref(false);
const status = ref(t("editor.common.loading"));
const kind = ref("");
const busy = ref(false);
const editor = ref<HTMLTextAreaElement | null>(null);
const gutter = ref<HTMLDivElement | null>(null);
const lines = computed(() => content.value.split("\n").length);
const gutterText = computed(() => Array.from({ length: lines.value }, (_, i) => i + 1).join("\n"));
const count = computed(() => `${t("editor.override.characters", content.value.length)} · ${t("editor.override.lines", lines.value)}`);
let alive = true;
function setStatus(message: string, k = "") { status.value = message; kind.value = k; }
async function load() {
  if (!profile.value) { setStatus(t("editor.override.no_profile"), "error"); return; }
  setStatus(t("editor.common.loading"));
  try {
    const data = await getJson(`firmware/profiles/${encodeURIComponent(profile.value)}/override`);
    file.value = data.override_file;
    attached.value = Boolean(data.attached);
    content.value = data.exists && data.content !== "{}\n" ? data.content : "";
    setStatus(t(data.attached ? "editor.override.attached" : "editor.override.not_attached"));
  } catch (error: any) {
    setStatus(error.message, "error");
  }
}
async function saveOverride(runCheck = false) {
  if (!profile.value || busy.value) return;
  busy.value = true;
  setStatus(t("editor.override.saving"));
  try {
    const data = await send(`firmware/profiles/${encodeURIComponent(profile.value)}/override`, "PUT", { content: content.value });
    file.value = data.override_file;
    attached.value = true;
    if (!runCheck) {
      setStatus(t("editor.override.saved"), "ok");
      toast(t("editor.override.saved_toast"));
      return;
    }
    setStatus(t("editor.override.checking"));
    await send("firmware/jobs", "POST", { file: profile.value, action: "validate" });
    pollCheck();
  } catch (error: any) {
    setStatus(error.message, "error");
  } finally {
    busy.value = false;
  }
}
function pollCheck() {
  const started = Date.now(), checked = profile.value;
  const poll = async () => {
    if (!alive || profile.value !== checked) return;  // the page closed or shows another screen
    // A hidden tab asks nothing until it is shown again; an answer another view has just had is this one's too.
    if (document.hidden) { if (Date.now() - started < 7200000) setTimeout(poll, 1200); return; }
    try {
      const data = await fetchFirmware(1000);
      const current = data.job;
      if (current && current.file === checked && current.state === "running") {
        setStatus(current.stage ? t("editor.override.checking_stage", { stage: current.stage }) : t("editor.override.checking_profile"));
      } else if (current && current.file === checked && current.state === "success") {
        setStatus(t("editor.override.valid"), "ok");
        return;
      } else if (current && current.file === checked && current.state === "failed") {
        const error = (data.logs || []).filter((line: string) => /error|failed/i.test(line)).pop();
        setStatus(error || t("editor.override.rejected"), "error");
        return;
      }
      if (Date.now() - started < 7200000) setTimeout(poll, 1200);
    } catch (error: any) {
      setStatus(error.message, "error");
    }
  };
  poll();
}
function useExample() {
  if (!content.value.trim() || confirm(t("editor.override.confirm_example"))) {
    content.value = OVERRIDE_EXAMPLE;
    setStatus(t("editor.override.example_loaded"));
    editor.value?.focus();
  }
}
function clear() {
  if (!content.value.trim() || confirm(t("editor.override.confirm_clear"))) {
    content.value = "";
    setStatus(t("editor.override.cleared"));
    editor.value?.focus();
  }
}
function onKey(event: KeyboardEvent) {
  const area = editor.value!;
  if (event.key === "Tab") {
    event.preventDefault();
    const start = area.selectionStart, end = area.selectionEnd;
    area.setRangeText("  ", start, end, "end");
    content.value = area.value;
  } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
    event.preventDefault();
    saveOverride(false);
  }
}
function syncScroll() { if (gutter.value && editor.value) gutter.value.scrollTop = editor.value.scrollTop; }
onMounted(load);
onBeforeUnmount(() => { alive = false; });
</script>

<template>
  <div class="panel" id="override-dialog">
    <div class="panel-head">
      <div class="tx">
        <span class="eyebrow">{{ t("editor.override.eyebrow") }}</span>
        <h1 id="override-title">{{ state.overrideFriendly ? t("editor.override.title_named", { name: state.overrideFriendly }) : t("editor.override.title") }}</h1>
        <p>{{ t("editor.override.intro") }}</p>
      </div>
      <button type="button" class="btn quiet" id="close-override" @click="go('')">{{ t("editor.common.back") }}</button>
    </div>
    <div class="notice">
      <span class="mdi">{{ glyph("F0493") }}</span>
      <div><strong>{{ t("editor.override.safe_title") }}</strong><span>{{ t("editor.override.safe_text") }}</span></div>
    </div>
    <div class="file-row">
      <code id="override-file">{{ file || profile || "" }}</code>
      <span id="override-state" class="chip" :class="{ good: attached }">{{ attached ? t("editor.override.active") : t("editor.override.ready") }}</span>
    </div>
    <div class="yaml-editor" id="yaml-editor-wrap">
      <div ref="gutter" class="yaml-gutter" id="override-gutter" aria-hidden="true">{{ gutterText }}</div>
      <textarea ref="editor" id="override-editor" v-model="content" spellcheck="false" autocapitalize="off" autocomplete="off" autocorrect="off"
        :aria-label="t('editor.override.editor_label')" placeholder="# Example&#10;display:&#10;  - id: !extend my_display&#10;    model: ST7789V" @keydown="onKey" @scroll="syncScroll"></textarea>
    </div>
    <div class="actions">
      <button type="button" class="btn quiet mini" id="override-example" @click="useExample">{{ t("editor.override.use_example") }}</button>
      <button type="button" class="btn quiet mini" id="override-empty" @click="clear">{{ t("editor.override.clear") }}</button>
      <span id="override-count" class="hint">{{ count }}</span>
    </div>
    <p id="override-status" class="status-line" :class="kind" role="status">{{ status }}</p>
    <div class="actions">
      <button type="button" class="btn quiet" id="override-check" :disabled="busy || !profile" @click="saveOverride(true)">{{ t("editor.override.save_check") }}</button>
      <button type="button" class="btn primary" id="override-save" :disabled="busy || !profile" @click="saveOverride(false)">{{ t("editor.override.save") }}</button>
    </div>
  </div>
</template>
