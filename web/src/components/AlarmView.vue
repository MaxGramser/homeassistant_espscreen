<script setup lang="ts">
// The alarm, a part of Events (EventsView, docs/ALARM_PANEL.md): no automation fires anything here, the screens follow
// the alarm panels of Home Assistant themselves. Per panel two choices, kept by the app (alarm_screens.py, api/alarms):
// which screens open the keypad by themselves when it goes off (every screen by default, also one added later), and
// after how many digits the code sends itself (the OK key by default). A screen that wakes for a panel it has on no tile
// gets that panel as a tile without a cell, so the choice holds for every screen, not only those with the alarm on a page.
import { computed, onMounted, ref } from "vue";
import { getJson, send } from "../api";
import { t } from "../i18n";
import { glyph } from "../model/topbar";
import { useInventoryStore } from "../stores/inventory";
import { useUiStore } from "../stores/ui";
import ChoiceField from "./ChoiceField.vue";
import CheckRow from "./ui/CheckRow.vue";
import SwitchRow from "./ui/SwitchRow.vue";
import theme from "virtual:esp-screens-theme";

type Alarm = { entity: string; name: string; code: boolean; screens: "all" | string[]; send_after: string };
type View = { alarms: Alarm[]; send_after: string[] };

const ui = useUiStore();
const inv = useInventoryStore();
const view = ref<View | null>(null);
const busy = ref("");
const screens = computed(() => inv.inventory.screens.filter((s) => !s.virtual));

onMounted(async () => { view.value = await getJson<View>("alarms"); });

const lengths = computed(() => (view.value?.send_after ?? ["off"]).map((key) => [key, key === "off" ? t("editor.alarm.send_off") : key] as const));
const every = (alarm: Alarm) => alarm.screens === "all";
const chosen = (alarm: Alarm, id: string) => every(alarm) || (alarm.screens as string[]).includes(id);
// A screen whose firmware takes no tiles without a cell wakes only for an alarm it has on a page (core.BAR_CARDS_FEATURE).
const older = (screen: { memory?: { bar_cards?: boolean } | null }) => Boolean(screen.memory && !screen.memory.bar_cards);

async function save(alarm: Alarm, change: Partial<Pick<Alarm, "screens" | "send_after">>) {
  busy.value = alarm.entity;
  try {
    view.value = await send<View>("alarms", "PUT", { entity: alarm.entity, screens: alarm.screens, send_after: alarm.send_after, ...change });
    ui.toast(t("editor.alarm.saved"));
  } finally {
    busy.value = "";
  }
}
const setEvery = (alarm: Alarm, on: boolean) => save(alarm, { screens: on ? "all" : screens.value.map((s) => s.id) });
function toggle(alarm: Alarm, id: string) {
  const now = every(alarm) ? screens.value.map((s) => s.id) : [...(alarm.screens as string[])];
  save(alarm, { screens: now.includes(id) ? now.filter((s) => s !== id) : [...now, id] });
}

// The mock of the red keypad in the firmware's own colours (theme.h): the alarm's red, the white keys and their ink.
const hex = (role: string) => `#${theme.roles[role].light.toString(16).padStart(6, "0")}`;
const mock = { "--al-red": `#${theme.ha.RED.toString(16).padStart(6, "0")}`, "--al-key": hex("CARD"), "--al-ink": hex("INK"), "--al-on": hex("ON_ACCENT") };
</script>

