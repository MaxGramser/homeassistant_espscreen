<script setup lang="ts">
// The top of the inspector: what is open, and the way up to what holds it (the screen, a page). A step of that way
// that can be opened is a link, so a tile leads to its page and a top bar to the page it sits on.
import { t } from "../../i18n";
import { closeInspector } from "../../store";
import type { IconName } from "../../model/ui-icons";
import { glyph as glyphOf } from "../../model/topbar";
import Icon from "./Icon.vue";
import type { Crumb } from "./types";
defineProps<{ title: string; icon?: IconName; code?: string; tone?: { color?: string; background?: string }; crumbs?: Crumb[] }>();
</script>

<template>
  <div class="dr-head">
    <span class="av" :style="tone ? { color: tone.color, background: tone.background } : undefined">
      <Icon v-if="icon" :name="icon" /><span v-else-if="code" class="mdi" aria-hidden="true">{{ glyphOf(code) }}</span>
    </span>
    <span class="tx">
      <b>{{ title }}</b>
      <span v-if="crumbs?.length" class="crumbs">
        <template v-for="(crumb, i) in crumbs" :key="i">
          <Icon v-if="i" name="chevron-right" class="crumb-sep" />
          <button v-if="crumb.open" type="button" class="crumb" :class="{ mono: crumb.mono }" @click="crumb.open()">{{ crumb.text }}</button>
          <span v-else class="crumb" :class="{ mono: crumb.mono }">{{ crumb.text }}</span>
        </template>
      </span>
    </span>
    <button type="button" class="icon-btn" :aria-label="t('editor.common.close')" @click="closeInspector"><Icon name="close" /></button>
  </div>
</template>
