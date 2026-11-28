<script setup lang="ts">
// The icons a screen takes on top of the fixed set (docs/ICONS.md). The list changes at once; what is on the glass
// changes with a build, so the page always says which of the two it is talking about. The screen is in the address
// (#/screens/<id>/icons, router.ts).
import { computed, onMounted, onBeforeUnmount, ref, watch } from "vue";
import { useBusy } from "../composables/useBusy";
import { useConfirm } from "../composables/useConfirm";
import { t } from "../i18n";
import { glyph } from "../model/topbar";
import { matchesQuery } from "../model/search";
import Icon from "./ui/Icon.vue";
import { useBuildsStore } from "../stores/builds";
import { useDocumentStore } from "../stores/document";
import { useInventoryStore } from "../stores/inventory";
import { useScreenIconsStore, type OwnYaml } from "../stores/screenIcons";
import { useUiStore } from "../stores/ui";

const ui = useUiStore();
const inv = useInventoryStore();
const doc = useDocumentStore();
const builds = useBuildsStore();
const icons = useScreenIconsStore();
const { confirm } = useConfirm();
const { busy, runOnce } = useBusy();

const screen = computed(() => inv.inventory.screens.find((s) => s.id === icons.screenId));
const view = computed(() => icons.view);
const left = computed(() => (view.value ? view.value.room - view.value.chosen.length : 0));
const building = computed(() => Boolean(view.value?.building || (screen.value && builds.buildOf(screen.value))));
const changes = computed(() => (view.value ? view.value.waiting.length + view.value.leaving.length : 0));

// The fixed set by name (the groups and what every screen carries beyond them): those need no room and no build.
const fixed = computed(() => new Set([...(inv.inventory.icons?.groups || []).flatMap((group) => group.icons.map((i) => i.name)),
  ...(inv.inventory.icons?.more || []).map((i) => i.name)]));

// The list of every icon shows some and adds more as it is scrolled: 7,430 buttons at once would hold the page up.
const STEP = 240;
const query = ref("");
const shown = ref(STEP);
watch(query, () => { shown.value = STEP; });
const found = computed(() => {
  const names = Object.keys(icons.table || {});
  return query.value ? names.filter((name) => matchesQuery(query.value, name)) : names;
});
const more = ref<HTMLElement | null>(null);
let observer: IntersectionObserver | null = null;
watch(more, (element) => {
  observer?.disconnect();
  if (!element) return;
  observer = new IntersectionObserver((entries) => { if (entries.some((entry) => entry.isIntersecting)) shown.value += STEP; }, { rootMargin: "400px" });
  observer.observe(element);
});
onBeforeUnmount(() => observer?.disconnect());
onMounted(() => { void icons.load(); void icons.loadTable(); });

// A build that ends changes what the screen has: the page follows without a reload.
watch(() => (screen.value ? builds.buildOf(screen.value)?.id : undefined), () => { void icons.load(); });

const cp = (name: string) => icons.table?.[name]?.[0] || view.value?.icons[name]?.[0] || "";
const draw = (name: string) => (cp(name) ? glyph(cp(name)) : "");
const isChosen = (name: string) => Boolean(view.value?.chosen.includes(name));
const isFixed = (name: string) => fixed.value.has(name);
const waits = (name: string) => Boolean(view.value?.waiting.includes(name));
const label = (name: string) => name.replaceAll("-", " ");

async function remove(name: string) {
  const uses = (doc.layout?.tiles || []).filter((tile) => tile.options?.icon === name).length;
  if (uses && !await confirm(t("editor.screen_icons.in_use", { icon: label(name), n: uses }, uses), { confirm: t("editor.screen_icons.remove"), danger: true })) return;
  await icons.remove(name);
}
function toggle(name: string) {
  if (isFixed(name)) return;
  if (isChosen(name)) return void remove(name);
  if (left.value > 0) void icons.add([name]);
  else ui.toast(t("editor.screen_icons.full"));
}
const suggestions = computed(() => view.value?.suggested || []);
const addSuggested = () => icons.add(suggestions.value.slice(0, left.value));

const ownYaml = ref<OwnYaml | null>(null);
const build = () => runOnce(async () => { ownYaml.value = await icons.build(); });

// The other screens that can take this list; a screen with 4 MB of flash has no room and stays as it is. How many that
// is decides the sentence, and the add-on knows what each of them has: it builds only those that differ.
const others = computed(() => inv.inventory.screens.filter((other) => !other.virtual && other.id !== icons.screenId && other.shape));
const everywhere = () => runOnce(async () => {
  const n = others.value.length + 1;
  if (!await confirm(t("editor.screen_icons.everywhere_ask", { n }, n), { confirm: t("editor.screen_icons.everywhere_yes", { n }, n) })) return;
  const outcome = await icons.everywhere();
  if (!outcome) return;
  if (outcome.queued.length) ui.toast(t("editor.screen_icons.everywhere_done", { names: outcome.queued.join(", ") }));
  if (outcome.off.length) ui.toast(t("editor.screen_icons.everywhere_off", { names: outcome.off.join(", ") }));
});
</script>

