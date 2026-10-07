<script setup lang="ts">
// What a favourite plays (app 0.4.42): the player's library as Home Assistant browses it, folder by folder, with the
// pictures the add-on prepares. A tap on something that plays chooses it; a folder opens; something that does both (an
// artist, a playlist) is chosen on a tap and opened with its arrow. Nothing here knows a brand: the folders, the titles
// and the pictures are Home Assistant's, through the add-on (api/media/browse). A player the add-on says plays a pasted
// link (app 0.4.84, `spotify_link`) also takes one: the add-on reads it (api/media/link) and answers an item like the
// library's, chosen the same way.
import { computed, ref, watch } from "vue";
import { getJson } from "../api";
import { t } from "../i18n";
import { glyph } from "../model/topbar";
import type { FavoritePlay } from "../types";
import Icon from "./ui/Icon.vue";

type Item = { item: number; title: string; play: boolean; expand: boolean; icon: string; picture: string | null; favorite: FavoritePlay | null };
const props = defineProps<{ entity: string; chosen?: FavoritePlay }>();
const emit = defineEmits<{ pick: [play: FavoritePlay] }>();

const trail = ref<{ folder: number; title: string }[]>([]);
const items = ref<Item[]>([]);
const loading = ref(false);
const failed = ref("");
const linkable = ref(false);
const link = ref("");
const linked = ref<Item | null>(null);
const linkFailed = ref("");
const linking = ref(false);
const title = computed(() => trail.value[trail.value.length - 1]?.title || "");
// The pictures of a folder that has them: a grid of covers; a folder of folders: rows.
const pictured = computed(() => items.value.some((item) => item.picture));

async function open(folder: number, name: string, back = false) {
  loading.value = true;
  failed.value = "";
  try {
    const answer = await getJson<{ title: string; folder: number; items: Item[]; spotify_link?: boolean }>(`media/browse?entity=${encodeURIComponent(props.entity)}&folder=${folder}`);
    items.value = answer.items;
    if (!folder) linkable.value = Boolean(answer.spotify_link);
    if (!back) trail.value = [...trail.value, { folder, title: answer.title || name }];
  } catch (error) {
    failed.value = error instanceof Error ? error.message : String(error);
  } finally {
    loading.value = false;
  }
}
function up() {
  if (trail.value.length < 2) return;
  trail.value = trail.value.slice(0, -1);
  const last = trail.value[trail.value.length - 1];
  void open(last.folder, last.title, true);
}
function tap(item: Item) {
  if (item.play && item.favorite) emit("pick", item.favorite);
  else if (item.expand) void open(item.item, item.title);
}
async function readLink() {
  const text = link.value.trim();
  if (!text || linking.value) return;
  linking.value = true;
  linkFailed.value = "";
  try {
    linked.value = await getJson<Item>(`media/link?entity=${encodeURIComponent(props.entity)}&link=${encodeURIComponent(text)}`);
  } catch (error) {
    linked.value = null;
    linkFailed.value = error instanceof Error ? error.message : String(error);
  } finally {
    linking.value = false;
  }
}
const isChosen = (item: Item) => Boolean(props.chosen && item.favorite && item.favorite.id === props.chosen.id && item.favorite.type === props.chosen.type);
watch(() => props.entity, () => {
  trail.value = []; linkable.value = false; link.value = ""; linked.value = null; linkFailed.value = "";
  void open(0, "");
}, { immediate: true });
</script>

