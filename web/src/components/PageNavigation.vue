<script setup lang="ts">
import { computed } from 'vue';
import { t } from '../i18n';
import { navigationFooter, pagination } from '../model/pages';
import { navigationSettings, screenText, state } from '../store';
const props = defineProps<{ pageId: string; interactive?: boolean; canGoBack?: boolean }>();
const emit = defineEmits<{ navigate: [direction: 'previous' | 'next' | 'back'] }>();
const sequence = computed(() => state.document ? pagination(state.document) : []);
const index = computed(() => sequence.value.indexOf(props.pageId));
const visible = computed(() => state.document && navigationFooter(state.document, navigationSettings()));
const detail = computed(() => state.document?.pages.find((page) => page.id === props.pageId)?.navigation.excludeFromPagination);
const sequential = computed(() => !detail.value && navigationSettings().pageButtons && sequence.value.length > 1);
defineExpose({ visible });
</script>
<template>
  <div v-if="visible" class="page-navigation" :aria-label="t('editor.pages.navigation')">
    <button v-if="detail" type="button" class="page-back" :disabled="!interactive || canGoBack === false" @click="emit('navigate', 'back')">‹ <span>{{ screenText('screen.navigation.back') }}</span></button>
    <template v-else-if="sequential">
      <button type="button" :disabled="!interactive || index === 0" :aria-label="t('editor.pages.previous')" @click="emit('navigate', 'previous')">‹</button>
      <span>{{ index + 1 }} / {{ sequence.length }}</span>
      <button type="button" :disabled="!interactive || index === sequence.length - 1" :aria-label="t('editor.pages.next')" @click="emit('navigate', 'next')">›</button>
    </template>
  </div>
</template>
<style scoped>
.page-navigation { display: flex; align-items: center; justify-content: space-between; height: 100%; min-height: 0; color: #46525e; font-size: 11px; }
/* Its chevrons at most as high as the page bar of the glass (--frame-bar, DevicePage): on a 10-inch it is 15 px. */
button { border: 0; background: transparent; color: inherit; font-size: min(24px, var(--frame-bar, 24px)); width: 40px; line-height: 1; }
button:disabled { opacity: .3; cursor: default; }
.page-back { display: flex; align-items: center; gap: 6px; width: 50%; text-align: left; }
.page-back span { font-size: 11px; }
.page-back:disabled { opacity: 1; }
</style>
