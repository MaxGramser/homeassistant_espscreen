<script setup lang="ts">
// The screensaver (app 0.4.48): what this screen shows in standby instead of its dimmed tiles. A player and a camera of
// your choice and the clock, in the order the screen tries them: it shows the first one that is there right now (a
// player that plays with a cover, a camera Home Assistant has, the clock always). The add-on decides and tells the
// screen; nothing on the screensaver takes a tap, so the first touch wakes the screen as standby always did.
import { computed, ref, type Ref } from "vue";
import { t } from "../i18n";
import { dropIndex, moved } from "../model/reorder";
import { glyph } from "../model/topbar";
import { currentScreen, setScreensaver, settingValues, state } from "../store";
import type { SaverKind } from "../types";
import Icon from "./ui/Icon.vue";
import UiSelect from "./ui/UiSelect.vue";

const saver = computed(() => currentScreen.value?.screensaver);
const MIN_FIRMWARE = "0.29.0";
const ICONS: Record<SaverKind, string> = { media: "F075A", camera: "F07AE", clock: "F0150" };
const DOMAINS: Record<"media" | "camera", string[]> = { media: ["media_player"], camera: ["camera", "image"] };
const standbyOn = computed(() => settingValues().standby_enabled !== false && settingValues().standby_enabled !== 0);
const ready = computed(() => Boolean(saver.value?.ready));
// A board without pictures shows the clock alone, so its list has nothing to order.
const order = computed<SaverKind[]>(() => {
  const list = steps.live.value || saver.value?.order || ["media", "camera", "clock"];
  return saver.value?.pictures ? list : list.filter((kind) => kind === "clock");
});
const isOn = (kind: SaverKind) => !saver.value?.off.includes(kind);
const choices = (kind: "media" | "camera", empty = `choose_${kind}`, taken: string[] = []) => [
  ["", t(`editor.screen_settings.screensaver.${empty}`)] as const,
  ...state.inventory.entities
    .filter((e) => DOMAINS[kind].includes(e.id.split(".")[0]) && !taken.includes(e.id))
    .map((e) => [e.id, e.area ? `${e.name} · ${e.area}` : e.name] as const)
    .sort((a, b) => a[1].localeCompare(b[1])),
];
// The players of the music step (app 0.4.54), in the order it tries them: the first that plays with a cover shows. A
// speaker first and the television under it next, say. An empty row after the last one adds a player, and a row set
// back to its first line leaves the list.
const MAX_PLAYERS = 4;
const chosen = computed(() => [saver.value?.media, ...(saver.value?.more || [])].filter((id): id is string => Boolean(id)));
// While one is dragged the list shows where it would land (app 0.4.55): the players are a list you drag into their
// order, the first at the top, with the mouse, the arrow keys or a finger.
const players = computed(() => playerSort.live.value || chosen.value);
const adding = computed(() => players.value.length < MAX_PLAYERS);
const playerChoices = (row: number) =>
  choices("media", row ? "add_media" : "choose_media", players.value.filter((_, i) => i !== row));
const setPlayers = (list: string[]) => change({ media: list[0] || "", more: list.slice(1) });
function setPlayer(row: number, value: string) {
  const list = [...chosen.value];
  if (value) list[row] = value;
  else list.splice(row, 1);
  setPlayers(list);
}
// The temperature under the clock (app 0.4.52): Home Assistant's first weather entity by default, one of your choice, or
// none. The screen shows the number in the unit Home Assistant is set to.
const weatherChoices = computed(() => [
  ["auto", t("editor.screen_settings.screensaver.weather_auto")] as const,
  ["", t("editor.screen_settings.screensaver.weather_none")] as const,
  ...state.inventory.entities
    .filter((e) => e.id.startsWith("weather."))
    .map((e) => [e.id, e.area ? `${e.name} · ${e.area}` : e.name] as const)
    .sort((a, b) => a[1].localeCompare(b[1])),
]);
const motionChoices = computed(() => [
  ["", t("editor.screen_settings.screensaver.choose_motion_sensor")] as const,
  ...state.inventory.entities
    .filter((e) => e.id.startsWith("binary_sensor."))
    .map((e) => [e.id, e.area ? `${e.name} · ${e.area}` : e.name] as const)
    .sort((a, b) => a[1].localeCompare(b[1])),
]);
const detail = (kind: SaverKind) => {
  if (kind === "media" && chosen.value.length > 1) return t("editor.screen_settings.screensaver.details.media_more");
  if (kind === "media" ? !chosen.value.length : kind !== "clock" && !saver.value?.[kind]) return t(`editor.screen_settings.screensaver.details.${kind}_unset`);
  return t(`editor.screen_settings.screensaver.details.${kind}`);
};
const label = (kind: SaverKind) => t(`editor.screen_settings.screensaver.kinds.${kind}`);
function change(patch: Parameters<typeof setScreensaver>[1]) {
  if (currentScreen.value) setScreensaver(currentScreen.value, patch);
}
function toggle(kind: SaverKind) {
  const off = saver.value?.off || [];
  change({ off: off.includes(kind) ? off.filter((k) => k !== kind) : [...off, kind] });
}

