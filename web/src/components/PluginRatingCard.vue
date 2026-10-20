<script setup lang="ts">
// How does a plugin work for you (docs/PLUGINS.md, "Likes, ratings and counting")? The card above a screen a few days
// after the screen first ran a plugin of the index, as the board's card asks a day after a screen works, and never at
// the same time as that one: the plugin's picture, its name and maker, one to five stars. The first card also asks
// whether this app may count its plugins, off until it is ticked. Only Send sends anything; the add-on keeps the key.
// Later, Don't ask again, what is shared and the privacy page sit behind the card's ⋯ menu, so the card itself has
// two keys. After the stars it thanks, and offers a heart for a good plugin or the plugin's issues for a poor one.
import { computed, ref } from "vue";
import { useBusy } from "../composables/useBusy";
import { t } from "../i18n";
import { text } from "../model/plugins";
import type { PluginAsk, Screen } from "../types";
import { useBuildsStore } from "../stores/builds";
import { usePluginsStore } from "../stores/plugins";
import { useUiStore } from "../stores/ui";
import StarPicker from "./StarPicker.vue";
import Icon from "./ui/Icon.vue";
import UiMenu from "./ui/UiMenu.vue";
import UiMenuItem from "./ui/UiMenuItem.vue";
import UiMenuSeparator from "./ui/UiMenuSeparator.vue";
import UiSwitch from "./ui/UiSwitch.vue";

const props = defineProps<{ screen: Screen }>();
const builds = useBuildsStore();
const plugins = usePluginsStore();
const ui = useUiStore();
const { busy, runOnce } = useBusy();

// While someone answers, the card keeps the plugin it asked about: the add-on stops asking once the stars are in.
const engaged = ref(false);
const held = ref<PluginAsk | null>(null);
const ask = computed(() => (engaged.value ? held.value : props.screen.plugin_ask || null));
const step = ref<"ask" | "thanks">("ask");
const stars = ref<number | null>(null);
const count = ref(false);
const shared = ref(false);
const hearted = ref(false);
const pictureFailed = ref(false);
const visible = computed(() => Boolean(ask.value) && (engaged.value || (props.screen.online && !props.screen.feedback?.ask
  && !builds.updating.includes(props.screen.id))));
const name = computed(() => (ask.value ? text(ask.value.name) : ""));
const maker = computed(() => (ask.value?.tessera ? "Tessera" : ask.value?.maintainer || ""));

function choose(n: number) {
  if (!engaged.value) held.value = props.screen.plugin_ask || null;
  engaged.value = true;
  stars.value = n;
}
async function send() {
  const now = ask.value;
  if (!now || !stars.value) return;
  const done = await runOnce(async () => {
    await plugins.rate({ id: now.plugin }, stars.value, props.screen.id);
    if (now.ask_counting) await (count.value ? plugins.setCounting(true) : plugins.cardAnswer(now.plugin, "asked_counting"));
    return true;
  }).catch((error: any) => { ui.toast(error.message); return false; });
  if (done) step.value = "thanks";
}
async function later() {
  if (!ask.value) return;
  await runOnce(() => plugins.cardAnswer(ask.value!.plugin, "later")).catch((error: any) => ui.toast(error.message));
  close();
}
async function never() {
  if (!ask.value) return;
  await runOnce(() => plugins.cardAnswer(ask.value!.plugin, "never")).catch((error: any) => ui.toast(error.message));
  close();
}
// A heart from the thanks: the button says that it counts in a public number, so pressing it is the yes it needs.
async function heart() {
  if (!ask.value) return;
  await runOnce(() => plugins.like({ id: ask.value!.plugin }, true, true)).then(() => { hearted.value = true; })
    .catch((error: any) => ui.toast(error.message));
}
function close() {
  engaged.value = false;
  held.value = null;
  step.value = "ask";
  stars.value = null;
  shared.value = false;
}
// A problem goes to the plugin's own issues on GitHub, filled in with what the card knows; the person posts it.
const issueUrl = computed(() => {
  const now = ask.value;
  if (!now?.issues) return null;
  const query = new URLSearchParams({
    title: `[${now.plugin}] `,
    body: [`Plugin: ${now.plugin} ${now.version || ""}`.trim(), now.board ? `Screen: ${now.board}` : "", "", "What goes wrong:"]
      .filter((line, i) => line || i > 1).join("\n"),
  });
  return `${now.issues}?${query}`;
});
const openPrivacy = () => { if (ask.value) window.open(ask.value.privacy, "_blank", "noopener"); };
</script>

