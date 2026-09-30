<script setup lang="ts">
// A page's settings (app 0.3.19): what stands above it, how you get to it, its top bar, and on the map where it
// stands and which tiles lead to it. The title of a page lives here and only here; the screen's own title, which every
// page without one says, waits behind a link under it.
import { computed, ref } from "vue";
import { t } from "../i18n";
import { connections, titleOf } from "../model/pages";
import { beginFieldEdit, endFieldEdit } from '../store';
import { currentScreen, duplicateEditorPage, pageCopyable, homeKeyShown, pageTitleShown, movePage, moveWorkspacePage, openBar, openTile, pageReady, pageTitle, removePage, screenTitle,
  setHomePage, setPageExcluded, setPageHomeControl, setPageTitle, state, topbarItems, topbarMax, workspacePositions } from "../store";
import { textDraft } from '../model/text-draft';
import { noTitle, setScreenTitle } from '../store';
import TopbarSvg from "./TopbarSvg.vue";
import Segmented from "./Segmented.vue";
import Icon from "./ui/Icon.vue";
import InspectorHead from "./ui/InspectorHead.vue";
import Section from "./ui/Section.vue";
import SwitchRow from "./ui/SwitchRow.vue";
import HelpTip from "./HelpTip.vue";

const props = defineProps<{ id: string }>();
const page = computed(() => state.document?.pages.find((item) => item.id === props.id));
const index = computed(() => state.document?.pages.findIndex((item) => item.id === props.id) ?? -1);
const count = computed(() => state.document?.pages.length || 0);
const home = computed(() => state.document?.homePageId === props.id);
const point = computed(() => workspacePositions()[props.id] || { x: 0, y: 0 });
const routes = computed(() => state.document ? connections(state.document).filter((route) => route.from === props.id || route.to === props.id) : []);
const name = (id: string) => { const page = state.document?.pages.find((item) => item.id === id); return page ? titleOf(state.document!, page) : ""; };
const canCopy = computed(() => pageCopyable(page.value?.tiles));
function editRoute(tileId: string) { const tile = state.layout?.tiles.find((item) => item.id === tileId); if (tile) openTile(tile); }
// One page and the screen's title are one thing: a single field. A page that kept a title of its own from a longer
// row keeps its own field, so nothing is set that nobody can see.
const ownTitle = computed(() => count.value > 1 || !!pageTitle(index.value));
// Firmware 0.17.0+ takes a screen without a title: an empty field leaves the home key alone in the top bar.
const titleDraft = textDraft(screenTitle, setScreenTitle, () => !noTitle.value);
// A page's own title keeps the spaces you type while you type, and is saved without the ones at its ends (app 0.4.2).
const pageTitleDraft = textDraft(() => page.value?.topbar.title.source === 'text' ? page.value.topbar.title.text : '', (value) => setPageTitle(index.value, value));
const screenTitleOpen = ref(false);
const orders = computed(() => (state.document?.pages || []).map((_, at) => [at, String(at + 1)] as [number, string]));
const barItems = computed(() => topbarItems(index.value));
const tiles = computed(() => page.value?.tiles.length || 0);
</script>

