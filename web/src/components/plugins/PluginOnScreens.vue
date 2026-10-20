<script setup lang="ts">
// A plugin's details on the Plugins page: a box per screen, ticked where it is on, and what does not fit greyed out with
// its reason; the boxes apply together into the tray (adding sets it aside on each screen, taking it off is asked of the
// details around it, `remove`, and set aside as well), and the screens with an update take it at once. A box starts as
// the screen will be after the tray: on where it runs or is set aside, off where it is set aside to come off.
import { computed, reactive, watch } from "vue";
import { t } from "../../i18n";
import { applyText, text, type Plugin } from "../../model/plugins";
import type { Screen } from "../../types";
import PluginSetup from "../PluginSetup.vue";
import { usePluginsStore } from "../../stores/plugins";

const plugins = usePluginsStore();
const props = defineProps<{ plugin: Plugin }>();
const emit = defineEmits<{ remove: [screens: Screen[]] }>();

const screens = computed(() => plugins.realScreens());
const wanted = reactive<Record<string, boolean>>({});
const has = (screen: Screen) => Boolean(plugins.installedOn(screen, props.plugin.id));
const planned = (screen: Screen) => (has(screen) && !plugins.isTakingOff(screen, props.plugin.id)) || plugins.isSetAside(screen, props.plugin.id);
function reset() {
  for (const key of Object.keys(wanted)) delete wanted[key];
  for (const screen of screens.value) wanted[screen.id] = planned(screen);
}
watch([() => props.plugin.id, () => screens.value.map((s) => s.id).join()], reset, { immediate: true });
watch(() => screens.value.map((s) => `${s.id}:${plugins.installedOn(s, props.plugin.id)?.version || ""}:${planned(s)}`).join(), reset);
const canTick = (screen: Screen) => !plugins.buildingOn(screen, props.plugin.id)
  && (!plugins.needsAttach(screen) || Boolean(props.plugin.build_settings?.length)) && (has(screen) || plugins.fits(props.plugin, screen).ok);
const adding = computed(() => screens.value.filter((s) => wanted[s.id] && !planned(s)));
const removing = computed(() => screens.value.filter((s) => !wanted[s.id] && planned(s)));
// An update that asks for other rights waits for the person's yes, shown above the update keys.
const askConsent = computed(() => screens.value.some((s) => plugins.installedOn(s, props.plugin.id) && plugins.needsConsent(s, props.plugin)));
const agreed = computed(() => !askConsent.value || Boolean(plugins.consented[props.plugin.id]));
const updatable = computed(() => screens.value.filter((s) => plugins.hasUpdate(s, props.plugin)));
const dependencies = computed(() => screens.value.filter((screen) => adding.value.includes(screen) || updatable.value.includes(screen)).map((screen) => {
  const plan = plugins.planOn(screen, [props.plugin.id]);
  return { screen, plan, rows: plugins.comesAlong(plan, [props.plugin.id]) };
}));
const ready = computed(() => adding.value.every((screen) => plugins.changeReady(screen, [props.plugin])));
function apply() {
  for (const screen of adding.value) plugins.setAside(screen, props.plugin);
  // Set aside and not built yet: it only leaves the tray. On the screen: taking it off is set aside too.
  for (const screen of removing.value.filter((s) => !has(s))) plugins.takeOut(screen, props.plugin.id);
  const off = removing.value.filter(has);
  if (off.length) emit("remove", off);
}
</script>

<template>
  <div class="pd-action pd-screens-box">
    <p class="pd-label">{{ t("editor.plugins.on_screens") }}</p>
    <ul class="pd-screens" id="plugin-screens">
      <li v-for="s in screens" :key="s.id" :class="{ off: !canTick(s) }">
        <label>
          <input type="checkbox" :checked="wanted[s.id]" :disabled="!canTick(s)" :data-screen="s.name" @change="wanted[s.id] = ($event.target as HTMLInputElement).checked" />
          <span class="pd-screen-words"><b>{{ s.name }}</b><small :class="{ 'pd-pending': Boolean(wanted[s.id]) !== has(s) }">{{ plugins.screenLine(plugin, s, Boolean(wanted[s.id])) }}</small></span>
        </label>
        <span v-if="plugins.buildingOn(s, plugin.id)" class="spin small" aria-hidden="true"></span>
        <p v-if="plugins.recovery[s.id]" class="pd-misfit" data-plugin-recovery role="alert">{{ plugins.recovery[s.id].file }} · {{ plugins.recovery[s.id].reason }}</p>
      </li>
    </ul>
    <PluginSetup :plugin="plugin" :screens="adding" />
    <template v-for="group in dependencies" :key="group.screen.id">
      <PluginSetup v-for="row in group.rows" :key="row.plugin.id" :plugin="row.plugin" :screens="[group.screen]" />
      <p v-if="group.plan?.error" class="pd-misfit" role="alert">{{ group.plan.error }}</p>
      <label v-for="choice in group.plan?.choose || []" :key="choice.feature" class="field pd-choose">
        <span class="f-label">{{ t("editor.plugins.along.choose", { what: t(`editor.plugins.features.${choice.feature}`) }) }}</span>
        <select :data-feature="choice.feature" @change="plugins.chooseProvider(group.screen, choice.feature, ($event.target as HTMLSelectElement).value)">
          <option value="" selected disabled>{{ t("editor.plugin_tile.choose") }}</option>
          <option v-for="id in choice.options" :key="id" :value="id">{{ text(plugins.index.find((entry) => entry.id === id)?.name || { en: id }) }}</option>
        </select>
      </label>
    </template>
    <div class="pd-buttons">
      <button type="button" class="btn primary" id="plugin-apply" :disabled="!(adding.length || removing.length) || !ready" @click="apply">{{ applyText(adding.length, removing.length) }}</button>
      <label v-if="updatable.length && askConsent" class="pd-trust" id="plugin-consent-all">
        <input type="checkbox" :checked="plugins.consented[plugin.id]" @change="plugins.consented[plugin.id] = ($event.target as HTMLInputElement).checked" />
        <span><b>{{ t("editor.plugins.consent.title") }}</b>{{ t("editor.plugins.consent.agree") }}</span>
      </label>
      <button v-if="updatable.length" type="button" class="btn quiet" id="plugin-update-all" :disabled="!agreed || !updatable.every((screen) => plugins.changeReady(screen, [plugin]))" @click="plugins.addPlugin(updatable, plugin)">{{ t("editor.plugins.update_all", { n: updatable.length, version: plugin.version }, updatable.length) }}</button>
    </div>
  </div>
</template>
