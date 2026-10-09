<script setup lang="ts">
// What a plugin asks for before it goes on a screen: its inputs (a key, a pin, a name) and its optional parts. A key
// is asked once for all chosen screens; a pin or a name per screen, because each board has its own free pins.
import { editorLanguage, languageMarks, numberText, t, te } from "../i18n";
import { freePins, text, type Plugin } from "../model/plugins";
import { entitiesIn, partsOn, plugins, setParts, setValue, valueOf } from "../plugin-state";
import type { Screen } from "../types";

// `only` shows one half, for a plugin a screen already runs: "shared" its inputs for every screen, "screen" this
// screen's own inputs and its parts.
const props = defineProps<{ plugin: Plugin; screens: Screen[]; only?: "shared" | "screen" }>();
const showShared = () => props.only !== "screen";
const showScreen = () => props.only !== "shared";
const kb = (value: number) => numberText(value, languageMarks(editorLanguage()));
const shared = () => (props.plugin.inputs || []).filter((input) => input.scope === "all");
const perScreen = () => (props.plugin.inputs || []).filter((input) => input.scope === "screen");
// The entities an input of kind entity takes: those of its domains in Home Assistant.
const entitiesOf = (domains: string[] = []) => entitiesIn(domains);
function setAll(id: string, value: string) { props.screens.forEach((screen) => setValue(screen, props.plugin, id, value)); }
function togglePart(id: string, on: boolean) {
  for (const screen of props.screens) {
    const now = partsOn(screen, props.plugin).filter((part) => part !== id);
    setParts(screen, props.plugin, on ? [...now, id] : now);
  }
}
// A part that uses a feature (a speaker) is built only on a screen that has it: there it is a choice, elsewhere it says why not.
const lacking = (features: string[] = []) => features.filter((f) => props.screens.some((screen) => !(plugins.features[screen.id] || []).includes(f)));
const featureWord = (name: string) => (te(`editor.plugins.features.${name}`) ? t(`editor.plugins.features.${name}`) : name);
const partOn = (id: string) => props.screens.length > 0 && props.screens.every((screen) => partsOn(screen, props.plugin).includes(id));
</script>

<template>
  <div v-if="screens.length && ((plugin.inputs || []).length || (plugin.parts || []).length)" class="pd-setup">
    <div v-for="input in showShared() ? shared() : []" :key="input.id" class="field">
      <label class="f-label" :for="`plugin-input-${input.id}`">{{ text(input.label) }}</label>
      <input :id="`plugin-input-${input.id}`" :type="input.kind === 'secret' ? 'password' : 'text'" autocomplete="off" spellcheck="false"
        :value="valueOf(screens[0], plugin, input.id)" @input="setAll(input.id, ($event.target as HTMLInputElement).value)" />
      <small v-if="input.kind === 'secret' && plugins.secrets[plugin.id]?.[input.id]">{{ t("editor.plugins.setup.secret_set") }}</small>
      <small v-else-if="input.hint">{{ text(input.hint) }}</small>
    </div>
    <template v-for="screen in showScreen() ? screens : []" :key="screen.id">
      <div v-for="input in perScreen()" :key="`${screen.id}-${input.id}`" class="field">
        <label class="f-label" :for="`plugin-input-${screen.id}-${input.id}`">{{ screens.length > 1 ? t("editor.plugins.setup.on_screen", { label: text(input.label), screen: screen.name }) : text(input.label) }}</label>
        <select v-if="input.kind === 'gpio'" :id="`plugin-input-${screen.id}-${input.id}`" :value="valueOf(screen, plugin, input.id)" @change="setValue(screen, plugin, input.id, ($event.target as HTMLSelectElement).value)">
          <option value="" disabled>{{ t("editor.plugins.setup.choose_pin") }}</option>
          <option v-for="pin in freePins(screen)" :key="pin" :value="pin">{{ pin }}</option>
        </select>
        <select v-else-if="input.kind === 'entity'" :id="`plugin-input-${screen.id}-${input.id}`" :value="valueOf(screen, plugin, input.id)" @change="setValue(screen, plugin, input.id, ($event.target as HTMLSelectElement).value)">
          <option value="" disabled>{{ t("editor.plugin_tile.choose") }}</option>
          <option v-for="entity in entitiesOf(input.domains)" :key="entity.id" :value="entity.id">{{ entity.name || entity.id }}</option>
        </select>
        <input v-else :id="`plugin-input-${screen.id}-${input.id}`" type="text" autocomplete="off" :value="valueOf(screen, plugin, input.id)"
          @input="setValue(screen, plugin, input.id, ($event.target as HTMLInputElement).value)" />
        <small v-if="input.hint">{{ text(input.hint) }}</small>
      </div>
    </template>
    <label v-for="part in showScreen() ? plugin.parts || [] : []" :key="part.id" class="pd-part" :class="{ off: lacking(part.features).length }">
      <input type="checkbox" :checked="partOn(part.id) && !lacking(part.features).length" :disabled="lacking(part.features).length > 0" :data-part="part.id" @change="togglePart(part.id, ($event.target as HTMLInputElement).checked)" />
      <span><b>{{ text(part.label) }}</b><small>{{ lacking(part.features).length ? t("editor.plugins.setup.part_needs", { what: lacking(part.features).map(featureWord).join(", ") })
        : `${text(part.hint)} · ${t("editor.plugins.setup.part_kb", { kb: kb(part.flash_kb) })}` }}</small></span>
    </label>
  </div>
</template>
