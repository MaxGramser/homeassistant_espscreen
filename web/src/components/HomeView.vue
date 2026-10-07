<script setup lang="ts">
// The add-on's home (app 0.4.0): every screen of the house with its home page as it stands on the glass right now, the
// page shown when no screen is chosen and where the logo leads. A click on a screen opens it in the editor.
import { computed, onMounted, reactive } from "vue";
import { t } from "../i18n";
import { barMetricsFor } from "../model/topbar";
import { boardTitle } from "../model/boards";
import { drawsPictures, go, homeView, loadOverview, phone, screenLight, screenSubline, select, setFullEditor, state } from "../store";
import UiMenu from "./ui/UiMenu.vue";
import UiMenuItem from "./ui/UiMenuItem.vue";
import UiMenuSeparator from "./ui/UiMenuSeparator.vue";
import { previewShapeOf } from "../model/preview";
import type { Screen } from "../types";
import FirmwarePreview from "./FirmwarePreview.vue";
import DonateCard from "./DonateCard.vue";
import TileCard from "./TileCard.vue";
import TopbarSvg from "./TopbarSvg.vue";
import Icon from "./ui/Icon.vue";

// The glass stands in a band of one height, whatever its shape, so a row of screens reads as one row.
const STAGE = 196;
const views = computed(() => state.inventory.screens.map((screen) => {
  const view = homeView(screen), record = screen.page_document;
  // The screen's own firmware draws its saved home page when the preview knows its board; the mockup stays until then.
  const live = view && record?.format === "pages-v2" ? previewShapeOf(screen, record.sourceGrid) : null;
  return { screen, view, live, layout: record?.format === "pages-v2" ? record.layout : null };
}));
const drawn = reactive(new Set<string>());
const failed = reactive(new Set<string>());
const liveWidth = (shape: { width: number; height: number }) => `min(100%, ${Math.round(STAGE * shape.width / shape.height)}px)`;
const online = computed(() => state.inventory.screens.filter((screen) => screen.online).length);
const scale = (style: Record<string, string>, shape: { width: number; height: number }) => {
  const width = parseFloat(style["--mockup-width"]), height = width * shape.height / shape.width + 20;
  return Math.min(1, STAGE / height);
};
const place = (screen: Screen) => [screen.area, screen.board && screen.shape?.catalog?.name ? boardTitle(screen.shape.catalog) : ""].filter(Boolean).join(" · ");
onMounted(loadOverview);
</script>

<template>
  <section id="home" class="home">
    <header class="home-head">
      <!-- On a phone the sidebar's row is gone (app 0.4.40): search, alerts, settings and a new screen are in this menu. -->
      <UiMenu v-if="phone" width="240px">
        <template #trigger><button type="button" class="icon-btn home-more" :aria-label="t('editor.screen_view.more')"><Icon name="dots-horizontal" /></button></template>
        <UiMenuItem icon="magnify" @select="state.palette = true">{{ t("editor.sidebar.search") }}</UiMenuItem>
        <UiMenuItem icon="alert-circle-outline" @select="go('#alerts')">{{ t("editor.nav.alerts") }}</UiMenuItem>
        <UiMenuItem icon="cog-outline" @select="go('#settings')">{{ t("editor.nav.settings") }}</UiMenuItem>
        <UiMenuItem icon="plus" @select="go('#new-screen')">{{ t("editor.nav.new_screen") }}</UiMenuItem>
        <UiMenuSeparator />
        <UiMenuItem icon="monitor-dashboard" @select="setFullEditor(true)">{{ t("editor.phone.full_editor") }}</UiMenuItem>
      </UiMenu>
      <h1>{{ t("editor.home.title") }}</h1>
      <p>{{ t("editor.home.summary", { online, count: state.inventory.screens.length }) }}</p>
    </header>
    <div class="home-grid">
      <div v-for="{ screen, view, live, layout } in views" :key="screen.id" role="button" tabindex="0" class="home-card" :class="{ away: !screen.online }"
        :aria-label="t('editor.home.open', { name: screen.name })" @click="select(screen.id)" @keydown.enter.prevent="select(screen.id)" @keydown.space.prevent="select(screen.id)">
        <span class="home-stage">
          <span v-if="live && layout && !failed.has(screen.id)" class="home-live" :style="{ width: liveWidth(live) }" aria-hidden="true">
            <FirmwarePreview :key="`${screen.id}:${JSON.stringify(live)}`" :width="live.width" :height="live.height" :dpi="live.dpi"
              :columns="live.columns" :rows="live.rows" :layout="layout" :pictures="drawsPictures(screen)" still
              @ready="drawn.add(screen.id)" @failed="failed.add(screen.id)" />
          </span>
          <span v-if="view && !(live && layout && drawn.has(screen.id) && !failed.has(screen.id))" class="home-glass"
            :style="{ zoom: scale(view.style, view.shape) }" aria-hidden="true">
            <span class="page home-page" :style="view.style">
              <span class="device" :class="{ compact: view.compact }">
                <TopbarSvg :items="view.items" :name-text="view.title" :home="view.home" :metrics="barMetricsFor(view.shape)" />
                <span class="tiles">
                  <TileCard v-for="entry in view.tiles" :key="entry.tile.id" :tile="entry.tile" :slot="entry.slot" :grid="view.grid" preview
                    :keys="view.keys.filter((key) => key.in === entry.tile.entity)" />
                </span>
              </span>
            </span>
          </span>
          <span v-else class="home-empty"><Icon name="view-dashboard-outline" />{{ t("editor.home.no_layout") }}</span>
        </span>
        <span class="home-foot">
          <span class="led" :class="screenLight(screen)"></span>
          <span class="home-name">
            <strong>{{ screen.name }}</strong>
            <small v-if="screenSubline(screen)" :class="screenSubline(screen)!.kind">{{ screenSubline(screen)!.text }}</small>
            <small v-else-if="place(screen)">{{ place(screen) }}</small>
          </span>
          <!-- A screen with 4 MB of flash on ESPHome's partition table (app 0.4.82): its next update comes from Tessera. -->
          <span v-if="screen.update_in_tessera" class="home-badge" :title="t('editor.sidebar.update.in_tessera_why')">
            <Icon name="information-outline" />{{ t("editor.home.in_tessera") }}
          </span>
          <Icon name="chevron-right" class="home-go" />
        </span>
      </div>
      <button type="button" class="home-new" @click="go('#new-screen')"><Icon name="plus" class="home-plus" />{{ t("editor.nav.new_screen") }}</button>
    </div>
    <DonateCard />
  </section>