<template>
  <section v-if="visible && ask" class="rate-card" id="plugin-rate-card" :data-plugin="ask.plugin" aria-labelledby="plugin-rate-title">
    <UiMenu v-if="step === 'ask'" width="230px">
      <template #trigger><button type="button" class="icon-btn rate-more" id="plugin-rate-more" :aria-label="t('editor.screen_view.more')"><Icon name="dots-horizontal" /></button></template>
      <UiMenuItem icon="information-outline" @select="shared = !shared">{{ t("editor.plugins.rate_card.what_title") }}</UiMenuItem>
      <UiMenuItem icon="link-variant" @select="openPrivacy">{{ t("editor.feedback.privacy") }}</UiMenuItem>
      <UiMenuSeparator />
      <UiMenuItem icon="close" @select="never">{{ t("editor.feedback.never") }}</UiMenuItem>
    </UiMenu>
    <template v-if="step === 'ask'">
      <div class="rate-main" :class="{ pictured: ask.image && !pictureFailed }">
        <img v-if="ask.image && !pictureFailed" class="rate-picture" :src="ask.image" alt="" decoding="async" @error="pictureFailed = true" />
        <div class="rate-body">
          <p class="rate-who">{{ t("editor.plugins.rate_card.by", { maker, version: ask.version || "" }) }}</p>
          <h2 id="plugin-rate-title" class="rate-question">{{ t("editor.plugins.rate_card.question", { name, screen: screen.name, days: ask.days }, ask.days) }}</h2>
          <StarPicker :model-value="stars" :label="t('editor.plugins.stars.label', { name })" :disabled="busy" say id="plugin-rate-stars" @update:model-value="choose" />
          <label v-if="stars && ask.ask_counting" class="rate-count" for="plugin-rate-count">
            <UiSwitch id="plugin-rate-count" v-model="count" :disabled="busy" />
            <span><b>{{ t("editor.plugins.counting.label") }}</b><small>{{ t("editor.plugins.counting.hint") }}</small></span>
          </label>
          <div v-if="shared" class="rate-shared" id="plugin-rate-shared">
            <b>{{ t("editor.plugins.rate_card.what_title") }}</b>
            <ul>
              <li>{{ t("editor.plugins.rate_card.what.plugin", { name, version: ask.version || "" }) }}</li>
              <li v-if="ask.board">{{ t("editor.plugins.rate_card.what.board", { board: ask.board }) }}</li>
              <li>{{ t("editor.plugins.rate_card.what.stars") }}</li>
              <li v-if="count">{{ t("editor.plugins.rate_card.what.counting") }}</li>
            </ul>
            <span>{{ t("editor.plugins.rate_card.what.nothing_else") }}</span>
          </div>
          <div class="rate-actions">
            <button type="button" class="btn primary" id="plugin-rate-send" :disabled="busy || !stars" @click="send">{{ t("editor.plugins.rate_card.send") }}</button>
            <button type="button" class="btn quiet" id="plugin-rate-later" :disabled="busy" @click="later">{{ t("editor.feedback.later") }}</button>
          </div>
        </div>
      </div>
    </template>
    <template v-else>
      <p class="rate-thanks" id="plugin-rate-thanks"><Icon name="check" />{{ t("editor.plugins.rate_card.thanks", { name }) }}</p>
      <template v-if="(stars || 0) >= 4">
        <p class="hint">{{ t("editor.plugins.rate_card.heart_hint", { maker }) }}</p>
        <div class="rate-actions">
          <button type="button" class="pd-like" id="plugin-rate-heart" :class="{ on: hearted }" :aria-pressed="hearted" :disabled="busy || hearted" @click="heart">
            <Icon :name="hearted ? 'heart' : 'heart-outline'" /><span>{{ hearted ? t("editor.plugins.rate_card.hearted") : t("editor.plugins.likes.like") }}</span></button>
          <button type="button" class="btn quiet" @click="close">{{ t("editor.common.close") }}</button>
        </div>
      </template>
      <template v-else-if="(stars || 0) <= 2 && issueUrl">
        <p class="hint">{{ t("editor.plugins.rate_card.issue_hint", { maker }) }}</p>
        <div class="rate-actions">
          <a class="btn primary" id="plugin-rate-issue" :href="issueUrl" target="_blank" rel="noopener noreferrer" @click="close">{{ t("editor.plugins.rate_card.issue_open") }}</a>
          <button type="button" class="btn quiet" @click="close">{{ t("editor.common.close") }}</button>
        </div>
      </template>
      <div v-else class="rate-actions"><button type="button" class="btn quiet" @click="close">{{ t("editor.common.close") }}</button></div>
    </template>
  </section>
</template>

<style scoped>
.rate-card { position: relative; flex: none; margin: 14px 18px 0; padding: 14px 16px; border: 1px solid var(--line); border-radius: 12px; background: var(--surface); }
.rate-more { position: absolute; top: 8px; right: 8px; color: var(--muted); }
.rate-main { display: grid; grid-template-columns: minmax(0, 1fr); gap: 16px; align-items: start; }
.rate-main.pictured { grid-template-columns: 168px minmax(0, 1fr); }
.rate-picture { width: 100%; aspect-ratio: 16 / 9; object-fit: cover; border-radius: 9px; border: 1px solid var(--line); display: block; }
.rate-body { display: grid; gap: 10px; min-width: 0; justify-items: start; }
.rate-who { margin: 0; font-size: 11.5px; color: var(--muted); }
.rate-question { margin: 0; padding-right: 32px; font-size: 14px; font-weight: 600; line-height: 1.35; text-wrap: balance; }
.rate-count { display: flex; align-items: flex-start; gap: 10px; padding: 10px 12px; border-radius: 10px; background: var(--surface-2); cursor: pointer; max-width: 520px; }
.rate-count span { display: grid; gap: 2px; font-size: 12.5px; }
.rate-count small { color: var(--muted); line-height: 1.4; }
.rate-shared { display: grid; gap: 6px; padding: 10px 12px; border-radius: 10px; background: var(--surface-2); font-size: 12.5px; color: var(--ink-2); max-width: 520px; }
.rate-shared ul { margin: 0; padding-left: 16px; display: grid; gap: 2px; }
.rate-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.rate-thanks { display: flex; align-items: center; gap: 8px; margin: 0 0 4px; font-size: 13px; font-weight: 550; color: var(--good); }
.rate-card .hint { margin: 0 0 10px; }
@media (max-width: 640px) {
  .rate-card { margin: 10px 16px 0; }
  .rate-main.pictured { grid-template-columns: 1fr; }
  .rate-picture { max-width: 240px; }
}
</style>
