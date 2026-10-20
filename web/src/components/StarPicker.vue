<script setup lang="ts">
// One to five stars for a plugin (plugin_likes.py), on Reka UI's Rating: a radio group, so the arrow keys move the
// choice and a screen reader says which star of five, and a hover shows what a click would give. The word for it
// stands beside them (`say`).
import { RatingItem, RatingItemIndicator, RatingRoot } from "reka-ui";
import { computed, ref } from "vue";
import { t } from "../i18n";
import Icon from "./ui/Icon.vue";

const props = defineProps<{ modelValue: number | null; label: string; disabled?: boolean; small?: boolean; say?: boolean; id?: string }>();
const emit = defineEmits<{ "update:modelValue": [value: number] }>();
const hover = ref(0);
const word = computed(() => hover.value || props.modelValue || 0);
const pick = (value: number) => { if (value >= 1 && value <= 5) emit("update:modelValue", value); };
</script>

<template>
  <span class="stars" :class="{ small }" :id="id">
    <RatingRoot v-slot="{ items }" class="stars-keys" :model-value="modelValue ?? 0" :length="5" hoverable :disabled="disabled"
      :aria-label="label" @update:model-value="pick" @mouseleave="hover = 0">
      <RatingItem v-for="n in items" :key="n" :item="n" as="span" @mouseenter="hover = disabled ? 0 : n">
        <RatingItemIndicator :step="n" class="star" :data-star="n" :aria-label="t('editor.plugins.stars.of_five', { n })">
          <Icon name="star" class="star-on" /><Icon name="star-outline" class="star-off" />
        </RatingItemIndicator>
      </RatingItem>
    </RatingRoot>
    <span v-if="say" class="stars-say" aria-hidden="true">{{ word ? t(`editor.plugins.stars.say.${word}`) : "" }}</span>
  </span>
</template>

<style>
/* Not scoped: the stars are Reka's own radio buttons (RatingItemIndicator), which a scoped style does not reach. */
.stars { display: inline-flex; align-items: center; gap: 8px; }
.stars-keys { display: inline-flex; align-items: center; }
.stars .star { display: grid; place-items: center; padding: 2px; border-radius: 6px; color: var(--line-strong); font-size: 26px; line-height: 1; transition: transform 0.12s; }
.stars.small .star { font-size: 18px; padding: 1px; }
.stars .star[data-state="active"] { color: var(--star); }
.stars .star .star-on, .stars .star[data-state="active"] .star-off { display: none; }
.stars .star[data-state="active"] .star-on { display: inline; }
.stars .star:active:not([data-disabled]) { transform: scale(0.9); }
.stars .star[data-disabled] { cursor: default; }
.stars .star:focus-visible { outline: none; box-shadow: var(--focus); }
.stars-say { font-size: 12.5px; color: var(--ink-2); min-width: 7ch; }
@media (prefers-reduced-motion: reduce) { .stars .star { transition: none; } }
</style>
