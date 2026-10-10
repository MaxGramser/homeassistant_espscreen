<script setup lang="ts">
// The top of the inspector: what is open, and the way up to what holds it (the screen, a page). A step of that way
// that can be opened is a link, so a tile leads to its page and a top bar to the page it sits on. The `title` slot takes
// a field where the name is edited in place, the `actions` slot a menu beside the close button (app 0.4.32).
import { t } from "../../i18n";
import type { IconName } from "../../model/ui-icons";
import { glyph as glyphOf } from "../../model/topbar";
import Icon from "./Icon.vue";
import type { Crumb } from "./types";
import { useInspectorStore } from "../../stores/inspector";

const insp = useInspectorStore();
// `kind` says which of the three things is open (app 0.4.32): a tile, a page or the top bar, each with its own colour,
// shown here as a word over the title and a line along the top, and on the canvas as the ring around what is chosen.
defineProps<{ title: string; icon?: IconName; code?: string; tone?: { color?: string; background?: string }; crumbs?: Crumb[]; kind?: "tile" | "page" | "bar" }>();
const KIND_ICONS = { tile: "view-dashboard-outline", page: "view-column-outline", bar: "page-layout-header" } as const;
</script>

<template>
  <div class="dr-head" :class="kind ? `kind-${kind}` : undefined">
    <span class="av" :style="tone ? { color: tone.color, background: tone.background } : undefined">
      <Icon v-if="icon" :name="icon" /><span v-else-if="code" class="mdi" aria-hidden="true">{{ glyphOf(code) }}</span>
    </span>
    <span class="tx">
      <span v-if="kind" class="dr-kind"><Icon :name="KIND_ICONS[kind]" />{{ t(`editor.inspector.kind.${kind}`) }}</span>
      <slot name="title"><b>{{ title }}</b></slot>
      <span v-if="crumbs?.length" class="crumbs">
        <template v-for="(crumb, i) in crumbs" :key="i">
          <Icon v-if="i" name="chevron-right" class="crumb-sep" />
          <button v-if="crumb.open" type="button" class="crumb" :class="{ mono: crumb.mono }" @click="crumb.open()">{{ crumb.text }}</button>
          <span v-else class="crumb" :class="{ mono: crumb.mono }">{{ crumb.text }}</span>
        </template>
      </span>
    </span>
    <slot name="actions" />
    <button type="button" class="icon-btn" :aria-label="t('editor.common.close')" :title="`${t('editor.common.close')} · Esc`" @click="insp.closeInspector"><Icon name="close" /></button>
  </div>
</template>
