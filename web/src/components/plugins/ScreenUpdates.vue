<script setup lang="ts">
// Every update of one screen in one card, at the top of its Plugins tab (docs/BUILDS.md, "Updates of a screen"): its
// firmware and its plugins, each from the version it runs to the new one, and one key that does all of it in one build
// (the add-on's update_everything: the plugins file gets the new versions and the firmware update builds it). Plugin
// updates that ask for other rights are named and go only with one yes. A screen that is away says so instead.
import { computed } from "vue";
import { t } from "../../i18n";
import { needsUpdate } from "../../model/screen-status";
import { text, type Plugin } from "../../model/plugins";
import type { Screen } from "../../types";
import BuildRoom from "../BuildRoom.vue";
import Icon from "../ui/Icon.vue";
import { usePluginsStore } from "../../stores/plugins";
import { useBuildsStore } from "../../stores/builds";

const plugins = usePluginsStore();
const builds = useBuildsStore();
const props = defineProps<{ screen: Screen }>();

const list = computed(() => plugins.updatesOn(props.screen));
// The firmware's update, when this app can build the screen (it has its YAML) and it is not on its way already.
const firmware = computed(() => (needsUpdate(props.screen) && props.screen.update?.profile && !builds.buildOf(props.screen) ? props.screen.update.target : null));
const asking = computed(() => list.value.filter((p) => plugins.needsConsent(props.screen, p)));
const agreed = computed(() => asking.value.every((p) => plugins.consented[p.id]));
const names = (items: Plugin[]) => items.map((p) => text(p.name)).join(", ");
function agree(on: boolean) { for (const p of asking.value) plugins.consented[p.id] = on; }
const from = (p: Plugin) => plugins.installedOn(props.screen, p.id)?.version ?? "";
const count = computed(() => list.value.length + (firmware.value ? 1 : 0));
// One request: the add-on builds the firmware's update with the plugins' when there is one, else the plugins alone.
const go = () => void plugins.updateEverything(props.screen, list.value);
</script>

<template>
  <div v-if="count" class="sp-updates" id="screen-plugin-updates">
    <p><b>{{ t("editor.updates_card.title", { n: count, screen: screen.name }, count) }}</b>{{ t(count > 1 ? "editor.updates_card.one_build" : "editor.updates_card.one", { screen: screen.name }) }}</p>
    <ul class="sp-update-list">
      <li v-if="firmware" data-update="firmware"><Icon name="chip" /><span>{{ t("editor.updates_card.firmware") }}</span><small>{{ screen.firmware }} → {{ firmware }}</small></li>
      <li v-for="p in list" :key="p.id" :data-update="p.id"><Icon name="puzzle-outline" /><span>{{ text(p.name) }}</span><small>{{ from(p) }} → {{ p.version }}</small></li>
    </ul>
    <label v-if="asking.length" class="pd-trust" id="screen-plugin-consent">
      <input type="checkbox" :checked="agreed" @change="agree(($event.target as HTMLInputElement).checked)" />
      <span><b>{{ t("editor.plugins.tab.updates_rights", { names: names(asking) }, asking.length) }}</b>{{ t("editor.plugins.consent.agree") }}</span>
    </label>
    <BuildRoom />
    <p v-if="!screen.online" class="sp-update-away"><Icon name="information-outline" />{{ t("editor.updates_card.away", { screen: screen.name }) }}</p>
    <button type="button" class="btn primary" id="screen-plugin-update-all" :disabled="!agreed || !screen.online" @click="go">
      {{ count > 1 ? t("editor.updates_card.go_all") : t("editor.plugins.tab.update_all") }}
    </button>
  </div>
</template>
