<script setup lang="ts">
// The drawer's title as the way to its name (app 0.4.x): it reads as the title, and a pencil beside it on hover and on
// focus says it can be renamed; a click goes to the Name field (inspector/NameField.vue), the one place it is changed.
import { t } from "../../i18n";
import Icon from "../ui/Icon.vue";

defineProps<{ text: string }>();
defineEmits<{ rename: [] }>();
</script>

<template>
  <button type="button" class="dr-title-btn" :title="t('editor.naming.rename')" :aria-label="`${t('editor.naming.rename')}: ${text}`" @click="$emit('rename')">
    <b>{{ text }}</b><Icon name="pencil-outline" class="dr-pencil" />
  </button>
</template>

<style scoped>
.dr-title-btn { justify-self: start; display: inline-flex; align-items: center; gap: 6px; max-width: 100%; min-width: 0; margin-left: -6px; padding: 2px 6px; border-radius: 6px;
  color: inherit; text-align: left; transition: background 0.12s; }
.dr-title-btn b { font-weight: 600; font-size: 14px; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dr-pencil { flex: none; font-size: 14px; opacity: 0; transition: opacity 0.12s; color: var(--head-soft, var(--muted)); }
.dr-title-btn:hover, .dr-title-btn:focus-visible { background: color-mix(in srgb, var(--head-ink, var(--ink)) 12%, transparent); }
.dr-title-btn:hover .dr-pencil, .dr-title-btn:focus-visible .dr-pencil { opacity: 1; }
.dr-title-btn:focus-visible { outline: none; box-shadow: 0 0 0 2px color-mix(in srgb, var(--head-ink, var(--accent)) 60%, transparent); }
@media (hover: none) { .dr-pencil { opacity: 1; } }
@media (prefers-reduced-motion: reduce) { .dr-title-btn, .dr-pencil { transition: none; } }
</style>
