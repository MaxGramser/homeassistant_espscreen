<script setup lang="ts" generic="Id extends string">
// The list of a page's parts (model/parts.ts, docs/PAGES.md "Pages of parts"): its rows in a few cards, the way Home
// Assistant's Settings groups them. A row opens its part (`open`); the `control` slot puts one control of its own on a
// row (a switch for what people change most), and is handed the row.
import { cardsOf, type PartRow } from "../../model/parts";
import PartLink from "./PartLink.vue";

defineProps<{ rows: PartRow<Id>[]; id?: string; idPrefix: string }>();
const emit = defineEmits<{ open: [id: Id] }>();
defineSlots<{ control?: (props: { row: PartRow<Id> }) => unknown }>();
</script>

<template>
  <div :id="id" class="set-cards">
    <div v-for="(card, i) in cardsOf(rows)" :key="i" class="set-list">
      <PartLink v-for="row in card" :key="row.id" :id="`${idPrefix}-${row.id}`" :icon="row.icon" :tone="row.tone" :title="row.title"
        :summary="row.summary" :badge="row.badge" @open="emit('open', row.id)">
        <template v-if="$slots.control" #default><slot name="control" :row="row" /></template>
      </PartLink>
    </div>
  </div>
</template>
