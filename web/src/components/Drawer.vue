<script setup lang="ts">
// The inspector: a column of its own on the right (app 0.4.32), there only while something is selected, so it never
// covers the pages or the library. Its content follows what is selected. It glides open and shut (app 0.4.32): the
// column grows while its content keeps its own width, so the pages beside it make room once instead of reflowing.
import { computed } from "vue";
import { closeInspector, currentTile, phone, state } from "../store";
import TileInspector from "./TileInspector.vue";
import TopbarInspector from "./TopbarInspector.vue";
import TopbarAdd from "./TopbarAdd.vue";
import SaverItemInspector from "./SaverItemInspector.vue";
import SaverAdd from "./SaverAdd.vue";
import SaverInspector from "./SaverInspector.vue";
import InspectPanel from "./InspectPanel.vue";
import PageInspector from "./PageInspector.vue";

const open = computed(() => Boolean(state.inspector && (state.inspector.kind !== "tile" || currentTile.value)));
</script>

<template>
  <!-- On a phone (app 0.4.40) the inspector is a sheet from the bottom over a dimmed page; a tap beside it closes it. -->
  <Transition name="dim"><div v-if="open && phone" class="sheet-dim" @click="closeInspector"></div></Transition>
  <Transition name="drawer">
  <aside v-if="open" class="drawer open" id="tile-sheet" @click.stop>
    <div v-if="state.inspector" class="drawer-inner">
      <TileInspector v-if="state.inspector.kind === 'tile' && currentTile" :tile="currentTile" />
      <TopbarInspector v-else-if="state.inspector.kind === 'bar'" :index="state.inspector.index" />
      <TopbarAdd v-else-if="state.inspector.kind === 'bar-add'" />
      <SaverItemInspector v-else-if="state.inspector.kind === 'saver-item'" :index="state.inspector.index" />
      <SaverAdd v-else-if="state.inspector.kind === 'saver-add'" />
      <SaverInspector v-else-if="state.inspector.kind === 'saver'" :step="state.inspector.step" />
      <PageInspector v-else-if="state.inspector.kind === 'page'" :id="state.inspector.id" />
      <InspectPanel v-else-if="state.inspector.kind === 'inspect'" :entity="state.inspector.entity" :slot="state.inspector.slot" :tile-key="state.inspector.key" />
    </div>
  </aside>
  </Transition>
</template>
