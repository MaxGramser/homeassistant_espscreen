<script setup lang="ts">
// One plugin as a card: its icon, its maker, one line of what it does, its label and one line of state. The Plugins
// page and a screen's Plugins tab draw the same card; only the state they hand it differs. Where a plugin can go on a
// screen, the card has a round Add, the way a store has Get: it sets the plugin aside in the tray (PluginTray) without opening
// its details, and turns into a tick until it is taken out again. The card itself opens the details.
import { t } from "../i18n";
import { text, type Plugin } from "../model/plugins";
import { glyph } from "../model/topbar";
import { labelOf, stageOf, type Status } from "../plugin-state";
import Icon from "./ui/Icon.vue";

defineProps<{ plugin: Plugin; status: Status; chosen: boolean; staged?: boolean | null }>();
defineEmits<{ open: []; add: [] }>();
</script>

<template>
  <div role="listitem" tabindex="0" class="plugin-card" :class="[status.kind, { chosen, staged, addable: staged != null }]" :data-plugin="plugin.id"
    @click="$emit('open')" @keydown.enter.self="$emit('open')">
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
      <em class="plugin-chip" :class="labelOf(plugin)">{{ t(`editor.plugins.label.${labelOf(plugin)}`) }}</em>
      <em v-if="stageOf(plugin)" class="plugin-chip" :class="stageOf(plugin)" :title="t(`editor.plugins.stage_hint.${stageOf(plugin)}`)">{{ t(`editor.plugins.stage.${stageOf(plugin)}`) }}</em>
      <span v-if="plugin.likes" class="plugin-likes" :class="{ mine: plugin.liked }" :title="t('editor.plugins.likes.count', { n: plugin.likes }, plugin.likes)">
        <Icon :name="plugin.liked ? 'heart' : 'heart-outline'" />{{ plugin.likes }}</span>
      <span v-if="status.label" class="plugin-state" :class="status.kind">
        <Icon v-if="status.kind === 'installed'" name="check" />
        <Icon v-else-if="status.kind === 'update'" name="update" />
        <span v-else-if="status.kind === 'building'" class="spin" aria-hidden="true"></span>
        {{ status.label }}
      </span>
    </span>
  </div>
</template>
