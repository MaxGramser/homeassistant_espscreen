<script setup lang="ts">
// The inspector: a column of its own on the right (app 0.4.32), there only while something is selected, so it never
// covers the pages or the library. Its content follows what is selected. It glides open and shut (app 0.4.32): the
// column grows while its content keeps its own width, so the pages beside it make room once instead of reflowing.
import { computed } from "vue";
import TileInspector from "./TileInspector.vue";
import TopbarInspector from "./TopbarInspector.vue";
import TopbarAdd from "./TopbarAdd.vue";
import SaverItemInspector from "./SaverItemInspector.vue";
import SaverAdd from "./SaverAdd.vue";
import SaverInspector from "./SaverInspector.vue";
import InspectPanel from "./InspectPanel.vue";
import PageInspector from "./PageInspector.vue";
import { useUiStore } from "../stores/ui";
import { useDocumentStore } from "../stores/document";
import { useInspectorStore } from "../stores/inspector";

const ui = useUiStore();
const doc = useDocumentStore();
const insp = useInspectorStore();

const open = computed(() => Boolean(insp.inspector && (insp.inspector.kind !== "tile" || doc.currentTile)));
</script>

<template>
  <!-- On a phone (app 0.4.40) the inspector is a sheet from the bottom over a dimmed page; a tap beside it closes it. -->
  <Transition name="dim"><div v-if="open && ui.phone" class="sheet-dim" @click="insp.closeInspector"></div></Transition>
  <Transition name="drawer">
  <aside v-if="open" class="drawer open" id="tile-sheet" @click.stop>
    <div v-if="insp.inspector" class="drawer-inner">
      <!-- Keyed by the tile: another tile's settings start as a tile's settings start, with More settings and every chooser closed. -->
      <TileInspector v-if="insp.inspector.kind === 'tile' && doc.currentTile" :key="doc.currentTile.id" :tile="doc.currentTile" />
      <TopbarInspector v-else-if="insp.inspector.kind === 'bar'" :index="insp.inspector.index" />
      <TopbarAdd v-else-if="insp.inspector.kind === 'bar-add'" />
      <SaverItemInspector v-else-if="insp.inspector.kind === 'saver-item'" :index="insp.inspector.index" />
      <SaverAdd v-else-if="insp.inspector.kind === 'saver-add'" />
      <SaverInspector v-else-if="insp.inspector.kind === 'saver'" :step="insp.inspector.step" />
      <PageInspector v-else-if="insp.inspector.kind === 'page'" :id="insp.inspector.id" />
      <InspectPanel v-else-if="insp.inspector.kind === 'inspect'" :entity="insp.inspector.entity" :slot="insp.inspector.slot" :tile-key="insp.inspector.key" />
    </div>
  </aside>
  </Transition>
</template>
