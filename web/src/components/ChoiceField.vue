<script setup lang="ts">
// One choice of a tile's setting (app 0.4.32). A few short ones stay in sight side by side; a longer list folds into
// a field with the current one, whose list opens under it. Either way, the choice the pointer rests on (or the
// keyboard is on) is drawn on the tile in the pages before it is picked, so what a setting does shows on the card
// instead of in words. `previewKey` is the tile option it previews; `sample` turns a choice into that option's value.
import { computed, onBeforeUnmount, ref } from "vue";
import { PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger } from "reka-ui";
import type { Tile } from "../types";
import Icon from "./ui/Icon.vue";
import { useInspectorStore } from "../stores/inspector";

const insp = useInspectorStore();

const props = defineProps<{
  choices: readonly (readonly [unknown, string])[]; value: unknown; disabled?: boolean; shapes?: Record<string, [number, number]>;
  tile?: Tile; previewKey?: string; sample?: (value: any) => unknown; id?: string; ariaLabel?: string;
}>();
const emit = defineEmits<{ (e: "pick", value: any): void }>();
// Side by side while they fit the column: three short words, or two longer ones.
const inline = computed(() => {
  const words = props.choices.reduce((sum, [, text]) => sum + text.length, 0);
  return props.choices.length <= 2 ? words <= 18 : props.choices.length <= 3 && words <= 12;
});
const open = ref(false);
const currentText = computed(() => props.choices.find(([key]) => String(key) === String(props.value))?.[1] ?? "");
function show(key: unknown) {
  if (!props.tile?.id || !props.previewKey || String(key) === String(props.value)) { hide(); return; }
  insp.optionPreview = { tileId: props.tile.id, key: props.previewKey, value: props.sample ? props.sample(key) : key };
}
function hide() {
  if (insp.optionPreview && insp.optionPreview.tileId === props.tile?.id && insp.optionPreview.key === props.previewKey) insp.optionPreview = null;
}
function pick(key: unknown) {
  hide();
  open.value = false;
  emit("pick", key);
}
function onOpen(value: boolean) { open.value = value; if (!value) hide(); }
onBeforeUnmount(hide);
const shapeStyle = (key: unknown) => {
  const shape = props.shapes?.[String(key)];
  return shape ? { width: `${4 + shape[0] * 6}px`, height: `${4 + shape[1] * 6}px` } : undefined;
};
</script>

<template>
  <div v-if="inline" class="seg choice" role="group" :aria-label="ariaLabel" @pointerleave="hide">
    <button v-for="[key, text] in choices" :key="String(key)" type="button" :disabled="disabled"
      :aria-pressed="String(key) === String(value) ? 'true' : 'false'" @pointerenter="show(key)" @focus="show(key)" @blur="hide" @click="pick(key)">
      <i v-if="shapes?.[String(key)]" class="seg-shape" :class="{ whole: String(key) === 'full' }" aria-hidden="true" :style="shapeStyle(key)"></i>{{ text }}
    </button>
  </div>
  <PopoverRoot v-else :open="open" @update:open="onOpen">
    <PopoverTrigger as-child>
      <button :id="id" type="button" class="choice-field" :disabled="disabled" :aria-label="ariaLabel ? `${ariaLabel}: ${currentText}` : undefined">
        <i v-if="shapes?.[String(value)]" class="seg-shape" :class="{ whole: String(value) === 'full' }" aria-hidden="true" :style="shapeStyle(value)"></i>
        <span class="choice-text">{{ currentText }}</span>
        <Icon name="chevron-down" />
      </button>
    </PopoverTrigger>
    <PopoverPortal>
      <PopoverContent class="ui-popover choice-list" align="start" :side-offset="4" :collision-padding="10" @pointerleave="hide">
        <button v-for="[key, text] in choices" :key="String(key)" type="button" class="ui-menu-item" :class="{ chosen: String(key) === String(value) }"
          @pointerenter="show(key)" @focus="show(key)" @click="pick(key)">
          <i v-if="shapes?.[String(key)]" class="seg-shape" :class="{ whole: String(key) === 'full' }" aria-hidden="true" :style="shapeStyle(key)"></i>
          <span class="choice-text">{{ text }}</span>
          <Icon v-if="String(key) === String(value)" name="check" class="ui-menu-end" />
        </button>
      </PopoverContent>
    </PopoverPortal>
  </PopoverRoot>
</template>
