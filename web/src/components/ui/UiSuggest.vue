<script setup lang="ts">
// A text field with the values it usually takes in a short list under it (GitHub #117): a remote's commands, read from
// Home Assistant and the library it pins. Typing narrows the list, the arrows and Enter pick, and anything else typed
// still goes, so a learned code or a hub's own name keeps working. The list stays in the panel (no popover), as the
// library's results do, and only while the field has the cursor.
import { computed, ref, useId } from "vue";
import { useListNavigation } from "../../composables/useListNavigation";
import { rankedValues } from "../../model/search";

const props = defineProps<{ modelValue: string; suggestions: readonly string[]; placeholder?: string; ariaLabel?: string; max?: number }>();
const emit = defineEmits<{ "update:modelValue": [value: string]; pick: [value: string]; focus: []; blur: [] }>();
const open = ref(false);
const id = `suggest-${useId()}`;
// What is typed narrows the list from the start of a word first, then anywhere: "vol" finds VOLUME_UP before
// MEDIA_VOLUME; case and _ / - / space don't matter, as the integrations that fold case take it either way.
const shown = computed(() => rankedValues(props.suggestions, props.modelValue || "").slice(0, props.max ?? 60));
// The list hides once the field holds exactly one of its values: there is nothing left to choose.
const visible = computed(() => open.value && shown.value.length > 0 && !(shown.value.length === 1 && shown.value[0] === props.modelValue));
function pick(value: string) {
  emit("pick", value);
  open.value = false;
}
// The arrows walk the list round, the one in focus scrolled into view; Enter picks it; what is typed starts at the first.
const { active, onKey: walk } = useListNavigation(shown, {
  wrap: true, onPick: pick, resetOn: () => props.modelValue,
  onMove: (index) => document.getElementById(`${id}-${index}`)?.scrollIntoView({ block: "nearest" }),
});
function onKey(event: KeyboardEvent) {
  if (!visible.value) {
    if (event.key === "ArrowDown") { open.value = true; event.preventDefault(); }
    return;
  }
  if (walk(event)) return;
  if (event.key === "Escape") {
    open.value = false;
    event.stopPropagation();
  }
}
</script>

<template>
  <div class="ui-suggest">
    <input type="text" role="combobox" autocomplete="off" spellcheck="false" :aria-label="ariaLabel" :aria-expanded="visible ? 'true' : 'false'"
      :aria-controls="id" :aria-activedescendant="visible ? `${id}-${active}` : undefined" :value="modelValue" :placeholder="placeholder"
      @input="emit('update:modelValue', ($event.target as HTMLInputElement).value); open = true" @focus="open = true; emit('focus')"
      @blur="open = false; emit('blur')" @keydown="onKey" />
    <div v-show="visible" :id="id" class="ui-suggest-list" role="listbox" :aria-label="ariaLabel">
      <!-- mousedown.prevent: the field keeps the cursor, so its blur doesn't close the list before the click lands. -->
      <div v-for="(value, i) in shown" :id="`${id}-${i}`" :key="value" class="ui-menu-item" role="option" :aria-selected="i === active ? 'true' : 'false'"
        :data-highlighted="i === active ? '' : undefined" @mousedown.prevent @mouseenter="active = i" @click="pick(value)">{{ value }}</div>
    </div>
  </div>
</template>
