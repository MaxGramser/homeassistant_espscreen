<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { t } from '../i18n';
import { clone, emptyPage, instanceId } from '../model/pages';
import { matchesQuery } from '../model/search';
import { tilePalette } from '../model/tile-palette';
import { glyph } from '../model/topbar';
import type { HeaderItem } from '../types';
import CheckRow from './ui/CheckRow.vue';
import rules from '../model/page-rules.json';
import Icon from './ui/Icon.vue';
import SwitchRow from './ui/SwitchRow.vue';
import TesseraMark from './TesseraMark.vue';
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
const title = ref(''), home = ref(true), clock = ref(true), query = ref('');
const chosen = ref<string[]>([]);
const count = computed(() => chosen.value.length + Number(clock.value));
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
  if (!home.value) page.topbar.leading = [];
  page.topbar.trailing = [
    ...(clock.value ? [{ id: instanceId(), type: 'clock' } as HeaderItem & { id: string }] : []),
    ...chosen.value.map(entity => ({ id: instanceId(), type: 'entity', entity, content: 'state', icon: 'auto', show: 'always' } as HeaderItem & { id: string })),
  ];
  if (addPage(page.topbar)) emit('close');
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
      <div v-if="scr.pageReady" class="wizard-group">
        <h3>{{ t('editor.topbar.title') }}</h3>
        <SwitchRow class="bar-choice home-choice" :label="t('editor.pages.home_control')" v-model="home"><template #icon><TesseraMark /></template></SwitchRow>
        <SwitchRow class="bar-choice clock-choice" icon="clock-outline" :label="t('editor.pages.clock_control')" :disabled="!clock && count >= scr.topbarMax" v-model="clock" />
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
.wizard-group { display: grid; gap: 2px; }
.wizard-group h3 { font-size: 12.5px; margin-bottom: 2px; }
.entity-options { max-height: 230px; overflow-y: auto; border: 1px solid var(--line); border-radius: 10px; padding: 4px; }
.entity-icon { display: grid; place-items: center; width: 30px; height: 30px; border-radius: 50%; flex: none; font-size: 17px; }
.entity-text { display: grid; min-width: 0; }
.entity-text b { font-weight: 500; font-size: 12.5px; }
.entity-text small { color: var(--muted); font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
