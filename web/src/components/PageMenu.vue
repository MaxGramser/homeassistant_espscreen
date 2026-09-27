<script setup lang="ts">
// Everything you do to a page as a whole, behind its ··· (app 0.3.19): its settings, its top bar, making it Home, a
// copy, and removing it. The header of the page keeps only its name, its handle and this menu.
import { computed } from "vue";
import { t } from "../i18n";
import { duplicateEditorPage, openBar, openPage, pageReady, removePage, setHomePage, state } from "../store";
import Icon from "./ui/Icon.vue";
import UiMenu from "./ui/UiMenu.vue";
import UiMenuItem from "./ui/UiMenuItem.vue";
import UiMenuSeparator from "./ui/UiMenuSeparator.vue";

const props = defineProps<{ id: string }>();
const index = computed(() => state.document?.pages.findIndex((page) => page.id === props.id) ?? -1);
const page = computed(() => state.document?.pages[index.value]);
const home = computed(() => state.document?.homePageId === props.id);
// A full copy only when every tile on it is a page tile: another entity cannot stand on a screen twice.
const canCopy = computed(() => page.value?.tiles.every((tile) => tile.content.kind === "navigation"));
const tiles = computed(() => page.value?.tiles.length || 0);
</script>

<template>
  <UiMenu v-if="page" width="248px">
    <template #trigger>
      <button type="button" class="icon-btn page-menu" :aria-label="t('editor.pages.page_menu', { page: index + 1 })"><Icon name="dots-horizontal" /></button>
    </template>
    <UiMenuItem icon="cog-outline" @select="openPage(id)">{{ t("editor.pages.page_settings") }}</UiMenuItem>
    <UiMenuItem icon="page-layout-header" @select="openBar(0, index)">{{ t("editor.page.edit_bar") }}</UiMenuItem>
    <UiMenuSeparator />
    <UiMenuItem icon="home-outline" :disabled="home || !pageReady" @select="setHomePage(id)">{{ t(home ? "editor.pages.is_home" : "editor.pages.set_home") }}</UiMenuItem>
    <UiMenuItem v-if="canCopy" icon="content-duplicate" @select="duplicateEditorPage(id, false)">{{ t("editor.pages.duplicate") }}</UiMenuItem>
    <UiMenuItem icon="file-plus-outline" @select="duplicateEditorPage(id, true)">{{ t("editor.pages.empty_copy") }}</UiMenuItem>
    <UiMenuSeparator />
    <UiMenuItem class="page-remove" icon="delete-outline" danger :disabled="state.document!.pages.length < 2"
      :hint="tiles ? t('editor.pages.tiles_go', tiles) : undefined" @select="removePage(index)">{{ t("editor.page.remove") }}</UiMenuItem>
  </UiMenu>
</template>
