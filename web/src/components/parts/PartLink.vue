<script setup lang="ts">
// One row of a list of parts (model/parts.ts, docs/PAGES.md "Pages of parts"): the part's round icon, its name, one line
// of what is set now, and the way into its page. A row can carry one control of its own beside the arrow (the slot), for
// the one thing people change most there, so that needs no page. The name is the row's button; a click anywhere else on
// the row but the control opens the part as well.
import type { IconName } from "../../model/ui-icons";
import type { Tone } from "../../model/parts";
import Icon from "../ui/Icon.vue";

// `tone`: the colour of the round icon, one of the --tone-* tokens (styles/tokens.css), as Home Assistant colours its own.
defineProps<{ icon: IconName; title: string; summary?: string; badge?: string; id?: string; tone?: Tone }>();
const emit = defineEmits<{ open: [] }>();
function rowClick(e: MouseEvent) {
  const target = e.target as HTMLElement;
  if (!target.closest(".set-link-control, .set-link-main")) emit("open");
}
</script>

<template>
  <div class="set-link" @click="rowClick">
    <button type="button" class="set-link-main" :id="id" @click="emit('open')">
      <span class="set-link-icon" :style="tone ? { '--tone': `var(--tone-${tone})` } : undefined"><Icon :name="icon" /></span>
      <span class="set-link-tx"><b>{{ title }}</b><small v-if="summary">{{ summary }}</small></span>
    </button>
    <span v-if="badge" class="chip update">{{ badge }}</span>
    <span v-if="$slots.default" class="set-link-control"><slot /></span>
    <Icon name="chevron-right" class="set-link-arrow" />
  </div>
</template>
