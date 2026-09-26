<script setup lang="ts">
// A group of settings in the inspector: a card with a title, so the drawer reads as a few questions instead of one
// long list. A group that is rarely needed can fold away, and then remembers nothing: it opens folded each time.
import { ref } from "vue";
import type { IconName } from "../../model/ui-icons";
import Icon from "./Icon.vue";
import HelpTip from "../HelpTip.vue";
const props = defineProps<{ title: string; icon?: IconName; aside?: string; hint?: string; foldable?: boolean; open?: boolean }>();
const shown = ref(!props.foldable || props.open);
</script>

<template>
  <section class="insp-sec" :class="{ folded: !shown }">
    <component :is="foldable ? 'button' : 'div'" class="insp-sec-head" v-bind="foldable ? { type: 'button', 'aria-expanded': shown ? 'true' : 'false' } : {}" @click="foldable && (shown = !shown)">
      <span v-if="icon" class="insp-sec-icon"><Icon :name="icon" /></span>
      <h3>{{ title }}</h3>
      <HelpTip v-if="hint" :text="hint" />
      <small v-if="aside">{{ aside }}</small>
      <Icon v-if="foldable" name="chevron-down" class="insp-sec-chevron" />
    </component>
    <div v-if="shown" class="insp-sec-body"><slot /></div>
  </section>
</template>
