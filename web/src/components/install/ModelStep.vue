<script setup lang="ts">
// New screen's question about the version (app 0.4.103), only for a screen sold in more than one: which model, by what is
// printed on its back, and the board's own choices (a CYD's display controller, a flash size), each starting at what
// most boards have.
import { computed } from "vue";
import { boardTitle } from "../../model/boards";
import { familyLead } from "../../model/installer";
import { injectInstaller } from "../../composables/useInstaller";
import { t, te } from "../../i18n";
import Icon from "../ui/Icon.vue";

const install = injectInstaller();
const lead = computed(() => (install.siblings.length ? familyLead(install.siblings).key : ""));
// A choice's value as New screen names it: its own words where the translations have them, else the value itself.
const optionLabel = (key: string, option: string) =>
  te(`editor.installer.choice_option.${key}.${option}`) ? t(`editor.installer.choice_option.${key}.${option}`) : option;
</script>

<template>
  <section class="ob-step model" data-step="model">
    <h1>{{ t("editor.installer.flow.model_title") }}</h1>
    <p class="ob-lead">{{ install.siblings.length > 1
      ? t("editor.installer.flow.model_lead", { name: install.chosen ? boardTitle(install.chosen) : "", n: install.siblings.length })
      : t("editor.installer.flow.choice_lead") }}</p>

    <fieldset v-if="install.siblings.length > 1" id="board-model" class="ob-rows">
      <legend class="sr-only">{{ t("editor.installer.model") }}</legend>
      <label v-for="board in install.siblings" :key="board.key" class="ob-row" :class="{ chosen: install.form.board === board.key }">
        <input type="radio" name="model" :value="board.key" v-model="install.form.board" />
        <span class="ob-row-words"><b class="ob-code">{{ board.model }}</b>
          <small v-if="board.key === lead">{{ t("editor.installer.flow.model_usual") }}</small></span>
        <em v-if="board.status !== 'stable'" class="ob-tag" :class="board.status">{{ t(`editor.installer.flow.status.${board.status}`) }}</em>
        <span class="ob-tick" aria-hidden="true"><Icon name="check" /></span>
      </label>
    </fieldset>

    <fieldset v-for="choice in install.choices" :key="choice.key" class="ob-rows" :id="`choice-${choice.key}`">
      <legend class="ob-legend">{{ t(`editor.installer.choice.${choice.key}`) }}</legend>
      <label v-for="(option, index) in choice.options" :key="option" class="ob-row" :class="{ chosen: install.form.choices[choice.key] === option }">
        <input type="radio" :name="`choice-${choice.key}`" :value="option" v-model="install.form.choices[choice.key]" />
        <span class="ob-row-words"><b>{{ optionLabel(choice.key, option) }}</b><small v-if="index === 0">{{ t("editor.installer.choice_usual") }}</small></span>
        <span class="ob-tick" aria-hidden="true"><Icon name="check" /></span>
      </label>
      <small class="ob-hint">{{ t(`editor.installer.choice_hint.${choice.key}`) }}</small>
    </fieldset>
  </section>
</template>
