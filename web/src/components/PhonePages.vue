<script setup lang="ts">
// The pages of a screen on a phone (app 0.4.40), in a sheet from the bottom: a tap goes to a page, the handle moves it,
// its ··· holds what the page's own menu holds on a wider page. The sheet goes once something else opens.
import { computed, ref, watch } from "vue";
import { t } from "../i18n";
import { titleOf } from "../model/pages";
import { editorLayout, movePage, state, tileLimit } from "../store";
import PageMenu from "./PageMenu.vue";
import MemoryMeter from "./MemoryMeter.vue";
import Icon from "./ui/Icon.vue";
import { useUiStore } from "../stores/ui";

const ui = useUiStore();

const emit = defineEmits<{ add: [] }>();
const list = computed(() => state.document?.pages || []);
const canAdd = computed(() => list.value.length < editorLayout.grid.pages);
const tiles = computed(() => list.value.reduce((n, page) => n + page.tiles.length, 0));
function close() { ui.pagesSheet = false; }
function choose(id: string) { state.selectedPageId = id; state.insertAt = -1; close(); }
watch(() => state.inspector, (open) => { if (open) close(); });

// Moving a page by its handle: the row follows the finger, and the page lands where the finger is let go.
const carried = ref<{ from: number; to: number; dy: number; y: number; row: number } | null>(null);
function grab(event: PointerEvent, from: number) {
  const row = (event.currentTarget as HTMLElement).closest("li")?.getBoundingClientRect().height || 56;
  carried.value = { from, to: from, dy: 0, y: event.clientY, row };
  (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
}
function carry(event: PointerEvent) {
  const c = carried.value;
  if (!c) return;
  c.dy = event.clientY - c.y;
  c.to = Math.max(0, Math.min(list.value.length - 1, c.from + Math.round(c.dy / c.row)));
}
function drop() {
  const c = carried.value;
  carried.value = null;
  if (c && c.to !== c.from) movePage(c.from, c.to);
}
const shift = (index: number) => {
  const c = carried.value;
  if (!c) return undefined;
  if (index === c.from) return { transform: `translateY(${c.dy}px)`, zIndex: 2, boxShadow: "var(--shadow)" };
  if (c.from < index && index <= c.to) return { transform: `translateY(${-c.row}px)` };
  if (c.to <= index && index < c.from) return { transform: `translateY(${c.row}px)` };
  return undefined;
};
</script>

<template>
  <div class="sheet-dim" @click="close"></div>
  <section class="phone-sheet phone-pages" role="dialog" :aria-label="t('editor.phone.pages')">
    <span class="sheet-grab" aria-hidden="true"></span>
    <header class="sheet-head">
      <span class="sheet-title"><b>{{ t("editor.phone.pages") }}</b><small>{{ t("editor.layout.count", { tiles, limit: tileLimit }, list.length) }} <MemoryMeter /></small></span>
      <button type="button" class="icon-btn sheet-close" :aria-label="t('editor.common.close')" @click="close"><Icon name="close" /></button>
    </header>
    <ol class="sheet-list">
      <li v-for="(page, index) in list" :key="page.id" :class="{ on: page.id === state.selectedPageId, carried: carried?.from === index }" :style="shift(index)">
        <button type="button" class="sheet-row" @click="choose(page.id)">
          <span class="num">{{ index + 1 }}</span>
          <span class="tx">
            <b>{{ titleOf(state.document!, page) || t("editor.page.label", { page: index + 1 }) }}<span v-if="page.id === state.document!.homePageId" class="home-tag">{{ t("editor.pages.home_chip") }}</span></b>
            <small>{{ t("editor.phone.page_tiles", page.tiles.length) }}</small>
          </span>
        </button>
        <PageMenu :id="page.id" />
        <button v-if="list.length > 1" type="button" class="icon-btn handle" :aria-label="t('editor.page.move_aria', { page: index + 1 })"
          @pointerdown.prevent="grab($event, index)" @pointermove="carry" @pointerup="drop" @pointercancel="carried = null"><Icon name="drag" /></button>
      </li>
    </ol>
    <button type="button" class="sheet-add" :disabled="!canAdd" @click="emit('add')"><Icon name="plus" />{{ t("editor.layout.add_page") }}</button>
  </section>
</template>
