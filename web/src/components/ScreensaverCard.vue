<script setup lang="ts">
// The screensaver (app 0.4.48): what this screen shows in standby instead of its dimmed tiles, a player's cover, a camera
// or the clock, in the order the screen tries them. Since app 0.4.83 the card is a short list of those steps, each with
// one line of what it shows and its switch, as calm as the other cards in a narrow column; a step opens in the drawer,
// where its players, its camera or its clock are chosen. A row drags into its place, by the mouse or a finger.
import { computed, onMounted } from "vue";
import { t } from "../i18n";
import { glyph } from "../model/topbar";
import { loadTopbarPreview, openSaverStep, state } from "../store";
import { changeSaver, isOn, SAVER_ICONS, SAVER_MIN_FIRMWARE, savedOrder, saver, saverLabel, saverReady, sorter, standbyOn, stepsShown, summary, toggleStep } from "../saver";
import type { SaverKind } from "../types";
import Icon from "./ui/Icon.vue";
import UiSwitch from "./ui/UiSwitch.vue";

onMounted(() => loadTopbarPreview(0));
const pictures = computed(() => Boolean(saver.value?.pictures));
const steps = sorter<SaverKind>("#screensaver-steps > .saver-row", () => savedOrder.value, (list) => changeSaver({ order: list }), ".ui-switch",
  () => saverReady.value && pictures.value);
const order = computed(() => stepsShown(steps.live.value));
const opened = (kind: SaverKind) => state.inspector?.kind === "saver" && state.inspector.step === kind;
const line = (kind: SaverKind) => (isOn(kind) ? summary(kind) : { text: t("editor.screen_settings.screensaver.summary.off"), missing: false });
function open(e: MouseEvent, kind: SaverKind) {
  if (steps.click(e) || (e.target as HTMLElement).closest(".ui-switch")) return;
  openSaverStep(kind);
}
</script>

<template>
  <section v-if="saver && saver.standby" class="set-card" id="settings-screensaver" :class="{ inactive: !saverReady }">
    <h4><span class="mdi">{{ glyph("F04B2") }}</span>{{ t("editor.screen_settings.screensaver.title") }}</h4>
    <div class="srow setting-toggle" :class="{ inactive: !saverReady || !standbyOn }" data-setting="screensaver"
      @click="saverReady && !($event.target as HTMLElement).closest('button') && changeSaver({ show: !saver.show })">
      <span class="s-label" id="screensaver-show-label">{{ t("editor.screen_settings.screensaver.show") }}</span>
      <div class="s-control">
        <button type="button" class="switch" role="switch" id="screensaver-show" :aria-checked="saver.show ? 'true' : 'false'"
          aria-labelledby="screensaver-show-label" :disabled="!saverReady" @click.stop="changeSaver({ show: !saver.show })"></button>
      </div>
    </div>
    <p v-if="!saverReady" class="hint" id="screensaver-firmware">{{ t("editor.screen_settings.screensaver.needs_firmware", { version: SAVER_MIN_FIRMWARE }) }}</p>
    <p v-else-if="!standbyOn" class="hint">{{ t("editor.screen_settings.screensaver.standby_off") }}</p>
    <template v-if="saverReady && saver.show">
      <p class="saver-caption">{{ pictures ? t("editor.screen_settings.screensaver.lead") : t("editor.screen_settings.screensaver.no_pictures") }}</p>
      <div class="saver-list" id="screensaver-steps" role="list" :aria-label="t('editor.screen_settings.screensaver.lead')">
        <div v-for="(kind, i) in order" :key="kind" class="saver-row" role="listitem" tabindex="0" :data-kind="kind"
          :class="{ off: !isOn(kind), opened: opened(kind), dragging: steps.drag.value.active && steps.drag.value.index === i, still: !pictures }"
          @pointerdown="steps.down($event, i)" @click="open($event, kind)" @keydown.enter.self.prevent="openSaverStep(kind)" @keydown="steps.key($event, i)">
          <span class="saver-av" aria-hidden="true">
            <span class="mdi">{{ glyph(SAVER_ICONS[kind]) }}</span>
            <Icon v-if="pictures" name="drag-vertical" class="saver-grip" />
          </span>
          <span class="saver-tx">
            <b>{{ saverLabel(kind) }}</b>
            <small :class="{ missing: line(kind).missing }">{{ line(kind).text }}</small>
          </span>
          <UiSwitch :model-value="isOn(kind)" :aria-label="t('editor.screen_settings.screensaver.use', { name: saverLabel(kind) })"
            @update:model-value="(on: boolean) => toggleStep(kind, on)" />
          <Icon name="chevron-right" class="saver-chev" />
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.set-card.inactive h4 { opacity: 0.6; }
.saver-caption { margin: 10px 0 6px; color: var(--muted); font-size: 11.5px; }
/* One grouped list, as a settings app draws a list that leads further: rows apart by a hairline, the whole in one frame. */
.saver-list { display: grid; grid-template-columns: minmax(0, 1fr); border: 1px solid var(--line); border-radius: 10px; overflow: hidden; margin-bottom: 10px; }
.saver-row { display: flex; align-items: center; gap: 10px; min-width: 0; padding: 9px 8px 9px 9px; background: var(--surface); cursor: pointer; outline: none; transition: background 0.12s; }
.saver-row + .saver-row { border-top: 1px solid var(--line); }
.saver-row:hover { background: var(--surface-2); }
.saver-row:focus-visible { box-shadow: inset 0 0 0 2px var(--accent); }
.saver-row.opened { background: var(--accent-soft); }
.saver-row.dragging { background: var(--accent-soft); cursor: grabbing; position: relative; z-index: 1; box-shadow: 0 6px 18px rgba(20, 24, 40, 0.14); }
.saver-av { position: relative; width: 28px; height: 28px; border-radius: 8px; background: var(--seg); color: var(--ink-2); display: grid; place-items: center; flex: none; font-size: 16px; }
.saver-av > * { grid-area: 1 / 1; transition: opacity 0.12s; }
/* The row's icon gives way to a grip under the pointer: the row drags by it, or anywhere, without a column for it. */
.saver-grip { opacity: 0; font-size: 17px; color: var(--muted); }
@media (hover: hover) {
  .saver-row:not(.still):hover .saver-av .mdi { opacity: 0; }
  .saver-row:not(.still):hover .saver-grip { opacity: 1; }
}
.saver-tx { flex: 1; min-width: 0; display: grid; gap: 1px; }
.saver-tx b { font-weight: 500; font-size: 13px; color: var(--ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.saver-tx small { font-size: 11.5px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.saver-tx small.missing { color: var(--accent); }
.saver-row.off .saver-av, .saver-row.off .saver-tx b { opacity: 0.5; }
.saver-chev { flex: none; margin-left: -4px; color: var(--muted); font-size: 16px; }
</style>
