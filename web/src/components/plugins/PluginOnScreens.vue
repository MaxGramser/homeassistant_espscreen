<script setup lang="ts">
// A plugin's details on the Plugins page: a box per screen, ticked where it is on, and what does not fit greyed out with
// its reason; the boxes apply together (adding sets it aside on each screen for the tray, taking it off is asked of the
// details around it, `remove`), and the screens with an update take it at once.
import { computed, reactive, watch } from "vue";
import { t } from "../../i18n";
import { applyText, type Plugin } from "../../model/plugins";
import type { Screen } from "../../types";
import PluginSetup from "../PluginSetup.vue";
import { usePluginsStore } from "../../stores/plugins";

const plugins = usePluginsStore();
const props = defineProps<{ plugin: Plugin }>();
const emit = defineEmits<{ remove: [screens: Screen[]] }>();

const screens = computed(() => plugins.realScreens());
const wanted = reactive<Record<string, boolean>>({});
function reset() {
  for (const key of Object.keys(wanted)) delete wanted[key];
  for (const screen of screens.value) wanted[screen.id] = Boolean(plugins.installedOn(screen, props.plugin.id));
}
watch([() => props.plugin.id, () => screens.value.map((s) => s.id).join()], reset, { immediate: true });
watch(() => screens.value.map((s) => `${s.id}:${plugins.installedOn(s, props.plugin.id)?.version || ""}`).join(), reset);
const has = (screen: Screen) => Boolean(plugins.installedOn(screen, props.plugin.id));
const canTick = (screen: Screen) => !plugins.buildingOn(screen, props.plugin.id) && !plugins.needsAttach(screen) && (has(screen) || plugins.fits(props.plugin, screen).ok);
const adding = computed(() => screens.value.filter((s) => wanted[s.id] && !has(s)));
const removing = computed(() => screens.value.filter((s) => !wanted[s.id] && has(s)));
// An update that asks for other rights waits for the person's yes, shown above the update keys.
const askConsent = computed(() => screens.value.some((s) => plugins.installedOn(s, props.plugin.id) && plugins.needsConsent(s, props.plugin)));
const agreed = computed(() => !askConsent.value || Boolean(plugins.consented[props.plugin.id]));
const updatable = computed(() => screens.value.filter((s) => plugins.hasUpdate(s, props.plugin)));
function apply() {
  for (const screen of adding.value) plugins.setAside(screen, props.plugin);
  if (removing.value.length) emit("remove", removing.value);
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
      </li>
    </ul>
    <PluginSetup :plugin="plugin" :screens="adding" />
    <div class="pd-buttons">
      <button type="button" class="btn primary" id="plugin-apply" :disabled="!(adding.length || removing.length) || !plugins.setupReady(plugin, adding)" @click="apply">{{ applyText(adding.length, removing.length) }}</button>
      <label v-if="updatable.length && askConsent" class="pd-trust" id="plugin-consent-all">
        <input type="checkbox" :checked="plugins.consented[plugin.id]" @change="plugins.consented[plugin.id] = ($event.target as HTMLInputElement).checked" />
        <span><b>{{ t("editor.plugins.consent.title") }}</b>{{ t("editor.plugins.consent.agree") }}</span>
      </label>
      <button v-if="updatable.length" type="button" class="btn quiet" id="plugin-update-all" :disabled="!agreed" @click="plugins.addPlugin(updatable, plugin)">{{ t("editor.plugins.update_all", { n: updatable.length, version: plugin.version }, updatable.length) }}</button>
    </div>
  </div>
</template>
