<script setup lang="ts">
// How a page stands in the Dock (docs/MODULES.md), on a screen whose board has one: one field of three, its picture
// (the default), an icon of its own, or not at all. Icon opens the icon picker; until an icon is picked nothing changes.
import { computed, ref } from "vue";
import { t } from "../i18n";
import IconPicker from "./IconPicker.vue";
import Segmented from "./Segmented.vue";
import HelpTip from "./HelpTip.vue";
import { useInspectorStore } from "../stores/inspector";

export type DockMode = "picture" | "icon" | "hidden";
const props = defineProps<{ mode: DockMode; icon?: string; disabled?: boolean }>();
const emit = defineEmits<{ change: [value: { mode: DockMode; icon?: string }] }>();
const insp = useInspectorStore();
// Icon chosen, no icon picked yet: the picker shows, the page keeps its picture until one is picked.
const choosing = ref(false);
const shown = computed<DockMode>(() => (choosing.value ? "icon" : props.mode));
const choices = computed(() => [["picture", t("editor.pages.dock_mode_picture")], ["icon", t("editor.pages.dock_mode_icon")],
  ["hidden", t("editor.pages.dock_mode_hidden")]] as const);
function pick(mode: DockMode) {
  if (mode === "icon") {
    if (props.icon) { choosing.value = false; emit("change", { mode, icon: props.icon }); return; }
    choosing.value = true; insp.iconPickerOpen = true; return;
  }
  choosing.value = false;
  emit("change", { mode });
}
function pickIcon(name: string) {
  choosing.value = false;
  if (name === "auto" || name === "none") emit("change", { mode: "picture" });
  else emit("change", { mode: "icon", icon: name });
}
</script>

<template>
  <div class="f dock-field">
    <span class="f-label"><span id="dock-field-label">{{ t("editor.pages.in_dock") }}</span><HelpTip :text="t('editor.pages.in_dock_hint')" /></span>
    <Segmented :choices="choices" :value="shown" :disabled="disabled" aria-labelledby="dock-field-label" @pick="pick" />
    <IconPicker v-if="shown === 'icon'" :selected="icon || 'auto'" automatic="" :auto-label="t('editor.pages.dock_picture')" @pick="pickIcon" />
    <small class="help">{{ t(`editor.pages.dock_hint_${shown}`) }}</small>
  </div>
</template>