// One dragged list: its rows follow the pointer and the new order is kept on release. Mouse and touch: a finger on the
// grip drags at once (the grip takes no scroll), a finger elsewhere on the row after a short hold, so the panel still
// scrolls. A finger on a control in the row is no drag. The arrow keys move the focused row.
function sorter<T>(rows: string, items: () => readonly T[], commit: (list: T[]) => void, skip: string) {
  const drag = ref({ index: -1, active: false });
  const live = ref<T[] | null>(null) as Ref<T[] | null>;
  let start: { x: number; y: number } | null = null, timer = 0, pointerId: number | null = null;
  const all = () => [...document.querySelectorAll<HTMLElement>(rows)];
  function begin() {
    drag.value.active = true;
    live.value = [...items()];
    document.addEventListener("touchmove", block, { passive: false });
  }
  function block(e: TouchEvent) { if (drag.value.active) e.preventDefault(); }
  function track(e: PointerEvent) {
    if (e.pointerId !== pointerId || !start) return;
    if (!drag.value.active) {
      const distance = Math.hypot(e.clientX - start.x, e.clientY - start.y);
      if (e.pointerType === "touch") { if (distance > 10) { clearTimeout(timer); start = null; } return; }
      if (distance < 6) return;
      begin();
    }
    const target = dropIndex(all().map((row) => row.getBoundingClientRect()), drag.value.index, e.clientY);
    if (target !== drag.value.index && live.value) {
      live.value = moved(live.value, drag.value.index, target);
      drag.value.index = target;
    }
  }
  function end(e: PointerEvent) {
    if (e.pointerId !== pointerId) return;
    clearTimeout(timer);
    document.removeEventListener("pointermove", track);
    document.removeEventListener("pointerup", end);
    document.removeEventListener("pointercancel", end);
    document.removeEventListener("touchmove", block);
    if (drag.value.active && e.type !== "pointercancel" && live.value && live.value.join() !== items().join()) commit(live.value);
    live.value = null;
    drag.value = { index: -1, active: false };
    start = null; pointerId = null;
  }
  function down(e: PointerEvent, i: number) {
    const target = e.target as HTMLElement;
    if (e.button !== 0 || !ready.value || pointerId !== null || target.closest(skip)) return;
    e.stopPropagation();
    const grip = Boolean(target.closest(".grip"));
    if (e.pointerType !== "touch" || grip) e.preventDefault();
    drag.value = { index: i, active: false };
    start = { x: e.clientX, y: e.clientY };
    pointerId = e.pointerId;
    clearTimeout(timer);
    if (e.pointerType === "touch") { if (grip) begin(); else timer = window.setTimeout(begin, 260); }
    document.addEventListener("pointermove", track);
    document.addEventListener("pointerup", end);
    document.addEventListener("pointercancel", end);
  }
  function key(e: KeyboardEvent, i: number) {
    if (e.target !== e.currentTarget) return;
    const step = ({ ArrowUp: -1, ArrowDown: 1 } as Record<string, number>)[e.key];
    const list = items();
    if (!step || i + step < 0 || i + step >= list.length) return;
    e.preventDefault();
    e.stopPropagation();
    commit(moved(list, i, i + step));
    requestAnimationFrame(() => all()[i + step]?.focus());
  }
  return { drag, live, down, key };
}
const steps = sorter<SaverKind>("#screensaver-steps > .item[data-index]", () => saver.value?.order || [], (list) => change({ order: list }),
  "button, .ui-select, .saver-player");
const playerSort = sorter<string>("#screensaver-players .saver-player[data-row]", () => chosen.value, setPlayers, "button, .ui-select");
</script>

