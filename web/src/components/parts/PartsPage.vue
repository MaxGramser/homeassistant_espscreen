<script setup lang="ts" generic="Id extends string">
// A whole page of parts (model/parts.ts, docs/PAGES.md "Pages of parts"): the app's Settings and Events. Closed, it shows
// its eyebrow, title and intro over the list of its parts; with a part open (`open`, the part the address names), the
// way back to the list and the part's title, and the part itself in the default slot. The key on the right leaves the
// page. A screen's Settings tab lives inside the screen's tabs and uses PartList and PartHead itself.
import { computed } from "vue";
import type { PartRow } from "../../model/parts";
import PartHead from "./PartHead.vue";
import PartList from "./PartList.vue";

const props = defineProps<{
  id: string; eyebrow: string; title: string; intro?: string; closeLabel: string;
  rows: PartRow<Id>[]; open: Id | null; wide?: boolean;
  // The ids its parts go by (tests and links know them): the close key, the list, each row's prefix, the title.
  closeId?: string; listId?: string; rowPrefix?: string; titleId?: string;
}>();
const emit = defineEmits<{ open: [id: Id | null]; close: [] }>();
defineSlots<{ default?: (props: { part: PartRow<Id> }) => unknown; control?: (props: { row: PartRow<Id> }) => unknown }>();
const part = computed(() => props.rows.find((row) => row.id === props.open) || null);
</script>

<template>
  <div class="panel parts-page" :class="{ wide }" :id="id">
    <div class="panel-head">
      <div class="tx">
        <PartHead v-if="part" :back="title" :title="part.title" as="h1" @back="emit('open', null)" />
        <template v-else>
          <span class="eyebrow">{{ eyebrow }}</span>
          <h1 :id="titleId || `${id}-title`">{{ title }}</h1>
          <p v-if="intro">{{ intro }}</p>
        </template>
      </div>
      <button type="button" class="btn quiet" :id="closeId || `${id}-close`" @click="emit('close')">{{ closeLabel }}</button>
    </div>

    <div v-if="!part" class="set-column">
      <PartList :id="listId || `${id}-parts`" :id-prefix="rowPrefix || `${id}-part`" :rows="rows" @open="(row) => emit('open', row)">
        <template v-if="$slots.control" #control="{ row }"><slot name="control" :row="row" /></template>
      </PartList>
    </div>
    <div v-else class="set-column">
      <slot :part="part" />
    </div>
  </div>
</template>
