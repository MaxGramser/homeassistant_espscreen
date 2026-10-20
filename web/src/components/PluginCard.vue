<script setup lang="ts">
// One plugin as a card: its icon, its maker, one line of what it does, its label and one line of state. The Plugins
// page and a screen's Plugins tab draw the same card; only the state they hand it differs. Where a plugin can go on a
// screen, the card has a round Add, the way a store has Get: it sets the plugin aside in the tray (PluginTray) without opening
// its details, and turns into a tick until it is taken out again. The card itself opens the details. A plugin with a
// picture (store.png in its repository) shows it across the top of the card; one the add-on cannot serve folds away.
import { ref } from "vue";
import { editorNumber, t } from "../i18n";
import { text, type Plugin } from "../model/plugins";
import { glyph } from "../model/topbar";
import Icon from "./ui/Icon.vue";
import { usePluginsStore, type Status } from "../stores/plugins";
import { useUiStore } from "../stores/ui";

const plugins = usePluginsStore();
const ui = useUiStore();
const pictureFailed = ref(false);

const props = defineProps<{ plugin: Plugin; status: Status; chosen: boolean; staged?: boolean | null }>();
const emit = defineEmits<{ open: []; add: [] }>();
// A heart on the card: once this app said yes to a public count it goes at once, else the details open and ask.
async function heart() {
  if (!props.plugin.liked && !plugins.likeConsent) { plugins.likeAsk = props.plugin.id; emit("open"); return; }
  try { await plugins.like(props.plugin, !props.plugin.liked); } catch (error: any) { ui.toast(error.message); }
}
</script>

<template>
  <div role="listitem" tabindex="0" class="plugin-card" :class="[status.kind, { chosen, staged, addable: staged != null, pictured: plugin.image && !pictureFailed }]" :data-plugin="plugin.id"
    @click="$emit('open')" @keydown.enter.self="$emit('open')">
    <img v-if="plugin.image && !pictureFailed" class="plugin-picture" :src="plugin.image" alt="" loading="lazy" decoding="async" @error="pictureFailed = true" />
    <span class="plugin-icon" :class="{ tessera: plugin.tessera }" aria-hidden="true"><span class="mdi">{{ glyph(plugin.icon) }}</span></span>
    <span class="plugin-words">
      <b>{{ text(plugin.name) }}</b>
      <small>{{ plugin.tessera ? t("editor.plugins.from_tessera") : t("editor.plugins.by", { maker: plugin.maintainer }) }}</small>
    </span>
    <button v-if="staged != null" type="button" class="plugin-get" :class="{ on: staged }" :aria-pressed="staged"
      :aria-label="staged ? t('editor.plugins.tray.added') : t('editor.plugins.tray.add')" :title="staged ? t('editor.plugins.tray.added') : t('editor.plugins.tray.add')" @click.stop="$emit('add')">
      <Transition name="get" mode="out-in"><Icon :key="String(staged)" :name="staged ? 'check' : 'plus'" /></Transition>
    </button>
    <span v-if="text(plugin.summary)" class="plugin-summary">{{ text(plugin.summary) }}</span>
    <span class="plugin-foot">
      <em class="plugin-chip" :class="plugins.labelOf(plugin)">{{ t(`editor.plugins.label.${plugins.labelOf(plugin)}`) }}</em>
      <em v-if="plugins.stageOf(plugin)" class="plugin-chip" :class="plugins.stageOf(plugin)" :title="t(`editor.plugins.stage_hint.${plugins.stageOf(plugin)}`)">{{ t(`editor.plugins.stage.${plugins.stageOf(plugin)}`) }}</em>
      <span v-if="plugin.rating != null" class="plugin-numbers" :title="t('editor.plugins.numbers.rating', { rating: editorNumber(plugin.rating.toFixed(1)), n: plugin.ratings || 0 }, plugin.ratings || 0)">
        <Icon name="star" class="star" />{{ editorNumber(plugin.rating.toFixed(1)) }}</span>
      <span v-if="plugin.homes" class="plugin-numbers" :title="t('editor.plugins.numbers.homes', { n: plugin.homes }, plugin.homes)">
        <Icon name="home-outline" />{{ plugin.homes }}</span>
      <!-- A heart right on the card, for any plugin of the index: the first one opens the details, which ask once. -->
      <button v-if="plugin.source === 'index'" type="button" class="plugin-likes" :class="{ mine: plugin.liked }" :aria-pressed="Boolean(plugin.liked)"
        :title="plugin.likes ? t('editor.plugins.likes.count', { n: plugin.likes }, plugin.likes) : t('editor.plugins.likes.like_hint')"
        :aria-label="t(plugin.liked ? 'editor.plugins.likes.unlike' : 'editor.plugins.likes.like')" @click.stop="heart">
        <Icon :name="plugin.liked ? 'heart' : 'heart-outline'" /><template v-if="plugin.likes">{{ plugin.likes }}</template></button>
      <span v-if="status.label" class="plugin-state" :class="status.kind">
        <Icon v-if="status.kind === 'installed'" name="check" />
        <Icon v-else-if="status.kind === 'update'" name="update" />
        <Icon v-else-if="status.kind === 'missing'" name="alert-circle-outline" />
        <span v-else-if="status.kind === 'building'" class="spin" aria-hidden="true"></span>
        {{ status.label }}
      </span>
    </span>
  </div>
</template>
