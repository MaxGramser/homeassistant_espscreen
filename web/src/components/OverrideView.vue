<script setup lang="ts">
// Per-screen local YAML override: a small file of the owner's, loaded after the shared screen package.
import { computed, onMounted, ref, watch } from "vue";
import { useBusy } from "../composables/useBusy";
import { useConfirm } from "../composables/useConfirm";
import { getJson, send } from "../api";
import { useLineBuild } from "../composables/useFirmwareJob";
import { t } from "../i18n";
import { errorLine } from "../model/firmware-job";
import { glyph } from "../model/topbar";
import { useBuildsStore } from "../stores/builds";
import { useInventoryStore } from "../stores/inventory";
import { useUiStore } from "../stores/ui";

const ui = useUiStore();
const builds = useBuildsStore();

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
const inv = useInventoryStore();
const profile = computed(() => ui.overrideProfile);
// The screen whose profile this is, by the inventory: the address carries the profile alone (router.ts).
const friendly = computed(() => inv.inventory.screens.find((s) => s.update?.profile === profile.value)?.name ?? "");
const content = ref("");
const file = ref("");
const attached = ref(false);
const status = ref(t("editor.common.loading"));
const kind = ref("");
const { busy, runOnce } = useBusy();
const editor = ref<HTMLTextAreaElement | null>(null);
const gutter = ref<HTMLDivElement | null>(null);
const lines = computed(() => content.value.split("\n").length);
const gutterText = computed(() => Array.from({ length: lines.value }, (_, i) => i + 1).join("\n"));
const count = computed(() => `${t("editor.override.characters", content.value.length)} · ${t("editor.override.lines", lines.value)}`);
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
const saveOverride = (runCheck = false) => runOnce(async () => {
  if (!profile.value) return;
  setStatus(t("editor.override.saving"));
  try {
    const data = await send(`firmware/profiles/${encodeURIComponent(profile.value)}/override`, "PUT", { content: content.value });
    file.value = data.override_file;
    attached.value = true;
    if (!runCheck) {
      setStatus(t("editor.override.saved"), "ok");
      ui.toast(t("editor.override.saved_toast"));
      return;
    }
    setStatus(t("editor.override.checking"));
    const build = await builds.askBuild({ file: profile.value, action: "validate" });
    checking.value = { profile: profile.value, id: build.id, started: Date.now() };
    followCheck();
  } catch (error: any) {
    setStatus(error.message, "error");
  }
});
// The check of a profile, followed by its id in the add-on's build line (useLineBuild): every 1.2 seconds while the page
// is in sight, until it ends, the page shows another screen or two hours have gone by. It may first wait its turn behind
// a screen's build. A hidden tab asks nothing until it is shown again, and an answer another view has had is this one's
// too.
const checking = ref<{ profile: string; id: number; started: number } | null>(null);
const CHECK_MS = 7200000;
const check = useLineBuild(() => checking.value?.id, { interval: 1200, onError: (error) => {
  if (!checking.value) return;
  checking.value = null;
  setStatus(error.message, "error");
} });
watch(() => [check.build.value?.state, check.build.value?.stage, check.build.value?.place, check.logs.value.length], followCheck);
function followCheck() {
  const asked = checking.value;
  if (!asked) return;
  if (profile.value !== asked.profile || Date.now() - asked.started >= CHECK_MS || builds.lineForgot(asked.id)) { checking.value = null; return; }
  // What the check is now and its log, read before `checking` lets go of it (which also lets go of the build).
  const current = check.build.value, lines = check.logs.value;
  if (!current) return;
  if (current.state === "queued") {
    setStatus(t("editor.override.checking_waits"));
  } else if (current.state === "running") {
    setStatus(current.stage ? t("editor.override.checking_stage", { stage: current.stage }) : t("editor.override.checking_profile"));
  } else if (current.state === "success") {
    checking.value = null;
    setStatus(t("editor.override.valid"), "ok");
  } else if (lines.length || current.reason || current.state !== "failed") {
    // A check that failed says why once its own log is here (asked once it ended), or the add-on's reason when it was
    // refused at its turn (its profile went).
    checking.value = null;
    setStatus(errorLine(lines) || current.reason || t("editor.override.rejected"), "error");
  }
}
const { confirm } = useConfirm();
async function useExample() {
  if (!content.value.trim() || await confirm(t("editor.override.confirm_example"), { confirm: t("editor.confirm.use_example"), danger: true })) {
    content.value = OVERRIDE_EXAMPLE;
    setStatus(t("editor.override.example_loaded"));
    editor.value?.focus();
  }
}
async function clear() {
  if (!content.value.trim() || await confirm(t("editor.override.confirm_clear"), { confirm: t("editor.confirm.clear_override"), danger: true })) {
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
</script>

<template>
  <div class="panel" id="override-dialog">
    <div class="panel-head">
      <div class="tx">
        <span class="eyebrow">{{ t("editor.override.eyebrow") }}</span>
        <h1 id="override-title">{{ friendly ? t("editor.override.title_named", { name: friendly }) : t("editor.override.title") }}</h1>
        <p>{{ t("editor.override.intro") }}</p>
      </div>
      <button type="button" class="btn quiet" id="close-override" @click="ui.go('')">{{ t("editor.common.back") }}</button>
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
