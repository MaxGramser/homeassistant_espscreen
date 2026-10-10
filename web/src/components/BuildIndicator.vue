<script setup lang="ts">
// While anything builds, one quiet ring in the head of the page (the sidebar's top, the overview's head on a phone), as
// a browser shows its downloads: how far the builds are together and how many there are, and a click lists each
// screen's with its step (BuildList). Nothing builds, nothing shows.
import { PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger } from "reka-ui";
import { computed, ref } from "vue";
import { t } from "../i18n";
import BuildList from "./BuildList.vue";
import ProgressRing from "./ui/ProgressRing.vue";
import { useBuildsStore } from "../stores/builds";

const builds = useBuildsStore();
const open = ref(false);
const screens = computed(() => builds.buildingScreens);
// Every build's share together, one waiting its turn at nothing yet.
const together = computed(() => screens.value.length
  ? Math.round(screens.value.reduce((sum, screen) => sum + (builds.buildProgress(screen)?.percent ?? 0), 0) / screens.value.length) : 0);
const label = computed(() => screens.value.length === 1
  ? `${screens.value[0].name} · ${builds.buildProgress(screens.value[0])?.text ?? t("editor.build.waiting")}` : t("editor.build.count", screens.value.length));
</script>

<template>
  <PopoverRoot v-if="screens.length" v-model:open="open">
    <PopoverTrigger as-child>
      <button type="button" id="builds" class="icon-btn builds-btn" :aria-label="label" :title="label">
        <ProgressRing :percent="together" :label="label" :size="16" />
        <span v-if="screens.length > 1" class="builds-count" aria-hidden="true">{{ screens.length }}</span>
      </button>
    </PopoverTrigger>
    <PopoverPortal>
      <PopoverContent class="ui-popover builds-pop" align="start" side="bottom" :side-offset="6" :collision-padding="12">
        <BuildList @done="open = false" />
      </PopoverContent>
    </PopoverPortal>
  </PopoverRoot>
</template>
