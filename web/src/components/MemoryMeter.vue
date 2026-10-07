<script setup lang="ts">
// How much of the screen's memory for tiles the layout takes (firmware 0.34.0+, model/memory.ts): a thin bar and a
// share beside the tile count, the kilobytes in its title. Quiet until it matters: the accent while there is room, amber
// from 80 %, red when it is full or over. A screen with no room to speak of says so in words rather than a share past
// ten times the room, and one that is still measuring (firmware 0.51.0) says that.
import { computed } from "vue";
import { t } from "../i18n";
import { kilobytes, noRoom } from "../model/memory";
import { memory, memoryMeasuring, screenMemory } from "../store";

const percent = computed(() => (memory.value ? Math.min(999, Math.round(memory.value.share * 100)) : 0));
const none = computed(() => !!memory.value && noRoom(memory.value));
const text = computed(() => (memoryMeasuring.value ? t("editor.memory.measuring") : none.value ? t("editor.memory.none") : t("editor.memory.share", { n: percent.value })));
const title = computed(() => {
  const use = memory.value, said = screenMemory.value;
  if (!said) return "";
  if (memoryMeasuring.value) return t("editor.memory.measuring_title");
  if (!use) return "";
  const lines = [none.value ? t("editor.memory.none_title") : t("editor.memory.title", { need: kilobytes(use.need, true), room: kilobytes(use.room) })];
  if (use.level === "over" && !none.value) lines.push(t("editor.memory.over"));
  if (said.short) lines.push(t("editor.memory.short"));
  if (said.live === false) lines.push(t("editor.memory.last_known"));
  return lines.join("\n");
});
</script>

<template>
  <span v-if="memory || memoryMeasuring" id="memory" class="memory-meter" :class="memory ? memory.level : 'measuring'" :title="title" role="meter"
    :aria-label="t('editor.memory.label')" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="memory ? percent : undefined" :aria-valuetext="title || text">
    <span class="memory-bar" aria-hidden="true"><i :style="{ width: (memory ? Math.min(100, percent) : 0) + '%' }"></i></span>
    <span class="memory-text">{{ text }}</span>
    <span v-if="screenMemory?.short" class="memory-short" aria-hidden="true"></span>
  </span>
</template>
