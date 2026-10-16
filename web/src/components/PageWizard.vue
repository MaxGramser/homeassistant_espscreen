<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { t } from '../i18n';
import { clone, emptyPage, instanceId } from '../model/pages';
import { matchesQuery } from '../model/search';
import { tilePalette } from '../model/tile-palette';
import { BUILTIN_ICONS, glyph, STATUS_CODES } from '../model/topbar';
import type { HeaderItem } from '../types';
import CheckRow from './ui/CheckRow.vue';
import rules from '../model/page-rules.json';
import Icon from './ui/Icon.vue';
import UiChips, { type Chip } from './ui/UiChips.vue';
import DockField, { type DockMode } from './DockField.vue';
import { useEntitiesStore } from '../stores/entities';
import { useScreenStore } from "../stores/screen";
import { useInventoryStore } from "../stores/inventory";
import { addPage } from "../editor/pages";
import { useDocumentStore } from "../stores/document";

const entities = useEntitiesStore();
const scr = useScreenStore();
const inv = useInventoryStore();
const doc = useDocumentStore();

const emit = defineEmits<{ close: [] }>();
const dialog = ref<HTMLDialogElement>();
const title = ref(''), query = ref(''), dockMode = ref<DockMode>('picture'), dockIcon = ref<string>();
const chosen = ref<string[]>([]);
// The top bar's quick choices as chips (app dev): the home key on, as every page has it, and the screen's own items off,
// the clock among them, so a new page starts with a bar of what was asked for and not a clock nobody picked.
const quick = ref<string[]>(['home']);
// How the page stands in the Dock, only on a screen whose board has it (docs/MODULES.md): its picture, an icon, or not.
const dock = computed(() => Boolean(scr.currentScreen?.dock));
const builtins = computed(() => (inv.inventory.header?.builtin || []).filter((b) => b.type !== 'battery' || scr.currentScreen?.battery));
const builtinItem = (type: string) => (type === 'wifi' || type === 'battery' ? { type, content: 'icon', show: 'always' } : { type });
const picked = computed(() => quick.value.filter((value) => value !== 'home'));
const count = computed(() => chosen.value.length + picked.value.length);
const barChips = computed<Chip[]>(() => [
  { value: 'home', label: t('editor.pages.wizard_home'), glyph: glyph(entities.iconNamed('home')?.cp || 'F02DC') },
  ...builtins.value.map((b) => ({ value: b.type, label: b.label, glyph: glyph(STATUS_CODES[b.type] || entities.iconNamed(BUILTIN_ICONS[b.type])?.cp || 'F0150'),
    disabled: !quick.value.includes(b.type) && count.value >= scr.topbarMax })),
]);

const matches = computed(() => {
  // Only what the top bar can show (app 0.4.1): the add-on's header domains, so Create never fails on a camera.
  return inv.inventory.entities.filter(entity => rules.headerDomains.includes(entity.id.split('.')[0]) && matchesQuery(query.value, entity.name, entity.id, entity.area));
});
const toggle = (id: string) => { chosen.value = chosen.value.includes(id) ? chosen.value.filter((item) => item !== id) : [...chosen.value, id]; };
const invalidTitle = computed(() => new TextEncoder().encode(title.value.trim()).length > 96);
function create() {
  if (invalidTitle.value || count.value > scr.topbarMax) return;
  // A screen whose firmware still shares one top bar (app 0.4.1): the new page takes that bar and its home key, as
  // every other page does, or the save is refused long after this dialog closed. Only the title is its own.
  if (!scr.pageReady) {
    const shared = clone(doc.document!.pages[0].topbar);
    shared.title = title.value.trim() ? { source: 'text', text: title.value.trim() } : { source: 'screen' };
    if (addPage(shared)) emit('close');
    return;
  }
  const page = emptyPage();
  page.topbar.title = title.value.trim() ? { source: 'text', text: title.value.trim() } : { source: 'screen' };
  if (!quick.value.includes('home')) page.topbar.leading = [];
  page.topbar.trailing = [
    ...picked.value.map((type) => ({ id: instanceId(), ...builtinItem(type) } as HeaderItem & { id: string })),
    ...chosen.value.map(entity => ({ id: instanceId(), type: 'entity', entity, content: 'state', icon: 'auto', show: 'always' } as HeaderItem & { id: string })),
  ];
  const extras = dock.value ? { icon: dockMode.value === 'icon' ? dockIcon.value : undefined, showInDock: dockMode.value !== 'hidden' } : {};
  if (addPage(page.topbar, extras)) emit('close');
}
onMounted(() => dialog.value?.showModal());
</script>

