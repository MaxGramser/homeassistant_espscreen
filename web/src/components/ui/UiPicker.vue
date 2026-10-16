<script setup lang="ts">
// A thing to pick from a list that can run long (Reka UI Popover + Listbox with its filter): a house with forty media
// players doesn't fit a plain menu. The button is the slot; it opens a search field with the list under it, which
// scrolls inside the window. Typing narrows it by name or by the hint (an area), the arrows walk it, Enter or a click picks.
// `remote`: the list comes from elsewhere for what is typed (a plugin's search, plugin API 0.12): the picker says what is
// typed (`search`) and shows the items it gets as they are, with `busy` while they are on their way.
import { computed, ref, watch } from "vue";
import { ListboxContent, ListboxFilter, ListboxItem, ListboxRoot, PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger } from "reka-ui";
import { matchesWords, queryWords } from "../../model/search";
import Icon from "./Icon.vue";

export interface PickerItem { id: string; name: string; hint?: string }
const props = withDefaults(defineProps<{ items: readonly PickerItem[]; placeholder?: string; empty?: string; align?: "start" | "center" | "end"; width?: string;
  remote?: boolean; busy?: boolean; id?: string }>(), { align: "start", width: "280px" });
const emit = defineEmits<{ pick: [id: string]; search: [query: string] }>();
const open = ref(false);
const query = ref("");
// The editor's one search: every typed word somewhere in the name, the hint or the id.
const shown = computed(() => {
  if (props.remote) return props.items;
  const words = queryWords(query.value);
  return words.length ? props.items.filter((item) => matchesWords(words, item.name, item.hint, item.id)) : props.items;
});
watch(query, (value) => { if (props.remote) emit("search", value); });
function pick(id: unknown) {
  if (typeof id !== "string" || !id) return;
  emit("pick", id);
  toggle(false);
}
function toggle(value: boolean) {
  open.value = value;
  if (!value) query.value = "";
}
</script>

<template>
  <PopoverRoot :open="open" @update:open="toggle">
    <PopoverTrigger as-child><slot name="trigger" /></PopoverTrigger>
    <PopoverPortal>
      <PopoverContent class="ui-popover ui-picker" :style="{ width }" :align="align" :side-offset="6" :collision-padding="8">
        <ListboxRoot highlight-on-hover @update:model-value="pick">
          <label class="ui-picker-search">
            <Icon name="magnify" />
            <ListboxFilter :id="id" v-model="query" auto-focus :placeholder="placeholder" :aria-label="placeholder" />
            <span v-if="busy" class="spin small" aria-hidden="true"></span>
          </label>
          <ListboxContent class="ui-picker-list">
            <ListboxItem v-for="item in shown" :key="item.id" :value="item.id" class="ui-menu-item">
              <span class="ui-menu-text">{{ item.name }}</span>
              <small v-if="item.hint" class="ui-menu-end">{{ item.hint }}</small>
            </ListboxItem>
            <div v-if="!shown.length && !busy" class="ui-picker-empty">{{ empty }}</div>
          </ListboxContent>
        </ListboxRoot>
      </PopoverContent>
    </PopoverPortal>
  </PopoverRoot>
</template>
