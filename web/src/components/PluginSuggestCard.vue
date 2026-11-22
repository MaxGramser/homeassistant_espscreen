<script setup lang="ts">
// A plugin for hardware this screen's board has (docs/PLUGINS.md, "Plugins a board starts with"): the card above a
// screen that suggests it, with the reason. Yes brings it with the update that waits for the screen, or builds it now
// when none does; no is kept, and the card does not come back for that plugin on this screen. One plugin at a time.
import { computed, ref } from "vue";
import { useBusy } from "../composables/useBusy";
import { t } from "../i18n";
import { text } from "../model/plugins";
import type { Screen } from "../types";
import { useBuildsStore } from "../stores/builds";
import { usePluginsStore } from "../stores/plugins";
import { useUiStore } from "../stores/ui";

const props = defineProps<{ screen: Screen }>();
const builds = useBuildsStore();
const plugins = usePluginsStore();
const ui = useUiStore();
const { busy, runOnce } = useBusy();

const card = computed(() => props.screen.plugin_suggest || null);
const plugin = computed(() => card.value?.plugins[0] || null);
const pictureFailed = ref(false);
// Never on top of the board's own card or the stars card, and not while the screen builds.
const visible = computed(() => Boolean(plugin.value) && props.screen.online && !props.screen.feedback?.ask
  && !props.screen.plugin_ask && !builds.updating.includes(props.screen.id));
const name = computed(() => (plugin.value ? text(plugin.value.name) : ""));

async function answer(yes: boolean) {
  const now = plugin.value, withUpdate = Boolean(card.value?.update);
  if (!now) return;
  await runOnce(async () => {
    await plugins.answerSuggested(props.screen, now.id, yes);
    ui.toast(t(!yes ? "editor.plugins.suggest.declined" : withUpdate ? "editor.plugins.suggest.with_update" : "editor.plugins.suggest.building",
      { name: text(now.name), screen: props.screen.name }));
  }).catch((error: any) => ui.toast(error.message));
}
</script>

<template>
  <section v-if="visible && plugin && card" class="suggest-card" id="plugin-suggest-card" :data-plugin="plugin.id" aria-labelledby="plugin-suggest-title">
    <div class="suggest-main" :class="{ pictured: plugin.image && !pictureFailed }">
      <img v-if="plugin.image && !pictureFailed" class="suggest-picture" :src="plugin.image" alt="" decoding="async" @error="pictureFailed = true" />
      <div class="suggest-body">
        <p class="suggest-why">{{ t(`editor.plugins.suggest.why.${plugin.why}`) }}</p>
        <h2 id="plugin-suggest-title" class="suggest-question">{{ t("editor.plugins.suggest.question", { name, screen: screen.name }) }}</h2>
        <p class="suggest-summary">{{ text(plugin.summary) }}</p>
        <div class="suggest-actions">
          <button type="button" class="btn primary" id="plugin-suggest-yes" :disabled="busy" @click="answer(true)">{{ t(card.update ? "editor.plugins.suggest.yes_update" : "editor.plugins.suggest.yes") }}</button>
          <button type="button" class="btn quiet" id="plugin-suggest-no" :disabled="busy" @click="answer(false)">{{ t("editor.plugins.suggest.no") }}</button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* The same box as the stars card (PluginRatingCard.vue). */
.suggest-card { position: relative; flex: none; margin: 14px 18px 0; padding: 14px 16px; border: 1px solid var(--line); border-radius: 12px; background: var(--surface); }
.suggest-main { display: grid; grid-template-columns: minmax(0, 1fr); gap: 16px; align-items: start; }
.suggest-main.pictured { grid-template-columns: 168px minmax(0, 1fr); }
.suggest-picture { width: 100%; aspect-ratio: 16 / 9; object-fit: cover; border-radius: 9px; border: 1px solid var(--line); display: block; }
.suggest-body { display: grid; gap: 8px; min-width: 0; justify-items: start; }
.suggest-why { margin: 0; font-size: 11.5px; color: var(--muted); }
.suggest-question { margin: 0; font-size: 14px; font-weight: 600; line-height: 1.35; text-wrap: balance; }
.suggest-summary { margin: 0; font-size: 12.5px; color: var(--ink-2); line-height: 1.4; max-width: 560px; }
.suggest-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 2px; }
@media (max-width: 640px) {
  .suggest-card { margin: 10px 16px 0; }
  .suggest-main.pictured { grid-template-columns: 1fr; }
  .suggest-picture { max-width: 240px; }
}
</style>
