<script setup lang="ts">
// The inspector slides in from the right and leaves the mockup visible; its content follows what is selected.
import { computed } from "vue";
import { currentTile, state } from "../store";
import TileInspector from "./TileInspector.vue";
import TopbarInspector from "./TopbarInspector.vue";
import TopbarAdd from "./TopbarAdd.vue";
import InspectPanel from "./InspectPanel.vue";
import PageInspector from "./PageInspector.vue";

const open = computed(() => Boolean(state.inspector && (state.inspector.kind !== "tile" || currentTile.value)));
</script>

<template>
  <aside class="drawer" id="tile-sheet" :class="{ open }" :aria-hidden="open ? 'false' : 'true'" @click.stop>
    <template v-if="state.inspector">
      <TileInspector v-if="state.inspector.kind === 'tile' && currentTile" :tile="currentTile" />
      <TopbarInspector v-else-if="state.inspector.kind === 'bar'" :index="state.inspector.index" />
      <TopbarAdd v-else-if="state.inspector.kind === 'bar-add'" />
      <PageInspector v-else-if="state.inspector.kind === 'page'" :id="state.inspector.id" />
      <InspectPanel v-else-if="state.inspector.kind === 'inspect'" :entity="state.inspector.entity" :slot="state.inspector.slot" :tile-key="state.inspector.key" />
    </template>
  </aside>
</template>
