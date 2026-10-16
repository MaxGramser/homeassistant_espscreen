<script setup lang="ts">
// The top bar in small at the head of its inspector (app 0.4.89): the title and Home button on the left, every item as
// the screen shows it, and a place to add one. It is the way through the bar: a part tapped shows its settings under it
// (Reka Tabs, so the arrow keys walk the parts and Home and End jump to the ends), and an item pressed and moved left or
// right takes another place; the right mouse button (a finger held still) offers to take it off, and so does pulling it
// off the strip and letting it go there, as an icon out of a menu bar. An item that is hidden right now stands dashed, one the glass leaves out for want of room
// dashed in orange, as on the mockup. Items that don't fit go on the next line, in the screen's order; many (a large board
// takes up to sixteen) stand under the title in lines of their own. The screensaver's clock row is the same strip (app
// 0.4.89): its time and temperature on the left, its entities as it draws them (`face`), white on black (`saver`).
import { computed } from "vue";
import { TabsList, TabsRoot, TabsTrigger } from "reka-ui";
import { t } from "../i18n";
import { glyph, itemKey } from "../model/topbar";
import type { HeaderItem } from "../types";
import Icon from "./ui/Icon.vue";
import UiContextMenu from "./ui/UiContextMenu.vue";
import UiMenuItem from "./ui/UiMenuItem.vue";
import TesseraMark from "./TesseraMark.vue";
import { useTopbarStore } from "../stores/topbar";

const topbar = useTopbarStore();
export type StripFace = { glyph: string; text: string; color?: string; shown: boolean };
const props = defineProps<{ items: readonly HeaderItem[]; selected: string; overflow: ReadonlySet<number>; title: string; home: boolean; full: boolean; max: number; dragging: number;
  /** The dragged item is pulled off the strip: let go, it is taken off. */
  leaving?: boolean;
  face?: (item: HeaderItem) => StripFace; label?: string; leftTitle?: string; addTitle?: string; addId?: string; saver?: boolean }>();
const emit = defineEmits<{ select: [value: string]; press: [event: PointerEvent, index: number]; remove: [index: number] }>();
const wrap = computed(() => props.items.length > 6);
// What a part shows: its glyph and, unless it is an icon alone, its words.
function face(item: HeaderItem): StripFace {
  if (props.face) return props.face(item);
  const view = topbar.topbarView(item);
  const code = topbar.topbarGlyph(item);
  const iconOnly = view.analog || item.content === "icon";
  return { glyph: code ? glyph(code) : "", text: iconOnly ? "" : view.text || "", color: view.color || undefined, shown: view.shown };
}
// A press chooses the item at once and may start a drag: the drag holds the mouse's own press back, which Reka Tabs
// would choose on.
function press(e: PointerEvent, index: number) {
  if (e.button === 0) emit("select", String(index));
  emit("press", e, index);
}
const justAdded = (item: HeaderItem) => topbar.topbarAdded?.key === itemKey(item) && Date.now() - topbar.topbarAdded.time < 1200;
</script>

<template>
  <TabsRoot :model-value="selected" activation-mode="automatic" @update:model-value="(value) => emit('select', String(value))">
    <TabsList class="bar-strip" :class="{ wrap, saver }" :aria-label="label || t('editor.topbar.title')">
      <TabsTrigger value="left" class="strip-slot strip-left" :title="leftTitle || t('editor.topbar.strip.left_title')">
        <TesseraMark v-if="home" class="strip-home" />
        <span class="strip-title">{{ title }}</span>
        <small v-if="wrap" class="strip-count">{{ t('editor.topbar.items', { used: items.length }, max) }}</small>
      </TabsTrigger>
      <UiContextMenu v-for="(item, i) in items" :key="itemKey(item) + i" width="180px" :disabled="dragging >= 0">
        <TabsTrigger :value="String(i)" class="strip-slot strip-item" :data-index="i"
          :class="{ 'is-hidden': !face(item).shown, 'is-overflow': overflow.has(i), 'just-added': justAdded(item), dragging: dragging === i, leaving: dragging === i && leaving }"
          :title="topbar.topbarLabel(item)" :aria-label="t('editor.topbar.item_label', { name: topbar.topbarLabel(item), slot: i + 1 })"
          @pointerdown="press($event, i)">
          <span v-if="face(item).glyph" class="mdi" :style="face(item).color ? { color: face(item).color } : undefined">{{ face(item).glyph }}</span>
          <span v-if="face(item).text && face(item).shown" class="strip-text">{{ face(item).text }}</span>
        </TabsTrigger>
        <template #menu>
          <UiMenuItem icon="delete-outline" danger @select="emit('remove', i)">{{ t("editor.common.remove") }}</UiMenuItem>
        </template>
      </UiContextMenu>
      <TabsTrigger value="add" class="strip-slot strip-add" :id="addId || 'topbar-add'" :disabled="full"
        :title="full ? t('editor.topbar.max', max) : addTitle || t('editor.topbar.add_title')" :aria-label="addTitle || t('editor.topbar.add_title')"><Icon name="plus" /></TabsTrigger>
    </TabsList>
  </TabsRoot>
</template>
