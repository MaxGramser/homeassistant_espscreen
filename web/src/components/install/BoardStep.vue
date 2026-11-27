<script setup lang="ts">
// New screen's first question, which screen (app 0.4.103): the recommended boards large, each drawn as it hangs, and
// behind "I have another screen" every board in one list to search, by brand, size or what is printed on it, with how
// far each has been tried (model/installer.ts familyTiers). A double click on a board goes on. Under them, "No screen
// yet?": the recommended screens the Tessera website has a shop link for (screen_manager/app/shops.py, app 0.4.110),
// with the photo through the app; nothing shows when the website can't be asked.
import { computed, onMounted, ref } from "vue";
import { getJson } from "../../api";
import { boardTitle } from "../../model/boards";
import { boardArt, boardFamilies, boardsMatching, familyLead, familyStatus, familyTiers, SIZES, type BoardRow } from "../../model/installer";
import { injectInstaller } from "../../composables/useInstaller";
import { t } from "../../i18n";
import DeviceArt from "../DeviceArt.vue";
import Icon from "../ui/Icon.vue";

const install = injectInstaller();
const all = computed(() => familyTiers(boardFamilies(install.boardRows)));
const shown = computed(() => {
  const tiers = familyTiers(boardFamilies(boardsMatching(install.boardRows, install.query, install.size)));
  return [...tiers.recommended, ...tiers.more];
});
const isChosen = (family: BoardRow[]) => family.some((board) => board.key === install.form.board);
function pick(family: BoardRow[]) { if (!isChosen(family)) install.form.board = familyLead(family).key; }
// What a person sees of a board before its name: its shape, and how many tiles a page of it holds lying down.
const line = (board: BoardRow) => {
  const art = boardArt(board);
  return `${t(board.square ? "editor.installer.flow.square" : "editor.installer.flow.wide")} · ${t("editor.installer.flow.tiles_a_page", art.columns * art.rows)}`;
};
// The line under a board in the list: what is printed on it, or how many versions there are.
const listLine = (family: BoardRow[]) => (family.length > 1 ? t("editor.installer.flow.versions", family.length) : family[0].model);

type Shop = { board: string; name: string | null; shop: string; url: string; discount: string | null; code: string | null; photo: boolean };
const shops = ref<Shop[]>([]);
onMounted(async () => {
  try {
    const answer = await getJson<{ shops?: Shop[] }>("shops");
    shops.value = Array.isArray(answer?.shops) ? answer.shops : [];
  } catch { shops.value = []; }
});
// A shop's screen named the way the cards above name it, when New screen knows the board.
const shopTitle = (shop: Shop) => {
  const board = install.boardRows.find((row) => row.key === shop.board);
  return board ? boardTitle(board) : shop.name || shop.board;
};
// The website writes a discount as "5% off"; a percentage is said in the editor's language, anything else as written.
const discount = (shop: Shop) => {
  const percent = /^(\d{1,2})\s*% off$/i.exec(shop.discount || "");
  return percent ? t("editor.installer.shops.off", { n: percent[1] }) : shop.discount;
};
// One line per shop and code, for whoever shops there without the link.
const codes = computed(() => [...new Map(shops.value.filter((shop) => shop.code).map((shop) => [`${shop.shop} ${shop.code}`, shop])).values()]);
</script>

