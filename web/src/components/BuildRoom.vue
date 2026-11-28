<script setup lang="ts">
// Before a build: whether this Home Assistant has the memory a build needs (the add-on's build_room, build_memory.py).
// Without a build server and with less free than the heaviest file takes, a build may fail or slow Home Assistant down;
// this says so where builds are started, with the two ways round it. Nothing at all when there is room.
import { computed } from "vue";
import { t } from "../i18n";
import Icon from "./ui/Icon.vue";
import { useInventoryStore } from "../stores/inventory";
import { useUiStore } from "../stores/ui";

const inv = useInventoryStore();
const ui = useUiStore();
const room = computed(() => inv.inventory.build_room);
const gb = (mb: number | null | undefined) => (mb == null ? "?" : (mb / 1024).toFixed(1));
</script>

<template>
  <div v-if="room?.tight" class="notice warn build-room" id="build-room" role="note">
    <Icon name="alert-circle-outline" />
    <span class="notice-text">
      <strong>{{ t("editor.build_room.title") }}</strong>{{ t("editor.build_room.text", { free: gb(room.free_mb), need: gb(room.need_mb) }) }}
      <button type="button" class="btn link mini" @click="ui.openSettings('builds')">{{ t("editor.build_room.server") }}<Icon name="arrow-right" /></button>
    </span>
  </div>
</template>
