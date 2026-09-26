<script setup lang="ts">
// Local navigation only. No service, save, setting or selection mutation.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { t } from '../i18n';
import { entriesOf } from '../model/layout';
import { navigationStep, titleOf, type NavigationIntent } from '../model/pages';
import { navigationSettings, state } from '../store';
import DevicePage from './DevicePage.vue';
import Icon from './ui/Icon.vue';
const emit = defineEmits<{ close: [] }>();
const dialog = ref<HTMLDialogElement>();
const current = ref(state.document!.homePageId);
const page = computed(() => Math.max(0, state.document!.pages.findIndex((page) => page.id === current.value)));
const visited = ref([current.value]);
const history = ref<string[]>([]);
const canGoBack = computed(() => navigationStep(state.document!, current.value, history.value, { kind: 'back' }, navigationSettings()).current !== current.value);
function navigate(intent: NavigationIntent) {
  const step = navigationStep(state.document!, current.value, history.value, intent, navigationSettings());
  const target = step.current; history.value = step.history;
  if (target !== current.value) { current.value = target; visited.value = [...visited.value.slice(-15), target]; }
}
const caption = computed(() => visited.value.map((id) => {
  const page = state.document!.pages.find((page) => page.id === id);
  return page ? titleOf(state.document!, page) : '';
}).join(' → '));
let origin: { x: number; y: number } | null = null;
let suppressClick = false;
function start(event: PointerEvent) { origin = { x: event.clientX, y: event.clientY }; }
function finish(event: PointerEvent) {
  if (!origin) return;
  const dx = event.clientX - origin.x, dy = event.clientY - origin.y; origin = null;
  if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 2) { suppressClick = true; navigate({ kind: dx < 0 ? 'swipe-next' : 'swipe-previous' }); }
}
function click(event: MouseEvent) { if (suppressClick) { event.preventDefault(); event.stopPropagation(); suppressClick = false; } }
const previouslyFocused = document.activeElement as HTMLElement | null;
onMounted(() => dialog.value?.showModal());
onBeforeUnmount(() => previouslyFocused?.focus());
</script>
<template>
  <dialog ref="dialog" class="navigation-preview" @cancel.prevent="emit('close')">
    <div class="preview-heading"><b><Icon name="play" />{{ t('editor.pages.try_navigation') }}</b><button class="icon-btn" :aria-label="t('editor.common.close')" @click="emit('close')"><Icon name="close" /></button></div>
    <p>{{ t('editor.pages.preview_hint') }}</p>
    <div class="preview-screen" @pointerdown="suppressClick = false; start($event)" @pointerup="finish" @pointercancel="origin = null" @click.capture="click">
      <DevicePage :page="page" :entries="entriesOf(state.layout!)" :pages="state.document!.pages.length" :moving="null" preview :can-go-back="canGoBack" @navigate="navigate" />
    </div>
    <div v-if="navigationSettings().swipe" class="preview-swipes">
      <button class="btn quiet mini" @click="navigate({ kind: 'swipe-previous' })"><Icon name="arrow-left" />{{ t('editor.pages.swipe_previous') }}</button>
      <button class="btn quiet mini" @click="navigate({ kind: 'swipe-next' })">{{ t('editor.pages.swipe_next') }}<Icon name="arrow-right" /></button>
    </div>
    <p class="preview-route" aria-live="polite">{{ caption }}</p>
  </dialog>
</template>
<style scoped>
.navigation-preview { max-width: calc(100vw - 24px); max-height: calc(100dvh - 24px); overflow: auto; color: var(--ink); background: var(--surface); border: 1px solid var(--line); border-radius: 16px; padding: 20px 22px; box-shadow: var(--shadow); }
.navigation-preview::backdrop { background: rgb(10 12 18 / .5); }
.preview-heading b { display: inline-flex; align-items: center; gap: 8px; font-size: 15px; }
.preview-heading b .ui-icon { color: var(--accent); }
.preview-heading, .preview-swipes { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
.preview-screen { display: flex; justify-content: center; margin: 18px 0; touch-action: pan-y; }
p { max-width: 480px; font-size: 13px; color: var(--muted); }
.preview-route { overflow-wrap: anywhere; }
</style>
