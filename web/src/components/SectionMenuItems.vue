<script setup lang="ts">
// Everything you do to a section as a whole (docs/PAGES.md "Menus" and "Sections"), on the right mouse button on its
// panel or its band: its settings, naming it, and taking it away with or without its tiles.
import { t } from "../i18n";
import UiMenuItem from "./ui/UiMenuItem.vue";
import UiMenuSeparator from "./ui/UiMenuSeparator.vue";
import { removeSection } from "../editor/sections";
import { useInspectorStore } from "../stores/inspector";

defineProps<{ id: string }>();
const insp = useInspectorStore();
</script>

<template>
  <UiMenuItem icon="cog-outline" @select="insp.openSection(id)">{{ t("editor.sections.settings") }}</UiMenuItem>
  <UiMenuItem class="section-rename" icon="pencil-outline" @select="insp.renameSection(id)">{{ t("editor.naming.rename") }}</UiMenuItem>
  <UiMenuSeparator />
  <UiMenuItem icon="view-grid-outline" @select="removeSection(id)">{{ t("editor.sections.remove") }}</UiMenuItem>
  <UiMenuItem class="section-remove" icon="delete-outline" danger @select="removeSection(id, true)">{{ t("editor.sections.remove_with_tiles") }}</UiMenuItem>
</template>
