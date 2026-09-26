<script setup lang="ts">
import { computed, ref } from 'vue';
import { Tooltip } from 'floating-vue';
import 'floating-vue/dist/style.css';
import { glyph } from '../model/topbar';

defineProps<{ text: string }>();
const hovered = ref(false), focused = ref(false), pinned = ref(false), dismissed = ref(false);
const shown = computed(() => !dismissed.value && (hovered.value || focused.value || pinned.value));
function close() { dismissed.value = true; pinned.value = false; }
function enter() { hovered.value = true; dismissed.value = false; }
function focus() { focused.value = true; dismissed.value = false; }
function tap() { if (pinned.value) close(); else { pinned.value = true; dismissed.value = false; } }
// Keep the popper inside native dialogs so it shares their browser top layer.
const placementOptions: Record<string, unknown> = { container: false };
</script>

<template>
  <Tooltip class="help-tip" :shown="shown" :triggers="[]" :hide-triggers="[]" :popper-triggers="[]" :auto-hide="true"
    :delay="{ show: 150, hide: 150 }" :distance="8" placement="top" strategy="fixed" v-bind="placementOptions"
    @hide="close">
    <button type="button" class="help-trigger mdi" :aria-label="text"
      @mouseenter="enter" @mouseleave="hovered = false" @focus="focus" @blur="focused = false; pinned = false"
      @click.stop="tap" @keydown.esc.stop.prevent="close" :data-glyph="glyph('F02FD')"></button>
    <template #popper><span class="help-content" role="tooltip" @mouseenter="enter" @mouseleave="hovered = false">{{ text }}</span></template>
  </Tooltip>
</template>

<style>
.help-tip { display: inline-flex; vertical-align: middle; }
.help-trigger { display: inline-grid; place-items: center; width: 28px; height: 28px; padding: 0; border: 0; border-radius: 50%; color: var(--muted); background: transparent; font-size: 18px; cursor: help; }
/* The icon comes from CSS, so a label with a tip beside it still reads as just its words. */
.help-trigger::before { content: attr(data-glyph); }
.help-trigger:hover, .help-trigger:focus-visible { color: var(--accent); background: var(--seg); }
.help-content { display: block; max-width: min(300px, calc(100vw - 48px)); line-height: 1.5; font-size: 13px; white-space: normal; text-transform: none; letter-spacing: normal; font-weight: 400; }
.v-popper--theme-tooltip .v-popper__inner { padding: 10px 12px; border-radius: 8px; }
</style>
