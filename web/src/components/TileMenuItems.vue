<script setup lang="ts">
// What you do to a tile as a whole: the items behind the ··· of its inspector, and the same on the right mouse button on
// its card (docs/PAGES.md, "Menus"). First what changes the tile, then where it stands, then the clipboard, Remove last.
// The settings themselves stay in the inspector; the size is the card's handles (app 0.4.32).
import { computed } from "vue";
import { t } from "../i18n";
import UiMenuItem from "./ui/UiMenuItem.vue";
import UiMenuSeparator from "./ui/UiMenuSeparator.vue";
import UiMenuSub from "./ui/UiMenuSub.vue";
import { copyChosen, cutChosen, shortcut } from "../editor/clipboard";
import { moveTileAndFollow, otherPages, removeTile } from "../editor/tiles";
import { usePluginsStore } from "../stores/plugins";
import { useDocumentStore } from "../stores/document";
import { useInspectorStore } from "../stores/inspector";
import type { Tile } from "../types";

const plugins = usePluginsStore();
const doc = useDocumentStore();
const insp = useInspectorStore();
const props = defineProps<{ tile: Tile }>();
// A screen's own card and a plugin's tile have no entity of Home Assistant to read or change.
const entity = computed(() => !props.tile.entity.startsWith("screen.") && !plugins.pluginTileOf(props.tile.entity));
const pages = computed(() => otherPages(props.tile));
// A clock's key is copied and cut with its clock.
const key = computed(() => props.tile.in !== undefined);
// Changing the entity happens in this tile's inspector, so the menu of a card that isn't open opens it first.
function change() { if (!doc.isSelected(props.tile)) insp.openTile(props.tile); insp.entityPickerOpen = true; }
// This tile's own data: its entity may be on several tiles (firmware 0.16.0+).
function inspect() { insp.inspector = { kind: "inspect", entity: props.tile.entity, slot: props.tile.slot, key: props.tile.key }; }
</script>

<template>
  <UiMenuItem class="tile-rename" icon="pencil-outline" @select="insp.renameTile(tile)">{{ t("editor.naming.rename") }}</UiMenuItem>
  <UiMenuItem v-if="entity" icon="swap-horizontal" @select="change">{{ t("editor.broken.change") }}</UiMenuItem>
  <UiMenuItem v-if="entity" icon="database-search-outline" @select="inspect">{{ t("editor.common.read_current_data") }}</UiMenuItem>
  <template v-if="pages.length">
    <UiMenuSeparator />
    <UiMenuSub class="tile-move" icon="arrow-right" :label="t('editor.menu.move_to')">
      <UiMenuItem v-for="page in pages" :key="page.index" icon="view-column-outline" @select="moveTileAndFollow(tile, page.index)">{{ page.name }}</UiMenuItem>
    </UiMenuSub>
  </template>
  <template v-if="!key">
    <UiMenuSeparator />
    <UiMenuItem class="tile-copy" icon="content-copy" :hint="shortcut('C')" @select="copyChosen">{{ t("editor.selection.copy") }}</UiMenuItem>
    <UiMenuItem class="tile-cut" icon="content-cut" :hint="shortcut('X')" @select="cutChosen">{{ t("editor.menu.cut") }}</UiMenuItem>
  </template>
  <UiMenuSeparator />
  <UiMenuItem class="tile-remove" icon="delete-outline" danger hint="⌫" @select="removeTile(tile)">{{ t("editor.common.remove") }}</UiMenuItem>
</template>
