<script setup lang="ts">
// A card a picture fills. A favourite (app 0.4.42): what it plays, dimmed as an album cover over a card is, with its name,
// its line and a round play key; on a screen without pictures the ordinary tile with the icon of what it plays. A live
// camera (app 0.3.13): the add-on's picture, cut the way the tile asks, with the name at the bottom or nothing on it.
// Until a picture is here, the head as on the screen. The card says once it has loaded (`loaded`): its look follows.
import { glyph } from "../../model/topbar";
import type { TileCardView } from "../../composables/useTileCard";

const props = defineProps<{ card: TileCardView }>();
// The same card for as long as this face stands (useTileCard): read without going through the props each time.
const card = props.card;
</script>

<template>
  <template v-if="card.face.kind === 'favorite'">
    <img v-if="card.favoritePicture" :key="card.favoritePicture" class="camera-art fill favorite-art" :src="card.favoritePicture" alt="" @load="card.loaded.favorite = true" @error="card.loaded.favorite = false" />
    <span v-if="!card.loaded.favorite" class="head"><span class="ic mdi">{{ glyph(card.favoriteIcon) }}</span><span class="tx"><span class="nm">{{ card.texts.name }}</span><span v-if="card.texts.favoriteLine" class="st">{{ card.texts.favoriteLine }}</span></span></span>
    <template v-else>
      <span class="favorite-text"><span class="nm">{{ card.texts.name }}</span><span v-if="card.texts.favoriteLine" class="st">{{ card.texts.favoriteLine }}</span></span>
      <span class="favorite-key mdi" aria-hidden="true">{{ glyph('F040A') }}</span>
    </template>
  </template>
  <template v-else>
    <img v-if="card.cameraPicture" :key="card.cameraPicture" class="camera-art" :class="card.tile.options?.fit === 'contain' ? 'contain' : 'fill'" :src="card.cameraPicture" alt="" @load="card.loaded.camera = true" @error="card.loaded.camera = false" />
    <span v-if="!card.loaded.camera" class="head"><span class="ic mdi">{{ glyph(card.icon) }}</span><span class="tx"><span class="nm">{{ card.texts.name }}</span><span v-if="card.texts.line" class="st" :class="{ off: card.gone }">{{ card.texts.line }}</span></span></span>
    <span v-else-if="card.tile.options?.overlay !== 'none'" class="camera-name"><span>{{ card.texts.name }}</span></span>
  </template>
</template>

<style scoped src="./parts.css"></style>
<style scoped>
.tile .camera-art { position: absolute; inset: 0; width: 100%; height: 100%; border-radius: inherit; background: #000; opacity: 0; pointer-events: none; }
.tile .camera-art.fill { object-fit: cover; }
.tile .camera-art.contain { object-fit: contain; }
.tile.camera .camera-art { opacity: 1; }
/* The shade the add-on puts under the name (tile_art.FADE_SHARE, FADE_DEPTH). */
.tile .camera-name { position: absolute; inset: auto 0 0 0; height: 42%; padding: 0 9px 8px; display: flex; align-items: end; color: white; font-weight: 700; background: linear-gradient(to bottom, transparent, rgba(0, 0, 0, .59)); border-bottom-left-radius: inherit; border-bottom-right-radius: inherit; pointer-events: none; }
.tile .camera-name > span { min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
/* A favourite (app 0.4.42): the picture dimmed as the screen dims it (a third of its light), the words and the key over it. */
.tile .favorite-art { filter: brightness(.333); }
.tile .favorite-text { position: absolute; inset: auto 0 0 0; padding: 0 calc(var(--key, 34px) + 14px) 8px 9px; display: flex; flex-direction: column; color: white; pointer-events: none; min-width: 0; }
.tile .favorite-text .nm { font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tile .favorite-text .st { font-size: .85em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tile .favorite-key { position: absolute; right: 8px; bottom: 8px; width: var(--key, 34px); height: var(--key, 34px); border-radius: 50%; background: #f2f2f2; color: #000; display: grid; place-items: center; font-size: 20px; pointer-events: none; }
</style>