<template>
  <div class="favorite-picker">
    <div class="picker-bar">
      <button v-if="trail.length > 1" type="button" class="icon-btn" :aria-label="t('editor.tile.favorite.back')" @click="up"><Icon name="arrow-left" /></button>
      <span class="picker-title">{{ title }}</span>
    </div>
    <p v-if="failed" class="help warn">{{ failed }}</p>
    <p v-else-if="loading && !items.length" class="help">{{ t('editor.tile.favorite.loading') }}</p>
    <p v-else-if="!items.length" class="help">{{ t('editor.tile.favorite.empty') }}</p>
    <div v-else class="picker-items" :class="{ grid: pictured, busy: loading }">
      <div v-for="item in items" :key="item.item" class="picker-item" :class="{ chosen: isChosen(item) }">
        <button type="button" class="pick" :disabled="!item.play && !item.expand" @click="tap(item)">
          <img v-if="pictured && item.picture" class="art" :src="item.picture" alt="" loading="lazy" />
          <span v-else class="badge mdi" aria-hidden="true">{{ glyph(item.icon) }}</span>
          <span class="name">{{ item.title }}</span>
        </button>
        <button v-if="item.play && item.expand" type="button" class="open icon-btn" :aria-label="t('editor.tile.favorite.open', { name: item.title })" @click="open(item.item, item.title)"><Icon name="chevron-right" /></button>
      </div>
    </div>
    <form v-if="linkable" class="picker-link" @submit.prevent="readLink">
      <label class="link-label" for="favorite-link">{{ t('editor.tile.favorite.link') }}</label>
      <div class="link-row">
        <input id="favorite-link" v-model="link" class="input" type="text" inputmode="url" autocomplete="off" spellcheck="false"
          placeholder="https://open.spotify.com/playlist/…" @input="linkFailed = ''" />
        <button type="submit" class="btn quiet mini" :disabled="!link.trim() || linking">{{ t('editor.tile.favorite.link_add') }}</button>
      </div>
      <p v-if="linkFailed" class="help warn">{{ linkFailed }}</p>
      <p v-else class="help">{{ t('editor.tile.favorite.link_hint') }}</p>
      <div v-if="linked" class="picker-item linked" :class="{ chosen: isChosen(linked) }">
        <button type="button" class="pick" @click="tap(linked)">
          <img v-if="linked.picture" class="art" :src="linked.picture" alt="" />
          <span v-else class="badge mdi" aria-hidden="true">{{ glyph(linked.icon) }}</span>
          <span class="name">{{ linked.title }}</span>
        </button>
      </div>
    </form>
  </div>
</template>

<style scoped>
.favorite-picker { display: flex; flex-direction: column; gap: 8px; }
.picker-bar { display: flex; align-items: center; gap: 6px; min-height: 28px; }
.picker-title { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.picker-items { display: flex; flex-direction: column; gap: 2px; max-height: 320px; overflow-y: auto; transition: opacity .12s; }
.picker-items.busy { opacity: .5; }
.picker-items.grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px 8px; }
.picker-item { position: relative; display: flex; align-items: center; min-width: 0; border-radius: 8px; }
.picker-items:not(.grid) .picker-item:hover { background: var(--hover, rgba(0, 0, 0, .04)); }
.pick { display: flex; align-items: center; gap: 8px; flex: 1; min-width: 0; padding: 6px; border: 0; background: none; color: inherit; font: inherit; text-align: left; cursor: pointer; border-radius: 8px; }
.grid .pick { flex-direction: column; align-items: stretch; padding: 0; gap: 4px; text-align: center; }
.art { width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 6px; background: var(--track, #e5e7eb); }
.badge { flex: none; width: 28px; height: 28px; border-radius: 50%; display: grid; place-items: center; background: #d9f2fd; color: #0c91ce; font-size: 16px; }
.name { min-width: 0; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; line-height: 1.25; font-size: .9em; }
.chosen .art { outline: 3px solid var(--accent, #03a9f4); outline-offset: 2px; }
.chosen .name { color: var(--accent, #03a9f4); }
.open { position: absolute; right: 2px; }
.picker-link { display: flex; flex-direction: column; gap: 6px; padding-top: 8px; border-top: 1px solid var(--line, rgba(0, 0, 0, .08)); }
.link-label { font-weight: 600; }
.link-row { display: flex; gap: 6px; }
.link-row .input { flex: 1; min-width: 0; }
.picker-link .help { margin: 0; }
.linked .pick { padding: 6px; }
.linked .art { width: 56px; flex: none; }
.grid .open { top: 4px; right: 4px; background: rgba(255, 255, 255, .85); border-radius: 50%; }
</style>