<template>
  <section v-if="saver && saver.standby" class="set-card" id="settings-screensaver" :class="{ inactive: !ready }">
    <h4><span class="mdi">{{ glyph("F04B2") }}</span>{{ t("editor.screen_settings.screensaver.title") }}</h4>
    <div class="srow setting-toggle" :class="{ inactive: !ready || !standbyOn }" data-setting="screensaver"
      @click="ready && !($event.target as HTMLElement).closest('button') && change({ show: !saver.show })">
      <span class="s-label" id="screensaver-show-label">{{ t("editor.screen_settings.screensaver.show") }}</span>
      <div class="s-control">
        <button type="button" class="switch" role="switch" id="screensaver-show" :aria-checked="saver.show ? 'true' : 'false'"
          aria-labelledby="screensaver-show-label" :disabled="!ready" @click.stop="change({ show: !saver.show })"></button>
      </div>
    </div>
    <p v-if="!ready" class="hint" id="screensaver-firmware">{{ t("editor.screen_settings.screensaver.needs_firmware", { version: MIN_FIRMWARE }) }}</p>
    <p v-else-if="!standbyOn" class="hint">{{ t("editor.screen_settings.screensaver.standby_off") }}</p>
    <template v-if="ready && saver.show">
      <p class="hint saver-lead">{{ t(saver.pictures ? "editor.screen_settings.screensaver.order" : "editor.screen_settings.screensaver.no_pictures") }}</p>
      <div class="items" id="screensaver-steps" role="list" :aria-label="t('editor.screen_settings.screensaver.order')">
        <div v-for="(kind, i) in order" :key="kind" class="item saver-step" role="listitem" :tabindex="saver.pictures ? 0 : -1" :data-index="i" :data-kind="kind"
          :class="{ 'is-hidden': !isOn(kind), 'dragging-chip': steps.drag.value.active && steps.drag.value.index === i, still: !saver.pictures }"
          @pointerdown="saver.pictures && steps.down($event, i)" @keydown="saver.pictures && steps.key($event, i)">
          <Icon v-if="saver.pictures" name="drag-vertical" class="grip" />
          <span class="av mdi">{{ glyph(ICONS[kind]) }}</span>
          <span class="tx">
            <b>{{ label(kind) }}</b>
            <div v-if="kind === 'media'" id="screensaver-players" role="list" :aria-label="t('editor.screen_settings.screensaver.players')">
              <div v-for="(entity, row) in players" :key="entity" class="saver-player" role="listitem" tabindex="0" :data-row="row"
                :class="{ 'dragging-chip': playerSort.drag.value.active && playerSort.drag.value.index === row, single: players.length < 2 }"
                @pointerdown="players.length > 1 && playerSort.down($event, row)" @keydown="playerSort.key($event, row)">
                <Icon v-if="players.length > 1" name="drag-vertical" class="grip" />
                <UiSelect class="saver-pick" :id="row ? `screensaver-media-${row + 1}` : 'screensaver-media'"
                  :model-value="entity" :options="playerChoices(row)" @update:model-value="(value: string) => setPlayer(row, value)" />
              </div>
              <UiSelect v-if="adding" class="saver-pick saver-add" :class="{ indented: players.length > 1 }" :id="players.length ? `screensaver-media-${players.length + 1}` : 'screensaver-media'"
                model-value="" :options="playerChoices(players.length)" @update:model-value="(value: string) => setPlayer(players.length, value)" />
            </div>
            <template v-else-if="kind === 'camera'">
              <UiSelect class="saver-pick" id="screensaver-camera" :model-value="saver.camera" :options="choices('camera')"
                @update:model-value="(value: string) => change({ camera: value })" />
              <template v-if="saver.camera">
                <UiSelect class="saver-pick" id="screensaver-motion-sensor" :model-value="saver.binary_sensor || ''" :options="motionChoices"
                  @update:model-value="(value: string) => change({ binary_sensor: value })" />
                <small>{{ t("editor.screen_settings.screensaver.motion_hint") }}</small>
              </template>
            </template>
            <UiSelect v-else class="saver-pick" id="screensaver-weather" :model-value="saver.weather ?? 'auto'" :options="weatherChoices"
              @update:model-value="(value: string) => change({ weather: value })" />
            <small>{{ detail(kind) }}</small>
          </span>
          <button type="button" class="switch" role="switch" :aria-checked="isOn(kind) ? 'true' : 'false'"
            :aria-label="t('editor.screen_settings.screensaver.use', { name: label(kind) })" @click.stop="toggle(kind)"></button>
        </div>
      </div>
      <p class="hint">{{ t("editor.screen_settings.screensaver.tap") }}</p>
    </template>
  </section>
</template>

<style scoped>
.set-card.inactive h4 { opacity: 0.6; }
.saver-lead { margin: 2px 0 8px; }
#screensaver-steps { margin-bottom: 8px; }
.saver-step { cursor: grab; align-items: flex-start; }
.saver-step.still { cursor: default; }
.saver-step > .grip { touch-action: none; }
.saver-step .av, .saver-step .grip, .saver-step .switch { margin-top: 3px; }
.saver-step .tx { gap: 4px; flex: 1; }
.saver-step .tx small { white-space: normal; }
.saver-step :deep(.saver-pick) { width: 100%; }
#screensaver-players { display: flex; flex-direction: column; gap: 6px; }
.saver-player { display: flex; align-items: center; gap: 6px; border-radius: 9px; cursor: grab; outline-offset: 2px; }
.saver-player.single { cursor: default; }
.saver-player .grip { margin-top: 0; flex: none; padding: 6px 2px; touch-action: none; color: var(--muted, currentColor); opacity: 0.7; }
.saver-player :deep(.saver-pick) { flex: 1; min-width: 0; }
/* The row that adds a player lines up with the players over it, past their grips. */
#screensaver-players :deep(.saver-add.indented) { margin-left: 28px; width: calc(100% - 28px); }
.saver-player.dragging-chip { outline: 2px dashed var(--accent); background: var(--accent-soft); cursor: grabbing; }
</style>
