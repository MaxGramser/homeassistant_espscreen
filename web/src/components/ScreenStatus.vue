<script setup lang="ts">
// The one thing a screen's head says about its screen (docs/PAGES.md, "The head and the toolbar"): a pill with the
// worst that is going on (model/screen-status.ts headStatus), quiet while nothing is. Behind it, in a popover, what the
// head and the toolbar used to spread over four places: the connection, the count of pages and tiles, whether the
// changes are sent, and the memory the layout takes with the lines that explain it.
import { computed } from "vue";
import { PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger } from "reka-ui";
import { t } from "../i18n";
import { entriesOf } from "../model/layout";
import { noRoom } from "../model/memory";
import { headStatus } from "../model/screen-status";
import { useMemoryWords } from "../composables/useMemoryWords";
import { useDocumentStore } from "../stores/document";
import { useScreenStore } from "../stores/screen";
import type { Screen } from "../types";
import MemoryMeter from "./MemoryMeter.vue";
import Icon from "./ui/Icon.vue";

// `word`, `kind` and `detail`: the connection as the head works it out for the phone's line too (ScreenView.vue).
const props = defineProps<{ screen: Screen; away: boolean; word: string; kind: string; detail: string }>();
const scr = useScreenStore();
const doc = useDocumentStore();
const { lines } = useMemoryWords();

const status = computed(() => headStatus(props.screen, {
  away: props.away, restarting: !props.screen.online && !props.away, dirty: doc.dirty, saved: Boolean(doc.saved),
  memory: doc.memory, none: Boolean(doc.memory && noRoom(doc.memory)) }));
const count = computed(() => {
  const layout = doc.layout;
  return layout ? t("editor.layout.count", { tiles: layout.tiles.length, limit: doc.tileLimit }, doc.editorLayout.pageCount(entriesOf(layout), layout.pages)) : "";
});
const changes = computed(() => doc.dirty ? t("editor.common.unsaved")
  : doc.saved ? t(props.screen.virtual ? "editor.preview.saved" : "editor.screen_view.sent") : t("editor.screen_view.all_saved"));
</script>

<template>
  <PopoverRoot>
    <PopoverTrigger as-child>
      <button type="button" id="delivery" class="status-pill" :class="status.kind" :title="detail">
        <Icon v-if="status.kind === 'bad'" name="alert-circle-outline" /><Icon v-else-if="status.kind === 'good'" name="check" /><span v-else class="dot"></span>{{ status.text }}
      </button>
    </PopoverTrigger>
    <PopoverPortal>
      <PopoverContent class="ui-popover status-pop" align="end" :side-offset="8" :collision-padding="12">
        <div class="status-row"><span>{{ t("editor.feedback.issues.connection") }}</span><b :title="detail"><span class="dot" :class="kind"></span>{{ screen.virtual ? t("editor.preview.virtual") : word }}</b></div>
        <div v-if="count" class="status-row"><span>{{ t("editor.screen_view.tabs.layout") }}</span><b id="count">{{ count }}</b></div>
        <div class="status-row"><span>{{ t("editor.screen_view.status.changes") }}</span><b id="dirty" :class="{ warn: doc.dirty }">{{ changes }}</b></div>
        <div v-if="doc.memory || scr.memoryMeasuring" class="status-row"><span>{{ t("editor.memory.label") }}</span><MemoryMeter /></div>
        <p v-for="line in lines" :key="line" class="status-why">{{ line }}</p>
      </PopoverContent>
    </PopoverPortal>
  </PopoverRoot>
</template>