<template>
  <dialog ref="dialog" class="page-wizard" aria-labelledby="page-wizard-title" @cancel.prevent="emit('close')">
    <form @submit.prevent="create">
      <header><h2 id="page-wizard-title">{{ t('editor.layout.add_page') }}</h2>
        <button class="icon-btn" type="button" :aria-label="t('editor.common.close')" @click="emit('close')"><Icon name="close" /></button>
      </header>
      <div class="f">
        <label class="f-label" for="new-page-title">{{ t('editor.pages.title') }}</label>
        <input id="new-page-title" v-model="title" :placeholder="doc.document?.title" :aria-invalid="invalidTitle" autofocus />
        <small v-if="invalidTitle" class="help warn">{{ t('addon.errors.layout.page_title') }}</small>
      </div>
      <div v-if="!scr.pageReady" class="notice warn"><Icon name="alert-circle-outline" /><span class="notice-text">{{ t('editor.pages.shared_bar') }}</span></div>
      <DockField v-if="scr.pageReady && dock" class="dock-group" :mode="dockMode" :icon="dockIcon"
        @change="(value) => { dockMode = value.mode; if (value.icon) dockIcon = value.icon; }" />
      <div v-if="scr.pageReady" class="wizard-group bar-group">
        <h3>{{ t('editor.topbar.title') }}</h3>
        <UiChips v-model="quick" :chips="barChips" :label="t('editor.topbar.title')" />
      </div>
      <div v-if="scr.pageReady" class="f">
        <label class="f-label" for="new-page-entity">{{ t('editor.pages.bar_entities') }} <span class="f-value">{{ count }} / {{ scr.topbarMax }}</span></label>
        <label class="search-field"><Icon name="magnify" /><input id="new-page-entity" v-model="query" type="search" :placeholder="t('editor.topbar.add.search')" /></label>
        <div class="entity-options check-list">
          <CheckRow v-for="entity in matches.slice(0, 40)" :key="entity.id" class="entity-option" :checked="chosen.includes(entity.id)"
            :disabled="!chosen.includes(entity.id) && count >= scr.topbarMax" @toggle="toggle(entity.id)">
            <span class="mdi entity-icon" :style="{ color: tilePalette(entity.id, entities.liveOf(entity.id)).icon, background: tilePalette(entity.id, entities.liveOf(entity.id)).circle }">{{ glyph(entities.automaticIcon(entity.id)) }}</span>
            <span class="entity-text"><b>{{ entity.name }}</b><small>{{ [entity.area, entity.id].filter(Boolean).join(' · ') }}</small></span>
          </CheckRow>
          <small v-if="!matches.length" class="help">{{ t('editor.topbar.add.none_found') }}</small>
          <small v-else-if="matches.length > 40" class="help">{{ t('editor.common.results', matches.length) }}</small>
        </div>
      </div>
      <footer><button type="button" class="btn quiet" @click="emit('close')">{{ t('editor.common.cancel') }}</button>
        <button type="submit" class="btn primary" :disabled="invalidTitle || count > scr.topbarMax"><Icon name="plus" />{{ t('editor.layout.add_page') }}</button></footer>
    </form>
  </dialog>
</template>

<style scoped>
.page-wizard { width: 500px; max-width: calc(100vw - 24px); max-height: calc(100dvh - 24px); overflow: auto; padding: 22px 24px; border: 1px solid var(--line); border-radius: 16px; background: var(--surface); color: var(--ink); box-shadow: var(--shadow); }
.page-wizard::backdrop { background: rgb(10 12 18 / .45); }
form { display: grid; gap: 18px; }
header, footer { display: flex; align-items: center; gap: 10px; }
header { justify-content: space-between; } h2 { margin: 0; font-size: 18px; }
footer { justify-content: flex-end; }
.wizard-group { display: grid; gap: 8px; }
.wizard-group h3 { font-size: 12.5px; margin-bottom: 2px; }
.entity-options { max-height: 230px; overflow-y: auto; border: 1px solid var(--line); border-radius: 10px; padding: 4px; }
.entity-icon { display: grid; place-items: center; width: 30px; height: 30px; border-radius: 50%; flex: none; font-size: 17px; }
.entity-text { display: grid; min-width: 0; }
.entity-text b { font-weight: 500; font-size: 12.5px; }
.entity-text small { color: var(--muted); font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