<template>
  <template v-if="page">
    <InspectorHead :title="t('editor.page.label', { page: index + 1 })" :icon="home ? 'home' : 'view-column-outline'"
      :crumbs="[{ text: currentScreen?.name || '' }, { text: name(id) }]" />
    <div class="dr-body">
      <Section :title="t('editor.pages.sections.title')" icon="format-title">
        <div v-if="ownTitle" class="f">
          <span class="f-label"><label for="owned-page-title">{{ t('editor.pages.title') }}</label><HelpTip :text="t('editor.pages.title_hint')" /></span>
          <input id="owned-page-title" :value="pageTitleDraft.value.value" :placeholder="state.document?.title"
            maxlength="60" @focus="beginFieldEdit(`page:${id}`); pageTitleDraft.focus()" @blur="endFieldEdit(); pageTitleDraft.blur()"
            @input="pageTitleDraft.input(($event.target as HTMLInputElement).value)" />
          <button type="button" class="disclosure" :aria-expanded="screenTitleOpen ? 'true' : 'false'" @click="screenTitleOpen = !screenTitleOpen">
            <Icon :name="screenTitleOpen ? 'chevron-down' : 'chevron-right'" />{{ t('editor.topbar.screen_name') }}
          </button>
        </div>
        <div v-if="!ownTitle || screenTitleOpen" class="f" :class="{ nested: ownTitle }">
          <span class="f-label"><label for="screen-title">{{ ownTitle ? t('editor.topbar.screen_name') : t('editor.topbar.name') }}</label><HelpTip v-if="ownTitle" id="screen-title-hint" :text="t('editor.topbar.screen_name_hint')" /></span>
          <input id="screen-title" :value="titleDraft.value.value" maxlength="60" :placeholder="t('editor.topbar.name_placeholder')"
            @focus="beginFieldEdit('screen-title'); titleDraft.focus()" @blur="endFieldEdit(); titleDraft.blur()"
            @input="titleDraft.input(($event.target as HTMLInputElement).value)" />
          <small v-if="noTitle" class="help">{{ t('editor.topbar.no_title_hint') }}</small>
        </div>
      </Section>

      <Section :title="t('editor.pages.sections.navigation')" icon="gesture-swipe-horizontal">
        <div class="switch-row">
          <span class="sr-text"><span class="sr-label"><b>{{ t('editor.pages.is_home') }}</b><HelpTip :text="t('editor.pages.home_hint')" /></span></span>
          <span v-if="home" class="chip good"><Icon name="check" />{{ t('editor.pages.home_chip') }}</span>
          <button v-else type="button" class="btn quiet mini" :disabled="!pageReady" @click="setHomePage(id)"><Icon name="home-outline" />{{ t('editor.pages.set_home') }}</button>
        </div>
        <SwitchRow class="page-check" :label="t('editor.pages.include_navigation')" :description="t('editor.pages.include_navigation_hint')"
          :model-value="!page.navigation.excludeFromPagination" :disabled="!pageReady" @update:model-value="(on) => setPageExcluded(id, !on)" />
        <SwitchRow class="home-control" :label="t('editor.pages.home_control')"
          :model-value="!!page.topbar.leading.length" :disabled="!pageReady" @update:model-value="(on) => setPageHomeControl(id, on)" />
        <div v-if="count > 1" class="f">
          <span class="f-label"><span id="page-order-label">{{ t('editor.pages.order') }}</span><HelpTip :text="t('editor.pages.order_hint')" /></span>
          <Segmented id="page-order" :choices="orders" :value="index" aria-labelledby="page-order-label" @pick="(to) => movePage(index, Number(to))" />
        </div>
      </Section>

      <Section :title="t('editor.topbar.title')" icon="page-layout-header">
        <button type="button" class="nav-row" :aria-label="t('editor.pages.edit_topbar')" :title="t('editor.pages.edit_topbar')" @click="openBar(0, index)">
          <span class="bar-preview"><TopbarSvg :items="barItems" :name-text="pageTitleShown(index)" :home="homeKeyShown(index)" /></span>
          <span class="nav-row-end"><small>{{ t('editor.topbar.items', { used: barItems.length }, topbarMax()) }}</small><Icon name="chevron-right" /></span>
        </button>
      </Section>

      <Section v-if="state.editorMode === 'advanced'" :title="t('editor.pages.view_map')" icon="sitemap-outline">
        <div class="f">
          <span class="f-label">{{ t('editor.pages.routes') }}</span>
          <button v-for="route in routes" :key="route.tileId" class="route-row" type="button" @click="editRoute(route.tileId)">
            <span class="route-page">{{ name(route.from) }}</span><Icon name="arrow-right" /><span class="route-page">{{ name(route.to) }}</span>
            <Icon name="chevron-right" class="route-end" />
          </button>
          <small v-if="!routes.length" class="help">{{ t('editor.pages.no_routes') }}</small>
        </div>
        <div class="switch-row">
          <span class="sr-text"><b>{{ t('editor.pages.map_position') }}</b></span>
          <span class="map-move" role="group" :aria-label="t('editor.pages.map_position')">
            <button v-for="[dx, dy, key, icon] in ([[-1, 0, 'left', 'chevron-left'], [0, -1, 'up', 'chevron-up'], [0, 1, 'down', 'chevron-down'], [1, 0, 'right', 'chevron-right']] as const)"
              :key="key" class="icon-btn" type="button" :aria-label="t(`editor.pages.${key}`)"
              @click="moveWorkspacePage(id, point.x + dx, point.y + dy)"><Icon :name="icon" /></button>
          </span>
        </div>
        <button type="button" class="btn quiet" @click="state.focusedPageId = id; state.selectedPageId = id"><Icon name="pencil-outline" />{{ t('editor.pages.edit_page') }}</button>
      </Section>

      <div class="insp-actions">
        <button v-if="canCopy" class="btn quiet" type="button" @click="duplicateEditorPage(id, false)"><Icon name="content-duplicate" />{{ t('editor.pages.duplicate') }}</button>
        <button class="btn quiet" type="button" @click="duplicateEditorPage(id, true)"><Icon name="file-plus-outline" />{{ t('editor.pages.empty_copy') }}</button>
      </div>
    </div>
    <div class="dr-foot">
      <button class="btn danger" type="button" :disabled="count < 2" @click="removePage(index)"><Icon name="delete-outline" />{{ t('editor.page.remove') }}</button>
      <span class="spacer"></span>
      <small v-if="tiles && count > 1" class="help">{{ t('editor.pages.tiles_go', tiles) }}</small>
    </div>
  </template>
</template>

<style scoped>
.nested { padding-left: 12px; border-left: 2px solid var(--line); }
.bar-preview { flex: 1; min-width: 0; background: #e7e7e7; border-radius: 8px; padding: 3px 6px; display: block; }
.bar-preview :deep(svg) { display: block; width: 100%; height: auto; }
.map-move { display: inline-flex; gap: 2px; padding: 2px; border-radius: 9px; background: var(--seg); }
.map-move .icon-btn { width: 28px; height: 28px; }
.route-row { display: flex; align-items: center; gap: 6px; padding: 7px 8px; border-radius: 8px; background: var(--surface-2); text-align: left; font-size: 12.5px; color: var(--ink-2); }
.route-row:hover { background: var(--seg); color: var(--ink); }
.route-row > .ui-icon { color: var(--accent); }
.route-page { padding: 1px 7px; border-radius: 6px; background: var(--surface); border: 1px solid var(--line); color: var(--ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 40%; }
.route-end { margin-left: auto; color: var(--muted) !important; }
</style>
