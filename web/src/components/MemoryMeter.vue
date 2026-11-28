<script setup lang="ts">
// How much of the screen's memory for tiles the layout takes (firmware 0.34.0+, model/memory.ts): a thin bar and a
// share, the kilobytes in its title. Quiet until it matters: the accent while there is room, amber from 80 %, red when
// it is full or over. A screen with no room to speak of says so in words rather than a share past ten times the room,
// and one that is still measuring (firmware 0.51.0) says that. Its words are useMemoryWords.
import { computed } from "vue";
import { t } from "../i18n";
import { useMemoryWords } from "../composables/useMemoryWords";
import { useScreenStore } from "../stores/screen";
import { useDocumentStore } from "../stores/document";

const scr = useScreenStore();
const doc = useDocumentStore();
const { percent, text, lines } = useMemoryWords();
const title = computed(() => lines.value.join("\n"));
</script>

<template>
  <span v-if="doc.memory || scr.memoryMeasuring" id="memory" class="memory-meter" :class="doc.memory ? doc.memory.level : 'measuring'" :title="title" role="meter"
    :aria-label="t('editor.memory.label')" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="doc.memory ? percent : undefined" :aria-valuetext="title || text">
    <span class="memory-bar" aria-hidden="true"><i :style="{ width: (doc.memory ? Math.min(100, percent) : 0) + '%' }"></i></span>
    <span class="memory-text">{{ text }}</span>
    <span v-if="scr.screenMemory?.short" class="memory-short" aria-hidden="true"></span>
  </span>
</template>
