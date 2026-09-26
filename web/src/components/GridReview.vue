<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { t } from '../i18n';
import { titleOf } from '../model/pages';
import { acceptGridReview, state } from '../store';
const dialog = ref<HTMLDialogElement>();
const review = computed(() => state.gridReview!);
const shape = (grid: { columns: number; rows: number }) => `${grid.columns} × ${grid.rows}`;
onMounted(() => dialog.value?.showModal());
</script>
<template>
  <dialog ref="dialog" class="grid-review" @cancel.prevent="state.gridReview = null">
    <h3>{{ t('editor.pages.grid_review') }}</h3>
    <p>{{ t('editor.pages.grid_review_hint') }}</p>
    <section v-for="(page, index) in review.layout.pages" :key="page.id">
      <b>{{ index + 1 }} · {{ titleOf(review.layout, page) }}</b>
      <div class="grid-comparison">
        <div v-for="(version, at) in [{ page: review.record.layout.pages[index], grid: review.record.sourceGrid }, { page, grid: review.target }]" :key="at">
          <small>{{ shape(version.grid) }}</small>
          <div class="placement-grid" :style="{ gridTemplateColumns: `repeat(${version.grid.columns}, 1fr)`, gridTemplateRows: `repeat(${version.grid.rows}, 44px)` }">
            <div v-for="(tile, tileIndex) in version.page.tiles" :key="tile.id" :style="{ gridColumn: `${tile.placement.column + 1} / span ${tile.placement.columns}`, gridRow: `${tile.placement.row + 1} / span ${tile.placement.rows}` }"
              :title="tile.appearance.label">{{ tileIndex + 1 }} · {{ tile.appearance.label || (tile.content.kind === 'entity' ? tile.content.entityId : '') }}</div>
          </div>
        </div>
      </div>
    </section>
    <footer><button class="btn quiet" @click="state.gridReview = null">{{ t('editor.common.cancel') }}</button><button class="btn primary" @click="acceptGridReview">{{ t('editor.pages.grid_accept') }}</button></footer>
  </dialog>
</template>
<style scoped>
.grid-review { width: 700px; max-width: calc(100vw - 24px); max-height: calc(100dvh - 24px); color: var(--ink); background: var(--surface); border: 1px solid var(--line); border-radius: 16px; padding: 24px; overflow: auto; }
.grid-review::backdrop { background: rgb(10 12 18 / .5); }
p, small { color: var(--muted); }
section { margin: 20px 0; }
.grid-comparison { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 8px; }
.placement-grid { display: grid; gap: 4px; padding: 5px; border: 1px solid var(--line); border-radius: 8px; margin-top: 6px; }
.placement-grid > div { background: var(--surface-2); border: 1px solid var(--accent); border-radius: 5px; padding: 5px; overflow: hidden; font-size: 11px; }
footer { display: flex; justify-content: flex-end; gap: 10px; }
</style>