<template>
  <div class="alarm" id="alarm-part">
    <section class="card event-create" id="alarm-hero">
      <div class="event-create-text">
        <h2>{{ t("editor.alarm.hero_title") }}</h2>
        <p>{{ t("editor.alarm.hero_text") }}</p>
      </div>
      <div class="alarm-mock" aria-hidden="true" :style="mock">
        <span class="alarm-mock-line"><span class="mdi">{{ glyph("F009E") }}</span>0:24</span>
        <span class="alarm-mock-dots"><i class="on" /><i class="on" /><i /><i /></span>
        <span class="alarm-mock-keys"><b v-for="(k, i) in ['1', '2', '3', '4', '5', '6', '7', '8', '9', '', '0', '']" :key="i" :class="{ empty: !k }">{{ k }}</b></span>
      </div>
    </section>

    <p v-if="view && !view.alarms.length" class="card hint" id="alarm-none">{{ t("editor.alarm.none") }}</p>

    <section v-for="alarm in view?.alarms ?? []" :key="alarm.entity" class="card alarm-panel" :data-entity="alarm.entity" :aria-busy="busy === alarm.entity">
      <div class="alarm-head">
        <span class="mdi alarm-glyph" aria-hidden="true">{{ glyph("F0498") }}</span>
        <span><strong>{{ alarm.name }}</strong><small>{{ alarm.entity }}</small></span>
      </div>
      <p v-if="!alarm.code" class="hint">{{ t("editor.alarm.no_code") }}</p>

      <div class="alarm-block">
        <h3>{{ t("editor.alarm.screens_label") }}</h3>
        <SwitchRow :label="t('editor.alarm.every_screen')" :description="t('editor.alarm.every_screen_hint')" :model-value="every(alarm)"
          :disabled="busy === alarm.entity" @update:model-value="(on) => setEvery(alarm, on)" />
        <div v-if="!every(alarm)" class="alarm-screens">
          <CheckRow v-for="screen in screens" :key="screen.id" :checked="chosen(alarm, screen.id)" :disabled="busy === alarm.entity" :data-screen="screen.id"
            @toggle="toggle(alarm, screen.id)">
            <span class="alarm-screen"><span>{{ screen.name }}</span><small v-if="older(screen)">{{ t("editor.alarm.older") }}</small></span>
          </CheckRow>
          <p v-if="!(alarm.screens as string[]).length" class="hint">{{ t("editor.alarm.none_chosen") }}</p>
        </div>
      </div>

      <div v-if="alarm.code" class="alarm-block">
        <h3>{{ t("editor.alarm.send_label") }}</h3>
        <ChoiceField :choices="lengths" :value="alarm.send_after" :aria-label="t('editor.alarm.send_label')" :disabled="busy === alarm.entity"
          @pick="(value) => save(alarm, { send_after: String(value) })" />
        <p class="hint">{{ alarm.send_after === "off" ? t("editor.alarm.send_off_hint") : t("editor.alarm.send_on_hint", { digits: alarm.send_after }) }}</p>
      </div>
    </section>

    <details class="card event-more" id="alarm-how">
      <summary>{{ t("editor.alarm.how_title") }}</summary>
      <ul class="alarm-how">
        <li>{{ t("editor.alarm.how_wake") }}</li>
        <li>{{ t("editor.alarm.how_keys") }}</li>
        <li>{{ t("editor.alarm.how_wrong") }}</li>
        <li>{{ t("editor.alarm.how_code") }}</li>
        <li>{{ t("editor.alarm.how_tile") }}</li>
      </ul>
    </details>
  </div>
</template>

<style scoped>
.alarm { display: grid; gap: 14px; }
.alarm h2 { font-size: 15px; margin: 0 0 10px; }
.alarm h3 { font-size: 13px; margin: 0 0 6px; color: var(--muted); font-weight: 600; }
.alarm-mock { width: 168px; max-width: 100%; border-radius: 14px; background: var(--al-red); color: var(--al-on); padding: 12px; display: grid; gap: 8px; justify-items: center; }
.alarm-mock-line { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; font-variant-numeric: tabular-nums; }
.alarm-mock-dots { display: flex; gap: 6px; }
.alarm-mock-dots i { width: 9px; height: 9px; border-radius: 50%; border: 1.5px solid var(--al-on); }
.alarm-mock-dots i.on { background: var(--al-on); }
.alarm-mock-keys { display: grid; grid-template-columns: repeat(3, 1fr); gap: 5px; width: 100%; }
.alarm-mock-keys b { display: grid; place-items: center; height: 22px; border-radius: 6px; background: var(--al-key); color: var(--al-ink); font-size: 13px; font-weight: 500; }
.alarm-mock-keys b.empty { background: transparent; }
.alarm-panel { gap: 14px; }
.alarm-head { display: flex; align-items: center; gap: 10px; }
.alarm-head > span:last-child { display: grid; line-height: 1.25; min-width: 0; }
.alarm-head small { color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }
.alarm-glyph { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 50%; background: var(--surface-2); font-size: 18px; flex: none; }
.alarm-block { display: grid; gap: 6px; }
.alarm-screens { display: grid; gap: 4px; padding-left: 4px; }
.alarm-screen { display: grid; text-align: left; }
.alarm-screen small { color: var(--muted); font-size: 12px; }
.alarm-how { margin: 8px 0 0; padding-left: 18px; display: grid; gap: 6px; }
</style>
