<script setup lang="ts">
// New screen's first step: which screen. A search, the sizes, and every family of boards drawn as it hangs, in two
// sections (app 0.4.102): the proven boards first and larger, then the new and experimental ones under a heading that
// says what that means (model/installer.ts, familyTiers). A double click goes on to the next step.
import { computed } from "vue";
import { boardTitle } from "../../model/boards";
import { boardArt, boardFamilies, boardsMatching, familyLead, familyLines, familyStatus, familyTiers, sizeCount, SIZES, type BoardRow } from "../../model/installer";
import { injectInstaller } from "../../composables/useInstaller";
import { t } from "../../i18n";
import DeviceArt from "../DeviceArt.vue";
import Icon from "../ui/Icon.vue";

const install = injectInstaller();
const emit = defineEmits<{ next: [] }>();
const shown = computed(() => boardsMatching(install.boardRows, install.query, install.size));
const tiers = computed(() => familyTiers(boardFamilies(shown.value)));
const sections = computed(() => [
  { key: "proven", families: tiers.value.proven },
  { key: "trying", families: tiers.value.trying },
].filter((section) => section.families.length));
function pickFamily(family: BoardRow[]) { if (!family.some((board) => board.key === install.form.board)) install.form.board = familyLead(family).key; }
</script>

<template>
  <section class="setup-step pick">
    <h1 id="install-title">{{ t("editor.installer.pick_title") }}</h1>
    <p class="setup-lead">{{ t("editor.installer.pick_intro") }}</p>
    <div class="pick-tools">
      <label class="pick-search"><Icon name="magnify" /><input id="board-search" v-model="install.query" type="search" :placeholder="t('editor.installer.search')" autocomplete="off" spellcheck="false" /></label>
      <div class="seg pick-sizes" role="group" :aria-label="t('editor.installer.board')">
        <button v-for="key in SIZES" :key="key" type="button" :aria-pressed="install.size === key" @click="install.size = key">{{ t(`editor.installer.sizes.${key || "all"}`) }} <small>{{ sizeCount(install.boardRows, key) }}</small></button>
      </div>
    </div>
    <section v-for="section in sections" :key="section.key" class="board-tier" :class="section.key" :aria-labelledby="`boards-${section.key}`">
      <header class="board-tier-head">
        <h2 :id="`boards-${section.key}`"><Icon v-if="section.key === 'proven'" name="check-circle" />{{ t(`editor.installer.tiers.${section.key}.title`) }}</h2>
        <p>{{ t(`editor.installer.tiers.${section.key}.lead`) }}</p>
      </header>
      <fieldset class="boards">
        <legend class="sr-only">{{ t(`editor.installer.tiers.${section.key}.title`) }}</legend>
        <label v-for="family in section.families" :key="family[0].key" class="board" :class="{ chosen: family.some((b) => b.key === install.form.board) }" @dblclick="pickFamily(family); emit('next')">
          <input type="radio" name="board" :value="familyLead(family).key" :checked="family.some((b) => b.key === install.form.board)" @change="pickFamily(family)" />
          <span class="board-art" aria-hidden="true" :style="{ '--inch': family[0].inch }"><DeviceArt v-bind="boardArt(family[0])" /></span>
          <span class="board-words"><b>{{ boardTitle(family[0]) }}</b><small v-for="line in familyLines(family)" :key="line">{{ line }}</small></span>
          <em v-if="familyStatus(family) !== 'stable'" class="board-badge" :class="familyStatus(family)">{{ t(`editor.installer.status.${familyStatus(family)}`) }}</em>
          <span class="board-check" aria-hidden="true"><Icon name="check" /></span>
        </label>
      </fieldset>
    </section>
    <p v-if="!shown.length" class="pick-none">{{ t("editor.installer.none_found", { query: install.query.trim() }) }}</p>
    <button type="button" class="btn link try-virtual" id="try-virtual" @click="install.tryVirtual">{{ t("editor.installer.try_virtual") }}</button>
  </section>
</template>