<template>
  <div class="panel wide" id="icons-panel">
    <div class="panel-head">
      <div class="tx">
        <span class="eyebrow">{{ t("editor.screen_icons.eyebrow") }}</span>
        <h1 id="icons-title">{{ t("editor.screen_icons.title", { name: screen?.name || "" }) }}</h1>
        <p v-if="view">{{ t("editor.screen_icons.intro", { room: view.room }) }}</p>
      </div>
      <button type="button" class="btn quiet" id="close-icons" @click="ui.go('')">{{ t("editor.common.back") }}</button>
    </div>

    <p v-if="!view" class="hint">{{ t("editor.screen_icons.loading") }}</p>
    <template v-else>
      <section class="icons-status" :class="{ waiting: changes || building }" aria-live="polite">
        <div class="tx">
          <strong v-if="building">{{ t("editor.screen_icons.building") }}</strong>
          <template v-else-if="changes">
            <strong v-if="view.waiting.length">{{ t("editor.screen_icons.waiting", { n: view.waiting.length }, view.waiting.length) }}</strong>
            <strong v-if="view.leaving.length">{{ t("editor.screen_icons.leaving", { n: view.leaving.length }, view.leaving.length) }}</strong>
            <span>{{ t("editor.screen_icons.changes") }}</span>
          </template>
          <strong v-else>{{ t("editor.screen_icons.all_up_to_date") }}</strong>
        </div>
        <span v-if="building" class="spin small" role="img" :aria-label="t('editor.screen_icons.building')"></span>
        <button v-else-if="changes" type="button" class="btn primary" id="icons-build" :disabled="busy" @click="build">{{ t("editor.screen_icons.build", { name: screen?.name || "" }) }}</button>
      </section>

      <section v-if="ownYaml" class="icons-own-yaml">
        <p>{{ t("editor.screen_icons.own_yaml", { file: ownYaml.file }) }}</p>
        <pre>{{ ownYaml.content }}</pre>
        <pre>{{ ownYaml.line }}</pre>
      </section>

      <section class="icons-section">
        <div class="icons-head">
          <h2>{{ t("editor.screen_icons.on_screen") }}</h2>
          <span class="icons-count">{{ t("editor.screen_icons.count", { n: view.chosen.length, room: view.room }) }}</span>
          <button v-if="others.length" type="button" class="btn quiet" id="icons-everywhere" :disabled="busy || building" @click="everywhere">{{ t("editor.screen_icons.everywhere") }}</button>
        </div>
        <p v-if="!view.chosen.length" class="hint">{{ t("editor.screen_icons.none_yet") }}</p>
        <div v-else class="icons-grid">
          <button v-for="name in view.chosen" :key="name" type="button" class="icon-choice" aria-pressed="true" :class="{ waits: waits(name) }" :title="label(name)" :aria-label="label(name)" @click="toggle(name)">
            <span class="mdi">{{ draw(name) }}</span>
          </button>
        </div>
      </section>

      <section v-if="suggestions.length && left > 0" class="icons-section">
        <div class="icons-head">
          <h2>{{ t("editor.screen_icons.from_ha") }}</h2>
          <button type="button" class="btn quiet" id="icons-add-suggested" @click="addSuggested">{{ t("editor.screen_icons.add_all") }}</button>
        </div>
        <p class="hint">{{ t("editor.screen_icons.from_ha_hint") }}</p>
        <div class="icons-grid">
          <button v-for="name in suggestions" :key="name" type="button" class="icon-choice" aria-pressed="false" :title="label(name)" :aria-label="label(name)" @click="toggle(name)">
            <span class="mdi">{{ draw(name) }}</span>
          </button>
        </div>
      </section>

      <section class="icons-section">
        <div class="icons-head"><h2>{{ t("editor.screen_icons.all") }}</h2></div>
        <label class="search-field"><Icon name="magnify" /><input id="icons-search" v-model="query" type="search" :placeholder="t('editor.screen_icons.search')" :aria-label="t('editor.screen_icons.search_label')" /></label>
        <p v-if="!icons.table" class="hint">{{ t("editor.screen_icons.loading") }}</p>
        <p v-else-if="!found.length" class="hint">{{ t("editor.screen_icons.nothing") }}</p>
        <div v-else class="icons-grid">
          <button v-for="name in found.slice(0, shown)" :key="name" type="button" class="icon-choice" :aria-pressed="isChosen(name) ? 'true' : 'false'" :disabled="isFixed(name)"
            :title="isFixed(name) ? `${label(name)} · ${t('editor.screen_icons.fixed')}` : label(name)" :aria-label="label(name)" @click="toggle(name)">
            <span class="mdi">{{ draw(name) }}</span>
          </button>
        </div>
        <div v-if="found.length > shown" ref="more" class="icons-more"></div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.icons-status { display: flex; align-items: center; gap: 14px; padding: 14px 16px; border-radius: 12px; background: var(--surface-2); }
.icons-status.waiting { background: var(--accent-soft); }
.icons-status .tx { display: grid; gap: 2px; flex: 1; min-width: 0; }
.icons-status strong { font-size: 13.5px; }
.icons-status span { color: var(--ink-2); font-size: 12.5px; }
.icons-section { display: grid; gap: 10px; }
.icons-head { display: flex; align-items: center; gap: 12px; }
.icons-head h2 { font-size: 14px; flex: 1; }
.icons-count { color: var(--muted); font-size: 12.5px; }
.icons-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(44px, 1fr)); gap: 6px; }
.icons-grid .icon-choice:disabled { opacity: 0.35; }
.icons-grid .icon-choice.waits { border-style: dashed; }
.icons-more { height: 1px; }
.icons-own-yaml { display: grid; gap: 8px; }
.icons-own-yaml pre { overflow: auto; padding: 10px 12px; border-radius: 9px; background: var(--code-bg, var(--surface-2)); font-size: 12px; }
</style>