</template>

<style scoped>
.home { padding: 28px 28px 40px; display: grid; gap: 20px; align-content: start; }
.home-head h1 { font-size: 20px; }
.home-head p { color: var(--muted); margin-top: 2px; }
.home-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); gap: 16px; }
.home-card { display: grid; cursor: pointer; grid-template-rows: auto auto; background: var(--surface); border: 1px solid var(--line); border-radius: 16px; overflow: hidden;
  text-align: left; transition: border-color 0.12s, box-shadow 0.12s, transform 0.12s; }
.home-card:hover { border-color: var(--line-strong); box-shadow: var(--shadow); transform: translateY(-1px); }
.home-stage { height: 236px; display: grid; place-items: center; background: var(--surface-2); border-bottom: 1px solid var(--line); padding: 20px; }
/* The live screen and the mockup it replaces share one place, the live one on top. */
.home-stage > * { grid-area: 1 / 1; }
.home-live { display: block; z-index: 1; border-radius: 4px; overflow: hidden; box-shadow: 0 1px 2px rgba(20, 24, 40, 0.1); }
.home-card.away .home-live { opacity: 0.55; filter: grayscale(0.6); }
/* The mockup at the editor's own size, drawn smaller as a whole: its type and spacing stay the screen's. */
.home-glass { display: block; pointer-events: none; }
.home-page { display: block; }
.home-page .device { display: grid; width: var(--mockup-width); box-shadow: 0 1px 2px rgba(20, 24, 40, 0.1); }
.home-page .tiles { display: grid; }
.home-card.away .home-glass { opacity: 0.55; filter: grayscale(0.6); }
.home-empty { display: grid; justify-items: center; gap: 6px; color: var(--muted); font-size: 12.5px; }
.home-empty .ui-icon { font-size: 26px; }
.home-foot { display: flex; align-items: center; gap: 12px; padding: 12px 14px; min-width: 0; }
.home-foot .led { position: relative; top: auto; right: auto; flex: none; box-shadow: none; }
.home-name { display: grid; min-width: 0; flex: 1; }
.home-name strong { font-size: 13.5px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.home-name small { font-size: 11.5px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.home-name small.down, .home-name small.failed { color: var(--danger); }
.home-name small.update, .home-name small.available, .home-name small.running, .home-name small.queued { color: var(--warn); }
.home-badge { flex: none; display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px 2px 6px; border-radius: 999px; font-size: 11.5px;
  font-weight: 500; color: var(--accent); background: var(--accent-soft); white-space: nowrap; }
.home-badge .ui-icon { font-size: 14px; }
.home-go { color: var(--muted); font-size: 18px; }
.home-card:hover .home-go { color: var(--accent); }
/* Adding a screen: a quiet dashed card beside the screens, never as tall as one. */
.home-new { align-self: start; display: flex; align-items: center; justify-content: center; gap: 8px; min-height: 64px; border: 1.5px dashed var(--line-strong);
  border-radius: 16px; color: var(--muted); font-weight: 500; }
.home-new:hover { color: var(--accent); border-color: var(--accent); background: var(--accent-soft); }
.home-plus { font-size: 18px; }
@media (max-width: 640px) {
  .home { padding: 18px 14px 32px; }
  .home-grid { grid-template-columns: minmax(0, 1fr); }
}
</style>