<template>
  <section v-if="!install.browse" class="ob-step pick" data-step="board">
    <h1 id="install-title">{{ t("editor.installer.pick_title") }}</h1>
    <p class="ob-lead">{{ t("editor.installer.flow.pick_lead") }}</p>
    <fieldset class="ob-cards" :style="{ '--cards': all.recommended.length }">
      <legend class="sr-only">{{ t("editor.installer.pick_title") }}</legend>
      <label v-for="family in all.recommended" :key="family[0].key" class="ob-card" :class="{ chosen: isChosen(family) }" @dblclick="pick(family); install.next()">
        <input type="radio" name="board" :value="familyLead(family).key" :checked="isChosen(family)" @change="pick(family)" />
        <span class="ob-art" aria-hidden="true" :style="{ '--inch': family[0].inch }"><DeviceArt v-bind="boardArt(family[0])" /></span>
        <span class="ob-card-words"><b>{{ boardTitle(family[0]) }}</b><small>{{ line(familyLead(family)) }}</small></span>
        <span class="ob-tick" aria-hidden="true"><Icon name="check" /></span>
      </label>
    </fieldset>
    <p class="ob-soon">{{ t("editor.installer.flow.more_soon") }}</p>
    <button type="button" class="ob-more" id="board-other" @click="install.browse = true">{{ t("editor.installer.flow.other_screen") }}<Icon name="chevron-right" /></button>
    <section v-if="shops.length" class="ob-shops" aria-labelledby="ob-shops-title">
      <h2 id="ob-shops-title">{{ t("editor.installer.shops.title") }}</h2>
      <p class="ob-shops-lead">{{ t("editor.installer.shops.lead") }}</p>
      <div class="ob-shop-list">
        <div v-for="shop in shops" :key="shop.board" class="ob-shop">
          <img v-if="shop.photo" :src="`api/shops/${shop.board}/photo`" alt="" loading="lazy" />
          <div class="ob-shop-words">
            <b>{{ shopTitle(shop) }}</b>
            <small>{{ shop.shop }}</small>
            <a class="ob-shop-buy" :href="shop.url" target="_blank" rel="sponsored noopener">{{ shop.discount ? t("editor.installer.shops.buy_discount", { discount: discount(shop) }) : t("editor.installer.shops.buy") }}</a>
          </div>
        </div>
      </div>
      <p class="ob-shops-note">{{ [t("editor.installer.shops.note"), ...codes.map((shop) => t("editor.installer.shops.code", { shop: shop.shop, code: shop.code }))].join(" ") }}</p>
    </section>
  </section>

  <section v-else class="ob-step browse" data-step="board-list">
    <h1>{{ t("editor.installer.flow.which_is_it") }}</h1>
    <p class="ob-lead">{{ t("editor.installer.pick_intro") }}</p>
    <label class="ob-search"><Icon name="magnify" /><span class="sr-only">{{ t("editor.installer.search") }}</span>
      <input id="board-search" v-model="install.query" type="search" :placeholder="t('editor.installer.search')" autocomplete="off" spellcheck="false" /></label>
    <div class="ob-chips pick-sizes" role="group" :aria-label="t('editor.installer.board')">
      <button v-for="key in SIZES" :key="key" type="button" class="ob-chip" :aria-pressed="install.size === key" @click="install.size = key">{{ t(`editor.installer.sizes.${key || "all"}`) }}</button>
    </div>
    <fieldset class="ob-rows">
      <legend class="sr-only">{{ t("editor.installer.board") }}</legend>
      <label v-for="family in shown" :key="family[0].key" class="ob-row" :class="{ chosen: isChosen(family) }" @dblclick="pick(family); install.next()">
        <input type="radio" name="board" :value="familyLead(family).key" :checked="isChosen(family)" @change="pick(family)" />
        <span class="ob-row-art" aria-hidden="true" :style="{ '--inch': family[0].inch }"><DeviceArt v-bind="boardArt(family[0])" /></span>
        <span class="ob-row-words"><b>{{ boardTitle(family[0]) }}</b><small>{{ listLine(family) }}</small></span>
        <em v-if="familyStatus(family) !== 'stable'" class="ob-tag" :class="familyStatus(family)">{{ t(`editor.installer.flow.status.${familyStatus(family)}`) }}</em>
        <span class="ob-tick" aria-hidden="true"><Icon name="check" /></span>
      </label>
      <p v-if="!shown.length" class="pick-none">{{ t("editor.installer.none_found", { query: install.query.trim() }) }}</p>
    </fieldset>
  </section>
</template>
