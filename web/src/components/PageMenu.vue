<script setup lang="ts">
// The page's ···: its items are PageMenuItems, the same as the right mouse button on the page. The header of the page
// keeps only its name, its handle and this menu.
import { computed } from "vue";
import { t } from "../i18n";
import Icon from "./ui/Icon.vue";
import UiMenu from "./ui/UiMenu.vue";
import PageMenuItems from "./PageMenuItems.vue";
import { useDocumentStore } from "../stores/document";

const doc = useDocumentStore();
const props = defineProps<{ id: string }>();
const index = computed(() => doc.document?.pages.findIndex((page) => page.id === props.id) ?? -1);
</script>

<template>
  <UiMenu v-if="index >= 0" width="248px">
    <template #trigger>
      <button type="button" class="icon-btn page-menu" :aria-label="t('editor.pages.page_menu', { page: index + 1 })"><Icon name="dots-horizontal" /></button>
    </template>
    <PageMenuItems :id="id" />
  </UiMenu>
</template>
